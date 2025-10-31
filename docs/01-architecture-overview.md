# Architecture Overview

## System Design Philosophy

ExG-Lab is built on three core principles:

1. **Reliability First**: Never lose data - recording takes priority
2. **Freshness Second**: Real-time feedback requires fresh data
3. **Scalability Third**: Design scales from 2 to 4+ devices

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Browser (Frontend)                   │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐  │
│  │ Device Panel │  │ Live Monitor│  │ Feedback Display │  │
│  │  + Connect   │  │ + EEG Viz   │  │ + 3 Timescales   │  │
│  │  + Status    │  │ + Quality   │  │ + Trends         │  │
│  └──────────────┘  └─────────────┘  └──────────────────┘  │
│                                                             │
│  WebSocket ←→ Real-time metrics (10-30 Hz)                 │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│              Python Backend (FastAPI + WebSocket)           │
│                                                             │
│  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Device Manager│→ │ LSL Receiver │→ │ Multi-Scale    │  │
│  │  - Scan       │  │  - 4 inlets  │  │ Processor      │  │
│  │  - Connect    │  │  - Buffers   │  │  - FFT 1s/2s/4s│  │
│  │  - Monitor    │  │  - Sync      │  │  - Band Powers │  │
│  └───────────────┘  └──────────────┘  └────────────────┘  │
│                            ↓                ↓               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Session Manager & Storage                    │  │
│  │  - Recording control  - CSV export  - Metadata       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    LSL Streams (muselsl)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Muse 1   │  │ Muse 2   │  │ Muse 3   │  │ Muse 4   │  │
│  │ (stream) │  │ (stream) │  │ (stream) │  │ (stream) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                    ↓ LSL network layer ↓                    │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                      Physical Devices                       │
│     Muse 1     Muse 2     Muse 3     Muse 4                │
│       ↓          ↓          ↓          ↓                    │
│   Bluetooth  Bluetooth  Bluetooth  Bluetooth               │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Acquisition Layer (Physical → LSL)

**Components**:
- Muse hardware: Samples EEG at 256 Hz
- Bluetooth transmission: ~10-50ms latency
- muselsl process: Publishes to LSL network

**Key points**:
- Each Muse runs as independent `muselsl stream` subprocess
- LSL maintains 360-second circular buffers (configurable)
- Streams are named for easy identification (`Muse_1`, `Muse_2`, etc.)

### 2. Processing Layer (LSL → Metrics)

**Components**:
- `StreamInlet`: Connects to each LSL stream
- `MultiScaleProcessor`: Computes FFT at 3 timescales
- Rolling buffers: 4-second windows per device

**Data pipeline**:
```python
LSL stream (256 Hz)
  ↓ pull_chunk() at 20 Hz
Rolling buffer (1024 samples = 4 seconds)
  ↓ Extract windows
  ├─ Last 256 samples  → FFT → 1s metrics
  ├─ Last 512 samples  → FFT → 2s metrics
  └─ Last 1024 samples → FFT → 4s metrics
  ↓
Band powers (delta, theta, alpha, beta, gamma)
  ↓
Relaxation indices (alpha/beta ratios)
  ↓
WebSocket to frontend
```

**Critical design**:
- **Single buffer** serves all three timescales (memory efficient)
- **Decoupled rates**: Pull (20 Hz) ≠ Calculate (10 Hz) ≠ UI (10 Hz)
- **Non-blocking pulls**: Never wait for data

### 3. Storage Layer (Parallel Recording)

**Components**:
- Separate recording buffers per device
- Continuous save every 5 seconds
- CSV format with timestamps

**Recording flow**:
```python
While session active:
  1. Pull data from LSL
  2. Append to recording buffer (ALL data)
  3. Add to rolling window (for feedback)
  4. Every 5s: Flush buffer to disk

On session end:
  - Final save of remaining data
  - Generate metadata JSON
  - Export summary statistics
```

**Key guarantee**: Recording happens BEFORE feedback processing - never lose data.

### 4. Communication Layer (Backend → Frontend)

**Protocol**: WebSocket (bidirectional)

**Message types**:

```typescript
// Backend → Frontend (10-30 Hz)
{
  type: 'feedback_update',
  timestamp: 1698765432.123,
  devices: {
    'Muse_1': {
      subject: 'Alice',
      relaxation: {
        '1s': 2.34,  // Fast metric
        '2s': 1.87,  // Balanced metric
        '4s': 1.65   // Stable metric
      },
      quality: {
        data_age_ms: 45,      // Latency check
        signal_quality: {...} // Per-channel
      }
    },
    // ... more devices
  }
}

// Frontend → Backend (on-demand)
{
  type: 'start_session',
  config: {
    duration: 540,
    devices: ['Muse_1', 'Muse_2'],
    protocol: 'meditation'
  }
}
```

## Component Responsibilities

### Device Manager

**Purpose**: Handle Muse discovery, connection, status

**Key functions**:
```python
def scan_devices() -> List[Dict]:
    """Use muselsl list (with bugfixes!) to find devices"""

def connect_device(mac_address: str, stream_name: str):
    """Start muselsl stream as subprocess"""

def get_device_status(stream_name: str) -> Dict:
    """Battery, signal quality, connection state"""
```

**Implementation note**: Uses subprocess approach for isolation - one device crash doesn't kill others.

### LSL Receiver

**Purpose**: Manage StreamInlets and buffer data

**Critical behavior**:
- **FIFO**: `pull_chunk()` returns oldest unread data
- **Must flush before feedback**: Discard accumulated startup data
- **Pull rate > data rate**: Prevent staleness

**Key functions**:
```python
def flush_inlet_buffer(inlet):
    """Empty LSL buffer before starting feedback"""
    while True:
        chunk, _ = inlet.pull_chunk(timeout=0.0, max_samples=1000)
        if not chunk:
            break

def pull_latest(inlet, duration=2.0):
    """Get last N seconds using timestamps"""
    # See docs/02-lsl-buffering-deep-dive.md
```

### Multi-Scale Processor

**Purpose**: Compute FFT at three timescales from single buffer

**Window sizes**:
- 1s = 256 samples → Δf = 1.0 Hz (fast, noisy)
- 2s = 512 samples → Δf = 0.5 Hz (balanced)
- 4s = 1024 samples → Δf = 0.25 Hz (stable)

**Performance** (per device, 4 channels):
- Single-device: 3 timescales × ~15ms = ~45ms total
- Target calc rate: 10 Hz (100ms budget) ✓ achievable

**Multi-device scaling**:
- Sequential (1→2→3→4): 4 × 45ms = **180ms** ❌ exceeds budget!
- Parallel (ThreadPoolExecutor): max(45ms) = **45ms** ✓ within budget
- **Conclusion**: Threading is MANDATORY for 2+ devices, not optional

**Key optimization**: Can't reuse FFT between windows (different sizes), but CAN reuse filtered data and same buffer.

### Session Manager

**Purpose**: Coordinate recording, phases, markers

**State machine**:
```
IDLE → CONNECTING → FLUSHING → RECORDING → SAVING → IDLE
```

**Features**:
- Protocol phases with auto-transitions
- Manual event markers
- Metadata collection (participants, date, config)

## System Modes

### Mode 1: Recording Only

```python
is_recording = True
is_feedback_active = False

while session_active:
    chunk = pull_from_lsl()
    save_to_file(chunk)  # That's it!
```

**Use case**: Pure data collection
**Pros**: Simple, no CPU overhead
**Cons**: Participants get no feedback

### Mode 2: Feedback Only

```python
is_recording = False
is_feedback_active = True

flush_buffers()  # Critical!

while session_active:
    chunk = pull_from_lsl()
    update_rolling_buffer(chunk)
    metrics = compute_fft(buffer)
    send_to_ui(metrics)
```

**Use case**: Training sessions
**Pros**: No disk I/O overhead
**Cons**: Data not saved

### Mode 3: Dual Mode (RECOMMENDED)

```python
is_recording = True
is_feedback_active = True

flush_buffers()  # Still needed!

while session_active:
    chunk = pull_from_lsl()

    # Recording: save everything
    save_to_file(chunk)

    # Feedback: update rolling window
    update_rolling_buffer(chunk)
    if time_for_update():
        metrics = compute_fft(buffer)
        send_to_ui(metrics)
```

**Use case**: Research experiments (our target)
**Pros**: Best of both worlds
**Cons**: Slightly more CPU

## Performance Characteristics

### Latency Budget

