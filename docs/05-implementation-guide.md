# Implementation Guide

## Project Structure

```
ExG-Lab/
├── backend/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app
│   ├── config.py                # Configuration
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── manager.py           # Device discovery & connection
│   │   └── stream.py            # LSL stream handling
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── multi_scale.py       # Multi-timescale processor
│   │   ├── rate_control.py      # Rate-decoupled loop
│   │   └── utils.py             # Signal processing utilities
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py           # Session state machine
│   │   └── storage.py           # Recording to disk
│   └── websocket/
│       ├── __init__.py
│       └── handler.py           # WebSocket communication
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── DevicePanel.tsx
│   │   │   ├── LiveMonitor.tsx
│   │   │   └── FeedbackDisplay.tsx
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts
│   │   └── App.tsx
│   ├── package.json
│   └── tsconfig.json
├── data/                        # Recorded sessions
│   └── session_YYYYMMDD_HHMMSS/
│       ├── Muse_1.csv
│       ├── Muse_2.csv
│       └── metadata.json
├── docs/                        # Documentation
├── tests/
│   ├── test_devices.py
│   ├── test_processing.py
│   └── test_session.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Step-by-Step Implementation

### Step 1: Environment Setup

```bash
# Create project directory
mkdir ExG-Lab
cd ExG-Lab

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn websockets
pip install pylsl numpy scipy
pip install muselsl  # Or your patched version

# Create project structure
mkdir -p backend/{devices,processing,session,websocket}
mkdir -p frontend/src/{components,hooks}
mkdir -p data tests docs

# Initialize git
git init
echo "venv/" >> .gitignore
echo "data/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
```

### Step 2: Configuration

**backend/config.py**:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LSL settings
    lsl_buffer_size: int = 360  # seconds
    lsl_resolve_timeout: float = 5.0  # seconds

    # Rate settings
    pull_rate_hz: int = 20
    calc_rate_hz: int = 10
    ui_rate_hz: int = 10

    # Processing settings
    sample_rate: int = 256  # Muse sampling rate
    buffer_duration: float = 4.0  # seconds
    n_channels: int = 4

    # Recording settings
    data_dir: str = "data"
    save_interval: float = 5.0  # seconds

    # WebSocket settings
    ws_host: str = "0.0.0.0"
    ws_port: int = 8000

    # Device settings
    max_devices: int = 4
    device_prefix: str = "Muse_"

    class Config:
        env_file = ".env"

settings = Settings()
```

### Step 3: Device Management

**backend/devices/manager.py**:
```python
import subprocess
import time
from typing import List, Dict, Optional
from pylsl import StreamInlet, resolve_stream, StreamInfo

class DeviceManager:
    def __init__(self):
        self.devices = {}  # name -> device_info
        self.processes = {}  # name -> subprocess

    def scan_devices(self, timeout: float = 5.0) -> List[Dict]:
        """
        Scan for available Muse devices

        Returns:
            List of device info dicts with 'name' and 'address'
        """
        try:
            # Use muselsl list to find devices
            result = subprocess.run(
                ['muselsl', 'list'],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            # Parse output
            devices = []
            for line in result.stdout.split('\n'):
                if 'Muse' in line:
                    # Extract name and address
                    # Format: "Muse-XXXX (00:00:00:00:00:00)"
                    parts = line.split()
                    if len(parts) >= 2:
                        name = parts[0]
                        address = parts[1].strip('()')

                        devices.append({
                            'name': name,
                            'address': address,
                            'status': 'available'
                        })

            return devices

        except subprocess.TimeoutExpired:
            print("Device scan timed out")
            return []

    def connect_device(self,
                       address: str,
                       stream_name: str,
                       backend: str = 'auto') -> bool:
        """
        Start muselsl stream for a device

        Args:
            address: Bluetooth MAC address
            stream_name: LSL stream name (e.g., 'Muse_1')
            backend: 'auto', 'bluemuse', 'gatt', or 'bgapi'

        Returns:
            True if connection successful
        """
        try:
            # Start muselsl stream subprocess
            cmd = [
                'muselsl', 'stream',
                '--address', address,
                '--name', stream_name,
                '--backend', backend
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for stream to appear
            time.sleep(2.0)

            # Verify stream exists
            streams = resolve_stream('name', stream_name, timeout=5.0)

            if streams:
                self.processes[stream_name] = process
                self.devices[stream_name] = {
                    'address': address,
                    'stream_name': stream_name,
                    'status': 'connected',
                    'process': process
                }
                return True

            else:
                process.terminate()
                return False

        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect_device(self, stream_name: str):
        """Stop muselsl stream for a device"""
        if stream_name in self.processes:
            process = self.processes[stream_name]
            process.terminate()
            process.wait(timeout=5.0)

            del self.processes[stream_name]
            del self.devices[stream_name]

    def disconnect_all(self):
        """Disconnect all devices"""
        for stream_name in list(self.processes.keys()):
            self.disconnect_device(stream_name)

    def get_device_status(self, stream_name: str) -> Optional[Dict]:
        """
        Get current status of a device

        Returns:
            Dict with status info or None if not found
        """
        if stream_name not in self.devices:
            return None

        device = self.devices[stream_name]
        process = device['process']

        return {
            'stream_name': stream_name,
            'address': device['address'],
            'connected': process.poll() is None,
            'pid': process.pid
        }
```

