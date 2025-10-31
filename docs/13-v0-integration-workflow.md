# V0 Integration Workflow: From Generation to Production

## Overview

This guide covers the complete process of using V0 to generate the ExG-Lab frontend and integrating it with the Python backend.

## Phase 1: Generate UI with V0

### Step 1.1: Create Components in V0

**Process**:
1. Go to https://v0.dev
2. Paste the comprehensive prompt from `docs/12-v0-prompt-comprehensive.md`
3. V0 will generate React components with:
   - shadcn/ui components
   - Tailwind CSS styling
   - TypeScript interfaces
   - Mock data and interactions

**Expected Output**:
- Interactive preview of the entire UI
- Downloadable code (components, hooks, types)
- Pre-configured package.json

### Step 1.2: Iterate and Refine

**Common iterations**:
- "Make the feedback bars larger and more prominent"
- "Add a collapsible chart to each device card"
- "Change the protocol selector to a dropdown instead of cards"
- "Add a dark mode toggle"

**Export when satisfied**:
- Click "Export" or "Download Code" in V0
- You'll get a ZIP file or can copy individual components

## Phase 2: Set Up Frontend Project Structure

### Step 2.1: Create Next.js Project in Repo

```bash
cd /home/fede/REPOS/ExG-Lab

# Create frontend directory
npx create-next-app@latest frontend --typescript --tailwind --app

# Answer prompts:
# ✔ Would you like to use ESLint? … Yes
# ✔ Would you like to use Tailwind CSS? … Yes
# ✔ Would you like to use `src/` directory? … Yes
# ✔ Would you like to use App Router? … Yes
# ✔ Would you like to customize the default import alias (@/*)? … No
```

### Step 2.2: Install shadcn/ui

```bash
cd frontend

# Initialize shadcn/ui
npx shadcn-ui@latest init

# Answer prompts:
# ✔ Which style would you like to use? › Default
# ✔ Which color would you like to use as base color? › Slate
# ✔ Would you like to use CSS variables for colors? … yes

# Install required components
npx shadcn-ui@latest add button card badge input progress
npx shadcn-ui@latest add select separator toast tabs
```

### Step 2.3: Install Additional Dependencies

```bash
# Charts
npm install recharts

# Icons
npm install lucide-react

# State management (optional, start with Context)
npm install zustand  # or use React Context

# WebSocket (native, but you might want reconnecting-websocket)
npm install reconnecting-websocket

# Utilities
npm install clsx tailwind-merge class-variance-authority
```

### Step 2.4: Project Structure

```
ExG-Lab/
├── backend/                    # Python backend (to be created)
│   ├── main.py                # FastAPI app
│   ├── requirements.txt
│   ├── src/
│   │   ├── devices/           # Device management
│   │   ├── processing/        # Signal processing
│   │   ├── session/           # Session management
│   │   └── websocket/         # WebSocket handlers
│   └── tests/
│
├── frontend/                   # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx     # Root layout
│   │   │   ├── page.tsx       # Main page
│   │   │   └── globals.css    # Global styles
│   │   ├── components/        # V0 components go here
│   │   │   ├── ui/            # shadcn/ui base components
│   │   │   ├── DevicePanel.tsx
│   │   │   ├── ProtocolSelector.tsx
│   │   │   ├── SessionConfig.tsx
│   │   │   ├── FeedbackDisplay.tsx
│   │   │   ├── SessionMonitor.tsx
│   │   │   └── Header.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useDeviceManager.ts
│   │   │   ├── useSessionManager.ts
│   │   │   └── useThrottledCallback.ts
│   │   ├── lib/
│   │   │   ├── api.ts         # Backend API client
│   │   │   ├── utils.ts       # Utilities
│   │   │   └── protocols.ts   # Protocol templates
│   │   ├── types/
│   │   │   └── index.ts       # TypeScript types
│   │   └── context/
│   │       └── AppContext.tsx # Global state (if using Context)
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── next.config.js
│
├── data/                       # Session recordings (gitignored)
├── docs/                       # Documentation
└── README.md
```

## Phase 3: Extract and Integrate V0 Code

### Step 3.1: Copy V0 Components

**From V0 export, copy files to your project**:

```bash
cd /home/fede/REPOS/ExG-Lab/frontend

# V0 typically exports to a single file or multiple files
# Extract each component to appropriate location

# Example: If V0 gives you a single page.tsx with everything
# You'll need to split it into separate components
```

