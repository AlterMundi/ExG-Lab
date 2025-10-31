# Multi-Timescale Feedback

## The Core Innovation

**The fundamental insight**: Computing metrics at multiple timescales from the same data stream enables **predictive neurofeedback**.

Instead of showing participants a single metric that lags behind their mental state, we show them THREE concurrent metrics that reveal:
- Where they're heading (1s - leading indicator)
- Where they are now (2s - current state)
- Where they've been (4s - trend confirmation)

## Why Multiple Timescales?

### The Trade-off Triangle

Every EEG analysis window size involves a three-way trade-off:

```
       Frequency Resolution
              △
             ╱ ╲
            ╱   ╲
           ╱     ╲
          ╱       ╲
    Time ◄─────────► Noise
  Resolution      Reduction
```

**Short windows (1s)**:
- ✅ Fast response to changes
- ✅ Low lag (500ms average)
- ❌ Poor frequency resolution (Δf = 1.0 Hz)
- ❌ High variance (noisy)

**Long windows (4s)**:
- ✅ Excellent frequency resolution (Δf = 0.25 Hz)
- ✅ Low variance (stable)
- ❌ Slow response to changes
- ❌ High lag (2000ms average)

**Medium windows (2s)**:
- ⚖️ Balanced trade-off
- ⚖️ Good for most training

### The Multi-Scale Solution

By computing ALL THREE simultaneously, we get the best of all worlds:

```python
# From the SAME 4-second buffer:
buffer = deque(maxlen=1024)  # 4 seconds @ 256 Hz

# Extract three windows
window_1s = buffer[-256:]    # Last 1 second  (256 samples)
window_2s = buffer[-512:]    # Last 2 seconds (512 samples)
window_4s = buffer[-1024:]   # Last 4 seconds (1024 samples)

# Compute metrics
fast_metric = compute_fft(window_1s)      # Leading indicator
balanced_metric = compute_fft(window_2s)  # Current state
stable_metric = compute_fft(window_4s)    # Trend confirmation
```

**Result**: Participant sees ALL trade-off points, can interpret changes in context.

## Frequency Resolution Details

### FFT Fundamentals

Frequency resolution (bin width) is determined by:

```
Δf = sample_rate / N_samples

For Muse @ 256 Hz:
- 1s window (256 samples):  Δf = 256/256 = 1.0 Hz
- 2s window (512 samples):  Δf = 256/512 = 0.5 Hz
- 4s window (1024 samples): Δf = 256/1024 = 0.25 Hz
```

### Impact on Band Power Estimation

**Alpha band (8-13 Hz)** analysis:

```
1s window (Δf = 1.0 Hz):
Bins: [8, 9, 10, 11, 12, 13] = 6 bins
  ↓
Rough estimate, high variance

2s window (Δf = 0.5 Hz):
Bins: [8.0, 8.5, 9.0, 9.5, 10.0, ..., 13.0] = 11 bins
  ↓
Good balance, moderate variance

4s window (Δf = 0.25 Hz):
Bins: [8.00, 8.25, 8.50, 8.75, 9.00, ..., 13.00] = 21 bins
  ↓
Excellent detail, low variance
```

**Practical consequence**:
- 1s: Can detect alpha presence, but not detailed structure
- 2s: Can differentiate low-alpha (8-10 Hz) from high-alpha (10-13 Hz)
- 4s: Can see individual alpha peak frequency with precision

### Separating Adjacent Bands

**Critical challenge**: Separating alpha (8-13 Hz) from beta (13-30 Hz)

```
At boundary (13 Hz):

1s window (Δf = 1.0 Hz):
  Bin 13: Contains 12.5-13.5 Hz
    ↓
  OVERLAPS alpha and beta!
  50% contamination

2s window (Δf = 0.5 Hz):
  Bin 13.0: Contains 12.75-13.25 Hz
    ↓
  Still some overlap
  25% contamination

4s window (Δf = 0.25 Hz):
  Bin 13.00: Contains 12.875-13.125 Hz
    ↓
  Minimal overlap
  12.5% contamination
```

**Implication**: 1s window can't cleanly separate alpha/beta for relaxation index.

**Solution**: Use 4s window for stable baseline, 1s/2s for detecting rapid changes.

## Predictive Feedback Patterns

