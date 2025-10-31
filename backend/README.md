# ExG-Lab Backend

FastAPI backend for multi-device EEG neurofeedback platform.

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn main:app --reload

# Or use Python directly
python main.py
```

## API Endpoints

### Health & Status
- `GET /` - API root
- `GET /api/health` - Health check

### Device Management
- `GET /api/devices/scan` - Scan for Muse devices
- `POST /api/devices/connect` - Connect to a device
- `POST /api/devices/disconnect/{stream_name}` - Disconnect device

### Session Management
- `POST /api/session/start` - Start new session
- `POST /api/session/end` - End current session
- `POST /api/session/marker` - Insert event marker

### Real-time Data
- `WS /ws` - WebSocket for real-time metrics

## Documentation

- API docs (Swagger): http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Architecture

See [/docs/01-architecture-overview.md](../docs/01-architecture-overview.md) for complete system design.

## Current Status

**Version**: 1.0.0 (Initial skeleton)

**Implemented**:
- ✅ FastAPI application with CORS
- ✅ WebSocket endpoint for real-time metrics
- ✅ Mock data broadcaster (10 Hz)
- ✅ REST API endpoints (mock implementations)
- ✅ Basic error handling and logging

**TODO**:
- ⏳ Device manager (muselsl integration)
- ⏳ LSL stream management
- ⏳ Signal processing (FFT, multi-timescale)
- ⏳ Session data recording
- ⏳ Threading architecture (pull/calc/save threads)
- ⏳ Production error handling and recovery

## Development

```bash
# Install dev dependencies
pip install pytest pytest-asyncio httpx black

# Run tests
pytest

# Format code
black .
```
