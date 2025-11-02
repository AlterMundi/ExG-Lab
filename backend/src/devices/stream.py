"""
LSL Stream Handler - Thread-safe EEG data acquisition from Lab Streaming Layer

This module provides thread-safe access to LSL streams from Muse devices:
- Non-blocking pulls at 20 Hz
- Thread-safe rolling buffers for multi-timescale processing
- Critical buffer flushing to prevent FIFO staleness
- Separate recording buffer for CSV export

Architecture:
- Uses pylsl.StreamInlet (blocking C extension, requires pure threading)
- Rolling buffers: 4 channels × deque(maxlen=1024) for 4-second windows @ 256 Hz
- Pull thread runs at 20 Hz (50ms intervals) independently from calc/UI threads
- All buffer access protected by threading.Lock

Critical Design Decisions:
1. BUFFER FLUSHING: LSL uses FIFO queue - must discard accumulated startup data
   before feedback to avoid showing 5-10 second old data
2. THREAD SAFETY: Multiple threads read buffers (calc thread, recording thread)
3. NON-BLOCKING: timeout=0.0 prevents blocking the pull thread
4. RATE DECOUPLING: Pull (20 Hz) ≠ Calc (10 Hz) ≠ UI (10 Hz)

Usage:
    handler = LSLStreamHandler(stream_name="Muse_1")
    handler.start()

    # Later, in calc thread:
    data = handler.get_recent_data(duration=4.0)  # Thread-safe

    # On shutdown:
    handler.stop()
    recording_data = handler.get_recording_buffer()
"""

import logging
import time
import threading
from typing import Optional, List, Tuple, Dict
from collections import deque
import numpy as np
from pylsl import StreamInlet, resolve_byprop, resolve_streams

logger = logging.getLogger(__name__)


