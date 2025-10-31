"use client"

import { useState, useEffect } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Slider } from "@/components/ui/slider"
import { Play, Pause, SkipBack, SkipForward, X } from "lucide-react"
import type { SavedSession } from "@/types"

interface SessionReplayProps {
  session: SavedSession
  onClose: () => void
}

export function SessionReplay({ session, onClose }: SessionReplayProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)

  const currentDataPoint = session.dataPoints[currentIndex]
  const progress = (currentIndex / (session.dataPoints.length - 1)) * 100

  // Auto-play
  useEffect(() => {
    if (!isPlaying) return

    const interval = setInterval(() => {
      setCurrentIndex((prev) => {
        if (prev >= session.dataPoints.length - 1) {
          setIsPlaying(false)
          return prev
        }
        return prev + 1
      })
    }, 100 / playbackSpeed)

    return () => clearInterval(interval)
  }, [isPlaying, playbackSpeed, session.dataPoints.length])

  const formatTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`
  }

  const handleSliderChange = (value: number[]) => {
    setCurrentIndex(Math.floor((value[0] / 100) * (session.dataPoints.length - 1)))
    setIsPlaying(false)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Session Replay: {session.protocol.name}</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {new Date(session.timestamp).toLocaleString()} • {session.devices.length} devices
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Playback Controls */}
        <div className="p-6 border-b border-border space-y-4">
          <div className="flex items-center gap-4">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCurrentIndex(Math.max(0, currentIndex - 10))}
              disabled={currentIndex === 0}
            >
              <SkipBack className="h-4 w-4" />
            </Button>

            <Button size="sm" onClick={() => setIsPlaying(!isPlaying)}>
              {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>

            <Button
              size="sm"
              variant="outline"
              onClick={() => setCurrentIndex(Math.min(session.dataPoints.length - 1, currentIndex + 10))}
              disabled={currentIndex === session.dataPoints.length - 1}
            >
              <SkipForward className="h-4 w-4" />
            </Button>

            <div className="flex-1">
              <Slider value={[progress]} onValueChange={handleSliderChange} max={100} step={0.1} />
            </div>

            <span className="text-sm font-mono text-muted-foreground min-w-[80px]">
              {formatTime(currentDataPoint?.timestamp || 0)} / {formatTime(session.duration)}
            </span>

            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              className="text-sm border border-border rounded px-2 py-1 bg-background"
            >
              <option value={0.5}>0.5x</option>
              <option value={1}>1x</option>
              <option value={2}>2x</option>
              <option value={4}>4x</option>
            </select>
          </div>
        </div>

        {/* Data Visualization */}
        <div className="flex-1 overflow-y-auto p-6">
          {currentDataPoint && (
            <div className="space-y-6">
              {session.devices.map((device) => {
                const metrics = currentDataPoint.metrics[device.streamName!]
                if (!metrics) return null

                return (
                  <Card key={device.streamName} className="p-6">
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-xl font-bold text-foreground">
                        {device.streamName}: {metrics.subject}
                      </h3>
                      <Badge variant="outline">
                        Data Age: {"<"}
                        {metrics.quality.data_age_ms}ms
                      </Badge>
                    </div>

                    {/* Timescale Bars */}
                    <div className="space-y-6">
                      {/* Fast (1s) */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-foreground">Fast (1s)</span>
                          <span className="text-lg font-bold text-green-600">
                            {metrics.frontal["1s"].relaxation.toFixed(2)}
                          </span>
                        </div>
                        <div className="h-8 bg-green-100 dark:bg-green-950/30 rounded-lg overflow-hidden">
                          <div
                            className="h-full bg-green-500 transition-all duration-100"
                            style={{ width: `${(metrics.frontal["1s"].relaxation / 4) * 100}%` }}
                          />
                        </div>
                      </div>

                      {/* Balanced (2s) */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-foreground">Balanced (2s)</span>
                          <span className="text-lg font-bold text-yellow-600">
                            {metrics.frontal["2s"].relaxation.toFixed(2)}
                          </span>
                        </div>
                        <div className="h-8 bg-yellow-100 dark:bg-yellow-950/30 rounded-lg overflow-hidden">
                          <div
                            className="h-full bg-yellow-500 transition-all duration-100"
                            style={{ width: `${(metrics.frontal["2s"].relaxation / 4) * 100}%` }}
                          />
                        </div>
                      </div>

                      {/* Stable (4s) */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-foreground">Stable (4s)</span>
                          <span className="text-lg font-bold text-blue-600">
                            {metrics.frontal["4s"].relaxation.toFixed(2)}
                          </span>
                        </div>
                        <div className="h-8 bg-blue-100 dark:bg-blue-950/30 rounded-lg overflow-hidden">
                          <div
                            className="h-full bg-blue-500 transition-all duration-100"
                            style={{ width: `${(metrics.frontal["4s"].relaxation / 4) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          )}
        </div>

        {/* Summary Stats */}
        <div className="p-6 border-t border-border bg-muted/30">
          <h3 className="text-sm font-semibold text-foreground mb-3">Session Summary</h3>
          <div className="grid grid-cols-3 gap-6">
            {Object.entries(session.summary.avgRelaxation).map(([deviceName, values]) => (
              <div key={deviceName} className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground">{deviceName}</p>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg Fast:</span>
                    <span className="text-green-600 font-semibold">{values.fast.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg Balanced:</span>
                    <span className="text-yellow-600 font-semibold">{values.balanced.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Avg Stable:</span>
                    <span className="text-blue-600 font-semibold">{values.stable.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}
