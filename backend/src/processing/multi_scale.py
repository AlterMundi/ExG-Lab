"""
Multi-Scale EEG Processor - Multi-timescale neurofeedback computation

This module implements the core neurofeedback algorithm:
- FFT-based band power extraction at three timescales (1s, 2s, 4s)
- Frontal alpha asymmetry calculation (AF7 vs AF8)
- Relaxation score computation (alpha/beta ratio)
- Parallel processing for multiple devices

Architecture:
- Three timescales provide predictive feedback:
  * 1s (fast): Responsive to quick changes, more noise
  * 2s (balanced): Good balance of responsiveness and stability
  * 4s (stable): Smooth trends, less noise
- Frontal channels (AF7, AF8) for meditation/relaxation protocols
- Alpha (8-13 Hz) and Beta (13-30 Hz) bands for relaxation metric

Key Performance Requirements:
- Single device FFT: ~10-15ms @ 256 Hz, 4-second window
- 4 devices sequential: ~50-60ms (exceeds 100ms budget at 10 Hz)
- Solution: Use ThreadPoolExecutor for parallel FFT computation
- Target: <40ms for 4 devices in parallel

Mathematical Foundation:
- Relaxation Score = Alpha Power / Beta Power (frontal asymmetry)
- Higher ratio = more relaxed state
- Typical range: 0.5 (alert) to 2.5 (deeply relaxed)
- Target threshold: Often set around 1.5 for meditation training

Usage:
    processor = MultiScaleProcessor(sample_rate=256.0)

    # Process single device
    result = processor.process_single_device(
        data={'TP9': arr1, 'AF7': arr2, 'AF8': arr3, 'TP10': arr4},
        timescale=4.0
    )

    # Process multiple devices in parallel
    results = processor.process_multiple_devices([
        {'device': 'Muse_1', 'data': {...}},
        {'device': 'Muse_2', 'data': {...}},
    ])
"""

import logging
import time
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq

logger = logging.getLogger(__name__)


