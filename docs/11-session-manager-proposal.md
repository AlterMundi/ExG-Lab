# Session Manager & Experimental Environment Configuration

## Overview

The current UI provides transparent backend access but lacks structured experimental environment management. This document proposes a **Session Manager** component to bridge this gap.

## Problem Statement

Researchers need to:
1. Define experimental protocols with specific feedback parameters
2. Manage different experimental conditions (A/B testing, randomization)
3. Configure multi-phase experiments (baseline → training → evaluation)
4. Save and reuse experimental configurations
5. Adjust parameters in real-time during sessions

Currently, the UI only allows basic session start/stop with freeform participant/protocol strings.

## Proposed Architecture

### Component Hierarchy

```
SessionManager (NEW)
├── ProtocolSelector
│   ├── ProtocolTemplates (presets)
│   └── CustomProtocolEditor
├── ExperimentalConfig
│   ├── PhaseDesigner
│   ├── FeedbackControls
│   └── RecordingOptions
├── SessionControl (existing, enhanced)
└── LiveSessionMonitor (NEW)
    ├── PhaseProgress
    ├── EventMarkers
    └── ParameterAdjustment
```

### Data Models

```typescript
// Core session configuration
interface SessionConfig {
  protocol: ExperimentalProtocol;
  devices: DeviceAssignment[];
  participants: ParticipantInfo[];
  condition: ExperimentalCondition;
}

// Experimental protocol definition
interface ExperimentalProtocol {
  id: string;
  name: string;
  description: string;
  phases: SessionPhase[];
  feedbackConfig: FeedbackConfiguration;
  recordingConfig: RecordingConfiguration;
}

// Individual phase in a session
interface SessionPhase {
  id: string;
  name: string;                    // "baseline", "training", "rest"
  duration: number;                // seconds
  autoAdvance: boolean;
  feedbackMode: FeedbackMode;
  instructions: string;            // Display to participants
  metadata: Record<string, any>;
}

// Feedback configuration
interface FeedbackConfiguration {
  enabled: boolean;
  timescales: TimescaleConfig[];
  displayMode: 'minimal' | 'standard' | 'detailed';
  thresholds: {
    relaxation_target?: number;
    improvement_threshold?: number;
  };
  visualStyle: 'bars' | 'gauge' | 'waveform';
}

interface TimescaleConfig {
  window: '1s' | '2s' | '4s';
  visible: boolean;
  primary: boolean;              // Main training target
  color: string;
}

// Recording configuration
interface RecordingConfiguration {
  saveRaw: boolean;
  saveMetrics: boolean;
  savePSD: boolean;
  flushInterval: number;         // seconds
  format: 'csv' | 'hdf5' | 'both';
}

// Device assignment to participants
interface DeviceAssignment {
  streamName: string;            // "Muse_1"
  participant: string;           // "Alice"
  role: 'subject' | 'control';
  condition: string;             // For experimental conditions
}

// Experimental condition (for A/B testing)
interface ExperimentalCondition {
  id: string;
  group: 'A' | 'B' | 'control';
  variations: {
    feedbackDelay?: number;
    timescaleSet?: string[];
    threshold?: number;
  };
}
```

### Built-in Protocol Templates

