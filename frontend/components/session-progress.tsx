"use client"

import { useState } from "react"
import { Clock, AlertTriangle, Tag } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Input } from "@/components/ui/input"
import { useSessionStatus } from "@/hooks/use-session-status"

interface SessionProgressProps {
  isActive: boolean
  onEndSession: () => void
  onInsertMarker?: (label: string) => void
}

export function SessionProgress({ isActive, onEndSession, onInsertMarker }: SessionProgressProps) {
  const { status } = useSessionStatus(isActive)
  const [markerLabel, setMarkerLabel] = useState("")
  const [showMarkerInput, setShowMarkerInput] = useState(false)

  if (!status || !status.isActive) {
    return null
  }

  // Format time as MM:SS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  // Calculate phase progress percentage
  const totalDuration = status.elapsedSeconds + (status.remainingSeconds || 0)
  const phaseProgress = totalDuration > 0 ? (status.elapsedSeconds / totalDuration) * 100 : 0

  // Get phase display
  const phaseDisplay = status.phaseName || status.currentPhase

  const handleInsertMarker = () => {
    if (markerLabel.trim() && onInsertMarker) {
      onInsertMarker(markerLabel.trim())
      setMarkerLabel("")
      setShowMarkerInput(false)
    }
  }

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">Session Progress</h3>
        <Clock className="h-5 w-5 text-muted-foreground" />
      </div>

      {/* Session Info */}
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Protocol</p>
        <p className="font-medium text-sm">{status.protocolName}</p>
      </div>

      {/* Phase Progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-foreground">{phaseDisplay}</span>
          <Badge variant="secondary" className="capitalize">
            {status.currentPhase.replace("_", " ")}
          </Badge>
        </div>
        <Progress value={phaseProgress} className="h-2" />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{formatTime(status.elapsedSeconds)}</span>
          <span>{formatTime(totalDuration)}</span>
        </div>
      </div>

      {/* Feedback Status */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Feedback</span>
        <Badge variant={status.feedbackEnabled ? "default" : "secondary"} className="text-xs">
          {status.feedbackEnabled ? "ON" : "OFF"}
        </Badge>
      </div>

      {/* Actions */}
      <div className="space-y-2">
        {showMarkerInput ? (
          <div className="flex gap-2">
            <Input
              placeholder="Marker label..."
              value={markerLabel}
              onChange={(e) => setMarkerLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleInsertMarker()
                if (e.key === "Escape") setShowMarkerInput(false)
              }}
              className="text-sm"
              autoFocus
            />
            <Button size="sm" onClick={handleInsertMarker} disabled={!markerLabel.trim()}>
              Add
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="w-full bg-transparent"
            onClick={() => setShowMarkerInput(true)}
          >
            <Tag className="h-4 w-4 mr-2" />
            Insert Marker
          </Button>
        )}
      </div>

      <Button variant="destructive" size="sm" className="w-full" onClick={onEndSession}>
        <AlertTriangle className="mr-2 h-4 w-4" />
        End Session Early
      </Button>
    </Card>
  )
}