**backend/devices/stream.py**:
```python
from pylsl import StreamInlet, resolve_stream
from collections import deque
import numpy as np
from typing import Optional, Tuple

def flush_inlet_buffer(inlet: StreamInlet) -> int:
    """
    Flush all accumulated data from LSL inlet

    Returns:
        Number of samples flushed
    """
    total_flushed = 0

    while True:
        chunk, timestamps = inlet.pull_chunk(
            timeout=0.0,
            max_samples=1000
        )

        if not timestamps:
            break

        total_flushed += len(timestamps)

    return total_flushed

class LSLStreamHandler:
    def __init__(self, stream_name: str, buffer_size: int = 1024):
        """
        Handle LSL stream connection and buffering

        Args:
            stream_name: Name of LSL stream
            buffer_size: Rolling buffer size (samples)
        """
        self.stream_name = stream_name
        self.buffer_size = buffer_size

        # Find and connect to stream
        streams = resolve_stream('name', stream_name, timeout=5.0)

        if not streams:
            raise ValueError(f"Stream '{stream_name}' not found")

        # Create inlet
        self.inlet = StreamInlet(streams[0], max_buflen=360)

        # Get stream info
        info = self.inlet.info()
        self.sample_rate = info.nominal_srate()
        self.n_channels = info.channel_count()

        # Rolling buffer (per channel)
        self.buffers = [
            deque(maxlen=buffer_size)
            for _ in range(self.n_channels)
        ]

        # Recording buffer (for saving to disk)
        self.recording_buffer = []

        # Flush accumulated data
        flushed = flush_inlet_buffer(self.inlet)
        print(f"Flushed {flushed} samples from {stream_name}")

    def pull_data(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Pull data from LSL stream (non-blocking)

        Returns:
            (chunk, timestamps) or (None, None) if no data
        """
        chunk, timestamps = self.inlet.pull_chunk(
            timeout=0.0,
            max_samples=256
        )

        if not timestamps:
            return None, None

        # Convert to numpy array
        chunk = np.array(chunk)  # Shape: (n_samples, n_channels)

        return chunk, np.array(timestamps)

    def add_to_buffers(self, chunk: np.ndarray):
        """
        Add chunk to rolling buffers

        Args:
            chunk: Array of shape (n_samples, n_channels)
        """
        for sample in chunk:
            for ch_idx, value in enumerate(sample):
                self.buffers[ch_idx].append(value)

    def add_to_recording(self, chunk: np.ndarray, timestamps: np.ndarray):
        """
        Add chunk to recording buffer

        Args:
            chunk: Array of shape (n_samples, n_channels)
            timestamps: Array of timestamps
        """
        for i, timestamp in enumerate(timestamps):
            sample_data = {
                'timestamp': timestamp,
                'sample': chunk[i, :].tolist()
            }
            self.recording_buffer.append(sample_data)

    def get_buffer_array(self, channel: int) -> np.ndarray:
        """
        Get rolling buffer as numpy array

        Args:
            channel: Channel index

        Returns:
            Array of buffer contents
        """
        return np.array(self.buffers[channel])

    def clear_recording_buffer(self):
        """Clear recording buffer after saving"""
        self.recording_buffer.clear()
```

### Step 4: Multi-Scale Processing

