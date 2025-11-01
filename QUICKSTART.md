# ExG-Lab Quick Start Guide

**Multi-Device EEG Neurofeedback Platform with LSL Integration**

---

## ✅ System Status

**Backend**: ✅ **PRODUCTION READY** (LSL integration complete)
**Frontend**: ✅ **PRODUCTION READY** (V0-generated UI)
**Hardware Testing**: ⏳ **PENDING** (requires Muse devices)

---

## 🚀 Quick Start (5 Minutes)

### 1. Start Backend

```bash
cd backend

# Start server (venv already created and dependencies installed)
./venv/bin/python main.py

# Expected output:
# 🚀 ExG-Lab Backend starting...
# ✓ Managers initialized
# INFO: Uvicorn running on http://0.0.0.0:8000
```

**Backend will be available at**: http://localhost:8000

### 2. Start Frontend

```bash
# Open new terminal
cd frontend

# Start Next.js dev server (dependencies already installed)
npm run dev

# Expected output:
# ▲ Next.js 16.0.0
# - Local: http://localhost:3000
```

**Frontend will be available at**: http://localhost:3000

### 3. Open Browser

Navigate to: **http://localhost:3000**

You should see the ExG-Lab interface with:
- Device management panel
- Protocol selector (3 built-in protocols)
- Live feedback display (will activate when devices connect)

---

## 🔌 Connect Muse Devices

### Without Hardware (Mock Mode)

The system starts successfully without devices. You can explore the UI and API:

```bash
# Test health endpoint
curl http://localhost:8000/api/health

# List available protocols
curl http://localhost:8000/api/protocols

# Response: 3 protocols available
# - Meditation Baseline (14 minutes)
# - Quick Test (30 seconds)
# - Eyes Open/Closed (4 minutes)
```

### With Real Hardware

1. **Turn on Muse headband** (LED should be solid white/blue)

2. **Scan for devices** (via UI or curl):
   ```bash
   curl http://localhost:8000/api/devices/scan
   ```

3. **Connect device** (via UI or curl):
   ```bash
   curl -X POST http://localhost:8000/api/devices/connect \
     -H "Content-Type: application/json" \
     -d '{
       "address": "00:55:DA:B3:3C:4F",
       "stream_name": "Muse_1"
     }'
   ```

4. **Frontend should start displaying real-time data** @ 10 Hz:
   - Three progress bars (1s, 2s, 4s timescales)
   - Relaxation score (alpha/beta ratio)
   - Signal quality indicators
   - Trend detection (IMPROVING ↗, STABLE ↔, DECLINING ↘)

---

## 📋 Built-in Protocols

### 1. Meditation Baseline (14 minutes)
```
Phase 1: Baseline (2 min) - Eyes closed, no feedback
Phase 2: Training (10 min) - Eyes closed, feedback enabled
Phase 3: Cooldown (2 min) - Eyes closed, no feedback
```

**Use case**: Standard meditation neurofeedback training

### 2. Quick Test (30 seconds)
```
Phase 1: Test (30 sec) - Feedback enabled
```

**Use case**: Validate system is working correctly

### 3. Eyes Open/Closed (4 minutes)
```
Phase 1: Eyes Open (1 min) - Looking at fixed point
Phase 2: Eyes Closed (1 min) - Relaxed
Phase 3: Eyes Open (1 min) - Looking at fixed point
Phase 4: Eyes Closed (1 min) - Relaxed
```

**Use case**: Classic EEG paradigm for validating alpha rhythm

---

## 🎯 Start a Session

### Via Frontend UI

1. Connect devices (Device Panel)
2. Select protocol (Protocol Selector)
3. Configure subjects (e.g., Muse_1 → P001, Muse_2 → P002)
4. Click "Start Session"
5. Follow on-screen instructions
6. Data automatically saved to `backend/data/sessions/{session_id}/`

### Via API

```bash
# Start session
curl -X POST http://localhost:8000/api/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "protocol_name": "Quick Test",
    "subject_ids": {"Muse_1": "P001"},
    "notes": "First test session",
    "experimenter": "John Doe"
  }'

# Check session status
curl http://localhost:8000/api/session/status

# End session
curl -X POST http://localhost:8000/api/session/end
```

---

## 📊 Access Recorded Data

### File Structure

```
backend/data/sessions/
└── {session_id}/
    ├── metadata.json          # Session info, timestamps, config
    ├── Muse_1_P001.csv        # Raw EEG data (256 Hz)
    ├── Muse_2_P002.csv        # Raw EEG data (256 Hz)
    └── ...
```

### CSV Format

```csv
timestamp,TP9,AF7,AF8,TP10
1234567890.123,12.5,8.3,7.1,11.2
1234567890.127,12.3,8.5,7.0,11.1
...
```

### List All Sessions

```bash
curl http://localhost:8000/api/sessions
```

### Get Session Metadata

```bash
curl http://localhost:8000/api/sessions/{session_id}
```

---

## 🔍 Monitoring & Debugging

### Check Backend Health

```bash
curl http://localhost:8000/api/health | jq
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": 1761898126.5875738,
  "websocket_clients": 1,
  "connected_devices": 2,
  "session_active": true,
  "performance": {
    "calc_loop_avg_ms": 38.5,
    "calc_loop_max_ms": 52.1
  }
}
```

