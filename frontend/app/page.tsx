"use client"

import { useState } from "react"
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
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedProtocol, setSelectedProtocol] = useState<Protocol | null>(null)
  const [sessionState, setSessionState] = useState<SessionState | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [showSessionsManager, setShowSessionsManager] = useState(false)
  const [replaySession, setReplaySession] = useState<SavedSession | null>(null)
  const [currentView, setCurrentView] = useState<"feedback" | "raw">("feedback")

  const { metrics, isConnected, error } = useRealtimeData()
  const rawData = useRawEEGData()

  const { saveSession } = useSessionRecorder(
    sessionState?.isActive || false,
    sessionState?.sessionId || null,
    selectedProtocol,
    sessionState?.config,
    devices,
    metrics,
  )

  const handleScan = async () => {
    setIsScanning(true)
    try {
      const response = await fetch(`${API_URL}/api/devices/scan`)
      const data = await response.json()

      if (data.success && data.devices) {
        setDevices(
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
    const connectedCount = devices.filter((dev) => dev.status === "connected").length
    const streamName = `Muse_${connectedCount + 1}`

    try {
      const response = await fetch(`${API_URL}/api/devices/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: mac, stream_name: streamName }),
      })
      const data = await response.json()

      if (data.success) {
        setDevices((prev) =>
          prev.map((d) =>
            d.mac === mac
              ? {
                  ...d,
                  status: "connected",
                  streamName: streamName,
                }
              : d
          )
        )
      } else {
        console.error("Device connection failed:", data.error || "Unknown error")
      }
    } catch (error) {
      console.error("Failed to connect device:", error)
    }
  }

  const handleDisconnect = async (mac: string) => {
    const device = devices.find((d) => d.mac === mac)
    if (!device?.streamName) {
      console.error("Cannot disconnect: device has no stream name")
      return
    }

    try {
      const response = await fetch(`${API_URL}/api/devices/disconnect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stream_name: device.streamName }),
      })
      const data = await response.json()

      if (data.success) {
        setDevices((prev) =>
          prev.map((d) => (d.mac === mac ? { ...d, status: "available", streamName: null } : d))
        )
      } else {
        console.error("Device disconnection failed:", data.error || "Unknown error")
      }
    } catch (error) {
      console.error("Failed to disconnect device:", error)
    }
  }

  const handleStartSession = (config: any) => {
    setSessionState({
      sessionId: `session_${Date.now()}`,
      config,
      currentPhase: 0,
      phaseStartTime: Date.now(),
      isActive: true,
    })
  }

  const handleEndSession = () => {
    saveSession()
    setSessionState(null)
    setSelectedProtocol(null)
  }

  const handleLoadSession = (session: SavedSession) => {
    setShowSessionsManager(false)
    setReplaySession(session)
  }

  const connectedDevices = devices.filter((d) => d.status === "connected")

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header isConnected={isConnected} />

      <div className="flex-1 flex">
        {/* Left Sidebar */}
        <aside className="w-80 border-r border-border bg-card p-6 space-y-6 overflow-y-auto">
          <DevicePanel
            devices={devices}
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

          {sessionState?.isActive && <SessionProgress sessionState={sessionState} onEndSession={handleEndSession} />}
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
