# Testing Guide

## Overview

This document outlines testing strategies for ExG-Lab, focusing on critical areas where threading, LSL integration, and real-time performance must be validated.

## Test Categories

### 1. Unit Tests (Basic Functionality)

Test individual components in isolation.

**Location**: `tests/unit/`

### 2. Thread Safety Tests (CRITICAL)

Test concurrent access to shared resources.

**Location**: `tests/thread_safety/`

### 3. Integration Tests (System-Level)

Test component interactions and LSL integration.

**Location**: `tests/integration/`

### 4. Performance Tests (Benchmarking)

Validate rate compliance and latency requirements.

**Location**: `tests/performance/`

---

## Critical Thread Safety Tests

### Test 1: Concurrent Buffer Access

**Objective**: Verify that multiple threads can safely read/write buffers without corruption.

```python
# tests/thread_safety/test_buffer_concurrent.py
import threading
import time
import numpy as np
from backend.devices.stream import LSLStreamHandler

def test_concurrent_buffer_writes():
    """Test multiple threads writing to buffer simultaneously"""

    # Mock handler with buffer
    handler = MockStreamHandler()

    errors = []
    write_counts = [0, 0]

    def writer(thread_id):
        """Writer thread function"""
        try:
            for i in range(1000):
                chunk = np.random.randn(10, 4)
                handler.add_to_buffers(chunk)
                write_counts[thread_id] += 10
        except Exception as e:
            errors.append(e)

    def reader():
        """Reader thread function"""
        try:
            for i in range(500):
                snapshot = handler.get_buffer_snapshot()
                # Verify integrity
                for ch_buf in snapshot:
                    assert len(ch_buf) <= 1024  # maxlen respected
        except Exception as e:
            errors.append(e)

    # Create threads
    threads = [
        threading.Thread(target=writer, args=(0,)),
        threading.Thread(target=writer, args=(1,)),
        threading.Thread(target=reader),
        threading.Thread(target=reader)
    ]

    # Run concurrently
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Verify all writes succeeded
    assert write_counts[0] == 10000
    assert write_counts[1] == 10000

    # Verify buffer integrity
    assert len(handler.buffers[0]) <= 1024
```

### Test 2: Metrics Cache Race Conditions

**Objective**: Verify calc thread and UI thread don't corrupt shared metrics.

```python
# tests/thread_safety/test_metrics_cache.py
import threading
from backend.processing.rate_control import RateControlledFeedbackLoop

def test_metrics_cache_concurrent_access():
    """Test calc thread writing while UI thread reads"""

    loop = RateControlledFeedbackLoop(calc_hz=100, ui_hz=100)

    read_values = []
    write_values = []
    errors = []

    def calc_callback():
        """Simulated calc callback"""
        try:
            metrics = {'value': np.random.random()}
            write_values.append(metrics['value'])
            return metrics
        except Exception as e:
            errors.append(e)
            return None

    def ui_callback(metrics):
        """Simulated UI callback"""
        try:
            if metrics and 'value' in metrics:
                read_values.append(metrics['value'])
        except Exception as e:
            errors.append(e)

    loop.set_calc_callback(calc_callback)
    loop.set_ui_callback(ui_callback)

    # Run for 1 second
    loop.start()
    time.sleep(1.0)
    loop.stop()

    # Verify no errors
    assert len(errors) == 0, f"Errors: {errors}"

    # Verify reads/writes occurred
    assert len(write_values) > 90  # ~100 Hz for 1s
    assert len(read_values) > 90

    # Verify no corruption (all values are valid floats)
    for val in read_values:
        assert 0.0 <= val <= 1.0
```

### Test 3: Recording Buffer Overflow

**Objective**: Verify recording buffer doesn't grow unbounded.

```python
# tests/thread_safety/test_recording_buffer.py
import threading
import time
from backend.devices.stream import LSLStreamHandler

def test_recording_buffer_bounded_growth():
    """Test that recording buffer is periodically flushed"""

    handler = MockStreamHandler()

    def pull_thread():
        """Simulate pull thread adding data"""
        for i in range(100):
            chunk = np.random.randn(256, 4)  # 1 second of data
            timestamps = np.arange(i, i+1, 1/256)
            handler.add_to_recording(chunk, timestamps)
            time.sleep(0.01)  # Simulate 100 Hz pull

    def save_thread():
        """Simulate save thread flushing buffer"""
        for i in range(10):
            time.sleep(0.1)  # Flush every 100ms
            data = handler.flush_recording_buffer()
            # Verify data not empty
            assert len(data) > 0

    threads = [
        threading.Thread(target=pull_thread),
        threading.Thread(target=save_thread)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify buffer is empty (or small) after flushing
    with handler.recording_lock:
        assert len(handler.recording_buffer) < 1000  # Should be flushed
```

---

## LSL Integration Tests

### Test 4: Buffer Flushing

**Objective**: Verify flushing removes all accumulated data.