**Manual extraction process**:

1. **Identify component boundaries** in V0's code
2. **Extract to separate files**:
   ```typescript
   // src/components/DevicePanel.tsx
   export function DevicePanel() { ... }

   // src/components/ProtocolSelector.tsx
   export function ProtocolSelector() { ... }
   ```

3. **Extract shared types**:
   ```typescript
   // src/types/index.ts
   export interface Device { ... }
   export interface SessionConfig { ... }
   export interface ExperimentalProtocol { ... }
   ```

4. **Extract hooks**:
   ```typescript
   // src/hooks/useWebSocket.ts
   export function useWebSocket(url: string) { ... }
   ```

### Step 3.2: Replace Mock Data with Real API Calls

**V0 will have mock data like**:
```typescript
// V0's mock version
const mockDevices = [
  { name: "Muse S - 3C4F", mac: "00:55:DA:B3:3C4F", ... }
];
```

**Replace with API client**:
```typescript
// src/lib/api.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = {
  async scanDevices() {
    const res = await fetch(`${BASE_URL}/api/devices/scan`);
    if (!res.ok) throw new Error('Failed to scan devices');
    return res.json();
  },

  async connectDevice(address: string, streamName: string) {
    const res = await fetch(`${BASE_URL}/api/devices/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, stream_name: streamName })
    });
    return res.json();
  },

  // ... other endpoints
};

// src/components/DevicePanel.tsx
import { api } from '@/lib/api';

export function DevicePanel() {
  const [devices, setDevices] = useState<Device[]>([]);

  const scanForDevices = async () => {
    try {
      const result = await api.scanDevices();
      setDevices(result.devices);
    } catch (error) {
      toast.error('Failed to scan devices');
    }
  };

  // ...
}
```

### Step 3.3: Implement Real WebSocket Connection

**Replace V0's mock WebSocket**:

```typescript
// src/hooks/useWebSocket.ts
import { useEffect, useState, useRef } from 'react';
import ReconnectingWebSocket from 'reconnecting-websocket';

interface WebSocketMessage {
  type: string;
  timestamp: number;
  devices: Record<string, any>;
}

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, any>>({});
  const ws = useRef<ReconnectingWebSocket | null>(null);

  useEffect(() => {
    // Create reconnecting WebSocket
    ws.current = new ReconnectingWebSocket(url, [], {
      connectionTimeout: 5000,
      maxRetries: 10,
      debug: process.env.NODE_ENV === 'development'
    });

    ws.current.addEventListener('open', () => {
      console.log('[WS] Connected');
      setIsConnected(true);
    });

    ws.current.addEventListener('message', (event) => {
      const data: WebSocketMessage = JSON.parse(event.data);

      if (data.type === 'feedback_update') {
        setMetrics(data.devices);
      }
    });

    ws.current.addEventListener('close', () => {
      console.log('[WS] Disconnected');
      setIsConnected(false);
    });

    ws.current.addEventListener('error', (error) => {
      console.error('[WS] Error:', error);
    });

    return () => {
      ws.current?.close();
    };
  }, [url]);

  const sendMessage = (message: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  };

  return { isConnected, metrics, sendMessage };
}
```

### Step 3.4: Configure Environment Variables

```bash
# frontend/.env.local (development)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws

# frontend/.env.production (production)
NEXT_PUBLIC_API_URL=https://api.exglab.yourdomain.com
NEXT_PUBLIC_WS_URL=wss://api.exglab.yourdomain.com/ws
```

**Add to .gitignore**:
```bash
# frontend/.gitignore
.env.local
.env*.local
```

## Phase 4: Backend Development

### Step 4.1: Create Backend Structure

```bash
cd /home/fede/REPOS/ExG-Lab

# Create backend directory
mkdir -p backend/src/{devices,processing,session,websocket}
touch backend/main.py
touch backend/requirements.txt
```

### Step 4.2: Install Backend Dependencies

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
cat > requirements.txt << EOF
fastapi==0.104.1
uvicorn[standard]==0.24.0
websockets==12.0
python-multipart==0.0.6
pylsl==1.16.2
numpy==1.26.2
scipy==1.11.4
pandas==2.1.3
pydantic==2.5.0
python-dotenv==1.0.0
EOF

pip install -r requirements.txt
```

### Step 4.3: Create FastAPI Backend Skeleton

