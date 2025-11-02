"use client"

import { useState, useEffect } from "react"
import { Header } from "@/components/header"
import { DevicePanel } from "@/components/device-panel"
import { ProtocolSelector } from "@/components/protocol-selector"
import { SessionConfig } from "@/components/session-config"
import { LiveFeedback } from "@/components/live-feedback"
import { SessionProgress } from "@/components/session-progress"
import { SessionsManager } from "@/components/sessions-manager"
import { SessionReplay } from "@/components/session-replay"
import { RawDataViewer } from "@/components/raw-data-viewer"
import { useRealtimeData } from "@/hooks/use-realtime-data"
import { useSessionRecorder } from "@/hooks/use-session-recorder"
import { useRawEEGData } from "@/hooks/use-raw-eeg-data"
import { Button } from "@/components/ui/button"
import { History, Activity } from "lucide-react"
import type { Device, Protocol, SessionState, SavedSession } from "@/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export default function ExGLabPage() {
  const [scannedDevices, setScannedDevices] = useState<Device[]>([])
  const [selectedProtocol, setSelectedProtocol] = useState<Protocol | null>(null)
  const [sessionState, setSessionState] = useState<SessionState | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [showSessionsManager, setShowSessionsManager] = useState(false)
  const [replaySession, setReplaySession] = useState<SavedSession | null>(null)
  const [currentView, setCurrentView] = useState<"feedback" | "raw">("feedback")

  const { metrics, deviceStatus, connectedStreamNames, isConnected, error } = useRealtimeData()
  const rawData = useRawEEGData()

  const { saveSession } = useSessionRecorder(
    sessionState?.isActive || false,
    sessionState?.sessionId || null,
    selectedProtocol,
    sessionState?.config,
    scannedDevices,
    metrics,
  )

  // Update scanned devices status based on connected stream names from WebSocket
  useEffect(() => {
    if (connectedStreamNames.length > 0) {
      setScannedDevices((prev) =>
        prev.map((device) => ({
          ...device,
          status: connectedStreamNames.includes(device.streamName || "")
            ? "connected"
            : device.status === "connecting"
              ? "connecting"
              : "available",
        })),
      )
    }
  }, [connectedStreamNames])

  const handleScan = async () => {
    setIsScanning(true)
    try {
      const response = await fetch(`${API_URL}/api/devices/scan`)
      const data = await response.json()

      if (data.success && data.devices) {
        setScannedDevices(
          data.devices.map((d: any) => ({
            name: d.name,
            mac: d.address,
            status: d.status,
            battery: d.battery || null,
            streamName: null,
          }))
        )
      } else {
        console.error("Device scan failed:", data.error || "Unknown error")
      }
    } catch (error) {
      console.error("Failed to scan devices:", error)
    } finally {
      setIsScanning(false)
    }
  }

  const handleConnect = async (mac: string) => {
    // Count currently connected devices from session (not including disconnected)
    const connectedCount = deviceStatus.filter((dev) => dev.status !== "disconnected").length
    const streamName = `Muse_${connectedCount + 1}`

    // Update device status to "connecting" immediately
    setScannedDevices((prev) =>
      prev.map((device) =>
        device.mac === mac
          ? { ...device, status: "connecting", streamName }
          : device,
      ),
    )

    try {
      const response = await fetch(`${API_URL}/api/devices/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: mac, stream_name: streamName }),
      })
      const data = await response.json()

      if (!data.success) {
        console.error("Device connection failed:", data.error || "Unknown error")
        // Reset status on failure
        setScannedDevices((prev) =>
          prev.map((device) =>
            device.mac === mac
              ? { ...device, status: "available", streamName: null }
              : device,
          ),
        )
      }
      // Note: Device status will be updated via WebSocket once connected
    } catch (error) {
      console.error("Failed to connect device:", error)
      // Reset status on error
      setScannedDevices((prev) =>
        prev.map((device) =>
          device.mac === mac
            ? { ...device, status: "available", streamName: null }
            : device,
        ),
      )
    }
  }

  const handleDisconnect = async (mac: string) => {
    // Find device in session devices OR scanned devices
    const sessionDevice = deviceStatus.find((d) => d.address === mac)
    const scannedDevice = scannedDevices.find((d) => d.mac === mac)

    const streamName = sessionDevice?.streamName || scannedDevice?.streamName

    if (!streamName) {
      console.error("Cannot disconnect: device has no stream name")
      return
    }

    try {
      const response = await fetch(`${API_URL}/api/devices/disconnect/${streamName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
      const data = await response.json()

      if (!data.success) {
        console.error("Device disconnection failed:", data.error || "Unknown error")
      } else {
        // Update scanned device status immediately
        setScannedDevices((prev) =>
          prev.map((device) =>
            device.mac === mac
              ? { ...device, status: "available", streamName: null }
              : device,
          ),
        )
      }
    } catch (error) {
      console.error("Failed to disconnect device:", error)
    }
  }

  const handleStartSession = async (config: any) => {
    try {
      // Transform assignments to backend format
      const subjectIds: Record<string, string> = {}
      config.assignments.forEach((assignment: any) => {
        subjectIds[assignment.streamName] = assignment.participantName
      })

      // Call backend API to start session
      const response = await fetch(`${API_URL}/api/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          protocol_name: config.protocol.name,
          subject_ids: subjectIds,
          notes: "",
          experimenter: "",
        }),
      })

      const data = await response.json()

      if (data.success && data.session_id) {
        // Backend session started successfully, update frontend state
        setSessionState({
          sessionId: data.session_id,
          config,
          currentPhase: 0,
          phaseStartTime: Date.now(),
          isActive: true,
        })
        console.log("✓ Session started:", data.session_id)
      } else {
        console.error("Failed to start session:", data.error || "Unknown error")
        alert("Failed to start session. Please check the console for details.")
      }
    } catch (error) {
      console.error("Error starting session:", error)
      alert("Failed to start session. Please check the console for details.")
    }
  }

  const handleEndSession = async () => {
    try {
      // Save session data locally
      saveSession()

      // Call backend API to end session
      const response = await fetch(`${API_URL}/api/session/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })

      const data = await response.json()

      if (data.success) {
        console.log("✓ Session ended successfully")
      } else {
        console.error("Failed to end session:", data.error || "Unknown error")
      }
    } catch (error) {
      console.error("Error ending session:", error)
    } finally {
      // Always clear frontend state
      setSessionState(null)
      setSelectedProtocol(null)
    }
  }

  const handleLoadSession = (session: SavedSession) => {
    setShowSessionsManager(false)
    setReplaySession(session)
  }

  const handleInsertMarker = async (label: string) => {
    try {
      const response = await fetch(`${API_URL}/api/session/marker`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label,
          timestamp: Date.now() / 1000, // Unix timestamp in seconds
          metadata: {},
        }),
      })

      const data = await response.json()

      if (data.success) {
        console.log(`✓ Marker inserted: ${label}`)
      } else {
        console.error("Failed to insert marker:", data.error || "Unknown error")
      }
    } catch (error) {
      console.error("Error inserting marker:", error)
    }
  }

  // Convert session devices or scanned devices to Device format for components that expect it
  const connectedDevices: Device[] = sessionState?.isActive
    ? // When session is active, use session devices
      deviceStatus
        .filter((d) => d.status !== "disconnected")
        .map((d) => ({
          name: d.name,
          mac: d.address,
          status: "connected" as const,
          battery: null,
          streamName: d.streamName,
        }))
    : // When no session, use scanned devices that are connected
      scannedDevices.filter((d) => d.status === "connected")

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header isConnected={isConnected} />

      <div className="flex-1 flex">
        {/* Left Sidebar */}
        <aside className="w-80 border-r border-border bg-card p-6 space-y-6 overflow-y-auto">
          <DevicePanel
            scannedDevices={scannedDevices}
            sessionDevices={deviceStatus}
            isScanning={isScanning}
            onScan={handleScan}
            onConnect={handleConnect}
            onDisconnect={handleDisconnect}
            disabled={sessionState?.isActive}
          />

          {!sessionState?.isActive && (
            <Button variant="outline" className="w-full bg-transparent" onClick={() => setShowSessionsManager(true)}>
              <History className="h-4 w-4 mr-2" />
              Session History
            </Button>
          )}

          {sessionState?.isActive && (
            <SessionProgress
              isActive={sessionState.isActive}
              onEndSession={handleEndSession}
              onInsertMarker={handleInsertMarker}
            />
          )}
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto">
          {!sessionState?.isActive && !selectedProtocol && <ProtocolSelector onSelectProtocol={setSelectedProtocol} />}

          {!sessionState?.isActive && selectedProtocol && (
            <SessionConfig
              protocol={selectedProtocol}
              connectedDevices={connectedDevices}
              onStartSession={handleStartSession}
              onCancel={() => setSelectedProtocol(null)}
            />
          )}

          {sessionState?.isActive && (
            <div className="flex flex-col h-full">
              <div className="border-b border-border bg-card px-6 py-3 flex gap-2">
                <Button
                  variant={currentView === "feedback" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setCurrentView("feedback")}
                >
                  Neurofeedback
                </Button>
                <Button
                  variant={currentView === "raw" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setCurrentView("raw")}
                >
                  <Activity className="h-4 w-4 mr-2" />
                  Raw Data
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {currentView === "feedback" && <LiveFeedback metrics={metrics} connectedDevices={connectedDevices} />}
                {currentView === "raw" && <RawDataViewer rawData={rawData} connectedDevices={connectedDevices} />}
              </div>
            </div>
          )}
        </main>
      </div>

      {showSessionsManager && (
        <SessionsManager onLoadSession={handleLoadSession} onClose={() => setShowSessionsManager(false)} />
      )}

      {replaySession && <SessionReplay session={replaySession} onClose={() => setReplaySession(null)} />}
    </div>
  )
}
