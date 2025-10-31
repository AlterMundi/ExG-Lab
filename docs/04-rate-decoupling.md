# Rate Decoupling

## The Core Principle

**Critical insight**: Pull rate, calculation rate, and UI update rate serve DIFFERENT purposes and should be controlled INDEPENDENTLY.

```python
# WRONG: Coupled rates
while active:
    chunk = inlet.pull_chunk(timeout=0.5)  # Pull every 500ms
    metrics = compute_fft(chunk)            # Calculate every 500ms
    send_to_ui(metrics)                     # Send every 500ms
    # Result: Stale data OR wasted CPU

# RIGHT: Decoupled rates
pull_rate = 20 Hz      # Keep data fresh
calc_rate = 10 Hz      # Limited by CPU
ui_rate = 10 Hz        # Limited by perception/browser
```

## Why Decouple?

### The Three Constraints

Each rate is limited by a DIFFERENT constraint:

**1. Pull Rate → Data Freshness**

```
Constraint: LSL buffer accumulation
Goal: Prevent staleness

Data arrives at 256 Hz (256 samples/second)
If you pull slower than data arrives:
  → Data accumulates in LSL buffer
  → You always process OLDEST data (FIFO!)
  → Feedback lags behind reality

Solution: Pull at 20+ Hz (every 50ms or less)
  → Faster than data arrival
  → Buffer never accumulates
  → Data max 50ms old
```

**2. Calculation Rate → CPU Budget**

```
Constraint: FFT computation time
Goal: Avoid frame drops

Computing 3 timescales × 4 channels × 4 devices:
  → Sequential: ~240ms per calculation
  → Parallel: ~60ms per calculation

If you calculate too fast:
  → CPU can't keep up
  → Computation takes longer than interval
  → Frames dropped

Solution: Match calc_rate to CPU capacity
  → Sequential: max 4 Hz (250ms interval)
  → Parallel: max 16 Hz (62ms interval)
  → Conservative: 10 Hz (100ms interval, plenty of headroom)
```

**3. UI Rate → Human Perception**

```
Constraint: Visual perception + browser rendering
Goal: Smooth without waste

Human perception:
  → 10-15 Hz: Smooth continuous motion
  → 25+ Hz: No perceptible improvement

Browser rendering:
  → Max 60 Hz (monitor refresh)
  → WebSocket overhead: ~2ms per message
  → React re-render: ~5-10ms

Solution: 10-30 Hz is optimal
  → Below 10 Hz: Choppy
  → Above 30 Hz: Wasted bandwidth/CPU
  → Sweet spot: 10-15 Hz
```

### The Coupling Problem

**Scenario 1: Pull rate coupled to calc rate**

```python
# BAD: Calculate on every pull
while active:
    chunk = inlet.pull_chunk(timeout=0.05)  # 20 Hz
    metrics = compute_fft(buffer)            # Takes 60ms!
    send_to_ui(metrics)                      # 20 Hz

# Timeline:
# t=0.00s: Pull (instant)
# t=0.00s: Start FFT
# t=0.06s: FFT done, send to UI
# t=0.05s: SHOULD pull again, but still computing!
# t=0.10s: Pull (late by 50ms)
#
# Result: Data accumulates, defeats purpose of fast pull!
```

**Scenario 2: Pull rate coupled to UI rate**

```python
# BAD: Pull only when UI updates
while active:
    chunk = inlet.pull_chunk(timeout=0.5)  # 2 Hz
    metrics = compute_fft(buffer)          # 2 Hz
    send_to_ui(metrics)                    # 2 Hz

# Timeline:
# t=0.0s: Pull (get 128 samples)
# t=0.5s: Pull (get 128 samples)
# t=1.0s: Pull (get 128 samples)
#
# But data arrives at 256 Hz!
# LSL buffer grows by 128 samples EVERY SECOND
# After 10 seconds: 1280 samples queued (5 seconds of lag!)
#
# Result: Feedback shows brain state from 5 seconds ago!
```

## Decoupled Architecture

### Pattern 1: Time-Based Intervals

