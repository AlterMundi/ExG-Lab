# LSL Buffering Deep-Dive

## The Critical Challenge

**The single most important insight about LSL for real-time feedback:**

> `pull_chunk()` returns **OLDEST** unread data, not newest!

This FIFO (First In, First Out) behavior is perfect for reliable data capture but creates challenges for real-time feedback. Understanding this is essential for building responsive systems.

## LSL Buffer Mechanics

### Buffer Structure

LSL maintains a **circular buffer** for each StreamInlet:

```
StreamInlet creation:
inlet = StreamInlet(stream_info, max_buflen=360)
                                    ↑
                    Buffer capacity: 360 seconds

Memory usage (Muse @ 256 Hz, 4 channels):
- Capacity: 360s × 256 samples/s = 92,160 samples
- Memory: 92,160 × 4 ch × 4 bytes = 1.47 MB
- Plus timestamps: 92,160 × 8 bytes = 0.74 MB
- Total per device: ~2.2 MB
```

**Key point**: Buffer size is NOT data age! It's just capacity.

### FIFO Behavior Explained

When data arrives from muselsl:

```python
t=0.0s: Stream starts
        LSL buffer: [empty]

t=1.0s: 256 samples arrive (sample IDs 0-255)
        LSL buffer: [0, 1, 2, ..., 255]
        Age: 0-1s old

t=2.0s: 256 more samples arrive (IDs 256-511)
        LSL buffer: [0, 1, ..., 255, 256, 257, ..., 511]
                     ^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^
                     2 seconds old   1 second old

t=2.0s: YOU CALL pull_chunk(max_samples=256)
        Returns: [0, 1, ..., 255]  ← OLDEST samples!
        LSL buffer now: [256, 257, ..., 511]

t=3.0s: 256 more arrive (IDs 512-767)
        LSL buffer: [256, ..., 511, 512, ..., 767]
                     ^^^^^^^^^^^^^  ^^^^^^^^^^^^^^
                     2s old         fresh

t=3.0s: YOU CALL pull_chunk(max_samples=256)
        Returns: [256, ..., 511]  ← STILL 1-2 seconds old!
```

**Problem**: If you pull slower than data arrives, you always process stale data.

### Why This Happens

LSL is designed for **reliable capture**, not **real-time display**:

✅ **Guarantees**:
- No data loss
- Correct temporal order
- Each sample processed exactly once

❌ **Consequences**:
- If you fall behind, data accumulates
- Can't "skip ahead" to latest samples
- Buffer acts as queue, not sliding window

## The Staleness Problem

### Scenario: Slow Pull Rate

```python
# BAD: Pull every 500ms
while feedback_active:
    chunk, timestamps = inlet.pull_chunk(timeout=0.5, max_samples=256)
    buffer.extend(chunk)

    metrics = compute_fft(buffer)
    send_to_ui(metrics)

# Timeline:
# t=0.0s: Flush buffer, start fresh
# t=0.5s: Pull 128 samples (samples from t=0.0-0.5s) ✓ fresh
# t=1.0s: Pull 128 samples (samples from t=0.5-1.0s) ✓ fresh
# t=1.5s: Pull 128 samples (samples from t=1.0-1.5s) ✓ fresh
#
# But what if FFT computation takes 100ms?
# t=2.0s: Still processing previous chunk!
#         256 samples accumulate in LSL buffer
# t=2.1s: Finally pull - get samples from t=1.5-2.0s
#         But we're now 100ms behind!
# t=2.6s: Pull again - get samples from t=2.0-2.5s
#         Still 100ms behind + accumulating...
#
# Result: Permanent 100-500ms lag!
```

### Scenario: Initial Accumulation

```python
# WORSE: Starting feedback without flushing

# t=0.0s: Start muselsl stream
# t=0.0-5.0s: User sets up experiment (5 seconds)
#             LSL buffer accumulates: 1280 samples!
#
# t=5.0s: Start feedback loop
#         Pull returns: samples from t=0.0-1.0s
#         These are 5 SECONDS OLD!
#
# User relaxes NOW but sees feedback from 5 seconds ago
# → Completely useless for neurofeedback!
```

