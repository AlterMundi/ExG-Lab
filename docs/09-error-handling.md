# Error Handling and Recovery Patterns

## Overview

This document defines error handling strategies for ExG-Lab, covering device disconnections, data gaps, buffer issues, and graceful degradation.

---

## Error Categories

### 1. Hardware Errors (Bluetooth/Device)
- Device disconnection during session
- Bluetooth interference
- Low battery causing disconnection

### 2. Data Stream Errors (LSL)
- Stream disappears unexpectedly
- Data gaps in timestamps
- Corrupt/invalid samples

### 3. Processing Errors (CPU/Memory)
- FFT computation timeout
- Buffer overflow/underflow
- Memory pressure

### 4. Network Errors (WebSocket)
- Frontend disconnection
- Send timeout
- Connection drops

---

## Device Disconnection Handling

### Detection Strategy

**Multi-layered detection**:

```python
# backend/devices/health_monitor.py
import threading
import time
from pylsl import resolve_stream
from typing import Dict, Callable
import logging

logger = logging.getLogger(__name__)

class DeviceHealthMonitor:
    """
    Monitors device health and triggers reconnection

    Runs in dedicated thread, checks all devices periodically
    """

    def __init__(self,
                 device_manager,
                 session_manager,
                 check_interval: float = 5.0):
        """
        Args:
            device_manager: DeviceManager instance
            session_manager: SessionManager instance
            check_interval: Seconds between health checks
        """
        self.device_manager = device_manager
        self.session_manager = session_manager
        self.check_interval = check_interval

        self.active = False
        self.thread = None

        # Reconnection state
        self.reconnect_attempts = {}  # device_name -> attempts
        self.last_check_time = {}     # device_name -> timestamp

    def start(self):
        """Start health monitoring thread"""
        self.active = True
        self.thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="health_monitor"
        )
        self.thread.start()
        logger.info("Device health monitor started")

    def stop(self):
        """Stop health monitoring"""
        self.active = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Device health monitor stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.active:
            try:
                # Check all registered devices
                for stream_name in list(self.device_manager.devices.keys()):
                    self._check_device(stream_name)

            except Exception as e:
                logger.error(f"Health monitor error: {e}", exc_info=True)

            time.sleep(self.check_interval)

    def _check_device(self, stream_name: str):
        """
        Check single device health

        Detection methods:
        1. LSL stream still resolvable?
        2. Recent data received (check handler.last_timestamp)?
        3. Process still running?
        """
        # Method 1: Check if LSL stream exists
        stream_alive = self._is_stream_resolvable(stream_name)

        # Method 2: Check data freshness
        data_fresh = self._is_data_fresh(stream_name, max_age=2.0)

        # Method 3: Check subprocess
        process_alive = self._is_process_alive(stream_name)

        # Device is healthy if all checks pass
        healthy = stream_alive and data_fresh and process_alive

        if not healthy:
            logger.warning(
                f"Device {stream_name} unhealthy: "
                f"stream={stream_alive}, data={data_fresh}, process={process_alive}"
            )
            self._handle_unhealthy_device(stream_name)
        else:
            # Reset reconnect counter on successful check
            if stream_name in self.reconnect_attempts:
                logger.info(f"Device {stream_name} recovered")
                self.reconnect_attempts[stream_name] = 0

    def _is_stream_resolvable(self, stream_name: str, timeout: float = 1.0) -> bool:
        """Check if LSL stream can be resolved"""
        try:
            streams = resolve_stream('name', stream_name, timeout=timeout)
            return len(streams) > 0
        except Exception as e:
            logger.debug(f"Stream resolution failed for {stream_name}: {e}")
            return False

    def _is_data_fresh(self, stream_name: str, max_age: float = 2.0) -> bool:
        """Check if data is recent (within max_age seconds)"""
        handler = self.device_manager.get_stream_handler(stream_name)
        if not handler:
            return False

        if handler.last_timestamp is None:
            return False  # No data received yet

        age = time.time() - handler.last_timestamp
        return age < max_age

    def _is_process_alive(self, stream_name: str) -> bool:
        """Check if muselsl subprocess is still running"""
        device_info = self.device_manager.devices.get(stream_name)
        if not device_info or 'process' not in device_info:
            return False

        process = device_info['process']
        return process.poll() is None  # None = still running

    def _handle_unhealthy_device(self, stream_name: str):
        """
        Handle unhealthy device with exponential backoff

        Backoff schedule: 2s, 4s, 8s, 16s, 32s, 60s (max)
        """
        # Get current attempt count
        attempts = self.reconnect_attempts.get(stream_name, 0)

        # Calculate backoff time
        backoff = min(2 ** attempts, 60)  # Max 60 seconds

        # Check if enough time has passed since last attempt
        last_check = self.last_check_time.get(stream_name, 0)
        if time.time() - last_check < backoff:
            return  # Too soon, skip this check

        # Update attempt tracking
        self.reconnect_attempts[stream_name] = attempts + 1
        self.last_check_time[stream_name] = time.time()

        logger.info(
            f"Attempting reconnection for {stream_name} "
            f"(attempt {attempts + 1}, backoff {backoff}s)"
        )

        # Mark gap in session
        if self.session_manager:
            self.session_manager.add_event_marker(
                f"Device {stream_name} disconnected (attempt {attempts + 1})"
            )

        # Attempt reconnection
        success = self._reconnect_device(stream_name)

        if success:
            logger.info(f"Successfully reconnected {stream_name}")
            self.reconnect_attempts[stream_name] = 0

            # Mark recovery in session
            if self.session_manager:
                self.session_manager.add_event_marker(
                    f"Device {stream_name} reconnected"
                )
        else:
            logger.error(f"Failed to reconnect {stream_name}")

            # Alert user if attempts exceeded threshold
            if attempts >= 5:
                logger.critical(
                    f"Device {stream_name} failed {attempts} reconnection attempts"
                )

    def _reconnect_device(self, stream_name: str) -> bool:
        """
        Attempt to reconnect device

        Returns:
            True if successful, False otherwise
        """
        device_info = self.device_manager.devices.get(stream_name)
        if not device_info:
            return False

        address = device_info.get('address')
        if not address:
            return False

        # Clean up old process
        if 'process' in device_info:
            try:
                device_info['process'].terminate()
                device_info['process'].wait(timeout=2.0)
            except:
                pass

        # Attempt new connection
        return self.device_manager.connect_device(address, stream_name)
```

