"""
Signal Processing Utilities - Preprocessing, filtering, and quality metrics

This module provides helper functions for EEG signal processing:
- Signal quality assessment
- Artifact detection and rejection
- Filtering (bandpass, notch)
- Preprocessing (detrending, normalization)

Usage:
    from processing.utils import assess_signal_quality, apply_bandpass_filter

    quality = assess_signal_quality(signal, sample_rate=256.0)
    if quality['is_good']:
        filtered = apply_bandpass_filter(signal, lowcut=0.5, highcut=50.0, fs=256.0)
"""

import logging
from typing import Dict, Tuple
import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


def assess_signal_quality(
    eeg_signal: np.ndarray,
    sample_rate: float = 256.0,
    voltage_threshold: float = 1000.0,
    std_threshold: float = 200.0
) -> Dict[str, any]:
    """
    Assess EEG signal quality for a single channel.

    Quality indicators:
    - Voltage range: Should be reasonable (not flat or saturated)
    - Standard deviation: Should indicate brain activity
    - Artifact detection: Check for large spikes

    Args:
        eeg_signal: 1D numpy array of EEG samples (μV)
        sample_rate: Sample rate in Hz
        voltage_threshold: Max acceptable voltage deviation (μV)
        std_threshold: Max acceptable standard deviation (μV)

    Returns:
        Dict with quality metrics:
        {
            'is_good': True/False,
            'voltage_range': 145.3,  # Peak-to-peak voltage
            'std': 42.1,             # Standard deviation
            'has_artifacts': False,   # Large spikes detected
            'quality_score': 0.85,    # 0-1, higher = better
            'issues': []              # List of detected issues
        }
    """
    issues = []

    # Compute basic statistics
    voltage_range = np.ptp(eeg_signal)  # Peak-to-peak
    std = np.std(eeg_signal)
    mean_abs = np.mean(np.abs(eeg_signal))

    # Check for flat signal (sensor disconnected)
    if voltage_range < 1.0:
        issues.append("Signal too flat - possible sensor disconnect")

    # Check for saturation (sensor contact issue)
    if voltage_range > voltage_threshold:
        issues.append(f"Voltage range too high ({voltage_range:.1f} μV) - possible artifact")

    # Check for excessive noise
    if std > std_threshold:
        issues.append(f"High noise level (std={std:.1f} μV)")

    # Check for DC drift (mean too far from zero)
    mean_val = np.mean(eeg_signal)
    if abs(mean_val) > 100.0:
        issues.append(f"DC offset detected ({mean_val:.1f} μV)")

    # Artifact detection: Count samples exceeding ±3 standard deviations
    artifact_threshold = 3 * std
    n_artifacts = np.sum(np.abs(eeg_signal - mean_val) > artifact_threshold)
    artifact_ratio = n_artifacts / len(eeg_signal)

    has_artifacts = artifact_ratio > 0.05  # >5% artifacts is concerning

    if has_artifacts:
        issues.append(f"Artifacts detected ({artifact_ratio*100:.1f}% of samples)")

    # Compute quality score (0-1, higher = better)
    # Based on: low noise, reasonable voltage, few artifacts
    score_voltage = 1.0 - min(voltage_range / voltage_threshold, 1.0)  # Penalize high voltage
    score_std = 1.0 - min(std / std_threshold, 1.0)  # Penalize high noise
    score_artifacts = 1.0 - min(artifact_ratio * 10, 1.0)  # Penalize artifacts

    quality_score = (score_voltage + score_std + score_artifacts) / 3.0

    # Overall quality flag
    is_good = len(issues) == 0 and quality_score > 0.6

    return {
        'is_good': is_good,
        'voltage_range': round(voltage_range, 2),
        'std': round(std, 2),
        'mean': round(mean_val, 2),
        'has_artifacts': has_artifacts,
        'artifact_ratio': round(artifact_ratio, 3),
        'quality_score': round(quality_score, 2),
        'issues': issues
    }


def apply_bandpass_filter(
    data: np.ndarray,
    lowcut: float,
    highcut: float,
    fs: float,
    order: int = 4
) -> np.ndarray:
    """
    Apply Butterworth bandpass filter to EEG signal.

    Typical EEG filtering:
    - Highpass at 0.5 Hz: Remove DC drift
    - Lowpass at 50 Hz: Remove electrical noise and high-freq artifacts
    - Notch at 50/60 Hz: Remove powerline interference

    Args:
        data: Input signal (1D numpy array)
        lowcut: Low cutoff frequency (Hz)
        highcut: High cutoff frequency (Hz)
        fs: Sample rate (Hz)
        order: Filter order (default 4)

    Returns:
        Filtered signal (same shape as input)

    Note:
        Uses scipy.signal.butter + filtfilt for zero-phase filtering
        filtfilt applies filter forward and backward to avoid phase shift
    """
    # Design Butterworth bandpass filter
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist

    b, a = signal.butter(order, [low, high], btype='band')

    # Apply filter (zero-phase using filtfilt)
    filtered_data = signal.filtfilt(b, a, data)

    return filtered_data


def apply_notch_filter(
    data: np.ndarray,
    notch_freq: float,
    fs: float,
    quality_factor: float = 30.0
) -> np.ndarray:
    """
    Apply notch filter to remove powerline interference.

    Removes narrow-band noise at specific frequency (50 Hz or 60 Hz).

    Args:
        data: Input signal (1D numpy array)
        notch_freq: Frequency to remove (Hz) - typically 50 or 60
        fs: Sample rate (Hz)
        quality_factor: Quality factor (higher = narrower notch, default 30)

    Returns:
        Filtered signal (same shape as input)
    """
    # Design notch filter
    b, a = signal.iirnotch(notch_freq, quality_factor, fs)

    # Apply filter
    filtered_data = signal.filtfilt(b, a, data)

    return filtered_data