```python
import time

class RateControlledLoop:
    def __init__(self, pull_hz=20, calc_hz=10, ui_hz=10):
        self.pull_interval = 1.0 / pull_hz
        self.calc_interval = 1.0 / calc_hz
        self.ui_interval = 1.0 / ui_hz

        self.last_pull = 0
        self.last_calc = 0
        self.last_ui = 0

        self.latest_metrics = None

    def run(self):
        while self.active:
            now = time.time()

            # Pull if interval elapsed
            if now - self.last_pull >= self.pull_interval:
                self.pull_data()
                self.last_pull = now

            # Calculate if interval elapsed
            if now - self.last_calc >= self.calc_interval:
                self.latest_metrics = self.calculate_metrics()
                self.last_calc = now

            # Send if interval elapsed AND metrics available
            if (now - self.last_ui >= self.ui_interval
                and self.latest_metrics is not None):
                self.send_to_ui(self.latest_metrics)
                self.last_ui = now

            # Small sleep to prevent busy-wait
            time.sleep(0.01)  # 100 Hz loop (faster than all rates)

    def pull_data(self):
        chunk, timestamps = self.inlet.pull_chunk(
            timeout=0.0,  # Non-blocking
            max_samples=256
        )
        if timestamps:
            self.buffer.extend(chunk)

    def calculate_metrics(self):
        if len(self.buffer) >= 1024:
            return self.processor.compute_all_timescales()
        return None

    def send_to_ui(self, metrics):
        self.websocket.send_json(metrics)
```

### Pattern 2: Separate Threads (RECOMMENDED)

```python
import threading
import time
from queue import Queue

class ThreadedRateControlledLoop:
    def __init__(self):
        self.buffer = deque(maxlen=1024)
        self.buffer_lock = threading.Lock()

        self.latest_metrics = None
        self.metrics_lock = threading.Lock()

        self.active = False
        self.threads = []

    def pull_loop(self):
        """Pull at 20 Hz in dedicated thread"""
        while self.active:
            try:
                chunk, timestamps = self.inlet.pull_chunk(
                    timeout=0.0,
                    max_samples=256
                )

                if timestamps:
                    with self.buffer_lock:  # Thread-safe
                        self.buffer.extend(chunk)

            except Exception as e:
                print(f"Pull error: {e}")
                time.sleep(1.0)  # Backoff on error

            time.sleep(0.05)  # 20 Hz

    def calc_loop(self):
        """Calculate at 10 Hz in dedicated thread"""
        while self.active:
            try:
                buffer_snapshot = None

                with self.buffer_lock:  # Thread-safe read
                    if len(self.buffer) >= 1024:
                        buffer_snapshot = np.array(self.buffer)

                if buffer_snapshot is not None:
                    metrics = self.processor.compute_all_timescales(buffer_snapshot)

                    with self.metrics_lock:  # Thread-safe write
                        self.latest_metrics = metrics

            except Exception as e:
                print(f"Calc error: {e}")

            time.sleep(0.1)  # 10 Hz

    def ui_loop(self):
        """Send to UI at 10 Hz in dedicated thread"""
        while self.active:
            metrics_copy = None

            with self.metrics_lock:  # Thread-safe read
                if self.latest_metrics is not None:
                    metrics_copy = self.latest_metrics.copy()

            if metrics_copy:
                # Bridge to async WebSocket
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send_json(metrics_copy),
                    self.event_loop
                )

            time.sleep(0.1)  # 10 Hz

    def start(self):
        """Start all threads"""
        self.active = True

        # Create threads
        self.threads = [
            threading.Thread(target=self.pull_loop, daemon=True, name="pull"),
            threading.Thread(target=self.calc_loop, daemon=True, name="calc"),
            threading.Thread(target=self.ui_loop, daemon=True, name="ui")
        ]

        # Start all
        for t in self.threads:
            t.start()

    def stop(self):
        """Stop all threads gracefully"""
        self.active = False
        for t in self.threads:
            t.join(timeout=2.0)
```

**Why This Works**:
- ✅ Each thread runs independently at its own rate
- ✅ Locks prevent race conditions on shared state
- ✅ Error handling prevents one thread from crashing others
- ✅ Clean shutdown with join timeout
- ✅ Compatible with FastAPI's async WebSocket (via run_coroutine_threadsafe)

### Pattern 3: Multi-Device with Threading