---

## Data Gap Handling

### Gap Detection and Logging

```python
# backend/session/gap_tracker.py
import time
from typing import List, Dict
import json

class GapTracker:
    """
    Tracks data gaps across all devices

    Gaps are logged to session metadata and can trigger alerts
    """

    def __init__(self, session_manager):
        self.session_manager = session_manager
        self.gaps = []  # List of gap events

    def record_gap(self,
                   device_name: str,
                   start_time: float,
                   end_time: float,
                   duration: float):
        """
        Record a data gap

        Args:
            device_name: Name of affected device
            start_time: LSL timestamp when gap started
            end_time: LSL timestamp when gap ended
            duration: Gap duration in seconds
        """
        gap_event = {
            'device': device_name,
            'start_timestamp': start_time,
            'end_timestamp': end_time,
            'duration': duration,
            'wall_clock_time': time.time()
        }

        self.gaps.append(gap_event)

        # Log to session
        self.session_manager.add_event_marker(
            f"Data gap in {device_name}: {duration*1000:.1f}ms",
            timestamp=start_time
        )

        # Alert if gap is severe (>500ms)
        if duration > 0.5:
            logger.warning(
                f"SEVERE GAP in {device_name}: {duration*1000:.1f}ms "
                f"({start_time:.3f} → {end_time:.3f})"
            )

    def get_gap_summary(self) -> Dict:
        """
        Get summary statistics of all gaps

        Returns:
            Dictionary with gap statistics per device
        """
        summary = {}

        for gap in self.gaps:
            device = gap['device']
            if device not in summary:
                summary[device] = {
                    'count': 0,
                    'total_duration': 0.0,
                    'max_duration': 0.0,
                    'gaps': []
                }

            summary[device]['count'] += 1
            summary[device]['total_duration'] += gap['duration']
            summary[device]['max_duration'] = max(
                summary[device]['max_duration'],
                gap['duration']
            )
            summary[device]['gaps'].append(gap)

        return summary

    def export_gaps(self, filepath: str):
        """Export gap data to JSON file"""
        with open(filepath, 'w') as f:
            json.dump({
                'gaps': self.gaps,
                'summary': self.get_gap_summary()
            }, f, indent=2)
```