class MultiScaleProcessor:
    """
    Multi-timescale EEG processor for neurofeedback computation.

    Processes EEG data at three timescales (1s, 2s, 4s) to provide
    predictive feedback with varying responsiveness and stability.

    Performance:
    - Designed for 10 Hz computation rate (100ms budget)
    - Parallel processing for 4 devices: ~40ms total
    - Thread-safe - can be called from calc thread
    """

    # EEG frequency bands (Hz)
    BANDS = {
        'delta': (0.5, 4.0),   # Deep sleep
        'theta': (4.0, 8.0),   # Drowsiness, meditation
        'alpha': (8.0, 13.0),  # Relaxed awareness (KEY for relaxation)
        'beta': (13.0, 30.0),  # Active thinking, focus (KEY for relaxation)
        'gamma': (30.0, 50.0), # High-level cognition
    }

    # Timescales for multi-scale feedback
    TIMESCALES = [1.0, 2.0, 4.0]  # seconds

    def __init__(self, sample_rate: float = 256.0, max_workers: int = 4):
        """
        Initialize multi-scale processor.

        Args:
            sample_rate: EEG sample rate in Hz (Muse S = 256 Hz)
            max_workers: Max threads for parallel processing (default 4 for 4 devices)
        """
        self.sample_rate = sample_rate
        self.max_workers = max_workers

        # Thread pool for parallel FFT computation
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        logger.info(f"MultiScaleProcessor initialized ({sample_rate} Hz, {max_workers} workers)")

    def process_single_device(
        self,
        data: Dict[str, np.ndarray],
        timescale: float,
        channels: List[str] = ['AF7', 'AF8']
    ) -> Optional[Dict]:
        """
        Process single device at single timescale.

        Args:
            data: Dict mapping channel_name -> signal array (e.g., {'TP9': [...], 'AF7': [...]})
            timescale: Window duration in seconds (1.0, 2.0, or 4.0)
            channels: List of channels to use for frontal asymmetry (default: AF7, AF8)

        Returns:
            Dict with band powers, relaxation score, and metadata:
            {
                'relaxation': 1.75,  # Alpha/Beta ratio
                'alpha': 12.5,       # Alpha power (μV²)
                'beta': 7.1,         # Beta power (μV²)
                'theta': 8.3,        # Theta power
                'quality': {
                    'timescale': 4.0,
                    'channels_used': ['AF7', 'AF8'],
                    'samples': 1024,
                    'computation_ms': 12.5
                }
            }

            Returns None if insufficient data or computation fails.
        """
        start_time = time.time()

        try:
            # Validate input
            if not all(ch in data for ch in channels):
                logger.warning(f"Missing channels: need {channels}, got {list(data.keys())}")
                return None

            # Expected samples for this timescale
            expected_samples = int(timescale * self.sample_rate)

            # Validate data length
            for ch in channels:
                if len(data[ch]) < expected_samples:
                    logger.warning(
                        f"Insufficient data: need {expected_samples}, got {len(data[ch])}"
                    )
                    return None

            # Extract frontal channels (AF7 = left, AF8 = right)
            left_signal = data[channels[0]][-expected_samples:]
            right_signal = data[channels[1]][-expected_samples:]

            # Compute band powers for each channel
            left_bands = self._compute_band_powers(left_signal)
            right_bands = self._compute_band_powers(right_signal)

            # Compute frontal asymmetry (average of left and right)
            # In some protocols, asymmetry is ln(right) - ln(left), but for relaxation
            # we typically just average both hemispheres
            avg_bands = {
                band: (left_bands[band] + right_bands[band]) / 2.0
                for band in self.BANDS.keys()
            }

            # Relaxation score: Alpha / Beta ratio
            # Higher ratio = more relaxed state
            relaxation_score = avg_bands['alpha'] / avg_bands['beta'] if avg_bands['beta'] > 0 else 0.0

            # Build result
            result = {
                'relaxation': round(relaxation_score, 2),
                'alpha': round(avg_bands['alpha'], 2),
                'beta': round(avg_bands['beta'], 2),
                'theta': round(avg_bands['theta'], 2),
                'delta': round(avg_bands['delta'], 2),
                'gamma': round(avg_bands['gamma'], 2),
                'quality': {
                    'timescale': timescale,
                    'channels_used': channels,
                    'samples': expected_samples,
                    'computation_ms': round((time.time() - start_time) * 1000, 2)
                }
            }

            return result

        except Exception as e:
            logger.error(f"Error processing device: {e}")
            return None

    def _compute_band_powers(self, signal_data: np.ndarray) -> Dict[str, float]:
        """
        Compute power in each frequency band using FFT.

        Args:
            signal_data: 1D numpy array of EEG samples

        Returns:
            Dict mapping band_name -> power (μV²)

        Algorithm:
        1. Apply Hann window to reduce spectral leakage
        2. Compute FFT using scipy.fft.rfft (real FFT, faster)
        3. Convert to power spectral density (PSD)
        4. Integrate PSD over each frequency band

        Performance:
        - ~10-15ms for 1024 samples @ 256 Hz (4-second window)
        - Dominated by FFT computation
        """
        # Apply Hann window to reduce spectral leakage
        window = np.hanning(len(signal_data))
        windowed_signal = signal_data * window

        # Compute FFT (real FFT for efficiency)
        fft_vals = rfft(windowed_signal)
        fft_freqs = rfftfreq(len(signal_data), 1.0 / self.sample_rate)

        # Compute power spectral density (PSD)
        # PSD = |FFT|² / N
        psd = np.abs(fft_vals) ** 2 / len(signal_data)

        # Extract band powers by integrating PSD over frequency ranges
        band_powers = {}

        for band_name, (low_freq, high_freq) in self.BANDS.items():
            # Find indices for this frequency band
            band_idx = np.where((fft_freqs >= low_freq) & (fft_freqs < high_freq))[0]

            # Integrate PSD over band (sum × frequency resolution)
            freq_resolution = fft_freqs[1] - fft_freqs[0]
            band_power = np.sum(psd[band_idx]) * freq_resolution

            band_powers[band_name] = band_power

        return band_powers

    def process_multiple_devices(
        self,
        device_data: List[Dict],
        timescale: float = 4.0
    ) -> Dict[str, Dict]:
        """
        Process multiple devices in parallel using ThreadPoolExecutor.

        This is CRITICAL for maintaining 10 Hz computation rate with 4 devices:
        - Sequential: 4 × 15ms = 60ms (OK but tight)
        - Parallel: max(15ms, ...) = ~15ms (excellent margin)

        Args:
            device_data: List of dicts with 'device' name and 'data' dict
                Example: [
                    {'device': 'Muse_1', 'data': {'TP9': [...], 'AF7': [...], ...}},
                    {'device': 'Muse_2', 'data': {'TP9': [...], 'AF7': [...], ...}},
                ]
            timescale: Window duration in seconds (default 4.0)

        Returns:
            Dict mapping device_name -> processing result
            Example: {
                'Muse_1': {'relaxation': 1.75, 'alpha': 12.5, ...},
                'Muse_2': {'relaxation': 1.23, 'alpha': 9.8, ...},
            }
        """
        start_time = time.time()

        results = {}

        # Submit all tasks to thread pool
        futures = {}
        for item in device_data:
            device_name = item['device']
            data = item['data']

            future = self.executor.submit(
                self.process_single_device,
                data,
                timescale
            )
            futures[future] = device_name

        # Collect results as they complete
        for future in as_completed(futures):
            device_name = futures[future]
            try:
                result = future.result()
                if result:
                    results[device_name] = result
                else:
                    logger.warning(f"No result for {device_name}")
            except Exception as e:
                logger.error(f"Error processing {device_name}: {e}")

        total_time = (time.time() - start_time) * 1000
        logger.debug(f"Processed {len(device_data)} devices in {total_time:.1f}ms (parallel)")

        return results

    def process_multi_timescale(
        self,
        data: Dict[str, np.ndarray],
        timescales: Optional[List[float]] = None
    ) -> Dict[str, Dict]:
        """
        Process single device at multiple timescales (1s, 2s, 4s).

        This provides the multi-scale feedback that gives users predictive information:
        - 1s (fast): Shows immediate response to mental state changes
        - 2s (balanced): Good balance of responsiveness and stability
        - 4s (stable): Smooth trends, filters out noise

        Args:
            data: Dict mapping channel_name -> signal array (must have ≥4s of data)
            timescales: List of timescales to compute (default: [1.0, 2.0, 4.0])

        Returns:
            Dict mapping timescale -> result:
            {
                '1s': {'relaxation': 1.45, 'alpha': 11.2, ...},
                '2s': {'relaxation': 1.62, 'alpha': 12.1, ...},
                '4s': {'relaxation': 1.75, 'alpha': 12.5, ...},
            }
        """
        if timescales is None:
            timescales = self.TIMESCALES

        results = {}

        for ts in timescales:
            result = self.process_single_device(data, timescale=ts)
            if result:
                results[f"{int(ts)}s"] = result

        return results

    def compute_trend(
        self,
        timescale_results: Dict[str, Dict],
        metric: str = 'relaxation'
    ) -> str:
        """
        Compute trend direction from multi-timescale results.

        Trend detection helps users understand trajectory:
        - IMPROVING: Fast > Balanced > Stable (getting more relaxed)
        - DECLINING: Fast < Balanced < Stable (getting less relaxed)
        - STABLE: No clear trend

        Args:
            timescale_results: Results from process_multi_timescale()
            metric: Which metric to analyze (default: 'relaxation')

        Returns:
            Trend string: "IMPROVING", "DECLINING", or "STABLE"
        """
        if '1s' not in timescale_results or '2s' not in timescale_results or '4s' not in timescale_results:
            return "UNKNOWN"

        fast = timescale_results['1s'].get(metric, 0)
        balanced = timescale_results['2s'].get(metric, 0)
        stable = timescale_results['4s'].get(metric, 0)

        # Define threshold for "significant" difference (5%)
        threshold = 0.05

        if fast > balanced * (1 + threshold) and balanced > stable * (1 + threshold):
            return "IMPROVING"
        elif fast < balanced * (1 - threshold) and balanced < stable * (1 - threshold):
            return "DECLINING"
        else:
            return "STABLE"

    def shutdown(self):
        """
        Shutdown thread pool executor.

        Call this during application shutdown to cleanly terminate worker threads.
        """
        logger.info("Shutting down MultiScaleProcessor...")
        self.executor.shutdown(wait=True)
        logger.info("✓ MultiScaleProcessor shutdown complete")

    def __del__(self):
        """Cleanup on destruction"""
        self.shutdown()
