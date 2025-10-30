# UI Design Guide

## Frontend Architecture

### Tech Stack

```
Frontend Framework: React + Next.js (via V0/Vercel)
UI Components: shadcn/ui
Styling: Tailwind CSS
Charts: Recharts or Chart.js
WebSocket: native WebSocket API
State Management: React Context + Hooks
```

### Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── DevicePanel.tsx      # Device connection/status
│   │   ├── DeviceCard.tsx       # Individual device display
│   │   ├── LiveMonitor.tsx      # Real-time EEG visualization
│   │   ├── FeedbackDisplay.tsx  # Multi-timescale feedback
│   │   ├── SessionControl.tsx   # Start/stop recording
│   │   └── MetricsChart.tsx     # Time-series charts
│   ├── hooks/
│   │   ├── useWebSocket.ts      # WebSocket connection
│   │   ├── useDeviceManager.ts  # Device state management
│   │   └── useSessionManager.ts # Session control
│   ├── lib/
│   │   ├── api.ts               # Backend API calls
│   │   └── utils.ts             # Utilities
│   └── types/
│       └── index.ts             # TypeScript types
├── package.json
└── tsconfig.json
```

## Core Components

### 1. WebSocket Hook

**src/hooks/useWebSocket.ts**:
```typescript
import { useEffect, useState, useCallback, useRef } from 'react';

interface WebSocketMessage {
  timestamp: number;
  devices: Record<string, any>;
}

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [metrics, setMetrics] = useState<Record<string, any>>({});

  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Create WebSocket connection
    ws.current = new WebSocket(url);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.current.onmessage = (event) => {
      const data: WebSocketMessage = JSON.parse(event.data);
      setLastMessage(data);
      setMetrics(data.devices);
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    // Cleanup
    return () => {
      ws.current?.close();
    };
  }, [url]);

  const sendMessage = useCallback((message: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  }, []);

  return {
    isConnected,
    lastMessage,
    metrics,
    sendMessage
  };
}
```

### 2. API Client

**src/lib/api.ts**:
```typescript
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Device {
  name: string;
  address: string;
  status: string;
}

export interface SessionConfig {
  devices: string[];
  participants: string[];
  protocol: string;
}

