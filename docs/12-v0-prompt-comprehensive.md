# V0 Prompt: ExG-Lab Multi-Device EEG Neurofeedback Platform

## Project Context

Build a **research-grade web interface** for real-time multi-device EEG neurofeedback experiments. This platform enables researchers to conduct synchronized experiments with up to 4 Muse EEG headbands, providing participants with multi-timescale brain activity feedback while recording all data for analysis.

### Core Concept: Multi-Timescale Neurofeedback

The breakthrough feature is **predictive feedback** using three time windows:
- **Fast (1s)**: Leading indicator - shows where you're heading (GREEN)
- **Balanced (2s)**: Current state - optimal training target (YELLOW/GOLD)
- **Stable (4s)**: Trend confirmation - validates sustained changes (BLUE)

**Why this matters**: Participants can see changes developing BEFORE they fully manifest. If the 1s metric rises above 2s, which is above 4s, it means "improvement in progress" - a powerful training signal.

### Technical Architecture Overview

**Backend** (Python FastAPI):
- 4 independent pull threads (20 Hz) reading from LSL streams
- 1 calculation thread with ThreadPoolExecutor (10 Hz) computing FFT
- 1 WebSocket thread (10 Hz) pushing real-time metrics to frontend
- 1 save thread (0.2 Hz) recording all data to CSV
- Thread-safe with multiple locks protecting shared buffers

**Frontend Requirements**:
- WebSocket connection for real-time metrics (10-30 Hz updates)
- REST API calls for device management and session control
- Handle 1-4 devices simultaneously
- Responsive design (desktop primary, tablet secondary)
- Performance: smooth 60fps rendering despite high-frequency updates

## Design Requirements

### Visual Style

**Aesthetic**: Clean, professional, scientific interface
- **Primary purpose**: Research tool, not consumer app
- **Tone**: Minimal, focused, information-dense but not cluttered
- **Color scheme**:
  - Background: Light gray/white (`bg-gray-50`)
  - Cards: White with subtle shadows
  - Accent colors:
    - Green `#22c55e` for fast/improving metrics
    - Yellow/Gold `#eab308` for balanced metrics
    - Blue `#3b82f6` for stable metrics
    - Red `#ef4444` for declining/errors
    - Gray `#6b7280` for neutral/inactive states

**Typography**:
- Headers: Bold, clear hierarchy
- Body: Readable sans-serif (Inter, system-ui)
- Monospace for: MAC addresses, session IDs, timestamps
- Font sizes: Generous - researchers may be viewing from distance