```python
# backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Dict, List
import logging

from src.devices.manager import DeviceManager
from src.session.manager import SessionManager
from src.websocket.connection_manager import ConnectionManager

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global managers
device_manager = DeviceManager()
session_manager = SessionManager()
ws_manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting ExG-Lab backend...")

    # Start background tasks
    asyncio.create_task(metrics_broadcast_loop())

    yield

    # Cleanup
    logger.info("Shutting down ExG-Lab backend...")
    await session_manager.end_session()
    device_manager.disconnect_all()

app = FastAPI(
    title="ExG-Lab API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# REST API Endpoints
# ============================================

@app.get("/")
async def root():
    return {"status": "ExG-Lab API running", "version": "1.0.0"}

@app.get("/api/devices/scan")
async def scan_devices():
    """Scan for available Muse devices"""
    devices = device_manager.scan()
    return {"devices": devices}

@app.post("/api/devices/connect")
async def connect_device(request: dict):
    """Connect to a Muse device"""
    address = request.get("address")
    stream_name = request.get("stream_name")

    success = device_manager.connect(address, stream_name)
    return {"success": success, "stream_name": stream_name}

@app.post("/api/devices/disconnect/{stream_name}")
async def disconnect_device(stream_name: str):
    """Disconnect a device"""
    success = device_manager.disconnect(stream_name)
    return {"success": success}

@app.post("/api/session/start")
async def start_session(config: dict):
    """Start a new session"""
    session_id = await session_manager.start_session(config)
    return {"session_id": session_id}

@app.post("/api/session/end")
async def end_session():
    """End current session"""
    session_dir = await session_manager.end_session()
    return {"session_dir": session_dir}

@app.post("/api/session/marker")
async def insert_marker(marker: dict):
    """Insert event marker"""
    await session_manager.insert_marker(
        label=marker.get("label"),
        metadata=marker.get("metadata", {})
    )
    return {"success": True}

# ============================================
# WebSocket Endpoint
# ============================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time metrics"""
    await ws_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive and receive client messages
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("Client disconnected")

# ============================================
# Background Tasks
# ============================================

async def metrics_broadcast_loop():
    """Broadcast metrics to all connected WebSocket clients"""
    while True:
        try:
            # Get latest metrics from session manager
            metrics = session_manager.get_latest_metrics()

            if metrics and ws_manager.active_connections:
                message = {
                    "type": "feedback_update",
                    "timestamp": metrics.get("timestamp"),
                    "devices": metrics.get("devices", {})
                }

                await ws_manager.broadcast(json.dumps(message))

            # Run at 10 Hz
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in metrics broadcast: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Step 4.4: Create Supporting Backend Modules

```python
# backend/src/websocket/connection_manager.py
from fastapi import WebSocket
from typing import List

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass
```

```python
# backend/src/devices/manager.py
from typing import List, Dict
import subprocess
import logging

logger = logging.getLogger(__name__)

class DeviceManager:
    def __init__(self):
        self.connected_devices: Dict[str, subprocess.Popen] = {}

    def scan(self) -> List[Dict]:
        """Scan for available Muse devices using muselsl"""
        # TODO: Implement muselsl list with bugfixes
        # For now, return mock data
        return [
            {
                "name": "Muse S - 3C4F",
                "address": "00:55:DA:B3:3C4F",
                "status": "available"
            }
        ]

    def connect(self, address: str, stream_name: str) -> bool:
        """Start muselsl stream for device"""
        try:
            # Start muselsl stream subprocess
            # muselsl stream --address {address} --name {stream_name}
            logger.info(f"Connecting {stream_name} at {address}")
            # TODO: Implement actual connection
            return True
        except Exception as e:
            logger.error(f"Failed to connect device: {e}")
            return False

    def disconnect(self, stream_name: str) -> bool:
        """Stop muselsl stream"""
        # TODO: Terminate subprocess
        return True

    def disconnect_all(self):
        """Disconnect all devices"""
        for stream_name in list(self.connected_devices.keys()):
            self.disconnect(stream_name)
