"use client"

import { useState, useEffect } from "react"
import type { DeviceMetrics } from "@/types"

export function useMockData() {
  const [metrics, setMetrics] = useState<Record<string, DeviceMetrics>>({
    Muse_1: {
      subject: "Alice",
      frontal: {
        "1s": { relaxation: 2.34, alpha: 0.45, beta: 0.32 },
        "2s": { relaxation: 1.87, alpha: 0.42, beta: 0.35 },
        "4s": { relaxation: 1.45, alpha: 0.38, beta: 0.37 },
      },
      quality: {
        data_age_ms: 45,
        signal_quality: { TP9: 0.95, AF7: 0.88, AF8: 0.92, TP10: 0.97 },
      },
    },
    Muse_2: {
      subject: "Bob",
      frontal: {
        "1s": { relaxation: 1.12, alpha: 0.35, beta: 0.41 },
        "2s": { relaxation: 1.25, alpha: 0.36, beta: 0.4 },
        "4s": { relaxation: 1.48, alpha: 0.38, beta: 0.38 },
      },
      quality: {
        data_age_ms: 52,
        signal_quality: { TP9: 0.91, AF7: 0.85, AF8: 0.89, TP10: 0.93 },
      },
    },
  })

  const [isConnected, setIsConnected] = useState(true)

  useEffect(() => {
    // Simulate real-time updates every 100ms
    const interval = setInterval(() => {
      setMetrics((prev) => {
        const updated = { ...prev }

        Object.keys(updated).forEach((key) => {
          // Random walk for relaxation values
          updated[key].frontal["1s"].relaxation += (Math.random() - 0.5) * 0.15
          updated[key].frontal["2s"].relaxation += (Math.random() - 0.5) * 0.1
          updated[key].frontal["4s"].relaxation += (Math.random() - 0.5) * 0.08

          // Keep values in reasonable range
          updated[key].frontal["1s"].relaxation = Math.max(0.5, Math.min(3.5, updated[key].frontal["1s"].relaxation))
          updated[key].frontal["2s"].relaxation = Math.max(0.5, Math.min(3.5, updated[key].frontal["2s"].relaxation))
          updated[key].frontal["4s"].relaxation = Math.max(0.5, Math.min(3.5, updated[key].frontal["4s"].relaxation))

          // Update data age
          updated[key].quality.data_age_ms = Math.floor(Math.random() * 100) + 30
        })

        return updated
      })
    }, 100)

    return () => clearInterval(interval)
  }, [])

  return { metrics, isConnected }
}