```python
# tests/integration/test_lsl_flushing.py
from pylsl import StreamInlet, StreamOutlet, StreamInfo
import time
from backend.devices.stream import flush_inlet_buffer

def test_buffer_flush_removes_old_data():
    """Test that flushing actually clears LSL buffer"""

    # Create mock LSL stream
    info = StreamInfo('TestStream', 'EEG', 4, 256, 'float32', 'test123')
    outlet = StreamOutlet(info)

    # Create inlet
    inlet = StreamInlet(resolve_stream('name', 'TestStream')[0], max_buflen=360)

    # Let data accumulate (2 seconds = 512 samples)
    for i in range(512):
        outlet.push_sample([1.0, 2.0, 3.0, 4.0])
        time.sleep(1/256)

    # Flush
    flushed = flush_inlet_buffer(inlet)

    # Verify samples were flushed
    assert flushed >= 500  # Should have flushed ~512 samples

    # New pull should get fresh data
    time.sleep(0.1)  # Let new data arrive

    chunk, timestamps = inlet.pull_chunk(timeout=0.0)

    # Verify timestamps are recent
    if timestamps:
        age = time.time() - timestamps[-1]
        assert age < 0.2  # Should be < 200ms old
```

### Test 5: Gap Detection

**Objective**: Verify gaps in data stream are detected.

```python
# tests/integration/test_gap_detection.py
import time
from backend.devices.stream import LSLStreamHandler

def test_gap_detection():
    """Test that data gaps are detected and logged"""

    handler = MockStreamHandler()

    # Add normal chunk
    chunk1 = np.random.randn(256, 4)
    timestamps1 = np.arange(0, 1.0, 1/256)
    handler.pull_data = lambda: (chunk1, timestamps1)
    chunk, ts = handler.pull_data()
    handler.add_to_buffers(chunk)
    handler.add_to_recording(chunk, ts)

    # Simulate 500ms gap
    time.sleep(0.5)

    # Add chunk after gap
    chunk2 = np.random.randn(256, 4)
    timestamps2 = np.arange(1.5, 2.5, 1/256)
    handler.pull_data = lambda: (chunk2, timestamps2)
    chunk, ts = handler.pull_data()
    handler.add_to_buffers(chunk)
    handler.add_to_recording(chunk, ts)

    # Verify gap was detected
    gaps = handler.get_gaps()
    assert len(gaps) == 1
    assert gaps[0]['duration'] > 0.4  # ~500ms gap
    assert gaps[0]['duration'] < 0.6
```

---

## Performance Tests

### Test 6: Pull Rate Compliance

**Objective**: Verify pull thread maintains 20 Hz rate.

```python
# tests/performance/test_pull_rate.py
import time
from backend.processing.rate_control import RateControlledFeedbackLoop

def test_pull_rate_compliance():
    """Verify pull thread maintains target rate"""

    pull_times = []

    def pull_callback():
        pull_times.append(time.time())

    loop = RateControlledFeedbackLoop(pull_hz=20, calc_hz=10, ui_hz=10)
    loop.set_pull_callback(pull_callback)

    # Run for 5 seconds
    loop.start()
    time.sleep(5.0)
    loop.stop()

    # Verify rate (±10% tolerance)
    pull_rate = len(pull_times) / 5.0
    assert 18 <= pull_rate <= 22, f"Pull rate: {pull_rate} Hz (expected 20±2)"

    # Verify timing consistency
    intervals = np.diff(pull_times)
    mean_interval = np.mean(intervals)
    std_interval = np.std(intervals)

    assert 0.045 <= mean_interval <= 0.055  # ~50ms
    assert std_interval < 0.01  # Low jitter
```

### Test 7: Calc Rate Compliance

**Objective**: Verify calc thread maintains 10 Hz despite FFT load.

```python
# tests/performance/test_calc_rate.py
import time
import numpy as np
from backend.processing.rate_control import RateControlledFeedbackLoop

def test_calc_rate_under_load():
    """Verify calc thread maintains rate with realistic FFT load"""

    calc_times = []

    def calc_callback():
        """Simulated calc with FFT"""
        calc_times.append(time.time())

        # Simulate FFT computation (~10ms)
        data = np.random.randn(1024)
        _ = np.fft.fft(data)

        return {'dummy': 'metrics'}

    loop = RateControlledFeedbackLoop(calc_hz=10)
    loop.set_calc_callback(calc_callback)

    # Run for 5 seconds
    loop.start()
    time.sleep(5.0)
    loop.stop()

    # Verify rate (±10% tolerance)
    calc_rate = len(calc_times) / 5.0
    assert 9 <= calc_rate <= 11, f"Calc rate: {calc_rate} Hz (expected 10±1)"
```

### Test 8: Multi-Device Parallel Processing

**Objective**: Verify parallel FFT processing scales correctly.