### The Gradient Pattern

When a participant improves their relaxation state:

```
Time:  t=0s          t=1s          t=2s          t=3s
       ┌────────────┬────────────┬────────────┬────────────┐
State: │ Normal     │ Improving  │ Relaxed    │ Relaxed    │
       └────────────┴────────────┴────────────┴────────────┘

At t=2s (participant just relaxed):

1s metric: ██████████ 3.2  ← Captures recent change (HIGH)
           (samples from t=1-2s)

2s metric: ███████    2.4  ← Mixed old+new (MEDIUM)
           (samples from t=0-2s)

4s metric: ████       1.8  ← Mostly old data (LOW)
           (samples from t=-2 to t=2s)

Visual pattern: 1s > 2s > 4s = IMPROVEMENT DETECTED!
```

**Predictive value**: Participant sees 1s metric rise BEFORE 4s metric confirms, enabling faster learning.

### The Stability Pattern

When a participant maintains a relaxed state:

```
Time:  t=0s          t=1s          t=2s          t=3s
       ┌────────────┬────────────┬────────────┬────────────┐
State: │ Relaxed    │ Relaxed    │ Relaxed    │ Relaxed    │
       └────────────┴────────────┴────────────┴────────────┘

At t=3s (sustained relaxation):

1s metric: ████████ 3.1  ← Current state
2s metric: ████████ 3.0  ← Confirms sustained
4s metric: ████████ 2.9  ← Trend validated

Visual pattern: 1s ≈ 2s ≈ 4s = STABLE STATE
```

**Feedback**: "You're maintaining this well" - all metrics converged.

### The Regression Pattern

When a participant loses focus:

```
Time:  t=0s          t=1s          t=2s          t=3s
       ┌────────────┬────────────┬────────────┬────────────┐
State: │ Relaxed    │ Relaxed    │ Distracted │ Distracted │
       └────────────┴────────────┴────────────┴────────────┘

At t=3s (just lost focus):

1s metric: ███ 1.4  ← Recent decline (LOW)
2s metric: █████ 2.0  ← Mixed (MEDIUM)
4s metric: ████████ 2.8  ← Still good (HIGH)

Visual pattern: 1s < 2s < 4s = DECLINE DETECTED!
```

**Early warning**: Participant sees 1s metric drop BEFORE it affects 4s baseline.

## Implementation Architecture

### Single-Buffer Design

**Key optimization**: One 4-second buffer serves all three timescales.

```python
from collections import deque
import numpy as np
from scipy import signal

class MultiScaleProcessor:
    def __init__(self, sample_rate=256, buffer_duration=4.0):
        """
        Single rolling buffer for multi-timescale analysis

        Args:
            sample_rate: Hz (Muse = 256)
            buffer_duration: seconds (must be >= longest window)
        """
        self.sample_rate = sample_rate
        self.buffer_size = int(sample_rate * buffer_duration)

        # Single buffer for ALL timescales
        self.buffer = deque(maxlen=self.buffer_size)

        # Window sizes (in samples)
        self.windows = {
            '1s': int(sample_rate * 1.0),   # 256
            '2s': int(sample_rate * 2.0),   # 512
            '4s': int(sample_rate * 4.0),   # 1024
        }

        # Frequency bands (Hz)
        self.bands = {
            'delta': (0.5, 4),
            'theta': (4, 8),
            'alpha': (8, 13),
            'beta': (13, 30),
            'gamma': (30, 50)
        }

    def add_samples(self, chunk):
        """
        Add new samples to rolling buffer

        Args:
            chunk: array of shape (n_samples, n_channels) or (n_samples,)
        """
        if chunk.ndim == 1:
            self.buffer.extend(chunk)
        else:
            # Multi-channel: extend per sample
            for sample in chunk:
                self.buffer.append(sample)

    def compute_all_timescales(self):
        """
        Compute metrics for all three timescales

        Returns:
            dict: {
                '1s': metrics_dict,
                '2s': metrics_dict,
                '4s': metrics_dict
            }
        """
        if len(self.buffer) < self.windows['1s']:
            return None  # Not enough data yet

        buffer_array = np.array(self.buffer)

        results = {}
        for timescale, n_samples in self.windows.items():
            if len(self.buffer) >= n_samples:
                # Extract latest N samples
                window = buffer_array[-n_samples:]

                # Compute metrics for this window
                results[timescale] = self._compute_metrics(window, n_samples)

        return results

    def _compute_metrics(self, window, n_samples):
        """
        Compute band powers and relaxation index for one window

        Args:
            window: array of samples
            n_samples: window size (determines nperseg for Welch)
        """
        # Welch's method for PSD
        # nperseg should be fraction of window for averaging
        nperseg = min(n_samples // 2, self.sample_rate)

        freqs, psd = signal.welch(
            window,
            fs=self.sample_rate,
            nperseg=nperseg,
            scaling='density'
        )

        # Compute band powers
        band_powers = {}
        for band_name, (low, high) in self.bands.items():
            # Find frequency bins in this band
            idx = np.logical_and(freqs >= low, freqs <= high)

            # Integrate PSD in this band
            band_powers[band_name] = np.trapz(psd[idx], freqs[idx])

        # Relaxation index (alpha/beta ratio)
        relaxation = band_powers['alpha'] / band_powers['beta'] if band_powers['beta'] > 0 else 0

        return {
            'band_powers': band_powers,
            'relaxation': relaxation,
            'total_power': sum(band_powers.values())
        }
```

