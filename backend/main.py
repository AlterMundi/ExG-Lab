"""
ExG-Lab Backend - Multi-Device EEG Neurofeedback Platform
FastAPI application with LSL integration for real-time neurofeedback

Architecture:
- Device Management: muselsl subprocess orchestration
- LSL Streaming: Thread-based pull threads @ 20 Hz
- Signal Processing: Multi-timescale FFT @ 10 Hz (parallel)
- Session Management: Protocol-based experimental sessions
- Data Recording: CSV export with metadata
- WebSocket Broadcast: Real-time feedback @ 10 Hz
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

# Import ExG-Lab modules
from src.devices import DeviceManager, LSLStreamHandler
from src.processing import MultiScaleProcessor, RateController, ui_broadcast_loop
from src.session import SessionManager, SessionPhase, DataRecorder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# Global State
# ==========================================

class ConnectionManager:
    """Manage WebSocket connections"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """Broadcast message to all connected clients"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                dead_connections.append(connection)

        # Remove dead connections
        for conn in dead_connections:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


# Global instances (initialized in lifespan)
ws_manager = ConnectionManager()
device_manager: Optional[DeviceManager] = None
processor: Optional[MultiScaleProcessor] = None
rate_controller: Optional[RateController] = None
session_manager: Optional[SessionManager] = None
data_recorder: Optional[DataRecorder] = None

# Stream handlers (device_name -> LSLStreamHandler)
stream_handlers: Dict[str, LSLStreamHandler] = {}

# Background tasks
ui_broadcast_task = None


# ==========================================
# Data Models
# ==========================================

class DeviceInfo(BaseModel):
    """Device information"""
    name: str
    address: str
    status: str
    battery: Optional[int] = None


class ConnectRequest(BaseModel):
    """Device connection request"""
    address: str
    stream_name: str


class SessionConfigRequest(BaseModel):
    """Session configuration request"""
    protocol_name: str
    subject_ids: Dict[str, str]  # device_name -> subject_id
    notes: str = ""
    experimenter: str = ""


class MarkerRequest(BaseModel):
    """Event marker request"""
    label: str
    timestamp: Optional[float] = None
    metadata: Optional[Dict] = None


# ==========================================
# Application Lifecycle
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global device_manager, processor, rate_controller, session_manager, data_recorder
    global ui_broadcast_task

    logger.info("🚀 ExG-Lab Backend starting...")

    # Initialize managers
    device_manager = DeviceManager()
    processor = MultiScaleProcessor(sample_rate=256.0, max_workers=4)
    data_recorder = DataRecorder(base_dir='./data/sessions')
    session_manager = SessionManager(devices=[], data_recorder=data_recorder)

    logger.info("✓ Managers initialized")

    # Note: RateController starts when devices connect
    # Note: UI broadcast loop starts when first device connects

    yield

    # Cleanup
    logger.info("🛑 ExG-Lab Backend shutting down...")

    # Cancel UI broadcast
    if ui_broadcast_task:
        ui_broadcast_task.cancel()
        try:
            await ui_broadcast_task
        except asyncio.CancelledError:
            pass

    # Stop rate controller
    if rate_controller and rate_controller.running:
        rate_controller.stop()

    # Stop all streams
    for handler in stream_handlers.values():
        handler.stop()

    # Stop session if active
    if session_manager and session_manager.current_session:
        session_manager.stop_session()

    # Shutdown processor
    if processor:
        processor.shutdown()

    logger.info("✓ Shutdown complete")


# ==========================================
# FastAPI Application
# ==========================================