**Layout Philosophy**:
- **Information hierarchy**: Most important info (live feedback) gets most space
- **Scannable**: Researchers need to quickly assess status of 4 devices
- **Persistent controls**: Device and session controls always visible (left sidebar)
- **Progressive disclosure**: Advanced options behind toggles/modals

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Header: ExG-Lab + Connection Status Badge + Settings       │
├─────────────┬───────────────────────────────────────────────┤
│             │                                               │
│  LEFT       │           MAIN CONTENT AREA                   │
│  SIDEBAR    │                                               │
│  (300px)    │  ┌─────────────────────────────────────────┐ │
│             │  │ Session Manager (when no active session)│ │
│  ┌────────┐ │  │  - Protocol Selector                    │ │
│  │Device  │ │  │  - Participant Assignment               │ │
│  │Panel   │ │  │  - Experimental Config                  │ │
│  │        │ │  └─────────────────────────────────────────┘ │
│  │Scan    │ │                                               │
│  │Connect │ │  ┌─────────────────────────────────────────┐ │
│  │Status  │ │  │ Live Feedback (during active session)   │ │
│  └────────┘ │  │                                         │ │
│             │  │  Muse_1: Alice                          │ │
│  ┌────────┐ │  │  ├─ Fast (1s): ████████░░ 2.34         │ │
│  │Session │ │  │  ├─ Balanced (2s): ██████░░░░ 1.87     │ │
│  │Control │ │  │  └─ Stable (4s): ████░░░░░░ 1.45       │ │
│  │        │ │  │  [IMPROVING ↗] Chart ~~~~~~~~~~~        │ │
│  │Protocol│ │  │                                         │ │
│  │Select  │ │  │  Muse_2: Bob                            │ │
│  │Start/  │ │  │  [Similar layout]                       │ │
│  │Stop    │ │  │                                         │ │
│  └────────┘ │  │  ... (up to 4 devices)                  │ │
│             │  └─────────────────────────────────────────┘ │
│  ┌────────┐ │                                               │
│  │Live    │ │  ┌─────────────────────────────────────────┐ │
│  │Session │ │  │ Session Progress (during session)       │ │
│  │Monitor │ │  │  Phase: Training [███████░░░] 7:42/10:00│ │
│  │        │ │  │  [Insert Marker] [Adjust Parameters]    │ │
│  │Phase   │ │  └─────────────────────────────────────────┘ │
│  │Progress│ │                                               │
│  └────────┘ │                                               │
│             │                                               │
└─────────────┴───────────────────────────────────────────────┘
```

## Detailed Component Specifications

### 1. Header Component

**Requirements**:
- App title: "ExG-Lab" (large, bold)
- Real-time connection status indicator:
  - Green dot + "Connected" when WebSocket active
  - Red dot + "Disconnected" when offline
  - Yellow dot + "Connecting..." during reconnection
- Settings icon (right side) - opens modal for:
  - Backend URL configuration
  - Update rate settings
  - Display preferences

**Visual Example**:
```
┌────────────────────────────────────────────────────────┐
│ 🧠 ExG-Lab              🟢 Connected         ⚙️       │
└────────────────────────────────────────────────────────┘
```

### 2. Device Panel (Left Sidebar)

**Purpose**: Discover, connect, and monitor Muse devices

**Components**:
- **Scan Button**:
  - Full width, primary action
  - Shows "Scanning..." with spinner when active
  - Disabled during active session

- **Device List**:
  - Each device shows:
    - Name: "Muse S - 3C4F" (last 4 chars of MAC)
    - MAC address: `00:55:DA:B3:3C:4F` (monospace, smaller)
    - Status badge: "Available" / "Connected" / "Streaming"
    - Battery level (if available): `🔋 87%`
    - Connect/Disconnect button
  - Visual states:
    - Available: Gray border, white background
    - Connected: Blue border, blue tint background
    - Streaming: Green border, green tint, pulsing animation
    - Error: Red border, red tint

**Mock Data** (for V0 preview):
```javascript
const mockDevices = [
  {
    name: "Muse S - 3C4F",
    mac: "00:55:DA:B3:3C:4F",
    status: "connected",
    battery: 87,
    streamName: "Muse_1"
  },
  {
    name: "Muse S - 7A21",
    mac: "00:55:DA:B3:7A:21",
    status: "connected",
    battery: 72,
    streamName: "Muse_2"
  },
  {
    name: "Muse S - 9B15",
    mac: "00:55:DA:B3:9B:15",
    status: "available",
    battery: null,
    streamName: null
  }
];
```

### 3. Protocol Selector (Main Content - Pre-Session)

**Purpose**: Choose experimental protocol before starting session

**Layout**: Grid of protocol cards (2 columns on desktop, 1 on tablet)

**Each Protocol Card Contains**:
- Title (large, bold)
- Description (2-3 lines)
- Badges showing:
  - Number of phases: `📋 3 phases`
  - Total duration: `⏱️ 15:00`
  - Feedback mode: `👁️ Feedback ON` or `📊 Recording Only`
  - Number of timescales: `🔢 3 timescales` or `🔢 Single (2s)`
- Hover state: Border highlight + subtle shadow
- Selected state: Blue border + blue background tint

**Built-in Protocols** (display these in V0):

1. **Meditation Baseline**
   - Description: "Pure data recording without feedback. Ideal for establishing participant baselines."
   - Badges: 1 phase, 5:00, Recording Only

2. **Neurofeedback Training**
   - Description: "Standard 3-phase protocol: pre-baseline, active training with full feedback, post-assessment."
   - Badges: 3 phases, 13:20, Feedback ON, 3 timescales

3. **Multi-Subject Synchronized**
   - Description: "4-person synchronized training session with group baseline and coordinated feedback."
   - Badges: 2 phases, 18:00, Feedback ON, 1 timescale (2s)

4. **A/B Test: Timescale Comparison**
   - Description: "Compare effectiveness of different feedback timescales across experimental groups."
   - Badges: 2 phases, 13:00, Conditional Feedback, Variable timescales

**Bottom of selector**:
- "Create Custom Protocol" button (outlined, secondary style)

### 4. Session Configuration Panel (After Protocol Selected)

**Purpose**: Assign devices to participants and configure experimental condition

**Layout**: Vertical form

**Sections**:

A. **Selected Protocol Summary** (collapsible):
   - Protocol name + "Change Protocol" button
   - Phase timeline visualization (horizontal bar with segments)
   - Quick stats

B. **Device Assignment**:
   - Table with columns:
     - Device (Muse_1, Muse_2, etc.)
     - Participant Name (text input)
     - Role (dropdown: Subject / Control)
     - Condition Group (dropdown: A / B / Control)
   - Only show connected devices
   - Example:
     ```
     Device    | Participant | Role    | Group
     ---------|-------------|---------|--------
     Muse_1   | Alice      | Subject | A
     Muse_2   | Bob        | Subject | B
     Muse_3   | Carol      | Control | Control
     Muse_4   | Dave       | Subject | A
     ```

C. **Experimental Condition Configuration** (if protocol supports it):
   - For A/B protocols, show:
     - Group A settings (e.g., "Timescale: 1s only")
     - Group B settings (e.g., "Timescale: 2s only")
     - Control settings (e.g., "No feedback")

D. **Action Buttons**:
   - "Start Session" (large, primary, green)
   - "Cancel" (secondary)

### 5. Live Feedback Display (Main Content - During Session)

**Purpose**: Show real-time neurofeedback for all active devices

**Layout**: Vertical stack of device cards (1 card per device)

**Each Device Card Contains**:

A. **Header**:
   - Left: Device name + Participant name (`Muse_1: Alice`)
   - Center: Trend badge (`IMPROVING ↗` / `STABLE ↔` / `DECLINING ↘`)
   - Right: Data age indicator (`<50ms` in green, `>500ms` in orange/red)

B. **Trend Message** (centered, large text):
   - Examples:
     - "You're getting more relaxed!" (when 1s > 2s > 4s)
     - "Nice and steady" (when all three within 0.3)
     - "Relaxation decreasing" (when 1s < 2s < 4s)
     - "Variable state" (for other patterns)

C. **Three Timescale Bars** (vertical stack):
   Each bar shows:
   - Label with timescale: "Fast (1s)" / "Balanced (2s)" / "Stable (4s)"
   - Color-coded progress bar:
     - Fast: Green bar on green-tinted background
     - Balanced: Yellow/gold bar on yellow-tinted background
     - Stable: Blue bar on blue-tinted background
   - Numeric value (right-aligned): `2.34`
   - Bar width: proportional to value (normalize: 0 = empty, 4 = full)

D. **Current State Callout Box** (bottom, centered):
   - Gray background box
   - Label: "Current Relaxation"
   - Large number: `1.87` (from 2s metric)
   - Subtext: "Target: 2.00" (if threshold configured)

E. **Mini Time-Series Chart** (optional, collapsible):
   - Line chart showing last 60 seconds
   - Three lines (green, yellow, blue) for three timescales
   - X-axis: time (relative, like "-60s" to "now")
   - Y-axis: relaxation index (0-4)

**Visual Representation**:
```
┌─────────────────────────────────────────────────────────┐
│ Muse_1: Alice          [IMPROVING ↗]         <45ms     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│           You're getting more relaxed! 🎯              │
│                                                         │
│  Fast (1s)      ████████████░░░░░░░░           2.34   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│                                                         │
│  Balanced (2s)  ██████████░░░░░░░░░░░░         1.87   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│                                                         │
│  Stable (4s)    ███████░░░░░░░░░░░░░░░         1.45   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│                                                         │
│            ┌──────────────────────────┐                │
│            │  Current Relaxation      │                │
│            │        1.87              │                │
│            │  Target: 2.00            │                │
│            └──────────────────────────┘                │
│                                                         │
│  [Show Chart ▼]                                        │
└─────────────────────────────────────────────────────────┘
```

### 6. Session Progress Monitor (Left Sidebar - During Session)

**Purpose**: Track experimental protocol progression and insert markers

**Layout**: Single card in sidebar (replaces session config during active session)

**Components**:

A. **Phase Progress Bar**:
   - Current phase name: "Active Training"
   - Progress bar showing elapsed/total
   - Time displays: "7:42 / 10:00"
   - Badge: "Phase 2/3"

B. **Current Instructions** (blue info box):
   - Text shown to participants
   - Example: "Try to increase the balanced (yellow) bar"

C. **Phase Controls**:
   - If manual advance: "Advance to Next Phase" button (enabled)
   - If auto-advance: Button disabled with countdown
   - "Insert Event Marker" button:
     - Clicks open small modal for marker label
     - Saves timestamp + label + current phase

D. **Real-time Parameter Adjustments** (collapsible):
   - Toggle: "Feedback Visibility" (show/hide all feedback)
   - Number input: "Target Threshold" (adjust training goal)
   - Dropdown: "Display Mode" (minimal/standard/detailed)

E. **Emergency Controls**:
   - "End Session Early" button (red, requires confirmation)

**Visual Mock**:
```
┌──────────────────────────────┐
│ Session Progress             │
├──────────────────────────────┤
│                              │
│ Active Training    [2/3]     │
│ ████████████░░░░░░░           │
│ 7:42 / 10:00                 │
│                              │
│ ┌──────────────────────────┐ │
│ │ 👁️ Current Instructions   │ │
│ │ Try to increase the      │ │
│ │ balanced (yellow) bar    │ │
│ └──────────────────────────┘ │
│                              │
│ [Insert Marker]              │
│ [Adjust Parameters ▼]        │
│                              │
│ [End Session Early]          │
└──────────────────────────────┘
```

### 7. WebSocket Status & Error Handling

**Requirements**:
- Automatic reconnection on disconnect (with exponential backoff)
- Visual feedback for connection states:
  - Connected: Green dot in header
  - Disconnected: Red dot + "Reconnecting..." message overlay
  - Degraded: Orange dot + "High latency" warning if data age > 500ms
- Error messages as toast notifications (bottom-right):
  - "Device Muse_1 disconnected"
  - "WebSocket connection lost - reconnecting..."
  - "Session ended successfully"

## Data Flow & State Management

### WebSocket Message Format (From Backend)

```typescript
interface FeedbackMessage {
  type: 'feedback_update';
  timestamp: number;  // Unix timestamp
  devices: {
    [streamName: string]: {
      subject: string;
      frontal: {
        '1s': { relaxation: number; alpha: number; beta: number };
        '2s': { relaxation: number; alpha: number; beta: number };
        '4s': { relaxation: number; alpha: number; beta: number };
      };
      quality: {
        data_age_ms: number;
        signal_quality: { TP9: number; AF7: number; AF8: number; TP10: number };
      };
    };
  };
}
```

### REST API Endpoints

```typescript
// Device Management
GET  /api/devices/scan -> { devices: Device[] }
POST /api/devices/connect { address: string, stream_name: string }
POST /api/devices/disconnect/:streamName

