"use client"

import { useState, useEffect } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Play, Trash2, Download, X } from "lucide-react"
import type { SavedSession } from "@/types"

interface SessionsManagerProps {
  onLoadSession: (session: SavedSession) => void
  onClose: () => void
}

export function SessionsManager({ onLoadSession, onClose }: SessionsManagerProps) {
  const [sessions, setSessions] = useState<SavedSession[]>([])

  useEffect(() => {
    loadSessions()
  }, [])

  const loadSessions = () => {
    const saved = JSON.parse(localStorage.getItem("exg-lab-sessions") || "[]")
    setSessions(saved.sort((a: SavedSession, b: SavedSession) => b.timestamp - a.timestamp))
  }

  const deleteSession = (sessionId: string) => {
    const filtered = sessions.filter((s) => s.sessionId !== sessionId)
    localStorage.setItem("exg-lab-sessions", JSON.stringify(filtered))
    setSessions(filtered)
  }

  const exportSession = (session: SavedSession) => {
    const dataStr = JSON.stringify(session, null, 2)
    const dataBlob = new Blob([dataStr], { type: "application/json" })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${session.sessionId}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`
  }

  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleString()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Session History</h2>
            <p className="text-sm text-muted-foreground mt-1">{sessions.length} saved sessions</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto p-6">
          {sessions.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No saved sessions yet</p>
              <p className="text-sm text-muted-foreground mt-2">Complete a session to see it here</p>
            </div>
          ) : (
            <div className="space-y-4">
              {sessions.map((session) => (
                <Card key={session.sessionId} className="p-4 hover:bg-muted/50 transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 space-y-2">
                      {/* Session Info */}
                      <div className="flex items-center gap-3">
                        <h3 className="font-semibold text-foreground">{session.protocol.name}</h3>
                        <Badge variant="outline">{session.devices.length} devices</Badge>
                        <Badge variant="outline">{formatDuration(session.duration)}</Badge>
                      </div>

                      <p className="text-sm text-muted-foreground">{formatDate(session.timestamp)}</p>

                      {/* Summary Stats */}
                      <div className="grid grid-cols-3 gap-4 mt-3">
                        {Object.entries(session.summary.avgRelaxation).map(([deviceName, values]) => (
                          <div key={deviceName} className="space-y-1">
                            <p className="text-xs font-semibold text-muted-foreground">{deviceName}</p>
                            <div className="flex gap-2 text-xs">
                              <span className="text-green-600">1s: {values.fast.toFixed(2)}</span>
                              <span className="text-yellow-600">2s: {values.balanced.toFixed(2)}</span>
                              <span className="text-blue-600">4s: {values.stable.toFixed(2)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => onLoadSession(session)}>
                        <Play className="h-4 w-4 mr-1" />
                        Replay
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => exportSession(session)}>
                        <Download className="h-4 w-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          if (confirm("Delete this session?")) deleteSession(session.sessionId)
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
