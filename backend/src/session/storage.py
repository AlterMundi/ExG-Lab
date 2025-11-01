"""
Data Recorder - CSV export of EEG data and session metadata

This module handles persistent storage of neurofeedback sessions:
- Raw EEG data export to CSV
- Session metadata (JSON)
- Multi-device coordination
- Efficient buffering and batch writes

File Structure:
sessions/
├── {session_id}/
│   ├── metadata.json          # Session configuration and info
│   ├── Muse_1_P001.csv        # Raw EEG data for device 1
│   ├── Muse_2_P002.csv        # Raw EEG data for device 2
│   └── ...

CSV Format:
timestamp,TP9,AF7,AF8,TP10
1234567890.123,12.5,8.3,7.1,11.2
1234567890.127,12.3,8.5,7.0,11.1
...

Usage:
    recorder = DataRecorder(base_dir='./data/sessions')

    # Start recording
    recorder.start_recording(
        session_id='abc-123',
        subject_ids={'Muse_1': 'P001', 'Muse_2': 'P002'},
        metadata={'protocol': 'Meditation Baseline', 'notes': '...'}
    )

    # During session (called by LSLStreamHandler or RateController)
    recorder.record_sample('Muse_1', timestamp, [12.5, 8.3, 7.1, 11.2])

    # Stop recording
    files = recorder.stop_recording()
"""