```typescript
const PROTOCOL_TEMPLATES: ExperimentalProtocol[] = [
  {
    id: 'meditation-baseline',
    name: 'Meditation Baseline',
    description: 'Pure recording with no feedback',
    phases: [
      {
        id: 'baseline',
        name: 'Baseline Recording',
        duration: 300,  // 5 minutes
        autoAdvance: true,
        feedbackMode: 'none',
        instructions: 'Sit quietly with eyes closed'
      }
    ],
    feedbackConfig: {
      enabled: false,
      timescales: [],
      displayMode: 'minimal',
      thresholds: {},
      visualStyle: 'bars'
    },
    recordingConfig: {
      saveRaw: true,
      saveMetrics: false,
      savePSD: false,
      flushInterval: 5,
      format: 'csv'
    }
  },

  {
    id: 'neurofeedback-training',
    name: 'Neurofeedback Training',
    description: 'Standard 3-phase neurofeedback session',
    phases: [
      {
        id: 'pre-baseline',
        name: 'Pre-Training Baseline',
        duration: 120,
        autoAdvance: true,
        feedbackMode: 'none',
        instructions: 'Relax with eyes closed - no feedback yet'
      },
      {
        id: 'training',
        name: 'Active Training',
        duration: 600,  // 10 minutes
        autoAdvance: true,
        feedbackMode: 'full',
        instructions: 'Try to increase the balanced (yellow) bar'
      },
      {
        id: 'post-baseline',
        name: 'Post-Training Assessment',
        duration: 120,
        autoAdvance: true,
        feedbackMode: 'none',
        instructions: 'Final baseline - maintain your relaxed state'
      }
    ],
    feedbackConfig: {
      enabled: true,
      timescales: [
        { window: '1s', visible: true, primary: false, color: 'green' },
        { window: '2s', visible: true, primary: true, color: 'yellow' },
        { window: '4s', visible: true, primary: false, color: 'blue' }
      ],
      displayMode: 'standard',
      thresholds: {
        relaxation_target: 2.0,
        improvement_threshold: 0.5
      },
      visualStyle: 'bars'
    },
    recordingConfig: {
      saveRaw: true,
      saveMetrics: true,
      savePSD: true,
      flushInterval: 5,
      format: 'both'
    }
  },

  {
    id: 'multi-subject-sync',
    name: 'Multi-Subject Synchronized',
    description: '4-person synchronized neurofeedback',
    phases: [
      {
        id: 'individual-baseline',
        name: 'Individual Baseline',
        duration: 180,
        autoAdvance: true,
        feedbackMode: 'none',
        instructions: 'Individual baseline - eyes closed'
      },
      {
        id: 'group-session',
        name: 'Group Neurofeedback',
        duration: 900,  // 15 minutes
        autoAdvance: false,  // Manual advance
        feedbackMode: 'full',
        instructions: 'Group training - try to synchronize with others'
      }
    ],
    feedbackConfig: {
      enabled: true,
      timescales: [
        { window: '2s', visible: true, primary: true, color: 'blue' }
      ],
      displayMode: 'detailed',
      thresholds: {},
      visualStyle: 'bars'
    },
    recordingConfig: {
      saveRaw: true,
      saveMetrics: true,
      savePSD: true,
      flushInterval: 2,
      format: 'hdf5'
    }
  },

  {
    id: 'ab-test-timescales',
    name: 'A/B Test: Timescale Comparison',
    description: 'Compare 1s vs 2s vs 4s feedback effectiveness',
    phases: [
      {
        id: 'baseline',
        name: 'Baseline',
        duration: 180,
        autoAdvance: true,
        feedbackMode: 'none',
        instructions: 'Pre-test baseline'
      },
      {
        id: 'condition-training',
        name: 'Training Phase',
        duration: 600,
        autoAdvance: true,
        feedbackMode: 'conditional',  // Determined by group assignment
        instructions: 'Use the feedback to improve relaxation'
      }
    ],
    feedbackConfig: {
      enabled: true,
      timescales: [],  // Set per condition
      displayMode: 'standard',
      thresholds: {
        relaxation_target: 2.0
      },
      visualStyle: 'bars'
    },
    recordingConfig: {
      saveRaw: true,
      saveMetrics: true,
      savePSD: true,
      flushInterval: 5,
      format: 'both'
    }
  }
];
```

## UI Components

### 1. Protocol Selector Component