```python
import threading
from queue import Queue

class MultiDeviceDecoupledLoop:
    def __init__(self, n_devices=4):
        self.devices = [Device(i) for i in range(n_devices)]

        # Shared queues for communication
        self.calc_queue = Queue()
        self.ui_queue = Queue()

        self.active = True

    def pull_thread(self, device):
        """One thread per device, pulls at 20 Hz"""
        while self.active:
            chunk, timestamps = device.inlet.pull_chunk(
                timeout=0.0,
                max_samples=256
            )

            if timestamps:
                device.buffer.extend(chunk)

                # Signal calc thread that data is ready
                self.calc_queue.put(device.id)

            time.sleep(0.05)  # 20 Hz

    def calc_thread(self):
        """One thread for all calculations, 10 Hz"""
        while self.active:
            # Process all devices that have data
            devices_to_calc = set()

            while not self.calc_queue.empty():
                device_id = self.calc_queue.get()
                devices_to_calc.add(device_id)

            # Calculate metrics for each
            metrics_batch = {}
            for device_id in devices_to_calc:
                device = self.devices[device_id]
                if len(device.buffer) >= 1024:
                    metrics_batch[device_id] = (
                        device.processor.compute_all_timescales()
                    )

            # Send to UI thread
            if metrics_batch:
                self.ui_queue.put(metrics_batch)

            time.sleep(0.1)  # 10 Hz

    def ui_thread(self):
        """One thread for UI updates, 10 Hz"""
        while self.active:
            if not self.ui_queue.empty():
                metrics_batch = self.ui_queue.get()
                self.websocket.send_json(metrics_batch)

            time.sleep(0.1)  # 10 Hz

    def run(self):
        # Start pull threads (one per device)
        for device in self.devices:
            threading.Thread(
                target=self.pull_thread,
                args=(device,),
                daemon=True
            ).start()

        # Start calc thread
        threading.Thread(
            target=self.calc_thread,
            daemon=True
        ).start()

        # Start UI thread
        threading.Thread(
            target=self.ui_thread,
            daemon=True
        ).start()

        # Main thread monitors
        while self.active:
            time.sleep(1.0)
```

## Timing Analysis

### Optimal Rate Combinations

**Conservative (recommended)**:
```
Pull: 20 Hz (50ms interval)
Calc: 10 Hz (100ms interval)
UI:   10 Hz (100ms interval)

Expected behavior:
- Pull: 2 pulls per calc
- Calc: 1 calc per UI update
- Buffer accumulation: None
- CPU usage: ~25% (4 devices, parallel)
- Latency: ~100ms (pull) + 60ms (calc) = 160ms total
```

**Aggressive**:
```
Pull: 50 Hz (20ms interval)
Calc: 25 Hz (40ms interval)
UI:   25 Hz (40ms interval)

Expected behavior:
- Pull: 2 pulls per calc
- Calc: 1 calc per UI update
- Buffer accumulation: None
- CPU usage: ~60% (4 devices, parallel)
- Latency: ~40ms (pull) + 60ms (calc) = 100ms total
```

**Minimal (for limited hardware)**:
```
Pull: 20 Hz (50ms interval)
Calc: 5 Hz (200ms interval)
UI:   5 Hz (200ms interval)

Expected behavior:
- Pull: 4 pulls per calc
- Calc: 1 calc per UI update
- Buffer accumulation: None (pull still faster than data)
- CPU usage: ~10% (4 devices, parallel)
- Latency: ~100ms (pull) + 60ms (calc) = 160ms total
```

### Performance Monitoring

```python
class PerformanceMonitor:
    def __init__(self):
        self.pull_times = deque(maxlen=100)
        self.calc_times = deque(maxlen=100)
        self.ui_times = deque(maxlen=100)

    def record_pull(self, duration):
        self.pull_times.append(duration)

    def record_calc(self, duration):
        self.calc_times.append(duration)

    def record_ui(self, duration):
        self.ui_times.append(duration)

    def get_stats(self):
        return {
            'pull': {
                'mean': np.mean(self.pull_times),
                'max': np.max(self.pull_times),
                'p95': np.percentile(self.pull_times, 95)
            },
            'calc': {
                'mean': np.mean(self.calc_times),
                'max': np.max(self.calc_times),
                'p95': np.percentile(self.calc_times, 95)
            },
            'ui': {
                'mean': np.mean(self.ui_times),
                'max': np.max(self.ui_times),
                'p95': np.percentile(self.ui_times, 95)
            }
        }

# Usage in loop
monitor = PerformanceMonitor()

# In pull_data():
start = time.time()
chunk, timestamps = inlet.pull_chunk(...)
monitor.record_pull(time.time() - start)

# In calculate_metrics():
start = time.time()
metrics = processor.compute_all_timescales()
monitor.record_calc(time.time() - start)

# In send_to_ui():
start = time.time()
websocket.send_json(metrics)
monitor.record_ui(time.time() - start)

# Periodically check stats
stats = monitor.get_stats()
print(f"Calc p95: {stats['calc']['p95']*1000:.1f}ms")

# Adaptive rate adjustment
if stats['calc']['p95'] > 0.08:  # >80ms
    # Calc taking too long, reduce rate
    calc_rate = max(5, calc_rate - 1)
```

