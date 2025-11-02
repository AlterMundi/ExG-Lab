"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Device, RawEEGData } from "@/types"
import { Activity, Waves } from "lucide-react"

interface RawDataViewerProps {
  rawData: Record<string, RawEEGData>
  connectedDevices: Device[]
}

export function RawDataViewer({ rawData, connectedDevices }: RawDataViewerProps) {
  const channels = ["TP9", "AF7", "AF8", "TP10"] as const

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-foreground">Raw EEG Data</h2>
          <p className="text-sm text-muted-foreground mt-1">Time domain waveforms and frequency domain analysis</p>
        </div>
        <Badge variant="outline" className="bg-background">
          <Activity className="h-3 w-3 mr-1" />
          {connectedDevices.length} Device{connectedDevices.length !== 1 ? "s" : ""}
        </Badge>
      </div>

      <div className="grid gap-6">
        {connectedDevices.map((device) => {
          const data = rawData[device.streamName || ""]
          if (!data) return null

          return (
            <Card key={device.mac} className="bg-card border-border">
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg font-medium text-foreground flex items-center gap-2">
                    <Waves className="h-5 w-5 text-primary" />
                    {device.streamName}
                  </CardTitle>
                  <Badge variant="secondary" className="bg-muted">
                    {device.name}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Time Domain Waveforms */}
                <div>
                  <h3 className="text-sm font-medium text-foreground mb-3">Time Domain (1 second window)</h3>
                  <div className="grid grid-cols-2 gap-4">
                    {channels.map((channel) => (
                      <div key={channel} className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-muted-foreground">{channel}</span>
                          <span className="text-xs text-muted-foreground">
                            Quality: {data.channels[channel].quality.toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-24 bg-background rounded border border-border relative overflow-hidden">
                          <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
                            <polyline
                              fill="none"
                              stroke="hsl(var(--primary))"
                              strokeWidth="0.5"
                              points={data.channels[channel].timeDomain
                                .map((value, i) => {
                                  const numSamples = data.channels[channel].timeDomain.length
                                  const x = (i / (numSamples - 1)) * 100
                                  // Auto-scale based on data range
                                  const maxVal = Math.max(...data.channels[channel].timeDomain.map(Math.abs))
                                  const scale = maxVal > 0 ? 40 / maxVal : 1
                                  const y = 50 - value * scale
                                  return `${x},${y}`
                                })
                                .join(" ")}
                              vectorEffect="non-scaling-stroke"
                            />
                            {/* Zero line */}
                            <line
                              x1="0"
                              y1="50"
                              x2="100"
                              y2="50"
                              stroke="hsl(var(--muted-foreground))"
                              strokeWidth="0.3"
                              strokeDasharray="2,2"
                              opacity="0.3"
                            />
                          </svg>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Frequency Domain */}
                <div>
                  <h3 className="text-sm font-medium text-foreground mb-3">Frequency Domain (Power Spectrum)</h3>
                  <div className="grid grid-cols-2 gap-4">
                    {channels.map((channel) => {
                      const bands = data.channels[channel].frequencyDomain
                      const maxPower = Math.max(bands.delta, bands.theta, bands.alpha, bands.beta, bands.gamma)

                      return (
                        <div key={channel} className="space-y-2">
                          <span className="text-xs font-medium text-muted-foreground">{channel}</span>
                          <div className="space-y-1.5">
                            {Object.entries(bands).map(([band, power]) => (
                              <div key={band} className="flex items-center gap-2">
                                <span className="text-xs text-muted-foreground w-12 capitalize">{band}</span>
                                <div className="flex-1 h-5 bg-background rounded-sm border border-border overflow-hidden">
                                  <div
                                    className="h-full bg-primary transition-all duration-300"
                                    style={{ width: `${(power / maxPower) * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-muted-foreground w-12 text-right">
                                  {power.toFixed(1)}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Frequency Band Legend */}
                <div className="pt-2 border-t border-border">
                  <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <span>
                      <strong>Delta:</strong> 0.5-4 Hz
                    </span>
                    <span>
                      <strong>Theta:</strong> 4-8 Hz
                    </span>
                    <span>
                      <strong>Alpha:</strong> 8-13 Hz
                    </span>
                    <span>
                      <strong>Beta:</strong> 13-30 Hz
                    </span>
                    <span>
                      <strong>Gamma:</strong> 30-50 Hz
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {connectedDevices.length === 0 && (
        <Card className="bg-card border-border">
          <CardContent className="py-12 text-center">
            <Waves className="h-12 w-12 text-muted-foreground mx-auto mb-3 opacity-50" />
            <p className="text-muted-foreground">No devices connected. Connect devices to view raw EEG data.</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