app = FastAPI(
    title="ExG-Lab API",
    description="Multi-Device EEG Neurofeedback Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "status": "running",
        "version": "1.0.0",
        "service": "ExG-Lab Backend",
        "lsl_enabled": True
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    health = {
        "status": "healthy",
        "timestamp": time.time(),
        "websocket_clients": len(ws_manager.active_connections),
        "connected_devices": len(stream_handlers),
        "session_active": session_manager.current_session is not None if session_manager else False
    }

    # Add performance stats if available
    if rate_controller:
        health["performance"] = rate_controller.get_performance_stats()

    return health


@app.get("/api/devices/scan")
async def scan_devices():
    """Scan for available Muse devices"""
    logger.info("Scanning for devices...")

    try:
        devices = device_manager.scan_devices(timeout=5.0)

        return {
            "success": True,
            "devices": [
                {
                    "name": dev.name,
                    "address": dev.address,
                    "status": "available"
                }
                for dev in devices
            ]
        }

    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/connect")
async def connect_device(request: ConnectRequest):
    """Connect to a Muse device and start LSL stream"""
    global rate_controller, ui_broadcast_task

    logger.info(f"Connecting device: {request.stream_name} at {request.address}")

    try:
        # Start muselsl subprocess
        success = device_manager.connect_device(
            address=request.address,
            stream_name=request.stream_name
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to start muselsl stream")

        # Wait for LSL stream to appear (up to 10 seconds)
        await asyncio.sleep(2.0)  # Give muselsl time to establish connection

        # Create stream handler
        handler = LSLStreamHandler(stream_name=request.stream_name)
        stream_started = handler.start(timeout=10.0)

        if not stream_started:
            device_manager.disconnect_device(request.stream_name)
            raise HTTPException(status_code=500, detail="Failed to connect to LSL stream")

        # Store handler
        stream_handlers[request.stream_name] = handler

        # Update session manager available devices
        session_manager.devices = list(stream_handlers.keys())

        # Start rate controller if first device
        if len(stream_handlers) == 1:
            rate_controller = RateController(
                stream_handlers=stream_handlers,
                processor=processor,
                calc_rate_hz=10.0
            )
            rate_controller.start()

            # Start UI broadcast loop
            ui_broadcast_task = asyncio.create_task(
                ui_broadcast_loop(rate_controller, ws_manager, broadcast_rate_hz=10.0)
            )

            logger.info("✓ Rate controller and UI broadcast started")
        else:
            # Update rate controller with new handlers
            rate_controller.stream_handlers = stream_handlers

        logger.info(f"✓ Device connected: {request.stream_name}")

        return {
            "success": True,
            "stream_name": request.stream_name,
            "address": request.address,
            "total_devices": len(stream_handlers)
        }

    except Exception as e:
        logger.error(f"Error connecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/disconnect/{stream_name}")
async def disconnect_device(stream_name: str):
    """Disconnect a device"""
    global rate_controller

    logger.info(f"Disconnecting device: {stream_name}")

    try:
        # Stop stream handler
        if stream_name in stream_handlers:
            stream_handlers[stream_name].stop()
            del stream_handlers[stream_name]

        # Stop muselsl subprocess
        device_manager.disconnect_device(stream_name)

        # Update session manager
        session_manager.devices = list(stream_handlers.keys())

        # Stop rate controller if no devices left
        if len(stream_handlers) == 0 and rate_controller:
            rate_controller.stop()
            rate_controller = None

            # Cancel UI broadcast
            if ui_broadcast_task:
                ui_broadcast_task.cancel()

            logger.info("✓ Rate controller stopped (no devices)")
        elif rate_controller:
            # Update rate controller handlers
            rate_controller.stream_handlers = stream_handlers

        return {
            "success": True,
            "stream_name": stream_name,
            "remaining_devices": len(stream_handlers)
        }

    except Exception as e:
        logger.error(f"Error disconnecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/status")
async def get_device_status():
    """Get status of all connected devices"""
    status = {}

    for device_name, handler in stream_handlers.items():
        status[device_name] = handler.get_stream_info()

    return {
        "success": True,
        "devices": status
    }


@app.get("/api/protocols")
async def list_protocols():
    """List available experimental protocols"""
    protocols = session_manager.list_protocols()

    return {
        "success": True,
        "protocols": protocols
    }


@app.post("/api/session/start")
async def start_session(config: SessionConfigRequest):
    """Start a new experimental session"""
    logger.info(f"Starting session with protocol: {config.protocol_name}")

    try:
        session_id = session_manager.start_session(
            protocol_name=config.protocol_name,
            subject_ids=config.subject_ids,
            notes=config.notes,
            experimenter=config.experimenter
        )

        if session_id is None:
            raise HTTPException(status_code=400, detail="Failed to start session")

        return {
            "success": True,
            "session_id": session_id,
            "status": "active"
        }

    except Exception as e:
        logger.error(f"Error starting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/end")
async def end_session():
    """End current session"""
    logger.info("Ending session")

    try:
        success = session_manager.stop_session()

        if not success:
            raise HTTPException(status_code=400, detail="No active session")

        return {
            "success": True
        }

    except Exception as e:
        logger.error(f"Error ending session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/status")
async def get_session_status():
    """Get current session status"""
    status = session_manager.get_session_status()

    return {
        "success": True,
        "is_active": status.is_active,
        "session_id": status.session_id,
        "protocol_name": status.protocol_name,
        "current_phase": status.current_phase.value,
        "phase_name": status.phase_name,
        "elapsed_seconds": status.elapsed_seconds,
        "remaining_seconds": status.remaining_seconds,
        "devices": status.devices,
        "subject_ids": status.subject_ids,
        "feedback_enabled": session_manager.is_feedback_enabled(),
        "instructions": session_manager.get_current_instructions()
    }


@app.post("/api/session/marker")
async def insert_marker(marker: MarkerRequest):
    """Insert event marker"""
    logger.info(f"Inserting marker: {marker.label}")

    # TODO: Implement marker storage in data recorder
    # For now, just log it

    return {
        "success": True,
        "timestamp": marker.timestamp or time.time()
    }


@app.get("/api/sessions")
async def list_sessions():
    """List all recorded sessions"""
    sessions = data_recorder.list_sessions()

    return {
        "success": True,
        "sessions": sessions
    }


@app.get("/api/sessions/{session_id}")
async def get_session_metadata(session_id: str):
    """Get metadata for specific session"""
    metadata = data_recorder.get_session_metadata(session_id)

    if metadata is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "metadata": metadata
    }


# ==========================================
# WebSocket Endpoint
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time metrics"""
    await ws_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

            # TODO: Handle client messages (e.g., parameter adjustments)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ==========================================
# Run Application
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