// Session Management
POST /api/session/start { config: SessionConfig }
POST /api/session/end -> { session_dir: string }
POST /api/session/marker { label: string, metadata: object }
POST /api/session/adjust { param: string, value: any }
POST /api/session/advance-phase
```

### React State Structure (Suggested)

```typescript
// Use React Context or Zustand for global state
interface AppState {
  // WebSocket
  wsConnected: boolean;
  latestMetrics: Record<string, DeviceMetrics>;

  // Devices
  availableDevices: Device[];
  connectedDevices: string[];  // stream names

  // Session
  activeSession: {
    sessionId: string;
    config: SessionConfig;
    currentPhase: number;
    phaseStartTime: number;
  } | null;

  // Protocol
  selectedProtocol: ExperimentalProtocol | null;
  customProtocols: ExperimentalProtocol[];
}
```

## Technical Implementation Notes

### Performance Optimizations Required

1. **Throttle updates**: Even though WebSocket sends at 10 Hz, throttle React re-renders to 10 Hz using `useThrottledCallback`

2. **Memoization**: Use `useMemo` for computed values like trend detection, normalized bar widths

3. **Virtual scrolling**: If showing >4 devices, use `react-window` for device list

4. **Debounce inputs**: Parameter adjustments should debounce by 300ms before sending to backend

5. **Chart optimization**: Use `recharts` with `isAnimationActive={false}` for time-series, limit to last 600 data points

### Accessibility Requirements

- All interactive elements keyboard accessible (tab navigation)
- Color-blind friendly: Don't rely ONLY on color (use icons + labels)
- Screen reader support: Proper ARIA labels on all metrics
- High contrast mode support
- Minimum font sizes: 14px for body, 16px for data values

### Responsive Breakpoints

```css
/* Desktop (primary target) */
@media (min-width: 1024px) {
  /* Sidebar + main content side-by-side */
}