export const api = {
  // Device management
  scanDevices: async (): Promise<Device[]> => {
    const response = await fetch(`${BASE_URL}/devices/scan`);
    const data = await response.json();
    return data.devices;
  },

  connectDevice: async (address: string, streamName: string): Promise<boolean> => {
    const response = await fetch(`${BASE_URL}/devices/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, stream_name: streamName })
    });
    const data = await response.json();
    return data.success;
  },

  disconnectDevice: async (streamName: string): Promise<boolean> => {
    const response = await fetch(`${BASE_URL}/devices/disconnect/${streamName}`, {
      method: 'POST'
    });
    const data = await response.json();
    return data.success;
  },

  // Session management
  startSession: async (config: SessionConfig): Promise<string> => {
    const response = await fetch(`${BASE_URL}/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    const data = await response.json();
    return data.session_id;
  },

  endSession: async (): Promise<string> => {
    const response = await fetch(`${BASE_URL}/session/end`, {
      method: 'POST'
    });
    const data = await response.json();
    return data.session_dir;
  }
};
```

### 3. Device Panel Component

**src/components/DevicePanel.tsx**:
```typescript
'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api, Device } from '@/lib/api';

export function DevicePanel() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [connectedDevices, setConnectedDevices] = useState<string[]>([]);
  const [scanning, setScanning] = useState(false);

  const scanForDevices = async () => {
    setScanning(true);
    try {
      const foundDevices = await api.scanDevices();
      setDevices(foundDevices);
    } catch (error) {
      console.error('Scan failed:', error);
    } finally {
      setScanning(false);
    }
  };

  const connectDevice = async (device: Device, index: number) => {
    const streamName = `Muse_${index + 1}`;
    const success = await api.connectDevice(device.address, streamName);

    if (success) {
      setConnectedDevices([...connectedDevices, streamName]);
    }
  };

  const disconnectDevice = async (streamName: string) => {
    await api.disconnectDevice(streamName);
    setConnectedDevices(connectedDevices.filter(d => d !== streamName));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Devices</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <Button
            onClick={scanForDevices}
            disabled={scanning}
            className="w-full"
          >
            {scanning ? 'Scanning...' : 'Scan for Devices'}
          </Button>

          <div className="space-y-2">
            {devices.map((device, index) => {
              const streamName = `Muse_${index + 1}`;
              const isConnected = connectedDevices.includes(streamName);

              return (
                <div
                  key={device.address}
                  className="flex items-center justify-between p-3 border rounded"
                >
                  <div>
                    <div className="font-medium">{device.name}</div>
                    <div className="text-sm text-gray-500">
                      {device.address}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge variant={isConnected ? 'success' : 'secondary'}>
                      {isConnected ? 'Connected' : 'Available'}
                    </Badge>

                    {isConnected ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => disconnectDevice(streamName)}
                      >
                        Disconnect
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => connectDevice(device, index)}
                      >
                        Connect
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

### 4. Multi-Timescale Feedback Display

**src/components/FeedbackDisplay.tsx**:
```typescript
'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

interface TimescaleMetrics {
  '1s': { relaxation: number };
  '2s': { relaxation: number };
  '4s': { relaxation: number };
}

interface FeedbackDisplayProps {
  deviceName: string;
  metrics: TimescaleMetrics | null;
}

export function FeedbackDisplay({ deviceName, metrics }: FeedbackDisplayProps) {
  if (!metrics) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{deviceName}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-gray-500">Waiting for data...</div>
        </CardContent>
      </Card>
    );
  }

  const r1 = metrics['1s']?.relaxation || 0;
  const r2 = metrics['2s']?.relaxation || 0;
  const r4 = metrics['4s']?.relaxation || 0;

  // Detect pattern
  let trend = 'STABLE';
  let trendColor = 'bg-gray-500';
  let message = 'Maintaining state';

  if (r1 > r2 && r2 > r4) {
    trend = 'IMPROVING';
    trendColor = 'bg-green-500';
    message = "You're getting more relaxed!";
  } else if (r1 < r2 && r2 < r4) {
    trend = 'DECLINING';
    trendColor = 'bg-red-500';
    message = "Relaxation decreasing";
  } else if (Math.abs(r1 - r4) < 0.3) {
    trend = 'STABLE';
    trendColor = 'bg-blue-500';
    message = 'Nice and steady';
  }

  // Normalize for display (0-100)
  const normalize = (value: number) => Math.min(100, value * 25);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{deviceName}</CardTitle>
          <Badge className={trendColor}>{trend}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Trend message */}
          <div className="text-center text-lg font-medium">
            {message}
          </div>

          {/* Three timescales */}
          <div className="space-y-4">
            {/* 1s - Fast */}
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-green-600">
                  Fast (1s)
                </span>
                <span className="text-sm">{r1.toFixed(2)}</span>
              </div>
              <Progress value={normalize(r1)} className="h-3 bg-green-200" />
            </div>

            {/* 2s - Balanced */}
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-yellow-600">
                  Balanced (2s)
                </span>
                <span className="text-sm">{r2.toFixed(2)}</span>
              </div>
              <Progress value={normalize(r2)} className="h-3 bg-yellow-200" />
            </div>

            {/* 4s - Stable */}
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-blue-600">
                  Stable (4s)
                </span>
                <span className="text-sm">{r4.toFixed(2)}</span>
              </div>
              <Progress value={normalize(r4)} className="h-3 bg-blue-200" />
            </div>
          </div>

          {/* Current state (2s metric) */}
          <div className="mt-6 p-4 bg-gray-100 rounded text-center">
            <div className="text-sm text-gray-600">Current Relaxation</div>
            <div className="text-3xl font-bold">{r2.toFixed(2)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

### 5. Time-Series Chart

**src/components/MetricsChart.tsx**:
```typescript
'use client';

import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';

interface DataPoint {
  timestamp: number;
  r1s: number;
  r2s: number;
  r4s: number;
}

interface MetricsChartProps {
  deviceName: string;
}

export function MetricsChart({ deviceName }: MetricsChartProps) {
  const [data, setData] = useState<DataPoint[]>([]);

  const addDataPoint = (metrics: any) => {
    if (!metrics?.frontal) return;

    const newPoint: DataPoint = {
      timestamp: Date.now(),
      r1s: metrics.frontal['1s']?.relaxation || 0,
      r2s: metrics.frontal['2s']?.relaxation || 0,
      r4s: metrics.frontal['4s']?.relaxation || 0
    };

    setData(prev => {
      const updated = [...prev, newPoint];

      // Keep last 60 seconds (assuming 10 Hz updates)
      if (updated.length > 600) {
        return updated.slice(-600);
      }

      return updated;
    });
  };

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={(ts) => {
              const date = new Date(ts);
              return date.toLocaleTimeString();
            }}
          />
          <YAxis domain={[0, 5]} />
          <Tooltip
            labelFormatter={(ts) => new Date(ts).toLocaleTimeString()}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="r1s"
            stroke="#22c55e"
            name="Fast (1s)"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="r2s"
            stroke="#eab308"
            name="Balanced (2s)"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="r4s"
            stroke="#3b82f6"
            name="Stable (4s)"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### 6. Session Control

**src/components/SessionControl.tsx**:
```typescript
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';

interface SessionControlProps {
  connectedDevices: string[];
}

export function SessionControl({ connectedDevices }: SessionControlProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [participants, setParticipants] = useState<string>('');
  const [protocol, setProtocol] = useState<string>('meditation');

  const startSession = async () => {
    if (connectedDevices.length === 0) {
      alert('Connect at least one device first');
      return;
    }

    const participantList = participants
      .split(',')
      .map(p => p.trim())
      .filter(p => p);

    const id = await api.startSession({
      devices: connectedDevices,
      participants: participantList,
      protocol
    });

    setSessionId(id);
    setIsRecording(true);
  };

  const endSession = async () => {
    const sessionDir = await api.endSession();
    console.log('Session saved to:', sessionDir);

    setIsRecording(false);
    setSessionId(null);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Session Control</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {!isRecording ? (
            <>
              <div>
                <label className="text-sm font-medium">Participants</label>
                <Input
                  placeholder="Alice, Bob, Carol, Dave"
                  value={participants}
                  onChange={(e) => setParticipants(e.target.value)}
                />
              </div>

              <div>
                <label className="text-sm font-medium">Protocol</label>
                <Input
                  placeholder="meditation"
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                />
              </div>

              <Button
                onClick={startSession}
                className="w-full"
                disabled={connectedDevices.length === 0}
              >
                Start Session
              </Button>
            </>
          ) : (
            <>
              <div className="p-4 bg-green-100 rounded">
                <div className="text-sm text-green-800">Recording Active</div>
                <div className="font-mono text-xs">{sessionId}</div>
              </div>

              <Button
                onClick={endSession}
                variant="destructive"
                className="w-full"
              >
                End Session
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
```

### 7. Main Application

**src/app/page.tsx**:
```typescript
'use client';

import { useState } from 'react';
import { DevicePanel } from '@/components/DevicePanel';
import { SessionControl } from '@/components/SessionControl';
import { FeedbackDisplay } from '@/components/FeedbackDisplay';
import { MetricsChart } from '@/components/MetricsChart';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function Home() {
  const [connectedDevices, setConnectedDevices] = useState<string[]>([]);

  const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
  const { isConnected, metrics } = useWebSocket(WS_URL);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">ExG-Lab</h1>

        {/* Connection status */}
        <div className="mb-4">
          <span
            className={`inline-block w-3 h-3 rounded-full mr-2 ${
              isConnected ? 'bg-green-500' : 'bg-red-500'
            }`}
          />
          {isConnected ? 'Connected' : 'Disconnected'}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column - Controls */}
          <div className="space-y-6">
            <DevicePanel
              onDevicesChanged={setConnectedDevices}
            />
            <SessionControl connectedDevices={connectedDevices} />
          </div>

          {/* Right columns - Feedback */}
          <div className="lg:col-span-2 space-y-6">
            {connectedDevices.map(deviceName => (
              <div key={deviceName} className="space-y-4">
                <FeedbackDisplay
                  deviceName={deviceName}
                  metrics={metrics[deviceName]?.frontal}
                />
                <MetricsChart deviceName={deviceName} />
              </div>
            ))}

            {connectedDevices.length === 0 && (
              <div className="text-center text-gray-500 py-12">
                Connect devices to see feedback
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
```

## Performance Optimization

### 1. Throttling Updates

```typescript
import { useEffect, useRef } from 'react';

export function useThrottledCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T {
  const lastRun = useRef(Date.now());

  return ((...args) => {
    const now = Date.now();

    if (now - lastRun.current >= delay) {
      callback(...args);
      lastRun.current = now;
    }
  }) as T;
}

// Usage in component
function FeedbackDisplay({ metrics }) {
  const updateChart = useThrottledCallback((newMetrics) => {
    // Update chart data
    setChartData(prev => [...prev, newMetrics]);
  }, 100); // Max 10 Hz updates

  useEffect(() => {
    if (metrics) {
      updateChart(metrics);
    }
  }, [metrics]);
}
```

### 2. Memoization

```typescript
import { useMemo } from 'react';

function FeedbackDisplay({ metrics }) {
  const trend = useMemo(() => {
    if (!metrics) return null;

    const r1 = metrics['1s']?.relaxation || 0;
    const r2 = metrics['2s']?.relaxation || 0;
    const r4 = metrics['4s']?.relaxation || 0;

    if (r1 > r2 && r2 > r4) return 'IMPROVING';
    if (r1 < r2 && r2 < r4) return 'DECLINING';
    if (Math.abs(r1 - r4) < 0.3) return 'STABLE';
    return 'VARIABLE';
  }, [metrics]);

  // ... rest of component
}
```

### 3. Virtual Scrolling for Long Lists

For displaying many devices:

```typescript
import { FixedSizeList as List } from 'react-window';

function DeviceList({ devices }) {
  const Row = ({ index, style }) => (
    <div style={style}>
      <DeviceCard device={devices[index]} />
    </div>
  );

  return (
    <List
      height={600}
      itemCount={devices.length}
      itemSize={120}
      width="100%"
    >
      {Row}
    </List>
  );
}
```

## Responsive Design

### Mobile Layout

```typescript
'use client';

import { useMediaQuery } from '@/hooks/useMediaQuery';

export default function Home() {
  const isMobile = useMediaQuery('(max-width: 768px)');

  return (
    <main className="p-4 md:p-8">
      <div className={`
        grid gap-6
        ${isMobile ? 'grid-cols-1' : 'grid-cols-1 lg:grid-cols-3'}
      `}>
        {/* Responsive layout */}
      </div>
    </main>
  );
}
```

## Deployment

### Building for Production

```bash
# Frontend
cd frontend
npm run build
npm run start  # Production server

# Or deploy to Vercel
vercel deploy
```

### Environment Variables

**.env.local**:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

**.env.production**:
```
NEXT_PUBLIC_API_URL=https://api.exglab.com
NEXT_PUBLIC_WS_URL=wss://api.exglab.com/ws
```

## Next Steps

- [Implementation Guide](05-implementation-guide.md) - Backend implementation
- [Multi-Timescale Feedback](03-multi-timescale-feedback.md) - Understanding the metrics
- [Architecture Overview](01-architecture-overview.md) - System design

---

**Last updated**: 2025-10-30