### Adaptive Rate Control

```python
class AdaptiveRateController:
    def __init__(self, target_calc_time=0.06):
        self.calc_rate = 10  # Start conservative
        self.target_calc_time = target_calc_time

        self.recent_calc_times = deque(maxlen=50)

    def update_calc_time(self, duration):
        self.recent_calc_times.append(duration)

        # Every 50 calculations, adjust rate
        if len(self.recent_calc_times) == 50:
            p95 = np.percentile(self.recent_calc_times, 95)

            if p95 < self.target_calc_time * 0.8:
                # Plenty of headroom, increase rate
                self.calc_rate = min(30, self.calc_rate + 1)
                print(f"Increasing calc_rate to {self.calc_rate} Hz")

            elif p95 > self.target_calc_time * 1.2:
                # Too slow, decrease rate
                self.calc_rate = max(5, self.calc_rate - 1)
                print(f"Decreasing calc_rate to {self.calc_rate} Hz")

            self.recent_calc_times.clear()

    def get_calc_interval(self):
        return 1.0 / self.calc_rate

# Usage
controller = AdaptiveRateController(target_calc_time=0.06)

while active:
    if time_for_calc():
        start = time.time()
        metrics = calculate_metrics()
        duration = time.time() - start

        controller.update_calc_time(duration)

        # Use updated interval
        calc_interval = controller.get_calc_interval()
```

## Common Pitfalls

### Pitfall 1: Blocking Pull

```python
# WRONG: Blocking pull couples rates
chunk, timestamps = inlet.pull_chunk(timeout=1.0)  # Waits up to 1s!

# If data not available:
#   - calc_loop waits
#   - ui_loop waits
#   - Everything coupled again!

# RIGHT: Non-blocking pull
chunk, timestamps = inlet.pull_chunk(timeout=0.0)  # Returns immediately

if timestamps:
    # Data available, process it
    buffer.extend(chunk)
# else:
    # No data, continue to calc/ui loops anyway
```

### Pitfall 2: Calculating Without Enough Data

```python
# WRONG: Calculate even with partial buffer
def calculate_metrics(self):
    return processor.compute_all_timescales()  # Might fail!

# RIGHT: Check buffer size first
def calculate_metrics(self):
    if len(self.buffer) >= 1024:  # Enough for 4s window
        return processor.compute_all_timescales()
    return None  # Signal not ready yet
```

### Pitfall 3: Busy-Wait

```python
# WRONG: No sleep, burns CPU
while active:
    if time_for_pull():
        pull_data()
    if time_for_calc():
        calculate_metrics()
    if time_for_ui():
        send_to_ui()
    # No sleep! CPU at 100%

# RIGHT: Small sleep between checks
while active:
    if time_for_pull():
        pull_data()
    if time_for_calc():
        calculate_metrics()
    if time_for_ui():
        send_to_ui()

    time.sleep(0.01)  # 100 Hz check rate (faster than all operations)
    # CPU usage: <5% for loop overhead
```

### Pitfall 4: Stale Metrics

```python
# WRONG: Send old metrics if no new calc
if time_for_ui():
    send_to_ui(self.latest_metrics)  # Might be outdated!

# RIGHT: Track metric age
class MetricsCache:
    def __init__(self, max_age=0.5):
        self.metrics = None
        self.timestamp = 0
        self.max_age = max_age

    def update(self, metrics):
        self.metrics = metrics
        self.timestamp = time.time()

    def get_if_fresh(self):
        if self.metrics is None:
            return None

        age = time.time() - self.timestamp
        if age > self.max_age:
            return None  # Too old

        return self.metrics

# Usage
cache = MetricsCache(max_age=0.5)  # 500ms max age

# In calc loop:
metrics = calculate_metrics()
cache.update(metrics)

# In UI loop:
metrics = cache.get_if_fresh()
if metrics is not None:
    send_to_ui(metrics)
# else: skip this UI update, wait for fresh calc
```

## Production Implementation

### Complete Example