### Check Device Status

```bash
curl http://localhost:8000/api/devices/status | jq
```

### View Backend Logs

```bash
# Backend outputs detailed logs to console
# Look for:
# - "✓ Device connected: Muse_1"
# - "✓ Session started: abc-123"
# - "✓ Recording started: abc-123"
# - Performance warnings if calc loop exceeds 100ms
```

---

## 📚 Architecture Overview

### Threading Model

```
PULL THREADS (20 Hz) → CALC THREAD (10 Hz) → UI THREAD (10 Hz)
     ↓                       ↓                      ↓
LSL buffers           FFT processing        WebSocket broadcast
Thread-safe           Parallel (4 devices)  Real-time feedback
```

### Processing Pipeline

```
Muse Device → Bluetooth → muselsl → LSL Stream → Pull Thread (20 Hz)
                                                       ↓
                                              Rolling Buffers
                                                       ↓
                                              Calc Thread (10 Hz)
                                                       ↓
                                          Multi-Scale FFT (1s, 2s, 4s)
                                                       ↓
                                        Relaxation Score (alpha/beta)
                                                       ↓
                                              WebSocket (10 Hz)
                                                       ↓
                                                   Frontend
```

### Tech Stack

**Backend**:
- Python 3.13
- FastAPI 0.120.3 (REST API + WebSocket)
- pylsl 1.17.6 (Lab Streaming Layer)
- muselsl 2.3.1 (Muse device interface)
- NumPy 1.26.4, SciPy 1.16.3 (signal processing)

**Frontend**:
- Next.js 16.0.0 (React framework)
- TypeScript 5.x
- shadcn/ui (component library)
- Recharts 2.15.4 (visualization)
- Tailwind CSS 4.x (styling)

---

## 🛠️ Troubleshooting

### Backend won't start

```bash
# Check if port 8000 is already in use
lsof -ti:8000

# Kill existing process if needed
kill -9 $(lsof -ti:8000)

# Restart backend
./venv/bin/python main.py
```

### Frontend won't start

```bash
# Check if port 3000 is already in use
lsof -ti:3000

# Kill existing process if needed
kill -9 $(lsof -ti:3000)

# Reinstall dependencies if needed
npm install --legacy-peer-deps

# Restart frontend
npm run dev
```

### Devices won't connect

```bash
# Check if muselsl is working
./venv/bin/muselsl list

# Check Bluetooth status
bluetoothctl

# Common issues:
# - Muse device not turned on (LED should be solid white/blue)
# - Muse device already connected to another app
# - Bluetooth adapter not working (try: sudo systemctl restart bluetooth)
```

### No real-time data

1. **Check WebSocket connection** (browser console):
   ```javascript
   // Should see: "WebSocket connected"
   ```

2. **Check backend logs**:
   ```
   # Should see:
   # "WebSocket client connected. Total clients: 1"
   # "✓ Rate controller and UI broadcast started"
   ```

3. **Check calc loop performance**:
   ```bash
   curl http://localhost:8000/api/health | jq '.performance'
   ```

### Data not saving

1. **Check if session started**:
   ```bash
   curl http://localhost:8000/api/session/status
   ```

2. **Check data directory exists**:
   ```bash
   ls -la backend/data/sessions/
   ```

3. **Check backend logs** for recording errors:
   ```
   # Should see:
   # "✓ Recording started: abc-123 (2 devices)"
   ```

---

## 📞 Support & Documentation

### Comprehensive Documentation

- **Architecture Overview**: `docs/06-architecture-overview.md`
- **muselsl Bugfixes**: `docs/07-muselsl-bugfixes.md`
- **LSL Integration Complete**: `docs/16-lsl-integration-complete.md`
- **V0 Integration Workflow**: `docs/13-v0-integration-workflow.md`

### Code Documentation

All modules have comprehensive docstrings:
```python
# Example: View LSLStreamHandler documentation
./venv/bin/python
>>> from src.devices import LSLStreamHandler
>>> help(LSLStreamHandler)
```

### API Documentation

FastAPI provides interactive docs at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🎯 Next Steps

### Testing Checklist

- [x] Backend starts successfully
- [x] Frontend starts successfully
- [x] API endpoints respond correctly
- [ ] Connect real Muse device
- [ ] Start session and validate recording
- [ ] Test multi-device setup (2-4 devices)
- [ ] Validate all 3 protocols work correctly

### Future Enhancements

- [ ] Add real-time signal quality filtering
- [ ] Implement event marker storage in CSV
- [ ] Add automatic phase transition timer
- [ ] Implement adaptive feedback thresholds
- [ ] Add real-time signal visualization plots
- [ ] Implement session templates for quick setup

---

**Ready to start? Just run:**

```bash
# Terminal 1: Start backend
cd backend && ./venv/bin/python main.py

# Terminal 2: Start frontend
cd frontend && npm run dev

# Browser: Open http://localhost:3000
```

**Status**: ✅ System ready for hardware testing!

---

**Last Updated**: 2025-10-31
**Version**: 1.0.0