```

```python
# backend/src/session/manager.py
from typing import Dict, Optional
import time
import logging

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        self.active_session: Optional[Dict] = None
        self.current_phase: int = 0
        self.metrics_cache: Dict = {}

    async def start_session(self, config: Dict) -> str:
        """Start new session with protocol configuration"""
        session_id = f"session_{int(time.time())}"

        self.active_session = {
            "session_id": session_id,
            "config": config,
            "start_time": time.time()
        }

        logger.info(f"Started session: {session_id}")
        return session_id

    async def end_session(self) -> str:
        """End current session and save data"""
        if not self.active_session:
            return ""

        session_dir = f"./data/{self.active_session['session_id']}"
        # TODO: Save data to disk

        logger.info(f"Ended session: {self.active_session['session_id']}")
        self.active_session = None

        return session_dir

    async def insert_marker(self, label: str, metadata: Dict):
        """Insert event marker"""
        # TODO: Implement marker storage
        logger.info(f"Marker: {label}")

    def get_latest_metrics(self) -> Dict:
        """Get latest computed metrics"""
        # TODO: Return actual metrics from processing thread
        return self.metrics_cache
```

## Phase 5: Development Workflow

### Step 5.1: Run Both Frontend and Backend

**Terminal 1 - Backend**:
```bash
cd /home/fede/REPOS/ExG-Lab/backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend**:
```bash
cd /home/fede/REPOS/ExG-Lab/frontend
npm run dev
```

**Access**:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs (Swagger UI)

### Step 5.2: Development Iteration Loop

```
1. Make changes to frontend components (auto-reload)
2. Test in browser
3. If API changes needed, update backend
4. Backend auto-reloads (--reload flag)
5. Test integration
6. Commit changes
```

### Step 5.3: Debug WebSocket Connection

**Browser DevTools** (Chrome/Firefox):
```javascript
// Open DevTools Console
// Check WebSocket connection
ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

**Backend logs**:
```bash
# Increase logging verbosity
uvicorn main:app --reload --log-level debug
```

## Phase 6: Testing

### Step 6.1: Frontend Testing

```bash
cd frontend

# Install testing dependencies
npm install -D @testing-library/react @testing-library/jest-dom vitest

# Test example
# frontend/src/components/__tests__/FeedbackDisplay.test.tsx
import { render, screen } from '@testing-library/react';
import { FeedbackDisplay } from '../FeedbackDisplay';

test('shows improving trend when 1s > 2s > 4s', () => {
  const mockMetrics = {
    '1s': { relaxation: 2.5 },
    '2s': { relaxation: 2.0 },
    '4s': { relaxation: 1.5 }
  };

  render(<FeedbackDisplay deviceName="Muse_1" metrics={mockMetrics} />);

  expect(screen.getByText(/IMPROVING/i)).toBeInTheDocument();
});
```

### Step 6.2: Backend Testing

```bash
cd backend

# Install testing dependencies
pip install pytest pytest-asyncio httpx

# Test example
# backend/tests/test_api.py
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_scan_devices():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/devices/scan")
        assert response.status_code == 200
        assert "devices" in response.json()
```

## Phase 7: Production Deployment

### Step 7.1: Build Frontend

```bash
cd frontend
npm run build

# Output goes to frontend/.next
# Can be served by:
npm run start  # Production server on port 3000
```

### Step 7.2: Containerize with Docker

```dockerfile
# ExG-Lab/docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - PYTHONUNBUFFERED=1

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
      - NEXT_PUBLIC_WS_URL=ws://backend:8000/ws
```

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

CMD ["npm", "run", "start"]
```

**Run everything**:
```bash
docker-compose up -d
```

## Summary: Quick Reference

### Development Commands

```bash
# Start development
cd backend && source venv/bin/activate && uvicorn main:app --reload &
cd frontend && npm run dev

# Run tests
cd frontend && npm test
cd backend && pytest

# Build production
cd frontend && npm run build
cd backend && # Already ready for production

# Deploy
docker-compose up -d
```

### File Checklist

- [ ] Frontend components from V0 extracted to `frontend/src/components/`
- [ ] Types extracted to `frontend/src/types/index.ts`
- [ ] API client created at `frontend/src/lib/api.ts`
- [ ] WebSocket hook created at `frontend/src/hooks/useWebSocket.ts`
- [ ] Environment variables configured in `.env.local`
- [ ] Backend API skeleton created at `backend/main.py`
- [ ] CORS configured to allow frontend origin
- [ ] WebSocket endpoint implemented
- [ ] Device manager stubbed out
- [ ] Session manager stubbed out
- [ ] Both servers running and communicating

---

**Next Document**: Implementation details for signal processing threads and LSL integration