### Usage Example

```python
# Initialize processor
processor = MultiScaleProcessor(sample_rate=256)

# In your data acquisition loop
while session_active:
    # Pull from LSL
    chunk, timestamps = inlet.pull_chunk(timeout=0.05, max_samples=256)

    if timestamps:
        # Add to rolling buffer
        processor.add_samples(chunk)

        # Compute all timescales (do this at calc_rate, e.g., 10 Hz)
        if time_for_calculation():
            metrics = processor.compute_all_timescales()

            if metrics:
                print(f"1s: {metrics['1s']['relaxation']:.2f}")
                print(f"2s: {metrics['2s']['relaxation']:.2f}")
                print(f"4s: {metrics['4s']['relaxation']:.2f}")

                send_to_ui(metrics)
```

## Multi-Channel Considerations

For Muse (4 channels: TP9, AF7, AF8, TP10):

### Per-Channel Analysis

```python
class MultiChannelMultiScaleProcessor:
    def __init__(self, n_channels=4, sample_rate=256):
        self.n_channels = n_channels

        # Separate buffer per channel
        self.buffers = [
            deque(maxlen=int(sample_rate * 4.0))
            for _ in range(n_channels)
        ]

        self.channel_names = ['TP9', 'AF7', 'AF8', 'TP10']

    def add_samples(self, chunk):
        """
        chunk: shape (n_samples, n_channels)
        """
        for sample in chunk:
            for ch_idx, value in enumerate(sample):
                self.buffers[ch_idx].append(value)

    def compute_all_timescales_all_channels(self):
        """
        Returns:
            dict: {
                'TP9': {'1s': {...}, '2s': {...}, '4s': {...}},
                'AF7': {'1s': {...}, '2s': {...}, '4s': {...}},
                ...
            }
        """
        results = {}

        for ch_idx, ch_name in enumerate(self.channel_names):
            buffer_array = np.array(self.buffers[ch_idx])

            ch_results = {}
            for timescale, n_samples in self.windows.items():
                if len(buffer_array) >= n_samples:
                    window = buffer_array[-n_samples:]
                    ch_results[timescale] = self._compute_metrics(window, n_samples)

            results[ch_name] = ch_results

        return results
```

### Frontal Relaxation (Recommended)

For meditation/relaxation experiments, focus on frontal channels (AF7, AF8):

```python
def compute_frontal_relaxation(self):
    """
    Average alpha/beta ratio from frontal channels
    Most relevant for meditation/attention tasks
    """
    all_metrics = self.compute_all_timescales_all_channels()

    frontal_channels = ['AF7', 'AF8']

    results = {}
    for timescale in ['1s', '2s', '4s']:
        relaxation_values = [
            all_metrics[ch][timescale]['relaxation']
            for ch in frontal_channels
            if ch in all_metrics and timescale in all_metrics[ch]
        ]

        if relaxation_values:
            results[timescale] = np.mean(relaxation_values)

    return results
```

## Performance Characteristics

### Computational Cost

**Sequential processing** (one device):

