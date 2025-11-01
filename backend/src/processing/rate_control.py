"""
Rate Control Loop - Multi-threaded orchestration of real-time neurofeedback pipeline

This is the CORE ORCHESTRATOR that manages the entire real-time processing pipeline.

Threading Architecture (CRITICAL):
┌──────────────────────────────────────────────────────────────────────┐
│ PULL THREADS (20 Hz, pure threading)                                │
│  - One thread per device: LSLStreamHandler._pull_loop()             │
│  - Pulls from pylsl.StreamInlet (blocking C extension)              │
│  - Updates rolling buffers (thread-safe with Lock)                  │
│  - Independent rate: 20 Hz (50ms intervals)                         │
└──────────────────────────────────────────────────────────────────────┘
              ↓ (thread-safe buffer access)
┌──────────────────────────────────────────────────────────────────────┐
│ CALC THREAD (10 Hz, pure threading)                                 │
│  - Single thread for all devices                                    │
│  - Reads from rolling buffers (thread-safe)                         │
│  - Computes FFT + band powers using MultiScaleProcessor             │
│  - Uses ThreadPoolExecutor for parallel device processing           │
│  - Independent rate: 10 Hz (100ms intervals)                        │
│  - Writes results to shared state (thread-safe with Lock)           │
└──────────────────────────────────────────────────────────────────────┘
              ↓ (thread-safe result access)
┌──────────────────────────────────────────────────────────────────────┐
│ UI THREAD (10 Hz, asyncio)                                          │
│  - Asyncio task in FastAPI event loop                               │
│  - Reads from shared state (thread-safe)                            │
│  - Broadcasts via WebSocket to frontend                             │
│  - Independent rate: 10 Hz (100ms intervals)                        │
└──────────────────────────────────────────────────────────────────────┘

Rate Independence (CRITICAL DESIGN):
- Pull @ 20 Hz: Ensures fresh data, prevents LSL buffer overflow
- Calc @ 10 Hz: Matches neurofeedback update needs (100ms is perceptually smooth)
- UI @ 10 Hz: Matches frontend animation frame rate
- All three rates are INDEPENDENT - no blocking between them

Threading vs Asyncio Bridge:
- pylsl is blocking C extension → MUST use threading
- FastAPI WebSocket is async → MUST use asyncio
- Solution: Calc thread writes to shared state, UI asyncio task reads from it
- Communication via thread-safe queue or shared dict with Lock

Performance Budget (10 Hz = 100ms):
- Pull threads: <5ms each (non-blocking, minimal work)
- Calc thread:
  * 1 device: ~15ms (sequential FFT)
  * 4 devices: ~40ms (parallel FFT with ThreadPoolExecutor)
  * Margin: 60ms buffer
- UI thread: <10ms (JSON serialization + WebSocket send)

Usage:
    # Create rate controller
    rate_controller = RateController(
        stream_handlers={'Muse_1': handler1, 'Muse_2': handler2},
        processor=multi_scale_processor
    )

    # Start processing
    rate_controller.start()

    # In FastAPI startup:
    @app.on_event("startup")
    async def startup():
        asyncio.create_task(rate_controller.ui_broadcast_loop(websocket_manager))

    # On shutdown:
    rate_controller.stop()
"""

import logging
import time
import threading
import asyncio
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)


@dataclass
class DeviceMetrics:
    """
    Neurofeedback metrics for a single device at a single timestamp.

    Matches frontend TypeScript interface:
    interface DeviceMetrics {
        subject: string
        frontal: {
            "1s": { relaxation: number, alpha: number, beta: number }
            "2s": { relaxation: number, alpha: number, beta: number }
            "4s": { relaxation: number, alpha: number, beta: number }
        }
        quality: {
            data_age_ms: number
            signal_quality: { TP9: number, AF7: number, AF8: number, TP10: number }
        }
    }
    """
    subject: str  # "Muse_1", "Muse_2", etc.
    frontal_1s: Dict[str, float]  # {'relaxation': 1.75, 'alpha': 12.5, 'beta': 7.1}
    frontal_2s: Dict[str, float]
    frontal_4s: Dict[str, float]
    data_age_ms: float
    signal_quality: Dict[str, float]  # {'TP9': 0.85, 'AF7': 0.92, ...}
    timestamp: float


