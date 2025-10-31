"""
ExG-Lab Backend - Multi-Device EEG Neurofeedback Platform
FastAPI application with WebSocket support for real-time metrics
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# Global State (will be moved to proper managers)
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
            self.active_connections.remove(conn)


# Global instances
ws_manager = ConnectionManager()
mock_data_task = None


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


class SessionConfig(BaseModel):
    """Session configuration"""
    devices: List[str]
    participants: List[str]
    protocol: str


# ==========================================
# Application Lifecycle
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 ExG-Lab Backend starting...")

    # Start mock data broadcaster
    global mock_data_task
    mock_data_task = asyncio.create_task(mock_data_broadcaster())

    yield

    # Cleanup
    logger.info("🛑 ExG-Lab Backend shutting down...")
    if mock_data_task:
        mock_data_task.cancel()


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
# Mock Data Generator (temporary)
# ==========================================

async def mock_data_broadcaster():
    """Broadcast mock metrics to all connected WebSocket clients"""
    import random

    # Initial values
    metrics_state = {
        "Muse_1": {
            "1s": 2.0,
            "2s": 1.8,
            "4s": 1.6
        },
        "Muse_2": {
            "1s": 1.5,
            "2s": 1.6,
            "4s": 1.7
        }
    }

    while True:
        try:
            if ws_manager.active_connections:
                # Random walk the metrics
                for device in metrics_state:
                    for timescale in metrics_state[device]:
                        # Random walk: ±0.05
                        change = (random.random() - 0.5) * 0.1
                        metrics_state[device][timescale] += change
                        # Clamp to 0-4 range
                        metrics_state[device][timescale] = max(0.5, min(3.5, metrics_state[device][timescale]))

                # Build message
                message = {
                    "type": "feedback_update",
                    "timestamp": time.time(),
                    "devices": {
                        "Muse_1": {
                            "subject": "Alice",
                            "frontal": {
                                "1s": {
                                    "relaxation": round(metrics_state["Muse_1"]["1s"], 2),
                                    "alpha": 0.45,
                                    "beta": 0.32
                                },
                                "2s": {
                                    "relaxation": round(metrics_state["Muse_1"]["2s"], 2),
                                    "alpha": 0.42,
                                    "beta": 0.35
                                },
                                "4s": {
                                    "relaxation": round(metrics_state["Muse_1"]["4s"], 2),
                                    "alpha": 0.38,
                                    "beta": 0.37
                                }
                            },
                            "quality": {
                                "data_age_ms": random.randint(30, 80),
                                "signal_quality": {
                                    "TP9": 0.95,
                                    "AF7": 0.88,
                                    "AF8": 0.92,
                                    "TP10": 0.97
                                }
                            }
                        },
                        "Muse_2": {
                            "subject": "Bob",
                            "frontal": {
                                "1s": {
                                    "relaxation": round(metrics_state["Muse_2"]["1s"], 2),
                                    "alpha": 0.35,
                                    "beta": 0.41
                                },
                                "2s": {
                                    "relaxation": round(metrics_state["Muse_2"]["2s"], 2),
                                    "alpha": 0.36,
                                    "beta": 0.40
                                },
                                "4s": {
                                    "relaxation": round(metrics_state["Muse_2"]["4s"], 2),
                                    "alpha": 0.38,
                                    "beta": 0.38
                                }
                            },
                            "quality": {
                                "data_age_ms": random.randint(40, 90),
                                "signal_quality": {
                                    "TP9": 0.91,
                                    "AF7": 0.85,
                                    "AF8": 0.89,
                                    "TP10": 0.93
                                }
                            }
                        }
                    }
                }

                await ws_manager.broadcast(json.dumps(message))

            # Run at 10 Hz
            await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in mock data broadcaster: {e}")
            await asyncio.sleep(1)


# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "status": "running",
        "version": "1.0.0",
        "service": "ExG-Lab Backend"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "websocket_clients": len(ws_manager.active_connections)
    }


@app.get("/api/devices/scan")
async def scan_devices():
    """Scan for available Muse devices"""
    # TODO: Implement real muselsl scan with bugfixes
    # For now, return mock devices
    logger.info("Scanning for devices (mock)")

    mock_devices = [
        {
            "name": "Muse S - 3C4F",
            "address": "00:55:DA:B3:3C:4F",
            "status": "available",
            "battery": 87
        },
        {
            "name": "Muse S - 7A21",
            "address": "00:55:DA:B3:7A:21",
            "status": "available",
            "battery": 72
        },
        {
            "name": "Muse S - 9B15",
            "address": "00:55:DA:B3:9B:15",
            "status": "available",
            "battery": 94
        }
    ]

    return {"devices": mock_devices}


@app.post("/api/devices/connect")
async def connect_device(request: ConnectRequest):
    """Connect to a Muse device"""
    logger.info(f"Connecting device: {request.stream_name} at {request.address}")

    # TODO: Implement real muselsl stream connection
    # For now, simulate success
    await asyncio.sleep(0.5)  # Simulate connection delay

    return {
        "success": True,
        "stream_name": request.stream_name,
        "address": request.address
    }


@app.post("/api/devices/disconnect/{stream_name}")
async def disconnect_device(stream_name: str):
    """Disconnect a device"""
    logger.info(f"Disconnecting device: {stream_name}")

    # TODO: Implement real device disconnection
    return {"success": True, "stream_name": stream_name}


@app.post("/api/session/start")
async def start_session(config: SessionConfig):
    """Start a new session"""
    session_id = f"session_{int(time.time())}"
    logger.info(f"Starting session: {session_id}")
    logger.info(f"  Devices: {config.devices}")
    logger.info(f"  Participants: {config.participants}")
    logger.info(f"  Protocol: {config.protocol}")

    # TODO: Implement real session management
    return {
        "session_id": session_id,
        "status": "active"
    }


@app.post("/api/session/end")
async def end_session():
    """End current session"""
    logger.info("Ending session")

    # TODO: Save session data
    session_dir = f"./data/session_{int(time.time())}"

    return {
        "success": True,
        "session_dir": session_dir
    }


@app.post("/api/session/marker")
async def insert_marker(marker: dict):
    """Insert event marker"""
    logger.info(f"Inserting marker: {marker.get('label')}")

    # TODO: Save marker to session data
    return {"success": True}


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