## Solutions

### Solution 1: Flush Buffer Before Feedback

**Always do this before starting real-time feedback:**

```python
def flush_inlet_buffer(inlet):
    """Discard all accumulated data"""
    total_flushed = 0
    while True:
        chunk, timestamps = inlet.pull_chunk(
            timeout=0.0,  # Non-blocking
            max_samples=1000
        )
        if not timestamps:
            break  # No more data
        total_flushed += len(timestamps)

    print(f"Flushed {total_flushed} samples")
    return total_flushed

# Usage:
inlet = StreamInlet(streams[0], max_buflen=360)
time.sleep(1.0)  # Let some data accumulate
flush_inlet_buffer(inlet)  # Throw it away!

# NOW start feedback - next pull gets fresh data
```

**When to flush**:
- ✅ Before starting real-time feedback
- ✅ When switching from idle to active
- ✅ After long pauses (>1 second)
- ❌ During continuous recording (you'd lose data!)

### Solution 2: Pull Faster Than Data Arrives

**Prevent accumulation in the first place:**

```python
# Data arrives at 256 Hz = 256 samples/second
# Pull at 20 Hz = every 50ms
# Each pull gets 256/20 = 12-13 samples

# This prevents ANY accumulation!

while feedback_active:
    # Pull with short timeout (or 0.0 for non-blocking)
    chunk, timestamps = inlet.pull_chunk(
        timeout=0.05,  # 50ms max wait
        max_samples=128  # Up to 500ms of data
    )

    if timestamps:
        buffer.extend(chunk)

    # Calculate metrics at slower rate
    if time_for_update():
        metrics = compute_fft(buffer)

    time.sleep(0.01)  # 10ms sleep = 100 Hz loop

# Result: Data max 50ms old (fresh!)
```

**Key ratios**:
```
Pull rate > Data rate → Fresh data ✓
Pull rate < Data rate → Stale data ✗

Recommended:
Data rate: 256 samples/s
Pull rate: 20 Hz (or higher)
Ratio: 20 Hz > 256/20 = 12.8 samples/pull
```

### Solution 3: Timestamp-Based Filtering

**Most robust - handles variable delays:**

```python
from pylsl import local_clock

def get_latest_data(inlet, duration=2.0):
    """
    Get only the last N seconds of data
    Discards older samples even if unread
    """
    # Pull ALL available data
    all_chunks, all_timestamps = inlet.pull_chunk(
        timeout=0.0,
        max_samples=10000  # Pull everything
    )

    if not all_timestamps:
        return None, None

    # Get current LSL time
    now = local_clock()
    cutoff = now - duration

    # Filter by timestamp
    recent_samples = []
    recent_timestamps = []

    for i, ts in enumerate(all_timestamps):
        if ts >= cutoff:
            recent_samples.append(all_chunks[i])
            recent_timestamps.append(ts)

    if recent_samples:
        return np.array(recent_samples), np.array(recent_timestamps)
    else:
        return None, None

# Usage:
while feedback_active:
    data, timestamps = get_latest_data(inlet, duration=2.0)

    if data is not None and len(data) >= 512:
        # Guaranteed to be < 2 seconds old!
        metrics = compute_fft(data[-512:])  # Last 512 samples
        send_to_ui(metrics)

    time.sleep(0.5)  # Can be slower - timestamp filter handles it
```

**Advantages**:
- ✅ Guaranteed fresh data
- ✅ Handles variable processing times
- ✅ Auto-recovers from temporary slowdowns

**Disadvantages**:
- ⚠️ Wastes CPU pulling data you'll discard
- ⚠️ Might discard data if recording simultaneously

### Solution 4: Dual Buffer Strategy (RECOMMENDED for dual-mode)

**For simultaneous recording + feedback:**

```python
# Separate concerns completely

# RECORDING: Save everything (FIFO is fine)
recording_buffer = []

# FEEDBACK: Rolling window (latest only)
feedback_buffer = deque(maxlen=1024)  # 4 seconds

while session_active:
    # Pull data
    chunk, timestamps = inlet.pull_chunk(
        timeout=0.05,
        max_samples=256
    )

    if timestamps:
        # RECORDING: Append all (no loss)
        recording_buffer.extend(zip(chunk, timestamps))

        # FEEDBACK: Add to rolling window (old drops off)
        for sample in chunk:
            feedback_buffer.append(sample)

    # Calculate feedback from rolling window
    if len(feedback_buffer) >= 512:
        metrics = compute_fft(np.array(feedback_buffer))
        send_to_ui(metrics)

    # Save recording periodically
    if time_to_save():
        save_to_disk(recording_buffer)
        recording_buffer.clear()
```

**Perfect separation**:
- Recording: FIFO queue (reliable)
- Feedback: Rolling window (fresh)

## Common Pitfalls

### Pitfall 1: Reducing Buffer Size

**Misconception**: "Small buffer = fresh data"

```python
# WRONG: This doesn't help!
inlet = StreamInlet(streams[0], max_buflen=5)  # Only 5 seconds

# What actually happens:
# t=0-5s: Buffer fills to capacity
# t=6s: New data arrives, OLDEST data DROPPED
#       You LOSE data from t=0-1s permanently!

# Data age is STILL determined by pull rate, not buffer size!
```

**Truth**: Buffer size is capacity, not age limit.

### Pitfall 2: Assuming max_chunklen Helps

**Misconception**: "Small max_chunklen = low latency"

```python
# WRONG: This just limits pull size
inlet = StreamInlet(streams[0], max_chunklen=12)

# This means:
# - Can only get 12 samples per pull (46ms @ 256 Hz)
# - Need 21 pulls to get 1 second of data
# - If you pull once per 500ms, you're missing data!

# Latency is NOT improved - just made data loss more likely!
```

**Truth**: max_chunklen limits throughput, not latency.

### Pitfall 3: Coupling Pull and Calculate Rates

**Misconception**: "Must calculate every time I pull"

```python
# INEFFICIENT: Wastes CPU or gets stale data
while True:
    chunk = inlet.pull_chunk(timeout=0.5)  # Pull every 500ms
    metrics = compute_fft(buffer)  # Takes 10ms
    # CPU idle 98% of time!

# OR:

while True:
    chunk = inlet.pull_chunk(timeout=0.01)  # Pull every 10ms
    metrics = compute_fft(buffer)  # Calculate every 10ms
    # Calculating 100x/sec when 10x/sec is enough!
```

**Truth**: Pull rate and calc rate are independent (see [Rate Decoupling](04-rate-decoupling.md)).

## Recording vs Feedback

### For Recording ONLY

```python
# FIFO is perfect - never flush!

inlet = StreamInlet(streams[0], max_buflen=360)
# No flushing!

recording = []

while session_active:
    chunk, timestamps = inlet.pull_chunk(
        timeout=1.0,
        max_samples=512
    )

    if timestamps:
        recording.extend(zip(chunk, timestamps))

    time.sleep(0.25)  # Pull 4x/sec (plenty fast enough)

# Result: All data captured, none lost
```

**FIFO guarantees**: Every sample saved exactly once in correct order.

### For Feedback ONLY

```python
# FIFO is a problem - must flush!

inlet = StreamInlet(streams[0], max_buflen=360)

# CRITICAL: Flush before starting
time.sleep(1.0)
flush_inlet_buffer(inlet)

buffer = deque(maxlen=1024)

while session_active:
    # Pull fast to prevent accumulation
    chunk, timestamps = inlet.pull_chunk(timeout=0.05, max_samples=256)

    if timestamps:
        buffer.extend(chunk)

    # Calculate at slower rate
    if len(buffer) >= 512:
        metrics = compute_fft(buffer)
        send_to_ui(metrics)

    time.sleep(0.01)  # 100 Hz loop

# Result: Fresh data (< 50ms old)
```

### For BOTH (Dual-Mode)

```python
# Best of both worlds

inlet = StreamInlet(streams[0], max_buflen=360)

# FLUSH before starting (discard startup data)
time.sleep(1.0)
flush_inlet_buffer(inlet)

# Separate buffers
recording_buffer = []
feedback_buffer = deque(maxlen=1024)

while session_active:
    chunk, timestamps = inlet.pull_chunk(timeout=0.05, max_samples=256)

    if timestamps:
        # RECORDING: Save all
        recording_buffer.extend(zip(chunk, timestamps))

        # FEEDBACK: Rolling window
        feedback_buffer.extend(chunk)

    # Calculate feedback
    if len(feedback_buffer) >= 512:
        metrics = compute_fft(feedback_buffer)
        send_to_ui(metrics)

    # Save recording periodically
    if len(recording_buffer) > 5000:  # Every ~20 seconds
        save_to_disk(recording_buffer)
        recording_buffer.clear()

# Result:
# - Recording: All data saved ✓
# - Feedback: Fresh data (< 50ms) ✓
```

## Performance Implications

### Latency Components

```
Total latency = Acquisition + Buffering + Processing + Display

Acquisition (fixed):
  Muse sampling:     ~4ms (256 Hz)
  Bluetooth:         ~20ms (BLE)
  muselsl:           ~5ms
  LSL publish:       ~1ms
  Subtotal:          ~30ms (deterministic)

Buffering (YOUR control):
  LSL queue time:    0-Xms (depends on pull rate)

  Pull every 50ms → queue time: 0-50ms (avg 25ms)
  Pull every 500ms → queue time: 0-500ms (avg 250ms!)

Processing (YOUR control):
  FFT computation:   ~10ms (scipy)

Display (fixed):
  WebSocket:         ~2ms (localhost)
  Browser render:    ~16ms (60 Hz)
  Subtotal:          ~18ms

TOTAL LATENCY:
  Optimal (pull 50ms):  30 + 25 + 10 + 18 = ~83ms
  Typical (pull 100ms): 30 + 50 + 10 + 18 = ~108ms
  Slow (pull 500ms):    30 + 250 + 10 + 18 = ~308ms
```

**Optimization target**: Keep pull-induced latency < 50ms.

### Memory Usage

```
LSL buffer (per device):
  Default (360s):    ~2.2 MB
  Conservative (60s): ~370 KB
  Minimal (10s):     ~62 KB

Rolling buffer (per device):
  4s window (1024 samples): ~16 KB

Total for 4 devices:
  LSL: 4 × 2.2 MB = 8.8 MB
  Rolling: 4 × 16 KB = 64 KB
  Total: < 10 MB (negligible)
```

**Takeaway**: Memory is not a concern. Use large LSL buffers for safety.

## Recommendations

### Conservative (Recommended)

```python
# Reliable, fresh data with headroom

inlet = StreamInlet(streams[0], max_buflen=360)  # Large for safety
flush_inlet_buffer(inlet)  # Start fresh

pull_rate = 20 Hz  # Every 50ms
calc_rate = 10 Hz  # Every 100ms

# Expected latency: ~80-110ms
# CPU usage: ~15-25%
```

### Aggressive (Maximum Performance)

```python
# Minimum latency, higher CPU

inlet = StreamInlet(streams[0], max_buflen=360)
flush_inlet_buffer(inlet)

pull_rate = 50 Hz  # Every 20ms
calc_rate = 25 Hz  # Every 40ms

# Expected latency: ~60-80ms
# CPU usage: ~40-60%
```

### Which to choose?

**Use conservative unless**:
- Neurofeedback requires <100ms latency
- You have CPU headroom to spare
- UI needs >10 Hz update rate

For most meditation/relaxation experiments: **Conservative is perfect**.

## Next Steps

- [Multi-Timescale Feedback](03-multi-timescale-feedback.md) - Using this fresh data wisely
- [Rate Decoupling](04-rate-decoupling.md) - Independent pull/calc/UI rates
- [Implementation Guide](05-implementation-guide.md) - Practical code patterns

---

**Last updated**: 2025-10-30