/* Tablet */
@media (min-width: 768px) and (max-width: 1023px) {
  /* Collapsible sidebar or stacked layout */
}

/* Mobile (limited support - show warning) */
@media (max-width: 767px) {
  /* Show message: "This app is optimized for desktop/tablet" */
}
```

## User Flows

### Flow 1: Quick Session Start (Pre-configured Protocol)

1. User opens app → See Protocol Selector
2. Click "Neurofeedback Training" card → Card highlights
3. Sidebar: Click "Scan for Devices" → Finds 2 devices
4. Click "Connect" on each device → Status changes to "Connected"
5. Main content shows "Device Assignment" form
6. Fill in participant names: Alice, Bob
7. Click "Start Session" → Transition to Live Feedback view
8. Watch real-time metrics update at 10 Hz
9. After 13:20 (auto-phases complete) → Session ends
10. Toast notification: "Session saved to /data/session_20251030_143022"

### Flow 2: Custom Protocol with Real-time Adjustments

1. User opens app → Protocol Selector
2. Click "Create Custom Protocol" → Opens protocol editor modal
3. Configure:
   - Name: "Quick Meditation Test"
   - Single phase: 5 minutes
   - Feedback: 2s timescale only
   - No auto-advance
4. Save protocol → Appears in protocol list
5. Select custom protocol → Assign devices → Start session
6. During session: Click "Insert Marker" → Label: "Eyes opened"
7. Click "Adjust Parameters" → Toggle feedback visibility OFF
8. Continue for 2 more minutes
9. Click "End Session Early" → Confirm → Session ends
10. See saved data location

### Flow 3: Multi-Subject A/B Test

1. Researcher selects "A/B Test: Timescale Comparison"
2. Connects 4 devices
3. Assigns:
   - Muse_1 (Alice) → Group A
   - Muse_2 (Bob) → Group B
   - Muse_3 (Carol) → Group A
   - Muse_4 (Dave) → Group B
4. Protocol automatically configures:
   - Group A sees only 1s timescale
   - Group B sees only 4s timescale
5. Start session → Each participant sees different feedback
6. After baseline phase → Automatically advances to training
7. Session completes → Data saved with group assignments

## Mock Data for V0 Preview

Since V0 needs to show interactive UI without real backend, use this mock data:

```javascript
// Mock WebSocket simulation
const mockWebSocketData = {
  Muse_1: {
    subject: 'Alice',
    frontal: {
      '1s': { relaxation: 2.34, alpha: 0.45, beta: 0.32 },
      '2s': { relaxation: 1.87, alpha: 0.42, beta: 0.35 },
      '4s': { relaxation: 1.45, alpha: 0.38, beta: 0.37 }
    },
    quality: {
      data_age_ms: 45,
      signal_quality: { TP9: 0.95, AF7: 0.88, AF8: 0.92, TP10: 0.97 }
    }
  },
  Muse_2: {
    subject: 'Bob',
    frontal: {
      '1s': { relaxation: 1.12, alpha: 0.35, beta: 0.41 },
      '2s': { relaxation: 1.25, alpha: 0.36, beta: 0.40 },
      '4s': { relaxation: 1.48, alpha: 0.38, beta: 0.38 }
    },
    quality: {
      data_age_ms: 52,
      signal_quality: { TP9: 0.91, AF7: 0.85, AF8: 0.89, TP10: 0.93 }
    }
  }
};