**backend/processing/multi_scale.py**:
```python
from collections import deque
import numpy as np
from scipy import signal
from typing import Dict, Optional

class MultiScaleProcessor:
    def __init__(self, sample_rate: int = 256):
        self.sample_rate = sample_rate

        # Window sizes
        self.windows = {
            '1s': int(sample_rate * 1.0),
            '2s': int(sample_rate * 2.0),
            '4s': int(sample_rate * 4.0)
        }

        # Frequency bands
        self.bands = {
            'delta': (0.5, 4),
            'theta': (4, 8),
            'alpha': (8, 13),
            'beta': (13, 30),
            'gamma': (30, 50)
        }

    def compute_all_timescales(self,
                               buffer: np.ndarray) -> Optional[Dict]:
        """
        Compute metrics for all timescales

        Args:
            buffer: Array of samples (should have >= 1024 samples)

        Returns:
            Dict with metrics for each timescale
        """
        if len(buffer) < self.windows['1s']:
            return None

        results = {}

        for timescale, n_samples in self.windows.items():
            if len(buffer) >= n_samples:
                # Extract latest N samples
                window = buffer[-n_samples:]

                # Compute metrics
                results[timescale] = self._compute_metrics(window, n_samples)

        return results

    def _compute_metrics(self, window: np.ndarray, n_samples: int) -> Dict:
        """
        Compute band powers and derived metrics

        Args:
            window: Time series data
            n_samples: Window size
        """
        # Welch's method for PSD
        nperseg = min(n_samples // 2, self.sample_rate)

        try:
            freqs, psd = signal.welch(
                window,
                fs=self.sample_rate,
                nperseg=nperseg,
                scaling='density'
            )
        except Exception as e:
            print(f"Welch failed: {e}")
            return self._empty_metrics()

        # Compute band powers
        band_powers = {}

        for band_name, (low, high) in self.bands.items():
            idx = np.logical_and(freqs >= low, freqs <= high)

            if np.any(idx):
                band_powers[band_name] = np.trapz(psd[idx], freqs[idx])
            else:
                band_powers[band_name] = 0.0

        # Relaxation index (alpha/beta)
        relaxation = (
            band_powers['alpha'] / band_powers['beta']
            if band_powers['beta'] > 0
            else 0.0
        )

        # Attention index (beta/theta)
        attention = (
            band_powers['beta'] / band_powers['theta']
            if band_powers['theta'] > 0
            else 0.0
        )

        return {
            'band_powers': band_powers,
            'relaxation': relaxation,
            'attention': attention,
            'total_power': sum(band_powers.values())
        }

    def _empty_metrics(self) -> Dict:
        """Return empty metrics structure"""
        return {
            'band_powers': {band: 0.0 for band in self.bands},
            'relaxation': 0.0,
            'attention': 0.0,
            'total_power': 0.0
        }

class MultiChannelMultiScaleProcessor:
    def __init__(self, n_channels: int = 4, sample_rate: int = 256):
        self.n_channels = n_channels
        self.processor = MultiScaleProcessor(sample_rate)
        self.channel_names = ['TP9', 'AF7', 'AF8', 'TP10']

    def compute_all_channels(self,
                            buffers: list) -> Dict:
        """
        Compute metrics for all channels

        Args:
            buffers: List of buffer arrays (one per channel)

        Returns:
            Dict with per-channel metrics
        """
        results = {}

        for ch_idx, ch_name in enumerate(self.channel_names):
            if ch_idx < len(buffers):
                buffer = np.array(buffers[ch_idx])
                ch_metrics = self.processor.compute_all_timescales(buffer)

                if ch_metrics:
                    results[ch_name] = ch_metrics

        return results

    def compute_frontal_average(self, all_metrics: Dict) -> Dict:
        """
        Average frontal channels (AF7, AF8) for relaxation

        Args:
            all_metrics: Output from compute_all_channels()

        Returns:
            Dict with averaged metrics per timescale
        """
        frontal_channels = ['AF7', 'AF8']

        results = {}

        for timescale in ['1s', '2s', '4s']:
            relaxation_values = []

            for ch in frontal_channels:
                if (ch in all_metrics
                    and timescale in all_metrics[ch]):
                    relaxation_values.append(
                        all_metrics[ch][timescale]['relaxation']
                    )

            if relaxation_values:
                results[timescale] = {
                    'relaxation': np.mean(relaxation_values),
                    'relaxation_std': np.std(relaxation_values)
                }

        return results
```

### Step 5: Rate-Controlled Loop