import logging
import os
import csv
import json
import threading
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class DataRecorder:
    """
    Handles CSV export of EEG data for neurofeedback sessions.

    Features:
    - Thread-safe recording (can be called from multiple threads)
    - Efficient buffering (writes batches every N samples)
    - Per-device CSV files
    - Session metadata export
    """

    def __init__(
        self,
        base_dir: str = './data/sessions',
        buffer_size: int = 256,
        channel_names: List[str] = ['TP9', 'AF7', 'AF8', 'TP10']
    ):
        """
        Initialize data recorder.

        Args:
            base_dir: Base directory for session data
            buffer_size: Number of samples to buffer before writing (default 256 = 1s @ 256 Hz)
            channel_names: EEG channel names for CSV headers
        """
        self.base_dir = Path(base_dir)
        self.buffer_size = buffer_size
        self.channel_names = channel_names

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Recording state
        self.is_recording = False
        self.session_id: Optional[str] = None
        self.session_dir: Optional[Path] = None
        self.subject_ids: Dict[str, str] = {}  # device_name -> subject_id

        # File handles and writers
        self.csv_files: Dict[str, any] = {}  # device_name -> file handle
        self.csv_writers: Dict[str, csv.writer] = {}  # device_name -> csv.writer

        # Buffering (per device)
        self.buffers: Dict[str, List[Tuple[float, List[float]]]] = {}
        self.buffer_lock = threading.Lock()

        # Statistics
        self.sample_counts: Dict[str, int] = {}

        logger.info(f"DataRecorder initialized (base_dir: {base_dir})")

    def start_recording(
        self,
        session_id: str,
        subject_ids: Dict[str, str],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Start recording session.

        Args:
            session_id: Unique session ID (UUID)
            subject_ids: Dict mapping device_name -> subject_id
            metadata: Optional session metadata (protocol, notes, etc.)

        Returns:
            True if recording started successfully
        """
        if self.is_recording:
            logger.error("Recording already active")
            return False

        try:
            # Create session directory
            self.session_id = session_id
            self.session_dir = self.base_dir / session_id
            self.session_dir.mkdir(parents=True, exist_ok=True)

            self.subject_ids = subject_ids

            # Write metadata
            metadata_file = self.session_dir / 'metadata.json'
            full_metadata = {
                'session_id': session_id,
                'start_time': datetime.now().isoformat(),
                'subject_ids': subject_ids,
                'channel_names': self.channel_names,
                **(metadata or {})
            }

            with open(metadata_file, 'w') as f:
                json.dump(full_metadata, f, indent=2)

            # Open CSV files for each device
            for device_name, subject_id in subject_ids.items():
                csv_filename = f"{device_name}_{subject_id}.csv"
                csv_path = self.session_dir / csv_filename

                # Open file
                file_handle = open(csv_path, 'w', newline='')
                writer = csv.writer(file_handle)

                # Write header
                header = ['timestamp'] + self.channel_names
                writer.writerow(header)

                self.csv_files[device_name] = file_handle
                self.csv_writers[device_name] = writer

                # Initialize buffer and counter
                self.buffers[device_name] = []
                self.sample_counts[device_name] = 0

            self.is_recording = True

            logger.info(f"✓ Recording started: {session_id} ({len(subject_ids)} devices)")
            return True

        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            return False

    def record_sample(
        self,
        device_name: str,
        timestamp: float,
        sample: List[float]
    ):
        """
        Record single EEG sample.

        Thread-safe - can be called from LSL pull threads.

        Args:
            device_name: Device name (e.g., 'Muse_1')
            timestamp: LSL timestamp (seconds)
            sample: EEG values for all channels (e.g., [12.5, 8.3, 7.1, 11.2])

        Note:
            Samples are buffered and written in batches for efficiency.
        """
        if not self.is_recording:
            return

        if device_name not in self.csv_writers:
            logger.warning(f"Device '{device_name}' not registered for recording")
            return

        # Validate sample length
        if len(sample) != len(self.channel_names):
            logger.warning(
                f"Sample length mismatch: expected {len(self.channel_names)}, "
                f"got {len(sample)}"
            )
            return

        # Add to buffer (thread-safe)
        with self.buffer_lock:
            self.buffers[device_name].append((timestamp, sample))
            self.sample_counts[device_name] += 1

            # Check if buffer full
            if len(self.buffers[device_name]) >= self.buffer_size:
                self._flush_buffer(device_name)

    def record_samples_batch(
        self,
        device_name: str,
        samples: List[Tuple[float, List[float]]]
    ):
        """
        Record batch of EEG samples.

        More efficient than calling record_sample() repeatedly.

        Args:
            device_name: Device name
            samples: List of (timestamp, sample) tuples
        """
        if not self.is_recording:
            return

        if device_name not in self.csv_writers:
            logger.warning(f"Device '{device_name}' not registered for recording")
            return

        # Add all to buffer (thread-safe)
        with self.buffer_lock:
            self.buffers[device_name].extend(samples)
            self.sample_counts[device_name] += len(samples)

            # Flush if buffer full
            if len(self.buffers[device_name]) >= self.buffer_size:
                self._flush_buffer(device_name)

    def _flush_buffer(self, device_name: str):
        """
        Write buffered samples to CSV file.

        Must be called with buffer_lock held.

        Args:
            device_name: Device name to flush
        """
        if device_name not in self.buffers:
            return

        buffer = self.buffers[device_name]
        if not buffer:
            return

        try:
            writer = self.csv_writers[device_name]

            # Write all buffered rows
            for timestamp, sample in buffer:
                row = [timestamp] + sample
                writer.writerow(row)

            # Flush file to disk
            self.csv_files[device_name].flush()

            # Clear buffer
            self.buffers[device_name] = []

            logger.debug(f"Flushed {len(buffer)} samples for {device_name}")

        except Exception as e:
            logger.error(f"Error flushing buffer for {device_name}: {e}")

    def stop_recording(self) -> Dict[str, str]:
        """
        Stop recording and close all files.

        Returns:
            Dict mapping device_name -> CSV file path
        """
        if not self.is_recording:
            logger.warning("No active recording to stop")
            return {}

        try:
            # Flush all buffers
            with self.buffer_lock:
                for device_name in self.buffers.keys():
                    self._flush_buffer(device_name)

            # Close all files
            file_paths = {}
            for device_name, file_handle in self.csv_files.items():
                file_handle.close()
                csv_path = self.session_dir / f"{device_name}_{self.subject_ids[device_name]}.csv"
                file_paths[device_name] = str(csv_path)

            # Update metadata with end time and sample counts
            metadata_file = self.session_dir / 'metadata.json'
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata['end_time'] = datetime.now().isoformat()
            metadata['sample_counts'] = self.sample_counts.copy()
            metadata['duration_seconds'] = (
                datetime.fromisoformat(metadata['end_time']) -
                datetime.fromisoformat(metadata['start_time'])
            ).total_seconds()

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Log statistics
            total_samples = sum(self.sample_counts.values())
            logger.info(
                f"✓ Recording stopped: {self.session_id} | "
                f"Total samples: {total_samples} | "
                f"Files: {list(file_paths.values())}"
            )

            # Reset state
            self.is_recording = False
            self.session_id = None
            self.session_dir = None
            self.subject_ids = {}
            self.csv_files = {}
            self.csv_writers = {}
            self.buffers = {}
            self.sample_counts = {}

            return file_paths

        except Exception as e:
            logger.error(f"Error stopping recording: {e}", exc_info=True)
            return {}

    def get_recording_status(self) -> Dict[str, any]:
        """
        Get current recording status.

        Returns:
            Dict with session_id, is_recording, sample_counts, etc.
        """
        with self.buffer_lock:
            return {
                'is_recording': self.is_recording,
                'session_id': self.session_id,
                'devices': list(self.subject_ids.keys()),
                'sample_counts': self.sample_counts.copy(),
                'buffer_sizes': {
                    device: len(buffer)
                    for device, buffer in self.buffers.items()
                }
            }

    def list_sessions(self) -> List[Dict]:
        """
        List all recorded sessions.

        Returns:
            List of session summaries with metadata
        """
        sessions = []

        try:
            for session_dir in self.base_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                metadata_file = session_dir / 'metadata.json'
                if not metadata_file.exists():
                    continue

                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Get CSV files
                csv_files = list(session_dir.glob('*.csv'))

                sessions.append({
                    'session_id': metadata.get('session_id'),
                    'start_time': metadata.get('start_time'),
                    'end_time': metadata.get('end_time'),
                    'duration_seconds': metadata.get('duration_seconds'),
                    'protocol': metadata.get('protocol'),
                    'subject_ids': metadata.get('subject_ids', {}),
                    'sample_counts': metadata.get('sample_counts', {}),
                    'num_files': len(csv_files),
                    'directory': str(session_dir)
                })

        except Exception as e:
            logger.error(f"Error listing sessions: {e}")

        return sessions

    def get_session_metadata(self, session_id: str) -> Optional[Dict]:
        """
        Get metadata for specific session.

        Args:
            session_id: Session ID

        Returns:
            Metadata dict or None if not found
        """
        session_dir = self.base_dir / session_id
        metadata_file = session_dir / 'metadata.json'

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading metadata for {session_id}: {e}")
            return None

    def __del__(self):
        """Cleanup on destruction"""
        if self.is_recording:
            logger.warning("DataRecorder destroyed while recording active - stopping")
            self.stop_recording()