```python
# tests/performance/test_parallel_processing.py
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor

def compute_fft(data):
    """Simulate device FFT computation"""
    return {
        '1s': np.fft.fft(data[-256:]),
        '2s': np.fft.fft(data[-512:]),
        '4s': np.fft.fft(data[-1024:])
    }

def test_parallel_speedup():
    """Verify parallel processing is faster than sequential"""

    # Generate data for 4 devices
    devices_data = [np.random.randn(1024) for _ in range(4)]

    # Sequential processing
    start = time.time()
    seq_results = [compute_fft(data) for data in devices_data]
    seq_time = time.time() - start

    # Parallel processing
    with ThreadPoolExecutor(max_workers=4) as executor:
        start = time.time()
        par_results = list(executor.map(compute_fft, devices_data))
        par_time = time.time() - start

    # Verify speedup (should be ~4x on 4+ core system)
    speedup = seq_time / par_time
    print(f"Sequential: {seq_time*1000:.1f}ms, Parallel: {par_time*1000:.1f}ms, Speedup: {speedup:.2f}x")

    assert speedup > 2.5, f"Insufficient speedup: {speedup:.2f}x"
    assert par_time < 0.060, f"Parallel too slow: {par_time*1000:.1f}ms"
```

---

## End-to-End Integration Tests

### Test 9: Complete Data Flow

**Objective**: Test full pipeline from LSL to WebSocket.

```python
# tests/integration/test_end_to_end.py
import asyncio
import time
from backend.main import create_app
from backend.devices.stream import LSLStreamHandler
from backend.processing.rate_control import RateControlledFeedbackLoop

async def test_complete_data_flow():
    """Test complete data flow: LSL → buffers → calc → WebSocket"""

    # Setup components
    handler = MockStreamHandler()
    loop = RateControlledFeedbackLoop(pull_hz=20, calc_hz=10, ui_hz=10)

    received_metrics = []

    def pull_callback():
        chunk = np.random.randn(13, 4)  # ~50ms @ 256 Hz
        timestamps = np.arange(13) / 256
        handler.add_to_buffers(chunk)

    def calc_callback():
        snapshot = handler.get_buffer_snapshot()
        if len(snapshot[0]) >= 1024:
            return {'test': 'metrics'}
        return None

    async def ui_callback(metrics):
        received_metrics.append(metrics)

    loop.set_pull_callback(pull_callback)
    loop.set_calc_callback(calc_callback)
    loop.set_ui_callback(ui_callback)

    # Run for 5 seconds
    loop.start()
    await asyncio.sleep(5.0)
    loop.stop()

    # Verify metrics received
    assert len(received_metrics) > 40  # ~10 Hz for 5s
    assert all('test' in m for m in received_metrics)
```

---

## Mock Objects for Testing

```python
# tests/mocks.py
import numpy as np
import threading
from collections import deque

class MockStreamHandler:
    """Mock LSL stream handler for testing"""

    def __init__(self, n_channels=4, buffer_size=1024):
        self.n_channels = n_channels
        self.buffers = [deque(maxlen=buffer_size) for _ in range(n_channels)]
        self.recording_buffer = []

        self.buffer_lock = threading.Lock()
        self.recording_lock = threading.Lock()

        self.last_timestamp = None
        self.gaps = []

    def add_to_buffers(self, chunk):
        with self.buffer_lock:
            for sample in chunk:
                for ch_idx, value in enumerate(sample):
                    self.buffers[ch_idx].append(value)

    def get_buffer_snapshot(self):
        with self.buffer_lock:
            return [np.array(buf) for buf in self.buffers]

    def add_to_recording(self, chunk, timestamps):
        with self.recording_lock:
            for i, timestamp in enumerate(timestamps):
                self.recording_buffer.append({
                    'timestamp': timestamp,
                    'sample': chunk[i, :].tolist()
                })

    def flush_recording_buffer(self):
        with self.recording_lock:
            data = self.recording_buffer.copy()
            self.recording_buffer.clear()
            return data

    def get_gaps(self):
        return self.gaps.copy()
```

---

## Running Tests

### Install Test Dependencies

```bash
pip install pytest pytest-asyncio pytest-cov pytest-timeout
```

### Run All Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=backend --cov-report=html

# Run specific category
pytest tests/thread_safety/
pytest tests/performance/

# Run with verbose output
pytest tests/ -v -s
```

### Continuous Integration

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run tests
        run: pytest tests/ --cov=backend --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Test Coverage Requirements

**Minimum Coverage Targets**:

- Overall: 80%
- Critical modules:
  - `devices/stream.py`: 90%
  - `processing/rate_control.py`: 90%
  - `processing/multi_scale.py`: 85%
  - `session/manager.py`: 80%

**Focus Areas**:
1. Thread safety (all lock-protected code paths)
2. Error handling (all exception branches)
3. Edge cases (empty buffers, disconnections, gaps)
4. Performance (rate compliance under load)

---

## Next Steps

- [Implementation Guide](05-implementation-guide.md) - Build the system
- [Architecture Overview](01-architecture-overview.md) - System design
- [Technical Analysis](TECHNICAL_ANALYSIS.md) - Known issues and solutions

---

**Last updated**: 2025-10-30