```typescript
// src/components/ProtocolSelector.tsx
'use client';

import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface ProtocolSelectorProps {
  onProtocolSelect: (protocol: ExperimentalProtocol) => void;
}

export function ProtocolSelector({ onProtocolSelect }: ProtocolSelectorProps) {
  const [selectedProtocol, setSelectedProtocol] = useState<string | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Select Experimental Protocol</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {PROTOCOL_TEMPLATES.map(protocol => (
            <div
              key={protocol.id}
              className={`p-4 border rounded cursor-pointer transition ${
                selectedProtocol === protocol.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'hover:border-gray-400'
              }`}
              onClick={() => {
                setSelectedProtocol(protocol.id);
                onProtocolSelect(protocol);
              }}
            >
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold">{protocol.name}</h3>
                <Badge variant="outline">
                  {protocol.phases.length} phases
                </Badge>
              </div>
              <p className="text-sm text-gray-600 mb-3">
                {protocol.description}
              </p>
              <div className="flex gap-2 text-xs">
                <Badge variant={protocol.feedbackConfig.enabled ? 'success' : 'secondary'}>
                  {protocol.feedbackConfig.enabled ? 'Feedback ON' : 'Recording Only'}
                </Badge>
                <Badge variant="outline">
                  {protocol.phases.reduce((sum, p) => sum + p.duration, 0)}s total
                </Badge>
              </div>
            </div>
          ))}
        </div>

        <Button
          variant="outline"
          className="w-full mt-4"
          onClick={() => {/* Open custom protocol editor */}}
        >
          + Create Custom Protocol
        </Button>
      </CardContent>
    </Card>
  );
}
```

### 2. Live Session Monitor Component

```typescript
// src/components/LiveSessionMonitor.tsx
'use client';

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';

interface LiveSessionMonitorProps {
  sessionConfig: SessionConfig;
  currentPhase: number;
  phaseElapsed: number;
  onAdvancePhase: () => void;
  onInsertMarker: (label: string) => void;
  onAdjustParameter: (param: string, value: any) => void;
}

export function LiveSessionMonitor({
  sessionConfig,
  currentPhase,
  phaseElapsed,
  onAdvancePhase,
  onInsertMarker,
  onAdjustParameter
}: LiveSessionMonitorProps) {
  const phase = sessionConfig.protocol.phases[currentPhase];
  const progress = (phaseElapsed / phase.duration) * 100;
  const remaining = phase.duration - phaseElapsed;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Session Progress</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Phase info */}
          <div>
            <div className="flex justify-between mb-2">
              <span className="font-medium">{phase.name}</span>
              <Badge>{currentPhase + 1} / {sessionConfig.protocol.phases.length}</Badge>
            </div>
            <Progress value={progress} className="h-2" />
            <div className="flex justify-between text-sm text-gray-600 mt-1">
              <span>{Math.floor(phaseElapsed)}s elapsed</span>
              <span>{Math.floor(remaining)}s remaining</span>
            </div>
          </div>

          {/* Instructions */}
          <div className="p-3 bg-blue-50 rounded">
            <div className="text-sm font-medium text-blue-900 mb-1">
              Current Instructions:
            </div>
            <div className="text-sm text-blue-700">
              {phase.instructions}
            </div>
          </div>

          {/* Phase controls */}
          <div className="flex gap-2">
            {!phase.autoAdvance && (
              <Button
                onClick={onAdvancePhase}
                className="flex-1"
              >
                Advance to Next Phase
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => {
                const label = prompt('Marker label:');
                if (label) onInsertMarker(label);
              }}
            >
              Insert Marker
            </Button>
          </div>

          {/* Live parameter adjustment */}
          <div className="border-t pt-4 mt-4">
            <div className="text-sm font-medium mb-3">Real-time Controls</div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm">Feedback Visibility</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const current = sessionConfig.protocol.feedbackConfig.enabled;
                    onAdjustParameter('feedback.enabled', !current);
                  }}
                >
                  {sessionConfig.protocol.feedbackConfig.enabled ? 'Hide' : 'Show'}
                </Button>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm">Target Threshold</span>
                <input
                  type="number"
                  step="0.1"
                  className="w-20 px-2 py-1 border rounded text-sm"
                  defaultValue={sessionConfig.protocol.feedbackConfig.thresholds.relaxation_target}
                  onChange={(e) => {
                    onAdjustParameter('feedback.threshold', parseFloat(e.target.value));
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

### 3. Enhanced Session Control

```typescript
// Updated SessionControl with protocol configuration
export function SessionControl({
  connectedDevices,
  selectedProtocol
}: SessionControlProps) {
  const [participants, setParticipants] = useState<ParticipantInfo[]>([]);
  const [condition, setCondition] = useState<ExperimentalCondition | null>(null);

  const configureSession = () => {
    // Map devices to participants
    // Assign experimental conditions
    // Validate configuration
    // Start session with full config
  };

  // ... rest of implementation
}
```

## Backend Extensions Required

### API Endpoints

```python
# New endpoints for session management
@app.post("/api/protocols/save")
async def save_protocol(protocol: ExperimentalProtocol):
    """Save custom protocol template"""
    pass