def detrend_signal(data: np.ndarray, method: str = 'linear') -> np.ndarray:
    """
    Remove linear or constant trend from signal.

    Useful for removing slow drifts in EEG baseline.

    Args:
        data: Input signal (1D numpy array)
        method: 'linear' or 'constant' (default 'linear')

    Returns:
        Detrended signal
    """
    return signal.detrend(data, type=method)


def normalize_signal(data: np.ndarray, method: str = 'zscore') -> np.ndarray:
    """
    Normalize signal to standard scale.

    Args:
        data: Input signal (1D numpy array)
        method: Normalization method:
            - 'zscore': (x - mean) / std  (default)
            - 'minmax': (x - min) / (max - min)
            - 'robust': (x - median) / IQR

    Returns:
        Normalized signal
    """
    if method == 'zscore':
        mean = np.mean(data)
        std = np.std(data)
        return (data - mean) / std if std > 0 else data - mean

    elif method == 'minmax':
        min_val = np.min(data)
        max_val = np.max(data)
        range_val = max_val - min_val
        return (data - min_val) / range_val if range_val > 0 else data - min_val

    elif method == 'robust':
        median = np.median(data)
        q75, q25 = np.percentile(data, [75, 25])
        iqr = q75 - q25
        return (data - median) / iqr if iqr > 0 else data - median

    else:
        raise ValueError(f"Unknown normalization method: {method}")


def detect_blinks(
    eeg_signal: np.ndarray,
    sample_rate: float = 256.0,
    threshold: float = 100.0
) -> np.ndarray:
    """
    Detect eye blinks in frontal EEG channels.

    Blinks create large amplitude spikes in frontal channels (AF7, AF8, Fp1, Fp2).

    Args:
        eeg_signal: Frontal channel signal (1D numpy array)
        sample_rate: Sample rate (Hz)
        threshold: Voltage threshold for blink detection (μV)

    Returns:
        Boolean array indicating blink samples (True = blink)
    """
    # Compute first derivative (rate of change)
    derivative = np.diff(eeg_signal, prepend=eeg_signal[0])

    # Blinks have large, rapid voltage changes
    is_blink = np.abs(derivative) > threshold

    return is_blink


def compute_signal_to_noise_ratio(
    eeg_signal: np.ndarray,
    noise_band: Tuple[float, float] = (50.0, 60.0),
    signal_band: Tuple[float, float] = (8.0, 30.0),
    sample_rate: float = 256.0
) -> float:
    """
    Compute signal-to-noise ratio (SNR) for EEG signal.

    SNR helps assess data quality - higher SNR = better signal.

    Args:
        eeg_signal: EEG signal (1D numpy array)
        noise_band: Frequency range for noise estimation (Hz)
        signal_band: Frequency range for signal estimation (Hz)
        sample_rate: Sample rate (Hz)

    Returns:
        SNR in dB (typically 5-20 dB for good EEG)
    """
    from scipy.fft import rfft, rfftfreq

    # Compute FFT
    fft_vals = rfft(eeg_signal)
    fft_freqs = rfftfreq(len(eeg_signal), 1.0 / sample_rate)
    psd = np.abs(fft_vals) ** 2

    # Extract signal power
    signal_idx = np.where((fft_freqs >= signal_band[0]) & (fft_freqs < signal_band[1]))[0]
    signal_power = np.mean(psd[signal_idx])

    # Extract noise power
    noise_idx = np.where((fft_freqs >= noise_band[0]) & (fft_freqs < noise_band[1]))[0]
    noise_power = np.mean(psd[noise_idx])

    # Compute SNR in dB
    snr_db = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else 0.0

    return snr_db


def preprocess_eeg(
    eeg_signal: np.ndarray,
    sample_rate: float = 256.0,
    apply_bandpass: bool = True,
    apply_notch: bool = True,
    notch_freq: float = 50.0,
    apply_detrend: bool = True
) -> np.ndarray:
    """
    Apply standard EEG preprocessing pipeline.

    Typical preprocessing steps:
    1. Detrend (remove DC offset and linear drift)
    2. Bandpass filter (0.5-50 Hz)
    3. Notch filter (remove powerline at 50/60 Hz)

    Args:
        eeg_signal: Raw EEG signal (1D numpy array)
        sample_rate: Sample rate (Hz)
        apply_bandpass: Apply bandpass filter (default True)
        apply_notch: Apply notch filter (default True)
        notch_freq: Powerline frequency to remove (50 or 60 Hz)
        apply_detrend: Apply detrending (default True)

    Returns:
        Preprocessed signal (same shape as input)
    """
    processed = eeg_signal.copy()

    # Step 1: Detrend
    if apply_detrend:
        processed = detrend_signal(processed, method='linear')

    # Step 2: Bandpass filter (0.5-50 Hz for EEG)
    if apply_bandpass:
        processed = apply_bandpass_filter(processed, lowcut=0.5, highcut=50.0, fs=sample_rate)

    # Step 3: Notch filter (remove powerline)
    if apply_notch:
        processed = apply_notch_filter(processed, notch_freq=notch_freq, fs=sample_rate)

    return processed