**backend/processing/rate_control.py**:
```python
import time
import threading
from typing import Dict, Callable, Optional
from collections import deque

class RateControlledFeedbackLoop:
    def __init__(self,
                 pull_hz: int = 20,
                 calc_hz: int = 10,
                 ui_hz: int = 10):

        self.pull_interval = 1.0 / pull_hz
        self.calc_interval = 1.0 / calc_hz
        self.ui_interval = 1.0 / ui_hz

        # Timing state
        self.last_pull = 0.0
        self.last_calc = 0.0
        self.last_ui = 0.0

        # Metrics cache
        self.latest_metrics = None
        self.metrics_lock = threading.Lock()

        # Control
        self.active = False

        # Callbacks
        self.pull_callback: Optional[Callable] = None
        self.calc_callback: Optional[Callable] = None
        self.ui_callback: Optional[Callable] = None

    def set_pull_callback(self, callback: Callable):
        """
        Set callback for data pulling

        Callback signature: () -> None
        """
        self.pull_callback = callback

    def set_calc_callback(self, callback: Callable):
        """
        Set callback for calculations

        Callback signature: () -> dict (metrics)
        """
        self.calc_callback = callback

    def set_ui_callback(self, callback: Callable):
        """
        Set callback for UI updates

        Callback signature: (metrics: dict) -> None
        """
        self.ui_callback = callback

    def run(self):
        """
        Main loop with decoupled rates
        """
        self.active = True

        self.last_pull = time.time()
        self.last_calc = time.time()
        self.last_ui = time.time()

        while self.active:
            now = time.time()

            # Pull if interval elapsed
            if (now - self.last_pull >= self.pull_interval
                and self.pull_callback):
                self.pull_callback()
                self.last_pull = now

            # Calculate if interval elapsed
            if (now - self.last_calc >= self.calc_interval
                and self.calc_callback):
                metrics = self.calc_callback()

                if metrics:
                    with self.metrics_lock:
                        self.latest_metrics = metrics

                self.last_calc = now

            # UI update if interval elapsed and metrics available
            if (now - self.last_ui >= self.ui_interval
                and self.ui_callback):

                with self.metrics_lock:
                    metrics = self.latest_metrics

                if metrics:
                    self.ui_callback(metrics)

                self.last_ui = now

            # Small sleep to prevent busy-wait
            time.sleep(0.01)

    def start_async(self):
        """Start loop in background thread"""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Stop the loop"""
        self.active = False
```

### Step 6: Session Management

**backend/session/manager.py**:
```python
import time
import os
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

class SessionState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    FLUSHING = "flushing"
    RECORDING = "recording"
    PAUSED = "paused"
    SAVING = "saving"

class SessionManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.state = SessionState.IDLE

        self.session_id: Optional[str] = None
        self.session_dir: Optional[str] = None
        self.start_time: Optional[float] = None

        self.metadata = {}
        self.devices = []

    def start_session(self,
                      devices: List[str],
                      participants: List[str],
                      protocol: str = "meditation") -> str:
        """
        Start a new recording session

        Args:
            devices: List of device names (e.g., ['Muse_1', 'Muse_2'])
            participants: List of participant names
            protocol: Experiment protocol name

        Returns:
            Session ID
        """
        # Generate session ID
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create session directory
        self.session_dir = os.path.join(self.data_dir, self.session_id)
        os.makedirs(self.session_dir, exist_ok=True)

        # Store metadata
        self.metadata = {
            'session_id': self.session_id,
            'start_time': time.time(),
            'start_time_iso': datetime.now().isoformat(),
            'devices': devices,
            'participants': participants,
            'protocol': protocol
        }

        self.devices = devices
        self.start_time = time.time()
        self.state = SessionState.RECORDING

        return self.session_id

    def end_session(self) -> str:
        """
        End current session and save metadata

        Returns:
            Path to session directory
        """
        if self.state != SessionState.RECORDING:
            raise ValueError("No active session")

        # Update metadata
        self.metadata['end_time'] = time.time()
        self.metadata['end_time_iso'] = datetime.now().isoformat()
        self.metadata['duration'] = time.time() - self.start_time

        # Save metadata
        metadata_path = os.path.join(self.session_dir, 'metadata.json')

        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        self.state = SessionState.IDLE
        session_dir = self.session_dir

        # Reset state
        self.session_id = None
        self.session_dir = None
        self.start_time = None

        return session_dir

    def get_device_filepath(self, device_name: str) -> str:
        """
        Get filepath for device recording

        Args:
            device_name: Name of device (e.g., 'Muse_1')

        Returns:
            Full path to CSV file
        """
        if not self.session_dir:
            raise ValueError("No active session")

        filename = f"{device_name}.csv"
        return os.path.join(self.session_dir, filename)

    def add_event_marker(self, event: str, timestamp: Optional[float] = None):
        """
        Add event marker to session metadata

        Args:
            event: Event description
            timestamp: Event timestamp (default: current time)
        """
        if 'events' not in self.metadata:
            self.metadata['events'] = []

        self.metadata['events'].append({
            'event': event,
            'timestamp': timestamp or time.time(),
            'timestamp_iso': datetime.now().isoformat()
        })
```