class RateController:
    """
    Orchestrates multi-threaded real-time neurofeedback pipeline.

    Manages:
    - Calc thread (10 Hz) for FFT computation
    - Shared state for calc → UI communication
    - Thread synchronization and lifecycle

    Note: Pull threads are managed by LSLStreamHandler instances.
    Note: UI broadcast is managed by FastAPI asyncio task.
    """

    def __init__(
        self,
        stream_handlers: Dict[str, 'LSLStreamHandler'],
        processor: 'MultiScaleProcessor',
        calc_rate_hz: float = 10.0
    ):
        """
        Initialize rate controller.

        Args:
            stream_handlers: Dict mapping device_name -> LSLStreamHandler instance
            processor: MultiScaleProcessor instance for FFT computation
            calc_rate_hz: Calculation rate in Hz (default 10.0 = 100ms intervals)
        """
        self.stream_handlers = stream_handlers
        self.processor = processor
        self.calc_rate_hz = calc_rate_hz
        self.calc_interval = 1.0 / calc_rate_hz

        # Shared state (calc thread writes, UI thread reads)
        self.latest_metrics: Dict[str, DeviceMetrics] = {}
        self.metrics_lock = threading.Lock()

        # Calc thread control
        self.calc_thread: Optional[threading.Thread] = None
        self.running = False

        # Performance monitoring
        self.calc_loop_times: List[float] = []

        logger.info(f"RateController initialized ({calc_rate_hz} Hz calc rate)")

    def start(self):
        """
        Start calculation thread.

        Pull threads are already started by LSLStreamHandler.start().
        UI broadcast loop should be started separately as asyncio task.
        """
        if self.running:
            logger.warning("RateController already running")
            return

        logger.info("Starting RateController...")

        self.running = True

        # Start calc thread
        self.calc_thread = threading.Thread(
            target=self._calc_loop,
            name="Calc-Thread",
            daemon=True
        )
        self.calc_thread.start()

        logger.info("✓ RateController started (calc thread running)")

    def stop(self):
        """
        Stop calculation thread.

        Pull threads should be stopped by calling LSLStreamHandler.stop().
        UI broadcast loop should be cancelled separately.
        """
        if not self.running:
            logger.warning("RateController not running")
            return

        logger.info("Stopping RateController...")

        self.running = False

        if self.calc_thread:
            self.calc_thread.join(timeout=2.0)
            if self.calc_thread.is_alive():
                logger.warning("Calc thread didn't stop gracefully")

        logger.info("✓ RateController stopped")

    def _calc_loop(self):
        """
        Calculation thread main loop - runs at 10 Hz (100ms intervals).

        For each iteration:
        1. Read recent data from all stream handlers (thread-safe)
        2. Process in parallel using MultiScaleProcessor
        3. Update shared metrics state (thread-safe)
        4. Sleep to maintain 10 Hz rate

        Performance:
        - Target: <100ms per iteration (10 Hz)
        - Actual: ~40ms for 4 devices with parallel FFT
        - Margin: ~60ms buffer for safety
        """
        logger.info(f"Calc thread started ({self.calc_rate_hz} Hz)")

        while self.running:
            loop_start = time.time()

            try:
                # Step 1: Gather data from all devices
                device_data = []
                for device_name, handler in self.stream_handlers.items():
                    # Check if buffer is sufficiently filled (>90% for stable feedback)
                    fill_ratio = handler.get_buffer_fill_ratio()
                    if fill_ratio < 0.9:
                        logger.debug(
                            f"{device_name} buffer not ready ({fill_ratio*100:.0f}% full)"
                        )
                        continue

                    # Get 4-second window (for stable timescale)
                    data = handler.get_recent_data(duration=4.0)
                    if data is None:
                        logger.warning(f"{device_name} insufficient data")
                        continue

                    device_data.append({
                        'device': device_name,
                        'data': data,
                        'handler': handler
                    })

                # Step 2: Process all devices at 4-second timescale (parallel)
                if device_data:
                    results_4s = self.processor.process_multiple_devices(
                        device_data,
                        timescale=4.0
                    )

                    # Step 3: Process at 1s and 2s timescales (parallel)
                    results_1s = self.processor.process_multiple_devices(
                        device_data,
                        timescale=1.0
                    )
                    results_2s = self.processor.process_multiple_devices(
                        device_data,
                        timescale=2.0
                    )

                    # Step 4: Collect signal quality metrics
                    quality_metrics = {}
                    for item in device_data:
                        device_name = item['device']
                        handler = item['handler']

                        # Get data age
                        data_age_ms = handler.get_data_age_ms()

                        # Assess signal quality for each channel
                        # For simplicity, use fill ratio as proxy (0-1 scale)
                        fill = handler.get_buffer_fill_ratio()
                        quality_metrics[device_name] = {
                            'data_age_ms': data_age_ms,
                            'signal_quality': {
                                'TP9': fill,  # Simplified - could use real SNR
                                'AF7': fill,
                                'AF8': fill,
                                'TP10': fill
                            }
                        }

                    # Step 5: Build DeviceMetrics objects
                    new_metrics = {}

                    for item in device_data:
                        device_name = item['device']

                        # Check if we have results for all timescales
                        if (device_name not in results_1s or
                            device_name not in results_2s or
                            device_name not in results_4s):
                            continue

                        # Extract metrics
                        r1 = results_1s[device_name]
                        r2 = results_2s[device_name]
                        r4 = results_4s[device_name]

                        metrics = DeviceMetrics(
                            subject=device_name,
                            frontal_1s={
                                'relaxation': r1['relaxation'],
                                'alpha': r1['alpha'],
                                'beta': r1['beta']
                            },
                            frontal_2s={
                                'relaxation': r2['relaxation'],
                                'alpha': r2['alpha'],
                                'beta': r2['beta']
                            },
                            frontal_4s={
                                'relaxation': r4['relaxation'],
                                'alpha': r4['alpha'],
                                'beta': r4['beta']
                            },
                            data_age_ms=quality_metrics[device_name]['data_age_ms'],
                            signal_quality=quality_metrics[device_name]['signal_quality'],
                            timestamp=time.time()
                        )

                        new_metrics[device_name] = metrics

                    # Step 6: Update shared state (thread-safe)
                    if new_metrics:
                        with self.metrics_lock:
                            self.latest_metrics.update(new_metrics)

                # Performance monitoring
                loop_time = (time.time() - loop_start) * 1000  # ms
                self.calc_loop_times.append(loop_time)
                if len(self.calc_loop_times) > 100:
                    self.calc_loop_times.pop(0)

                if loop_time > 100:
                    logger.warning(f"Calc loop exceeded budget: {loop_time:.1f}ms")

                # Rate limiting: Sleep to maintain 10 Hz
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.calc_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in calc loop: {e}", exc_info=True)
                time.sleep(0.1)  # Avoid tight loop on persistent errors

        logger.info("Calc thread stopped")

    def get_latest_metrics(self) -> Dict[str, DeviceMetrics]:
        """
        Get latest metrics for all devices (thread-safe).

        Called by UI broadcast loop to get current state.

        Returns:
            Dict mapping device_name -> DeviceMetrics
        """
        with self.metrics_lock:
            return self.latest_metrics.copy()

    def get_metrics_json(self) -> str:
        """
        Get latest metrics as JSON string for WebSocket broadcast.

        Converts DeviceMetrics to frontend-compatible format.

        Returns:
            JSON string matching frontend interface
        """
        metrics = self.get_latest_metrics()

        # Convert to frontend format
        output = []

        for device_name, m in metrics.items():
            output.append({
                'subject': m.subject,
                'frontal': {
                    '1s': m.frontal_1s,
                    '2s': m.frontal_2s,
                    '4s': m.frontal_4s
                },
                'quality': {
                    'data_age_ms': m.data_age_ms,
                    'signal_quality': m.signal_quality
                }
            })

        return json.dumps(output)

    def get_performance_stats(self) -> Dict[str, float]:
        """
        Get performance statistics for monitoring.

        Returns:
            Dict with calc_loop_avg_ms, calc_loop_max_ms, etc.
        """
        if not self.calc_loop_times:
            return {}

        return {
            'calc_loop_avg_ms': sum(self.calc_loop_times) / len(self.calc_loop_times),
            'calc_loop_max_ms': max(self.calc_loop_times),
            'calc_loop_min_ms': min(self.calc_loop_times),
            'calc_rate_hz': self.calc_rate_hz,
        }


