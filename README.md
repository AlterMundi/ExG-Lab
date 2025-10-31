# ExG-Lab: Multi-Device EEG Real-Time Feedback System

**A comprehensive platform for multi-subject EEG+ECG experiments with real-time neurofeedback**

## Overview

ExG-Lab is a system for conducting EEG experiments with multiple Muse headbands, featuring:

- **Multi-device support**: 1-4 Muse devices simultaneously (Muse S model tested and supported)
- **Dual-mode operation**: Complete data recording + real-time feedback
- **Multi-timescale feedback**: 1s/2s/4s windows for predictive insights
- **Optimized performance**: Decoupled data acquisition and processing rates
- **Web-based UI**: Modern React dashboard with real-time updates

## Key Features

### <� Multi-Timescale Neurofeedback

Provides three concurrent metrics from the same data stream:
- **Fast (1s)**: Leading indicator - shows where you're heading
- **Balanced (2s)**: Current state - optimal training target
- **Stable (4s)**: Trend confirmation - validates changes

This multi-scale approach enables **predictive feedback** - participants can see changes developing before they fully manifest.

### = Dual-Mode Recording

Simultaneously:
- Records ALL raw EEG data to CSV (no data loss)
- Computes real-time metrics for participant feedback
- Maintains data freshness through optimized buffering

### � Performance Optimized

- **Decoupled rates**: Data pulling (20 Hz) independent from calculations (10-30 Hz)
- **Efficient buffering**: Single 4-second rolling window serves all timescales
- **Latency**: Varies by metric timescale - 1s (~1s), 2s (~2s), 4s (~4s) plus ~10ms processing. Raw data display can achieve <50ms latency.
- **Scalable**: Handles 4 devices with 60% CPU headroom

## Documentation

Comprehensive documentation covers both theory and practice:

### Core Architecture
1. [**Architecture Overview**](docs/01-architecture-overview.md) - System design and threading model
2. [**LSL Buffering Deep-Dive**](docs/02-lsl-buffering-deep-dive.md) - Critical understanding of LSL mechanics
3. [**Multi-Timescale Feedback**](docs/03-multi-timescale-feedback.md) - The 1s/2s/4s approach
4. [**Rate Decoupling**](docs/04-rate-decoupling.md) - Independent pull/calc/UI threads

### Implementation
5. [**Implementation Guide**](docs/05-implementation-guide.md) - Thread-safe code patterns
6. [**UI Design Guide**](docs/06-ui-design.md) - Frontend implementation
7. [**Muselsl Bugfixes**](docs/07-muselsl-bugfixes.md) - Known issues and solutions

### Quality Assurance
8. [**Testing Guide**](docs/08-testing-guide.md) - Thread safety and integration tests
9. [**Error Handling**](docs/09-error-handling.md) - Recovery patterns and graceful degradation
10. [**Refactoring Summary**](docs/10-refactoring-summary.md) - Documentation corrections and production roadmap

### Technical Analysis
11. [**Technical Analysis**](docs/TECHNICAL_ANALYSIS.md) - Deep-dive review and issue identification

## Critical Insights

### LSL FIFO Behavior

**Key insight**: `pull_chunk()` returns OLDEST unread data, not newest!

-  **For recording**: Perfect - guarantees no data loss
- � **For real-time feedback**: Must flush buffer before starting
- � **Solution**: Pull faster than data arrives (20+ Hz)

See [LSL Buffering Deep-Dive](docs/02-lsl-buffering-deep-dive.md) for details.

### Multi-Timescale Strategy

Computing metrics at 1s, 2s, and 4s windows enables **predictive feedback**:

```
User improves their relaxation:
  1s: ��  (rising fast - user sees immediate effect)
  2s: �   (rising - confirms trend)
  4s: �   (stable - hasn't caught up yet)

Visual: Green > Yellow > Blue = Improvement detected!
```

### Threading Architecture (CRITICAL)

**Pure threading model** required - not async/await:

```python
# ✅ CORRECT: Pure threading with locks
def pull_thread_func(self):
    while self.active:
        chunk, ts = self.inlet.pull_chunk(timeout=0.0)  # Blocking OK in thread
        with self.buffer_lock:  # Thread-safe access
            self.buffer.extend(chunk)
        time.sleep(0.05)  # 20 Hz
```

**Why**: pylsl's `pull_chunk()` is a blocking C extension incompatible with async/await.

### Decoupled Rates

**Critical**: Pull rate ≠ Calculation rate ≠ UI rate

```python
# CORRECT: Independent threads with locks
pull_rate_hz=20    # Keep data fresh (prevent staleness)
calc_rate_hz=10    # Compute metrics (parallel ThreadPoolExecutor)
ui_rate_hz=10      # Update display (bridge to async WebSocket)
```

## Known Issues & Solutions

### Muselsl Bugs (Fixed)

We identified and fixed two critical bugs in muselsl v2.2.2:

1. **Bluetoothctl EOF handling** - `muselsl list` fails on some systems
2. **Record filename handling** - Simple filenames crash recording

See [Muselsl Bugfixes](docs/07-muselsl-bugfixes.md) and [our PR #224](https://github.com/alexandrebarachant/muse-lsl/pull/224).

---

**Status**: Active development
**Last updated**: 2025-10-30
**Python**: 3.11+
**Platform**: Linux (primary), macOS, Windows (limited Bluetooth support)
