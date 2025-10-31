"use client"

import { useState, useEffect, useCallback } from "react"
import type { Device, Protocol, DeviceMetrics, SavedSession, SessionDataPoint, SessionSummary } from "@/types"

export function useSessionRecorder(
  isActive: boolean,
  sessionId: string | null,
  protocol: Protocol | null,
  config: any,
  devices: Device[],
  metrics: Record<string, DeviceMetrics>,
) {
  const [dataPoints, setDataPoints] = useState<SessionDataPoint[]>([])
  const [startTime, setStartTime] = useState<number | null>(null)

  // Start recording
  useEffect(() => {
    if (isActive && !startTime) {
      setStartTime(Date.now())
      setDataPoints([])
    } else if (!isActive && startTime) {
      setStartTime(null)
    }
  }, [isActive, startTime])

  // Record data points
  useEffect(() => {
    if (isActive && startTime && Object.keys(metrics).length > 0) {
      const dataPoint: SessionDataPoint = {
        timestamp: Date.now() - startTime,
        metrics: { ...metrics },
      }
      setDataPoints((prev) => [...prev, dataPoint])
    }
  }, [metrics, isActive, startTime])

  // Save session
  const saveSession = useCallback(() => {
    if (!sessionId || !protocol || !startTime || dataPoints.length === 0) return

    const summary = calculateSummary(dataPoints, devices)
    const savedSession: SavedSession = {
      sessionId,
      timestamp: startTime,
      protocol,
      config,
      devices: devices.filter((d) => d.status === "connected"),
      duration: Date.now() - startTime,
      dataPoints,
      summary,
    }

    // Save to localStorage
    const existingSessions = JSON.parse(localStorage.getItem("exg-lab-sessions") || "[]")
    existingSessions.push(savedSession)
    localStorage.setItem("exg-lab-sessions", JSON.stringify(existingSessions))

    console.log("[v0] Session saved:", savedSession.sessionId)
  }, [sessionId, protocol, config, devices, dataPoints, startTime])

  return { saveSession, dataPoints }
}

function calculateSummary(dataPoints: SessionDataPoint[], devices: Device[]): SessionSummary {
  const summary: SessionSummary = {
    avgRelaxation: {},
    maxRelaxation: {},
    minRelaxation: {},
    totalDataPoints: dataPoints.length,
  }

  devices.forEach((device) => {
    if (!device.streamName) return

    const deviceData = dataPoints.map((dp) => dp.metrics[device.streamName!]).filter((m) => m !== undefined)

    if (deviceData.length === 0) return

    const fastValues = deviceData.map((m) => m.frontal["1s"].relaxation)
    const balancedValues = deviceData.map((m) => m.frontal["2s"].relaxation)
    const stableValues = deviceData.map((m) => m.frontal["4s"].relaxation)

    summary.avgRelaxation[device.streamName] = {
      fast: fastValues.reduce((a, b) => a + b, 0) / fastValues.length,
      balanced: balancedValues.reduce((a, b) => a + b, 0) / balancedValues.length,
      stable: stableValues.reduce((a, b) => a + b, 0) / stableValues.length,
    }

    summary.maxRelaxation[device.streamName] = {
      fast: Math.max(...fastValues),
      balanced: Math.max(...balancedValues),
      stable: Math.max(...stableValues),
    }

    summary.minRelaxation[device.streamName] = {
      fast: Math.min(...fastValues),
      balanced: Math.min(...balancedValues),
      stable: Math.min(...stableValues),
    }
  })

  return summary
}