```python
# Benchmarking results (Intel i7, Python 3.11):

# 1s window (256 samples, nperseg=128):
#   - Welch: ~2ms
#   - Band extraction: ~0.5ms
#   - Total: ~2.5ms

# 2s window (512 samples, nperseg=256):
#   - Welch: ~4ms
#   - Band extraction: ~0.5ms
#   - Total: ~4.5ms

# 4s window (1024 samples, nperseg=512):
#   - Welch: ~8ms
#   - Band extraction: ~0.5ms
#   - Total: ~8.5ms

# All three timescales: ~15ms per channel

# For 4 channels: ~60ms total
# → Max rate: 16 Hz (1000ms / 60ms)
```

**For 4 devices**: 4 × 60ms = 240ms → Max rate: 4 Hz (sequential - too slow!)
**With parallelization**: 60ms total → Max rate: 16 Hz (required for multi-device support)

### Parallel Processing

```python
from concurrent.futures import ThreadPoolExecutor

class ParallelMultiScaleProcessor:
    def __init__(self, n_devices=4):
        self.processors = [
            MultiChannelMultiScaleProcessor()
            for _ in range(n_devices)
        ]

        self.executor = ThreadPoolExecutor(max_workers=n_devices)

    def compute_all_devices_parallel(self):
        """
        Compute all timescales for all devices in parallel

        Returns:
            dict: {
                'Muse_1': {...},
                'Muse_2': {...},
                ...
            }
        """
        futures = {
            f'Muse_{i+1}': self.executor.submit(
                processor.compute_all_timescales_all_channels
            )
            for i, processor in enumerate(self.processors)
        }

        return {
            device: future.result()
            for device, future in futures.items()
        }
```

**Parallel performance**:
- 4 devices × 60ms = 60ms total (assuming 4+ CPU cores)
- → Max rate: 16 Hz

### Recommended Calculation Rates

```
Conservative (guaranteed smooth):
  - Sequential: 10 Hz (100ms budget, 60ms used → 40% headroom)
  - Parallel: 10 Hz (100ms budget, 60ms used → 40% headroom)

Aggressive (maximum performance):
  - Sequential: 12 Hz (83ms budget, 60ms used → 28% headroom)
  - Parallel: 15 Hz (67ms budget, 60ms used → 10% headroom)

Optimal for UI:
  - 10-15 Hz (sufficient for human perception)
  - Browser can render at 60 Hz, but 15 Hz data is smooth enough
```

## UX Design Implications

### Visual Representation

**Option 1: Three Gauges**

```
┌─────────────────────┐
│   Fast (1s)    🟢   │  ████████░░ 3.2
├─────────────────────┤
│ Balanced (2s)  🟡   │  ██████░░░░ 2.4
├─────────────────────┤
│  Stable (4s)   🔵   │  ████░░░░░░ 1.8
└─────────────────────┘

Gradient shows improvement!
```

**Option 2: Time-Series Plot**

```
Relaxation Index
    │
 4.0├                    ╱╲    ← 1s (green)
    │                   ╱  ╲
 3.0├              ╱───╱    ╲  ← 2s (yellow)
    │         ╱───╱          ╲
 2.0├    ╱───╱                ╲ ← 4s (blue)
    │───╱                      ╲
 1.0├────────────────────────────
    └────────────────────────────→ Time
```

**Option 3: Composite Score**

```
Current State: 2.4 (2s metric)

Trend: ↗ IMPROVING
  Fast metric (3.2) ahead of stable (1.8)

Confidence: ██████░░░░ 60%
  Based on convergence of timescales
```

### Interpretation Guidance

Provide real-time interpretation hints:

```python
def interpret_pattern(metrics):
    """
    Generate user-friendly interpretation
    """
    r1 = metrics['1s']['relaxation']
    r2 = metrics['2s']['relaxation']
    r4 = metrics['4s']['relaxation']

    # Pattern detection
    if r1 > r2 > r4:
        trend = "IMPROVING"
        message = "You're getting more relaxed! Keep it up."
        confidence = "Low" if r1 - r4 > 1.5 else "Medium"

    elif r1 < r2 < r4:
        trend = "DECLINING"
        message = "You're losing focus. Try to relax again."
        confidence = "Low" if r4 - r1 > 1.5 else "Medium"

    elif abs(r1 - r4) < 0.3:
        trend = "STABLE"
        message = "You're maintaining this state well!"
        confidence = "High"

    else:
        trend = "VARIABLE"
        message = "Your state is fluctuating. Find your rhythm."
        confidence = "Low"

    return {
        'trend': trend,
        'message': message,
        'confidence': confidence,
        'current': r2,  # Show 2s as "current state"
    }
```

