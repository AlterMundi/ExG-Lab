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
import { useMockData } from "@/hooks/use-mock-data"
import { useSessionRecorder } from "@/hooks/use-session-recorder"
import { useRawEEGData } from "@/hooks/use-raw-eeg-data"
import { Button } from "@/components/ui/button"
import { History, Activity } from "lucide-react"
import type { Device, Protocol, SessionState, SavedSession } from "@/types"

export default function ExGLabPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedProtocol, setSelectedProtocol] = useState<Protocol | null>(null)
  const [sessionState, setSessionState] = useState<SessionState | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [showSessionsManager, setShowSessionsManager] = useState(false)
  const [replaySession, setReplaySession] = useState<SavedSession | null>(null)
  const [currentView, setCurrentView] = useState<"feedback" | "raw">("feedback")

  const { metrics, isConnected } = useMockData()
  const rawData = useRawEEGData()

  const { saveSession } = useSessionRecorder(
    sessionState?.isActive || false,
    sessionState?.sessionId || null,
    selectedProtocol,
    sessionState?.config,
    devices,
    metrics,
  )

  const handleScan = () => {
    setIsScanning(true)
    setTimeout(() => {
      setDevices([
        {
          name: "Muse S - 3C4F",
          mac: "00:55:DA:B3:3C:4F",
          status: "available",
          battery: 87,
          streamName: null,
        },
        {
          name: "Muse S - 7A21",
          mac: "00:55:DA:B3:7A:21",
          status: "available",
          battery: 72,
          streamName: null,
        },
        {
          name: "Muse S - 9B15",
          mac: "00:55:DA:B3:9B:15",
          status: "available",
          battery: 94,
          streamName: null,
        },
      ])
      setIsScanning(false)
    }, 1500)
  }

  const handleConnect = (mac: string) => {
    setDevices((prev) =>
      prev.map((d) =>
        d.mac === mac
          ? {
              ...d,
              status: "connected",
              streamName: `Muse_${devices.filter((dev) => dev.status === "connected").length + 1}`,
            }
          : d,
      ),
    )
  }

  const handleDisconnect = (mac: string) => {
    setDevices((prev) => prev.map((d) => (d.mac === mac ? { ...d, status: "available", streamName: null } : d)))
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