@app.get("/api/protocols/list")
async def list_protocols():
    """List available protocol templates"""
    pass

@app.post("/api/session/configure")
async def configure_session(config: SessionConfig):
    """Configure session with full experimental protocol"""
    pass

@app.post("/api/session/marker")
async def insert_marker(marker: EventMarker):
    """Insert event marker during active session"""
    pass

@app.post("/api/session/adjust")
async def adjust_parameter(param: str, value: Any):
    """Adjust session parameter in real-time"""
    pass

@app.post("/api/session/advance-phase")
async def advance_phase():
    """Manually advance to next protocol phase"""
    pass
```

### Session State Management

```python
class SessionManager:
    def __init__(self):
        self.active_config: SessionConfig | None = None
        self.current_phase: int = 0
        self.phase_start_time: float = 0
        self.event_markers: List[EventMarker] = []

    async def start_session(self, config: SessionConfig):
        """Initialize session with protocol configuration"""
        self.active_config = config
        self.current_phase = 0
        self.phase_start_time = time.time()

        # Apply initial phase configuration
        await self._apply_phase_config(config.protocol.phases[0])

    async def _apply_phase_config(self, phase: SessionPhase):
        """Apply phase-specific settings"""
        # Update feedback visibility
        # Adjust processing parameters
        # Send UI configuration updates
        pass

    async def check_auto_advance(self):
        """Check if current phase should auto-advance"""
        if not self.active_config:
            return

        phase = self.active_config.protocol.phases[self.current_phase]
        elapsed = time.time() - self.phase_start_time

        if phase.autoAdvance and elapsed >= phase.duration:
            await self.advance_phase()

    async def advance_phase(self):
        """Move to next protocol phase"""
        if not self.active_config:
            return

        self.current_phase += 1
        if self.current_phase >= len(self.active_config.protocol.phases):
            await self.end_session()
            return

        self.phase_start_time = time.time()
        phase = self.active_config.protocol.phases[self.current_phase]
        await self._apply_phase_config(phase)

    async def insert_marker(self, label: str, metadata: dict = None):
        """Add event marker to session"""
        marker = EventMarker(
            timestamp=time.time(),
            label=label,
            phase=self.current_phase,
            metadata=metadata or {}
        )
        self.event_markers.append(marker)
        # Save to session file
```

## Benefits

1. **Research Flexibility**: Easily configure different experimental conditions
2. **Reproducibility**: Save and share exact experimental protocols
3. **Efficiency**: Quick setup with templates, no manual configuration
4. **Real-time Control**: Adjust parameters during active sessions
5. **Multi-phase Support**: Structured experiments with baseline/training/evaluation
6. **A/B Testing**: Built-in support for experimental conditions
7. **Better Data**: Event markers and phase metadata for analysis

## Migration Path

1. **Phase 1**: Add protocol templates to frontend (backward compatible)
2. **Phase 2**: Extend backend SessionManager with protocol support
3. **Phase 3**: Add custom protocol editor UI
4. **Phase 4**: Implement real-time parameter adjustment
5. **Phase 5**: Add protocol sharing and versioning

## Next Steps

1. Review and refine data models
2. Implement ProtocolSelector component
3. Extend backend SessionManager
4. Add protocol templates
5. Create custom protocol editor
6. Implement real-time controls

---

**Status**: Proposal
**Last updated**: 2025-10-30