---

## Buffer Error Handling

### Buffer Overflow Prevention

```python
# backend/devices/stream.py (additions)

class LSLStreamHandler:
    # ... existing code ...

    def __init__(self, stream_name: str, buffer_size: int = 1024):
        # ... existing code ...

        # Overflow protection
        self.max_recording_buffer_size = 5000  # ~20s @ 256 Hz
        self.overflow_count = 0

    def add_to_recording(self, chunk: np.ndarray, timestamps: np.ndarray):
        """Thread-safe: Add chunk to recording buffer with overflow protection"""
        with self.recording_lock:
            # Check for overflow before adding
            if len(self.recording_buffer) >= self.max_recording_buffer_size:
                self.overflow_count += 1
                logger.error(
                    f"Recording buffer overflow in {self.stream_name}! "
                    f"Size: {len(self.recording_buffer)}, "
                    f"Overflow count: {self.overflow_count}"
                )

                # Emergency flush to prevent memory issues
                logger.warning(f"Emergency flushing {self.stream_name}")
                # Don't clear - let caller save first
                raise BufferOverflowError(
                    f"Recording buffer exceeded {self.max_recording_buffer_size} samples"
                )

            # Normal addition
            for i, timestamp in enumerate(timestamps):
                sample_data = {
                    'timestamp': timestamp,
                    'sample': chunk[i, :].tolist()
                }
                self.recording_buffer.append(sample_data)


class BufferOverflowError(Exception):
    """Raised when recording buffer exceeds safe size"""
    pass
```

### Handling Buffer Overflow

```python
# backend/main.py (pull_data_callback modification)

def pull_data_callback():
    """Pull data from all devices with error handling"""
    for device_name, handler in stream_handlers.items():
        try:
            chunk, timestamps = handler.pull_data()

            if chunk is not None:
                # Add to rolling buffer (for feedback)
                handler.add_to_buffers(chunk)

                # Add to recording buffer (with overflow protection)
                if device_name in recorders:
                    try:
                        handler.add_to_recording(chunk, timestamps)

                    except BufferOverflowError:
                        # Emergency save
                        logger.critical(f"Emergency save for {device_name}")
                        data = handler.flush_recording_buffer()
                        recorders[device_name].save_chunk(data)

                    # Periodic save (every 1000 samples)
                    if len(handler.recording_buffer) > 1000:
                        data = handler.flush_recording_buffer()
                        recorders[device_name].save_chunk(data)

        except Exception as e:
            logger.error(f"Pull error for {device_name}: {e}", exc_info=True)

            # Mark error in session
            session_manager.add_event_marker(
                f"Pull error in {device_name}: {str(e)}"
            )
```

---

## FFT Computation Errors

### Timeout Protection

```python
# backend/processing/multi_scale.py (additions)
import signal
from contextlib import contextmanager

class TimeoutError(Exception):
    """Raised when FFT computation exceeds timeout"""
    pass

@contextmanager
def timeout(seconds):
    """Context manager for timing out operations"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation exceeded {seconds}s timeout")

    # Set alarm
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class MultiScaleProcessor:
    # ... existing code ...

    def compute_all_timescales(self,
                               buffer: np.ndarray,
                               timeout_seconds: float = 0.1) -> Optional[Dict]:
        """
        Compute metrics with timeout protection

        Args:
            buffer: Array of samples
            timeout_seconds: Max computation time

        Returns:
            Dict with metrics or None if timeout
        """
        try:
            with timeout(timeout_seconds):
                return self._compute_all_timescales_unsafe(buffer)

        except TimeoutError:
            logger.error("FFT computation exceeded timeout")
            return None

        except Exception as e:
            logger.error(f"FFT error: {e}", exc_info=True)
            return None

    def _compute_all_timescales_unsafe(self, buffer: np.ndarray) -> Optional[Dict]:
        """Original computation without timeout protection"""
        # ... existing computation code ...
```

