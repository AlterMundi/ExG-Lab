export interface Device {
  name: string
  mac: string
  status: "available" | "connected" | "streaming" | "connecting"
  battery: number | null
  streamName: string | null
}

export interface SessionDevice {
  address: string
  name: string
  streamName: string
  status: "connected" | "streaming" | "disconnected"
  connectedAt: number
  disconnectedAt: number | null
}

export interface Protocol {
  id: string
  name: string
  description: string
  phases: number
  duration: number
  feedbackEnabled: boolean
  timescales: number
}

export interface SessionState {
  isActive: boolean
  sessionId: string | null
  protocolName: string | null
  currentPhase: string
  phaseName: string | null
  elapsedSeconds: number
  remainingSeconds: number | null
  devices: string[]  // Stream names
  subjectIds: Record<string, string>
  connectedDevices: SessionDevice[]  // Full device state
  feedbackEnabled: boolean
  instructions: string | null
}

export interface DeviceMetrics {
  subject: string
  frontal: {
    "1s": { relaxation: number; alpha: number; beta: number }
    "2s": { relaxation: number; alpha: number; beta: number }
    "4s": { relaxation: number; alpha: number; beta: number }
  }
  quality: {
    data_age_ms: number
    signal_quality: {
      TP9: number
      AF7: number
      AF8: number
      TP10: number
    }
  }
}

export interface SavedSession {
  sessionId: string
  timestamp: number
  protocol: Protocol
  config: any
  devices: Device[]
  duration: number
  dataPoints: SessionDataPoint[]
  summary: SessionSummary
}

export interface SessionDataPoint {
  timestamp: number
  metrics: Record<string, DeviceMetrics>
}

export interface SessionSummary {
  avgRelaxation: Record<string, { fast: number; balanced: number; stable: number }>
  maxRelaxation: Record<string, { fast: number; balanced: number; stable: number }>
  minRelaxation: Record<string, { fast: number; balanced: number; stable: number }>
  totalDataPoints: number
}

export interface RawEEGData {
  subject: string
  channels: {
    TP9: ChannelData
    AF7: ChannelData
    AF8: ChannelData
    TP10: ChannelData
  }
}

export interface ChannelData {
  timeDomain: number[] // Raw voltage values (last 256 samples, ~1 second at 256Hz)
  frequencyDomain: FrequencyBands
  quality: number
}

export interface FrequencyBands {
  delta: number // 0.5-4 Hz
  theta: number // 4-8 Hz
  alpha: number // 8-13 Hz
  beta: number // 13-30 Hz
  gamma: number // 30-50 Hz
}