**backend/session/storage.py**:
```python
import csv
import os
from typing import List, Dict

class DataRecorder:
    def __init__(self, filepath: str, n_channels: int = 4):
        """
        Record EEG data to CSV file

        Args:
            filepath: Path to CSV file
            n_channels: Number of channels
        """
        self.filepath = filepath
        self.n_channels = n_channels

        # Create CSV file with header
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header row
            header = ['timestamp'] + [f'ch{i+1}' for i in range(n_channels)]
            writer.writerow(header)

    def save_chunk(self, data: List[Dict]):
        """
        Append data chunk to CSV

        Args:
            data: List of dicts with 'timestamp' and 'sample' keys
        """
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.writer(f)

            for item in data:
                row = [item['timestamp']] + item['sample']
                writer.writerow(row)

    def close(self):
        """Placeholder for future cleanup"""
        pass
```

### Step 7: Complete Integration

**backend/main.py**:
```python
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from typing import Dict, List

from config import settings
from devices.manager import DeviceManager
from devices.stream import LSLStreamHandler
from processing.multi_scale import MultiChannelMultiScaleProcessor
from processing.rate_control import RateControlledFeedbackLoop
from session.manager import SessionManager
from session.storage import DataRecorder

app = FastAPI(title="ExG-Lab Backend")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
device_manager = DeviceManager()
session_manager = SessionManager(data_dir=settings.data_dir)
stream_handlers: Dict[str, LSLStreamHandler] = {}
processors: Dict[str, MultiChannelMultiScaleProcessor] = {}
recorders: Dict[str, DataRecorder] = {}
feedback_loop: RateControlledFeedbackLoop = None

# WebSocket connections
active_connections: List[WebSocket] = []

@app.get("/devices/scan")
async def scan_devices():
    """Scan for available Muse devices"""
    devices = device_manager.scan_devices()
    return {"devices": devices}

@app.post("/devices/connect")
async def connect_device(address: str, stream_name: str):
    """Connect to a Muse device"""
    success = device_manager.connect_device(address, stream_name)

    if success:
        # Create stream handler
        stream_handlers[stream_name] = LSLStreamHandler(
            stream_name,
            buffer_size=int(settings.sample_rate * settings.buffer_duration)
        )

        # Create processor
        processors[stream_name] = MultiChannelMultiScaleProcessor(
            n_channels=settings.n_channels,
            sample_rate=settings.sample_rate
        )

        return {"success": True, "stream_name": stream_name}
    else:
        return {"success": False, "error": "Connection failed"}

@app.post("/devices/disconnect/{stream_name}")
async def disconnect_device(stream_name: str):
    """Disconnect a device"""
    device_manager.disconnect_device(stream_name)

    # Cleanup
    if stream_name in stream_handlers:
        del stream_handlers[stream_name]
    if stream_name in processors:
        del processors[stream_name]

    return {"success": True}

@app.post("/session/start")
async def start_session(devices: List[str],
                       participants: List[str],
                       protocol: str = "meditation"):
    """Start a recording session"""
    global feedback_loop, recorders

    session_id = session_manager.start_session(devices, participants, protocol)

    # Create recorders
    for device in devices:
        filepath = session_manager.get_device_filepath(device)
        recorders[device] = DataRecorder(
            filepath,
            n_channels=settings.n_channels
        )

    # Start feedback loop
    feedback_loop = RateControlledFeedbackLoop(
        pull_hz=settings.pull_rate_hz,
        calc_hz=settings.calc_rate_hz,
        ui_hz=settings.ui_rate_hz
    )

    # Set callbacks
    feedback_loop.set_pull_callback(pull_data_callback)
    feedback_loop.set_calc_callback(calculate_metrics_callback)
    feedback_loop.set_ui_callback(send_to_ui_callback)

    # Start loop
    feedback_loop.start_async()

    return {"session_id": session_id}

@app.post("/session/end")
async def end_session():
    """End current session"""
    global feedback_loop

    # Stop feedback loop
    if feedback_loop:
        feedback_loop.stop()
        feedback_loop = None

    # Save remaining data
    for device, handler in stream_handlers.items():
        if device in recorders:
            recorders[device].save_chunk(handler.recording_buffer)
            handler.clear_recording_buffer()
            recorders[device].close()

    # End session
    session_dir = session_manager.end_session()

    # Cleanup
    recorders.clear()

    return {"session_dir": session_dir}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time data"""
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Handle client messages if needed

    except:
        active_connections.remove(websocket)

# Callback functions

def pull_data_callback():
    """Pull data from all devices"""
    for device_name, handler in stream_handlers.items():
        chunk, timestamps = handler.pull_data()

        if chunk is not None:
            # Add to rolling buffer
            handler.add_to_buffers(chunk)

            # Add to recording buffer
            if device_name in recorders:
                handler.add_to_recording(chunk, timestamps)

                # Periodic save
                if len(handler.recording_buffer) > 1000:
                    recorders[device_name].save_chunk(handler.recording_buffer)
                    handler.clear_recording_buffer()

def calculate_metrics_callback() -> Dict:
    """Calculate metrics for all devices"""
    all_metrics = {}

    for device_name, handler in stream_handlers.items():
        if device_name in processors:
            processor = processors[device_name]

            # Get metrics for all channels
            ch_metrics = processor.compute_all_channels(handler.buffers)

            # Get frontal average
            frontal_metrics = processor.compute_frontal_average(ch_metrics)

            all_metrics[device_name] = {
                'channels': ch_metrics,
                'frontal': frontal_metrics
            }

    return all_metrics

async def send_to_ui_callback(metrics: Dict):
    """Send metrics to all connected clients"""
    payload = {
        'timestamp': time.time(),
        'devices': metrics
    }

    # Send to all WebSocket connections
    for connection in active_connections[:]:
        try:
            await connection.send_json(payload)
        except:
            active_connections.remove(connection)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.ws_host, port=settings.ws_port)
```