// Simulate updates every 100ms with small random changes
setInterval(() => {
  // Add random walk to relaxation values
  mockWebSocketData.Muse_1.frontal['1s'].relaxation += (Math.random() - 0.5) * 0.1;
  // ... etc
}, 100);
```

## V0 Deliverables Requested

Please generate:

1. **Main Application Shell** with:
   - Header with connection status
   - Sidebar/main content layout
   - Responsive grid system

2. **Device Panel Component** with:
   - Scan button
   - Device list with connection controls
   - Mock data showing 3 devices (2 connected, 1 available)

3. **Protocol Selector** with:
   - Grid of 4 protocol cards
   - Selectable states
   - "Create Custom" button

4. **Session Configuration Form** with:
   - Device assignment table
   - Participant name inputs
   - Start session button

5. **Live Feedback Display** with:
   - Two device cards (Alice and Bob)
   - Three timescale bars with animated values
   - Trend detection and messaging
   - Current state callout

6. **Session Progress Monitor** with:
   - Phase progress bar
   - Instruction display
   - Control buttons

7. **Complete integrated view** showing:
   - Active session state
   - All components working together
   - Simulated real-time updates

## Additional Context

**Target Users**: Neuroscience researchers, experimental psychologists, HCI researchers
**Use Case**: Laboratory experiments with 1-4 simultaneous participants
**Session Duration**: Typically 5-30 minutes
**Environment**: Desktop/laptop browsers in lab setting
**Critical Success Factor**: Clear, immediate visual feedback that participants can understand without training

## Design Inspirations

- **Scientific dashboards**: Grafana, Kibana (data density + clarity)
- **Biometric monitoring**: Apple Health, Oura Ring (clean metric visualization)
- **Research tools**: PsychoPy, OpenSesame (professional, no-nonsense UX)
- **Real-time monitoring**: OBS Studio, Streamlabs (live status indicators)

## Final Notes

- **Prioritize clarity over aesthetics**: This is a research tool, not a consumer product
- **Embrace information density**: Researchers want to see everything at once
- **Make feedback OBVIOUS**: Participants should instantly understand if they're improving
- **Plan for failure states**: Show clear messages when devices disconnect or data stops
- **Performance is critical**: Must maintain 60fps with 10 Hz WebSocket updates

Generate a fully functional, interactive prototype that demonstrates the complete user experience from protocol selection through active session monitoring. Use shadcn/ui components, Tailwind CSS, and Recharts as specified. Include mock data and simulated WebSocket updates to show the real-time nature of the interface.

---

**Ready to build!** 🚀