---

## WebSocket Error Handling

### Resilient WebSocket Sends

```python
# backend/main.py (modifications)
import asyncio

async def send_to_websockets(metrics: Dict):
    """
    Send metrics to all WebSocket connections with error handling

    Automatically removes dead connections
    """
    dead_connections = []

    for connection in active_connections:
        try:
            # Send with timeout
            await asyncio.wait_for(
                connection.send_json(metrics),
                timeout=1.0  # 1 second timeout
            )

        except asyncio.TimeoutError:
            logger.warning(f"WebSocket send timeout: {connection}")
            dead_connections.append(connection)

        except Exception as e:
            logger.debug(f"WebSocket send error: {e}")
            dead_connections.append(connection)

    # Remove dead connections
    for conn in dead_connections:
        try:
            active_connections.remove(conn)
            await conn.close()
        except:
            pass

    if dead_connections:
        logger.info(f"Removed {len(dead_connections)} dead connections")


def send_to_ui_callback(metrics: Dict):
    """
    Bridge from sync thread to async WebSocket

    Called by UI thread, schedules async send
    """
    if not event_loop:
        logger.warning("No event loop for WebSocket send")
        return

    try:
        # Schedule coroutine in event loop
        future = asyncio.run_coroutine_threadsafe(
            send_to_websockets(metrics),
            event_loop
        )

        # Optional: wait briefly to detect immediate errors
        future.result(timeout=0.1)

    except asyncio.TimeoutError:
        # This is OK - means send is still in progress
        pass

    except Exception as e:
        logger.error(f"WebSocket bridge error: {e}", exc_info=True)
```

---

## Graceful Degradation

### Continue with Fewer Devices

```python
# backend/main.py
class SystemState:
    """Track system health and adapt behavior"""

    def __init__(self):
        self.device_status = {}  # device_name -> 'healthy' | 'degraded' | 'failed'
        self.failed_devices = set()

    def mark_device_failed(self, device_name: str):
        """Mark device as failed, continue with others"""
        self.failed_devices.add(device_name)
        self.device_status[device_name] = 'failed'

        logger.warning(
            f"Device {device_name} marked as failed. "
            f"Continuing with {self.get_healthy_count()} devices"
        )

        # Notify frontend
        asyncio.create_task(
            broadcast_system_status({
                'type': 'device_failed',
                'device': device_name,
                'healthy_devices': self.get_healthy_count()
            })
        )

    def get_healthy_count(self) -> int:
        """Get count of healthy devices"""
        return sum(
            1 for status in self.device_status.values()
            if status == 'healthy'
        )

    def can_continue(self) -> bool:
        """Check if system can continue"""
        # Require at least 1 healthy device
        return self.get_healthy_count() >= 1


system_state = SystemState()
```

---

## Error Recovery Checklist

When an error occurs, the system should:

1. **Log the error** with full context (device, timestamp, stack trace)
2. **Mark the event** in session metadata for analysis
3. **Attempt recovery** if possible (reconnect, retry, etc.)
4. **Notify user** via WebSocket if critical
5. **Degrade gracefully** if recovery fails (continue with fewer devices)
6. **Preserve data** already recorded (don't corrupt files)

---

## Next Steps

- [Testing Guide](08-testing-guide.md) - Validate error handling
- [Implementation Guide](05-implementation-guide.md) - Build the system
- [Architecture Overview](01-architecture-overview.md) - System design

---

**Last updated**: 2025-10-30