**IMPORTANT**: Distinguish between **processing latency** (how long to compute) and **window delay** (how much data averaging):

**Processing Latency** (hardware + software):
```
Brain activity happens (t=0)
  ↓ ~4ms    (Muse sampling at 256 Hz)
Bluetooth transmission
  ↓ ~20ms   (BLE inherent latency)
muselsl receives
  ↓ ~5ms    (processing + LSL publish)
LSL buffer wait
  ↓ 0-50ms  (avg 25ms @ 20 Hz pull rate)
Backend pulls data
  ↓ ~1ms    (memory copy)
Rolling buffer update
  ↓ ~1ms    (thread-safe append)
Wait for calc cycle
  ↓ 0-100ms (avg 50ms @ 10 Hz calc rate)
FFT computation
  ↓ ~45ms   (parallel, 4 devices)
WebSocket send
  ↓ ~2ms    (localhost)
Browser render
  ↓ ~16ms   (60 Hz display)

Total Processing Latency: ~70-270ms (avg ~170ms)
```

**Window Delay** (data averaging period):
- 1s window: shows state averaged over last 1000ms (center: 500ms ago)
- 2s window: shows state averaged over last 2000ms (center: 1000ms ago)
- 4s window: shows state averaged over last 4000ms (center: 2000ms ago)

**Total Perceptual Delay** (processing + window center):
- 1s metric: ~170ms + 500ms = **~670ms** behind brain activity
- 2s metric: ~170ms + 1000ms = **~1170ms** behind brain activity
- 4s metric: ~170ms + 2000ms = **~2170ms** behind brain activity

**Note**: This is expected and intentional - longer windows provide stability at cost of responsiveness.

### Throughput

**Data rates** (per device):
- Input: 256 samples/sec × 4 channels × 4 bytes = 4 KB/s
- 4 devices: 16 KB/s total

**Processing rates**:
- Pull: 20 Hz = 50ms interval
- Calculate: 10-25 Hz = 40-100ms interval
- UI: 10-30 Hz = 33-100ms interval

**Resource usage** (4 devices):
- CPU: 10-60% (depending on calc_rate; parallel processing required for 4 devices)
- RAM: ~100-200 MB total (including LSL buffers and processing overhead)
- Network: ~5 KB/s (processed metrics only, not raw data)

## Design Decisions Rationale

### Why subprocess for muselsl streams?

**Considered**:
- Option A: Direct Python API (import muselsl)
- Option B: Subprocess wrapper

**Chose B because**:
- Process isolation: one device crash doesn't kill others
- Easier to restart individual streams
- Matches muselsl's design (CLI-first)

### Why 4-second buffer?

**Need longest window**: 4s for stable metrics
**Could use shorter?** Yes, but wastes opportunity
**Could use longer?** Diminishing returns above 4s

**Sweet spot**: 4s window gives 0.25 Hz resolution, excellent for alpha band separation.

### Why three timescales specifically?

**1 second**:
- Resolution: 1 Hz (minimum for alpha/beta separation)
- Update lag: ~500ms
- Shows immediate actions

**2 seconds**:
- Resolution: 0.5 Hz (good alpha detail)
- Update lag: ~1000ms
- Best balance for training

**4 seconds**:
- Resolution: 0.25 Hz (excellent detail)
- Update lag: ~2000ms
- Confirms sustained changes

**Why not more?** Diminishing returns + UI clutter

### Why decouple pull/calc/UI rates?

**Critical insight**: These serve different purposes!

- **Pull rate**: Prevents LSL buffer accumulation (freshness) - must be ≥20 Hz
- **Calc rate**: Limited by CPU (performance) - 10 Hz with parallel threading
- **UI rate**: Limited by human perception (UX) - 10 Hz is smooth

Coupling them wastes either CPU (too fast calc) or freshness (too slow pull).

**Threading Model Requirements**:
1. **Pure threading** (not async/await) - pylsl's `pull_chunk()` is blocking C extension
2. **ThreadPoolExecutor** for parallel FFT computation (4 workers minimum)
3. **threading.Lock** on all shared buffers to prevent race conditions
4. **Queue-based** communication between pull threads and calc thread
5. **Sync→Async bridge** for WebSocket sends (asyncio.create_task)

## Failure Modes & Recovery