```python
import time
import threading
from collections import deque
from queue import Queue
import numpy as np

class ProductionFeedbackSystem:
    def __init__(self,
                 n_devices=4,
                 pull_hz=20,
                 calc_hz=10,
                 ui_hz=10):

        self.n_devices = n_devices
        self.pull_interval = 1.0 / pull_hz
        self.calc_interval = 1.0 / calc_hz
        self.ui_interval = 1.0 / ui_hz

        # Device setup
        self.devices = self._initialize_devices()

        # Metrics cache
        self.latest_metrics = {}
        self.metrics_lock = threading.Lock()

        # Control
        self.active = False

        # Performance monitoring
        self.monitor = PerformanceMonitor()

    def _initialize_devices(self):
        """Set up LSL connections and processors"""
        devices = []

        for i in range(self.n_devices):
            streams = resolve_stream('name', f'Muse_{i+1}')
            inlet = StreamInlet(streams[0], max_buflen=360)

            # Flush accumulated data
            flush_inlet_buffer(inlet)

            device = {
                'id': i,
                'name': f'Muse_{i+1}',
                'inlet': inlet,
                'buffer': deque(maxlen=1024),
                'processor': MultiScaleProcessor()
            }

            devices.append(device)

        return devices

    def pull_thread_func(self, device):
        """Pull loop for one device"""
        last_pull = time.time()

        while self.active:
            now = time.time()

            if now - last_pull >= self.pull_interval:
                start = time.time()

                chunk, timestamps = device['inlet'].pull_chunk(
                    timeout=0.0,
                    max_samples=256
                )

                if timestamps:
                    device['buffer'].extend(chunk)

                self.monitor.record_pull(time.time() - start)
                last_pull = now

            time.sleep(0.01)

    def calc_thread_func(self):
        """Calculation loop for all devices"""
        last_calc = time.time()

        while self.active:
            now = time.time()

            if now - last_calc >= self.calc_interval:
                start = time.time()

                batch_metrics = {}

                for device in self.devices:
                    if len(device['buffer']) >= 1024:
                        device['processor'].buffer = device['buffer']
                        metrics = device['processor'].compute_all_timescales()

                        if metrics:
                            batch_metrics[device['name']] = metrics

                # Update cache (thread-safe)
                with self.metrics_lock:
                    self.latest_metrics = batch_metrics

                self.monitor.record_calc(time.time() - start)
                last_calc = now

            time.sleep(0.01)

    def ui_thread_func(self):
        """UI update loop"""
        last_ui = time.time()

        while self.active:
            now = time.time()

            if now - last_ui >= self.ui_interval:
                start = time.time()

                # Get metrics (thread-safe)
                with self.metrics_lock:
                    metrics = self.latest_metrics.copy()

                if metrics:
                    self.send_to_ui(metrics)

                self.monitor.record_ui(time.time() - start)
                last_ui = now

            time.sleep(0.01)

    def send_to_ui(self, metrics):
        """Send metrics to WebSocket"""
        # Format for frontend
        payload = {
            'timestamp': time.time(),
            'devices': metrics
        }

        self.websocket.send_json(payload)

    def start(self):
        """Start all threads"""
        self.active = True

        # One pull thread per device
        for device in self.devices:
            threading.Thread(
                target=self.pull_thread_func,
                args=(device,),
                daemon=True
            ).start()

        # Single calc thread
        threading.Thread(
            target=self.calc_thread_func,
            daemon=True
        ).start()

        # Single UI thread
        threading.Thread(
            target=self.ui_thread_func,
            daemon=True
        ).start()

        print(f"Started {self.n_devices} pull threads + calc + UI")

    def stop(self):
        """Stop all threads"""
        self.active = False

    def get_performance_stats(self):
        """Get performance statistics"""
        return self.monitor.get_stats()

# Usage
system = ProductionFeedbackSystem(
    n_devices=4,
    pull_hz=20,
    calc_hz=10,
    ui_hz=10
)

system.start()

# Monitor performance
while running:
    time.sleep(10)
    stats = system.get_performance_stats()
    print(f"Calc p95: {stats['calc']['p95']*1000:.1f}ms")

system.stop()
```

## Next Steps

- [Implementation Guide](05-implementation-guide.md) - Complete code examples
- [UI Design Guide](06-ui-design.md) - Frontend implementation
- [LSL Buffering Deep-Dive](02-lsl-buffering-deep-dive.md) - Why pull rate matters

---

**Last updated**: 2025-10-30