# Helper function for UI broadcast loop (to be used in FastAPI)
async def ui_broadcast_loop(
    rate_controller: RateController,
    websocket_manager: 'WebSocketManager',
    broadcast_rate_hz: float = 10.0
):
    """
    Asyncio task for broadcasting metrics to WebSocket clients.

    This runs in FastAPI's asyncio event loop and bridges the calc thread
    (pure threading) with WebSocket clients (asyncio).

    Args:
        rate_controller: RateController instance
        websocket_manager: WebSocketManager instance from main.py
        broadcast_rate_hz: Broadcast rate in Hz (default 10.0 = 100ms intervals)

    Usage in main.py:
        @app.on_event("startup")
        async def startup():
            asyncio.create_task(
                ui_broadcast_loop(rate_controller, websocket_manager)
            )
    """
    logger.info(f"UI broadcast loop started ({broadcast_rate_hz} Hz)")

    broadcast_interval = 1.0 / broadcast_rate_hz

    while True:
        try:
            loop_start = time.time()

            # Get latest metrics (thread-safe read from shared state)
            metrics_json = rate_controller.get_metrics_json()

            # Broadcast to all connected WebSocket clients
            if websocket_manager.active_connections:
                await websocket_manager.broadcast(metrics_json)

            # Rate limiting
            elapsed = time.time() - loop_start
            sleep_time = max(0, broadcast_interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                logger.debug(f"UI broadcast exceeded budget: {elapsed*1000:.1f}ms")

        except Exception as e:
            logger.error(f"Error in UI broadcast loop: {e}", exc_info=True)
            await asyncio.sleep(0.1)