### Device disconnection

**Detection**: LSL stream stops providing data or health monitoring fails
**Recovery**: Auto-reconnect with exponential backoff (implemented in DeviceManager.monitor_device_health)
**Recording**: Mark gap in data, continue other devices
**Implementation**: Reconnection logic is mandatory for production use

### Buffer overflow

**Cause**: Pulling slower than 256 Hz data arrival
**Detection**: LSL buffer fills, oldest data dropped
**Prevention**: Pull at 20 Hz (way faster than needed)

### Compute lag

**Cause**: FFT taking longer than calc_interval
**Detection**: Monitor `compute_time_ms` metric
**Recovery**: Auto-reduce calc_rate or drop frames

### WebSocket disconnect

**Detection**: Socket error event
**Recovery**: Auto-reconnect, re-send last metrics
**Recording**: Continues unaffected (independent)

## Design Requirements for Production

### Threading Architecture (CRITICAL)

**Why Pure Threading (Not Async/Await)**:

pylsl's `pull_chunk()` is a **blocking C extension** that cannot yield to Python's event loop. This makes async/await fundamentally incompatible with LSL operations:

```python
# ❌ WRONG - This will freeze the event loop
async def pull_loop(self):
    while self.active:
        chunk, ts = self.inlet.pull_chunk(timeout=0.0)  # Blocks event loop!
        await asyncio.sleep(0.05)

# ✅ CORRECT - Dedicated thread for blocking operations
def pull_thread(self):
    while self.active:
        chunk, ts = self.inlet.pull_chunk(timeout=0.0)
        with self.buffer_lock:  # Thread-safe
            self.buffer.extend(chunk)
        time.sleep(0.05)
```

**Required Threading Model**:

1. **Pull Threads** (4 threads, one per device):
   - Dedicated thread per LSL inlet
   - Runs blocking `pull_chunk()` at 20 Hz
   - Updates shared buffers with lock protection
   - Handles pull errors gracefully

2. **Calc Thread** (1 thread with ThreadPoolExecutor):
   - Reads from shared buffers (with locks)
   - Submits 4 FFT jobs to ThreadPoolExecutor
   - Waits for all results (parallel processing)
   - Updates metrics cache (with lock)

3. **Save Thread** (1 thread):
   - Periodically flushes recording buffers to disk
   - Independent of feedback processing

4. **WebSocket Bridge** (async task creation):
   - Calc thread triggers: `asyncio.create_task(send_metrics())`
   - Avoids blocking calc thread on WebSocket I/O

**Thread Synchronization**:
```python
import threading
from concurrent.futures import ThreadPoolExecutor

class ThreadSafeBuffer:
    def __init__(self, maxlen=1024):
        self.buffer = deque(maxlen=maxlen)
        self.lock = threading.Lock()

    def extend(self, data):
        with self.lock:
            self.buffer.extend(data)

    def get_snapshot(self):
        with self.lock:
            return np.array(self.buffer)

# Global resources
buffer_locks = {f'Muse_{i}': threading.Lock() for i in range(1, 5)}
metrics_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=4)
```

**Lock Acquisition Order** (prevent deadlock):
1. Pull threads: acquire only their device's buffer lock
2. Calc thread: acquire buffers in order (Muse_1 → Muse_4), then metrics lock
3. Save thread: acquire recording buffers in order
4. Never hold multiple locks simultaneously unless necessary

### Training Protocols and Onboarding

While training protocols are experiment-specific, the framework must support:
- Configurable training phases with different timescales
- Progress tracking and adaptive difficulty
- User onboarding flows for multi-timescale interpretation
- Data export for protocol analysis

### Edge Cases and Error Handling

**Must handle**:
- Device disconnection during sessions (reconnection logic)
- Data corruption and artifact detection
- Buffer underflow/overflow conditions
- Network interruptions (WebSocket reconnect)
- CPU overload (adaptive rate reduction)
- Memory pressure (buffer size management)

## Next Steps

- [LSL Buffering Deep-Dive](02-lsl-buffering-deep-dive.md) - Understand the FIFO challenge
- [Multi-Timescale Feedback](03-multi-timescale-feedback.md) - Why 1s/2s/4s works
- [Implementation Guide](05-implementation-guide.md) - Start coding

---

**Last updated**: 2025-10-30
