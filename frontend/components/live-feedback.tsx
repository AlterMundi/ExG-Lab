import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Device, DeviceMetrics } from "@/types"

interface LiveFeedbackProps {
  metrics: Record<string, DeviceMetrics>
  connectedDevices: Device[]
}

export function LiveFeedback({ metrics, connectedDevices }: LiveFeedbackProps) {
  const getTrendMessage = (fast: number, balanced: number, stable: number) => {
    if (fast > balanced && balanced > stable) {
      return { text: "You're getting more relaxed! 🎯", icon: TrendingUp, color: "text-green-600" }
    } else if (Math.abs(fast - balanced) < 0.3 && Math.abs(balanced - stable) < 0.3) {
      return { text: "Nice and steady", icon: Minus, color: "text-blue-600" }
    } else if (fast < balanced && balanced < stable) {
      return { text: "Relaxation decreasing", icon: TrendingDown, color: "text-orange-600" }
    }
    return { text: "Variable state", icon: Minus, color: "text-gray-600" }
  }

  const getTrendBadge = (fast: number, balanced: number, stable: number) => {
    if (fast > balanced && balanced > stable) {
      return { text: "IMPROVING ↗", color: "bg-green-500" }
    } else if (fast < balanced && balanced < stable) {
      return { text: "DECLINING ↘", color: "bg-orange-500" }
    }
    return { text: "STABLE ↔", color: "bg-blue-500" }
  }

  return (
    <div className="p-8 space-y-6">
      {connectedDevices.map((device) => {
        const deviceMetrics = metrics[device.streamName!]
        if (!deviceMetrics) return null

        const { frontal, quality } = deviceMetrics
        const trend = getTrendMessage(frontal["1s"].relaxation, frontal["2s"].relaxation, frontal["4s"].relaxation)
        const badge = getTrendBadge(frontal["1s"].relaxation, frontal["2s"].relaxation, frontal["4s"].relaxation)

        const dataAgeColor =
          quality.data_age_ms < 100 ? "text-green-600" : quality.data_age_ms < 500 ? "text-orange-600" : "text-red-600"

        return (
          <Card key={device.streamName} className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <h3 className="text-xl font-bold text-foreground">
                  {device.streamName}: {deviceMetrics.subject}
                </h3>
                <Badge className={`${badge.color} text-white`}>{badge.text}</Badge>
              </div>
              <span className={`text-sm font-mono font-semibold ${dataAgeColor}`}>
                {"<"}
                {quality.data_age_ms}ms
              </span>
            </div>

            {/* Trend Message */}
            <div className="text-center mb-8">
              <div className={`flex items-center justify-center gap-2 text-2xl font-semibold ${trend.color}`}>
                <trend.icon className="h-7 w-7" />
                <span>{trend.text}</span>
              </div>
            </div>

            {/* Timescale Bars */}
            <div className="space-y-6 mb-8">
              {/* Fast (1s) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-foreground">Fast (1s)</span>
                  <span className="text-lg font-bold text-green-600">{frontal["1s"].relaxation.toFixed(2)}</span>
                </div>
                <div className="h-8 bg-green-100 dark:bg-green-950/30 rounded-lg overflow-hidden">
                  <div
                    className="h-full bg-green-500 transition-all duration-300 animate-data-update"
                    style={{ width: `${(frontal["1s"].relaxation / 4) * 100}%` }}
                  />
                </div>
              </div>

              {/* Balanced (2s) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-foreground">Balanced (2s)</span>
                  <span className="text-lg font-bold text-yellow-600">{frontal["2s"].relaxation.toFixed(2)}</span>
                </div>
                <div className="h-8 bg-yellow-100 dark:bg-yellow-950/30 rounded-lg overflow-hidden">
                  <div
                    className="h-full bg-yellow-500 transition-all duration-300 animate-data-update"
                    style={{ width: `${(frontal["2s"].relaxation / 4) * 100}%` }}
                  />
                </div>
              </div>

              {/* Stable (4s) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-foreground">Stable (4s)</span>
                  <span className="text-lg font-bold text-blue-600">{frontal["4s"].relaxation.toFixed(2)}</span>
                </div>
                <div className="h-8 bg-blue-100 dark:bg-blue-950/30 rounded-lg overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-300 animate-data-update"
                    style={{ width: `${(frontal["4s"].relaxation / 4) * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Current State Callout */}
            <div className="bg-muted rounded-lg p-6 text-center">
              <p className="text-sm text-muted-foreground mb-2">Current Relaxation</p>
              <p className="text-4xl font-bold text-foreground mb-1">{frontal["2s"].relaxation.toFixed(2)}</p>
              <p className="text-sm text-muted-foreground">Target: 2.00</p>
            </div>
          </Card>
        )
      })}
    </div>
  )
}