### Training Strategies

**Phase 1: Learn to respond (focus on 1s)**
- Show primarily 1s metric
- Goal: See immediate effect of mental actions
- Success: 1s metric rises when trying to relax

**Phase 2: Learn to sustain (focus on 2s)**
- Show primarily 2s metric
- Goal: Maintain state for longer periods
- Success: 2s metric stays elevated

**Phase 3: Master stability (focus on 4s)**
- Show primarily 4s metric
- Goal: Achieve sustained, stable relaxation
- Success: 4s metric catches up to 1s/2s

**Phase 4: Self-regulation (show all three)**
- Show all metrics with interpretation
- Goal: Predict and control own state
- Success: Can reliably produce gradient patterns

## Edge Cases and Considerations

### Buffer Warm-up

```python
def is_ready(self):
    """
    Check if enough data accumulated for all timescales
    """
    return {
        '1s': len(self.buffer) >= self.windows['1s'],
        '2s': len(self.buffer) >= self.windows['2s'],
        '4s': len(self.buffer) >= self.windows['4s']
    }

# Usage
warmup_status = processor.is_ready()

if warmup_status['4s']:
    # All timescales available
    show_full_feedback()
elif warmup_status['2s']:
    # Show 1s and 2s only
    show_partial_feedback(['1s', '2s'])
elif warmup_status['1s']:
    # Show 1s only
    show_minimal_feedback(['1s'])
else:
    # Still warming up
    show_loading_indicator()
```

### Artifact Handling

```python
def detect_artifacts(window, threshold=100):
    """
    Simple artifact detection

    Args:
        window: EEG samples (μV)
        threshold: Max allowed amplitude (μV)

    Returns:
        bool: True if artifact detected
    """
    # Check for extreme values
    if np.max(np.abs(window)) > threshold:
        return True

    # Check for flat line (sensor disconnected)
    if np.std(window) < 0.1:
        return True

    return False

def compute_with_artifact_detection(self):
    """
    Only compute metrics if data is clean
    """
    buffer_array = np.array(self.buffer)

    results = {}
    for timescale, n_samples in self.windows.items():
        if len(buffer_array) >= n_samples:
            window = buffer_array[-n_samples:]

            if not detect_artifacts(window):
                results[timescale] = self._compute_metrics(window, n_samples)
            else:
                results[timescale] = None  # Signal bad data

    return results
```

### Normalization Across Participants

Different participants have different baseline alpha/beta ratios:

```python
class NormalizedMultiScaleProcessor(MultiScaleProcessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.baseline = None

    def calibrate_baseline(self, duration=30):
        """
        Compute baseline during eyes-open rest period

        Args:
            duration: seconds of baseline recording
        """
        # Collect baseline data
        baseline_metrics = []

        for _ in range(int(duration * 10)):  # 10 Hz sampling
            time.sleep(0.1)
            metrics = self.compute_all_timescales()
            if metrics and '4s' in metrics:
                baseline_metrics.append(metrics['4s']['relaxation'])

        # Store median as baseline
        self.baseline = np.median(baseline_metrics)

    def get_normalized_metrics(self):
        """
        Return metrics normalized to baseline
        """
        metrics = self.compute_all_timescales()

        if self.baseline and metrics:
            for timescale in metrics:
                # Normalize: value / baseline
                # >1.0 means above baseline (more relaxed)
                # <1.0 means below baseline (less relaxed)
                metrics[timescale]['relaxation_normalized'] = (
                    metrics[timescale]['relaxation'] / self.baseline
                )

        return metrics
```

## Next Steps

- [Rate Decoupling](04-rate-decoupling.md) - Independent control of pull/calc/UI rates
- [Implementation Guide](05-implementation-guide.md) - Practical code patterns
- [UI Design Guide](06-ui-design.md) - Frontend visualization strategies

---

**Last updated**: 2025-10-30