class LSLStreamHandler:
    """
    Thread-safe handler for a single LSL stream from a Muse device.

    Manages StreamInlet lifecycle and provides buffered access to EEG data.

    Threading Model:
    - Pull thread: Runs at 20 Hz, calls pull_chunk() continuously
    - Calc thread: Reads from rolling buffers at 10 Hz
    - Recording thread: Accesses recording buffer for CSV export

    All buffer operations are protected with threading.Lock.
    """

    def __init__(self, stream_name: str, buffer_duration: float = 4.0):
        """
        Initialize LSL stream handler.

        Args:
            stream_name: LSL stream name (e.g., "Muse_1", "Muse_2")
            buffer_duration: Duration of rolling buffer in seconds (default 4.0 for 4s window)

        Note:
            Muse S streams at 256 Hz, so 4-second buffer = 1024 samples
        """
        self.stream_name = stream_name
        self.buffer_duration = buffer_duration

        # LSL components
        self.inlet: Optional[StreamInlet] = None
        self.sample_rate: Optional[float] = None
        self.n_channels: Optional[int] = None
        self.channel_names: List[str] = []

        # Rolling buffers (one per channel) - thread-safe with lock
        # deque provides O(1) append and automatic size limiting
        self.rolling_buffers: Dict[str, deque] = {}
        self.timestamps_buffer: deque = deque(maxlen=1024)  # Matching 4s @ 256 Hz

        # Recording buffer (unlimited size) - for CSV export
        self.recording_buffer: List[Tuple[float, np.ndarray]] = []

        # Thread safety
        self.lock = threading.Lock()

        # Pull thread control
        self.pull_thread: Optional[threading.Thread] = None
        self.running = False

        logger.info(f"LSLStreamHandler created for '{stream_name}'")

    def start(self, timeout: float = 10.0) -> bool:
        """
        Connect to LSL stream and start pull thread.

        Args:
            timeout: Maximum time to wait for stream to appear (seconds)

        Returns:
            True if connection successful, False otherwise

        Note:
            This performs CRITICAL buffer flushing to discard stale startup data.
        """
        logger.info(f"Connecting to LSL stream '{self.stream_name}'...")

        try:
            # Resolve stream by name
            streams = resolve_byprop('name', self.stream_name, timeout=timeout)

            if not streams:
                logger.error(f"Stream '{self.stream_name}' not found within {timeout}s")

                # DIAGNOSTIC: List all available LSL streams
                logger.info("Listing ALL available LSL streams for diagnosis...")
                all_streams = resolve_streams(timeout=2.0)

                if not all_streams:
                    logger.warning("  No LSL streams found at all!")
                    logger.warning("  This suggests muselsl hasn't published the stream yet, or there's a network issue")
                else:
                    logger.info(f"  Found {len(all_streams)} total LSL stream(s):")
                    for i, stream in enumerate(all_streams):
                        info = stream
                        logger.info(f"    [{i+1}] name='{info.name()}' type='{info.type()}' source_id='{info.source_id()}'")
                        logger.info(f"         hostname='{info.hostname()}' channels={info.channel_count()} rate={info.nominal_srate()} Hz")

                return False

            # Create inlet
            self.inlet = StreamInlet(streams[0], max_buflen=360)  # 360s buffer (LSL default)

            # Get stream info
            info = self.inlet.info()
            self.sample_rate = info.nominal_srate()
            self.n_channels = info.channel_count()

            # Extract channel names from XML description
            ch = info.desc().child("channels").child("channel")
            self.channel_names = []
            for _ in range(self.n_channels):
                self.channel_names.append(ch.child_value("label"))
                ch = ch.next_sibling()

            logger.info(f"Connected: {self.n_channels} channels @ {self.sample_rate} Hz")
            logger.info(f"Channels: {', '.join(self.channel_names)}")

            # Initialize rolling buffers (one per channel)
            max_samples = int(self.buffer_duration * self.sample_rate)
            with self.lock:
                for ch_name in self.channel_names:
                    self.rolling_buffers[ch_name] = deque(maxlen=max_samples)
                self.timestamps_buffer = deque(maxlen=max_samples)
                self.recording_buffer = []

            # CRITICAL: Flush inlet buffer to discard stale startup data
            self._flush_inlet_buffer()

            # Start pull thread
            self.running = True
            self.pull_thread = threading.Thread(
                target=self._pull_loop,
                name=f"LSL-Pull-{self.stream_name}",
                daemon=True
            )
            self.pull_thread.start()

            logger.info(f"✓ LSL stream '{self.stream_name}' active (pull thread started)")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to '{self.stream_name}': {e}")
            return False

    def stop(self):
        """
        Stop pull thread and disconnect from LSL stream.

        Gracefully shuts down the pull thread and cleans up resources.
        """
        if not self.running:
            logger.warning(f"Stream '{self.stream_name}' not running")
            return

        logger.info(f"Stopping LSL stream '{self.stream_name}'...")

        # Stop pull thread
        self.running = False
        if self.pull_thread:
            self.pull_thread.join(timeout=2.0)
            if self.pull_thread.is_alive():
                logger.warning(f"Pull thread for '{self.stream_name}' didn't stop gracefully")

        # Close inlet
        if self.inlet:
            self.inlet.close_stream()
            self.inlet = None

        logger.info(f"✓ LSL stream '{self.stream_name}' stopped")

    def _flush_inlet_buffer(self):
        """
        CRITICAL: Discard accumulated data in LSL inlet buffer.

        LSL uses FIFO queue - if we don't flush, we'll be processing data from
        5-10 seconds ago during neurofeedback. This would make feedback useless.

        Called once after connection, before starting pull thread.
        """
        logger.info(f"Flushing inlet buffer for '{self.stream_name}'...")

        if not self.inlet:
            logger.warning("Cannot flush - inlet not initialized")
            return

        total_flushed = 0
        while True:
            chunk, timestamps = self.inlet.pull_chunk(timeout=0.0, max_samples=1000)

            if not timestamps:  # No more data available
                break

            total_flushed += len(timestamps)

        logger.info(f"✓ Flushed {total_flushed} stale samples from inlet buffer")

    def _pull_loop(self):
        """
        Pull thread main loop - runs at 20 Hz (50ms intervals).

        Continuously pulls data from LSL inlet and updates rolling buffers.
        This runs independently from calc thread (10 Hz) and UI thread (10 Hz).

        Threading:
        - Runs in dedicated thread (daemon=True for clean shutdown)
        - Non-blocking pulls (timeout=0.0)
        - Thread-safe buffer updates via lock
        """
        logger.info(f"Pull thread started for '{self.stream_name}' (20 Hz)")

        pull_interval = 0.05  # 20 Hz = 50ms

        while self.running:
            start_time = time.time()

            try:
                # Non-blocking pull (timeout=0.0)
                # max_samples=256 covers up to 1 second of data @ 256 Hz
                chunk, timestamps = self.inlet.pull_chunk(timeout=0.0, max_samples=256)

                if timestamps:  # Got data
                    # Convert to numpy array (shape: [n_samples, n_channels])
                    chunk = np.array(chunk)

                    # Update rolling buffers (thread-safe)
                    with self.lock:
                        for i, ch_name in enumerate(self.channel_names):
                            self.rolling_buffers[ch_name].extend(chunk[:, i])

                        self.timestamps_buffer.extend(timestamps)

                        # Add to recording buffer (unlimited size)
                        for j, ts in enumerate(timestamps):
                            self.recording_buffer.append((ts, chunk[j, :]))

                # Rate limiting: Sleep to maintain 20 Hz
                elapsed = time.time() - start_time
                sleep_time = max(0, pull_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in pull loop for '{self.stream_name}': {e}")
                time.sleep(0.1)  # Avoid tight loop on persistent errors

        logger.info(f"Pull thread stopped for '{self.stream_name}'")

    def get_recent_data(self, duration: float = 4.0) -> Optional[Dict[str, np.ndarray]]:
        """
        Get most recent N seconds of data from rolling buffers.

        Thread-safe - can be called from calc thread while pull thread is running.

        Args:
            duration: Duration of data to retrieve in seconds (e.g., 1.0, 2.0, 4.0)

        Returns:
            Dict mapping channel_name -> numpy array of samples
            Returns None if insufficient data available

        Example:
            data = handler.get_recent_data(duration=4.0)
            if data:
                tp9_signal = data['TP9']  # 1024 samples @ 256 Hz
                # Compute FFT...
        """
        n_samples_needed = int(duration * self.sample_rate)

        with self.lock:
            # Check if we have enough data
            if len(self.timestamps_buffer) < n_samples_needed:
                return None

            # Extract most recent N samples from each channel
            result = {}
            for ch_name in self.channel_names:
                # deque is efficient for this - get last N elements
                buffer = self.rolling_buffers[ch_name]
                recent = list(buffer)[-n_samples_needed:]
                result[ch_name] = np.array(recent)

            return result

    def get_data_age_ms(self) -> Optional[float]:
        """
        Get age of most recent data point in milliseconds.

        This is critical for monitoring data freshness - if age > 200ms,
        there may be connection issues.

        Returns:
            Age in milliseconds, or None if no data available
        """
        with self.lock:
            if not self.timestamps_buffer:
                return None

            latest_timestamp = self.timestamps_buffer[-1]
            current_time = time.time()

            age_ms = (current_time - latest_timestamp) * 1000
            return age_ms

    def get_buffer_fill_ratio(self) -> float:
        """
        Get current fill ratio of rolling buffer (0.0 to 1.0).

        Useful for monitoring startup - feedback should wait until ratio > 0.9
        to ensure we have sufficient data for 4-second window.

        Returns:
            Fill ratio (e.g., 0.5 = half full, 1.0 = completely full)
        """
        with self.lock:
            max_len = self.timestamps_buffer.maxlen
            current_len = len(self.timestamps_buffer)
            return current_len / max_len if max_len > 0 else 0.0

    def get_recording_buffer(self) -> List[Tuple[float, np.ndarray]]:
        """
        Get entire recording buffer for CSV export.

        Thread-safe - can be called while pull thread is running.

        Returns:
            List of (timestamp, sample_array) tuples
            Each sample_array has shape (n_channels,)

        Note:
            This returns a COPY to prevent modification during export.
            Recording buffer is unlimited size - may be large for long sessions.
        """
        with self.lock:
            return self.recording_buffer.copy()

    def clear_recording_buffer(self):
        """
        Clear recording buffer - useful for starting new trial/session.

        Does NOT affect rolling buffers (which are for real-time processing).
        """
        with self.lock:
            self.recording_buffer = []
            logger.info(f"Recording buffer cleared for '{self.stream_name}'")

    def get_stream_info(self) -> Dict[str, any]:
        """
        Get stream metadata for monitoring/debugging.

        Returns:
            Dict with stream_name, sample_rate, n_channels, channel_names, etc.
        """
        with self.lock:
            return {
                'stream_name': self.stream_name,
                'sample_rate': self.sample_rate,
                'n_channels': self.n_channels,
                'channel_names': self.channel_names,
                'buffer_duration': self.buffer_duration,
                'buffer_fill_ratio': self.get_buffer_fill_ratio(),
                'data_age_ms': self.get_data_age_ms(),
                'recording_samples': len(self.recording_buffer),
                'is_running': self.running,
            }

    def __repr__(self):
        return f"<LSLStreamHandler '{self.stream_name}' @ {self.sample_rate} Hz>"