### Step 8: Testing

**tests/test_processing.py**:
```python
import numpy as np
from backend.processing.multi_scale import MultiScaleProcessor

def test_multi_scale_processor():
    """Test multi-timescale processing"""
    processor = MultiScaleProcessor(sample_rate=256)

    # Generate test signal (10 Hz sine wave)
    duration = 4.0
    t = np.linspace(0, duration, int(256 * duration))
    signal_data = np.sin(2 * np.pi * 10 * t)  # 10 Hz

    # Compute metrics
    results = processor.compute_all_timescales(signal_data)

    assert results is not None
    assert '1s' in results
    assert '2s' in results
    assert '4s' in results

    # Check that alpha band captures 10 Hz signal
    for timescale in ['1s', '2s', '4s']:
        band_powers = results[timescale]['band_powers']
        assert band_powers['alpha'] > band_powers['delta']
        assert band_powers['alpha'] > band_powers['beta']

def test_empty_buffer():
    """Test with insufficient data"""
    processor = MultiScaleProcessor(sample_rate=256)

    # Too few samples
    short_signal = np.random.randn(100)

    results = processor.compute_all_timescales(short_signal)

    assert results is None  # Not enough data

if __name__ == "__main__":
    test_multi_scale_processor()
    test_empty_buffer()
    print("All tests passed!")
```

## Running the System

### Start Backend

```bash
cd backend
python main.py

# Output:
# INFO:     Started server process
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

### API Workflow

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Scan for devices
response = requests.get(f"{BASE_URL}/devices/scan")
devices = response.json()['devices']
print(f"Found {len(devices)} devices")

# 2. Connect devices
for i, device in enumerate(devices[:4]):
    requests.post(
        f"{BASE_URL}/devices/connect",
        params={
            'address': device['address'],
            'stream_name': f"Muse_{i+1}"
        }
    )

# 3. Start session
requests.post(
    f"{BASE_URL}/session/start",
    json={
        'devices': ['Muse_1', 'Muse_2', 'Muse_3', 'Muse_4'],
        'participants': ['Alice', 'Bob', 'Carol', 'Dave'],
        'protocol': 'meditation'
    }
)

# 4. Let it run...
time.sleep(300)  # 5 minutes

# 5. End session
response = requests.post(f"{BASE_URL}/session/end")
print(f"Session saved to: {response.json()['session_dir']}")
```

## Next Steps

- [UI Design Guide](06-ui-design.md) - Frontend implementation
- [Muselsl Bugfixes](07-muselsl-bugfixes.md) - Known issues and solutions
- [Architecture Overview](01-architecture-overview.md) - System design

---

**Last updated**: 2025-10-30
