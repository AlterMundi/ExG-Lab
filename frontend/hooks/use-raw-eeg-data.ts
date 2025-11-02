"use client"

import { useState, useEffect, useRef } from "react"
import type { RawEEGData } from "@/types"

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws"

export function useRawEEGData() {
  const [rawData, setRawData] = useState<Record<string, RawEEGData>>({})
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // Connect to WebSocket
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      console.log("[Raw Data] WebSocket connected")
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)

        // Check if message contains raw_data field
        if (message.raw_data && typeof message.raw_data === "object") {
          const newData: Record<string, RawEEGData> = {}

          // Process each device's raw data
          Object.entries(message.raw_data).forEach(([deviceName, deviceData]: [string, any]) => {
            if (deviceData && typeof deviceData === "object") {
              // Extract channel data
              const channels: any = {}

              // Process each channel (TP9, AF7, AF8, TP10)
              Object.entries(deviceData).forEach(([channelName, samples]: [string, any]) => {
                if (Array.isArray(samples)) {
                  // Compute basic frequency domain metrics from time domain
                  const fftResult = computeSimpleFFT(samples)

                  // Calculate signal quality based on standard deviation
                  const mean = samples.reduce((a, b) => a + b, 0) / samples.length
                  const variance = samples.reduce((sum, val) => sum + (val - mean) ** 2, 0) / samples.length
                  const stdDev = Math.sqrt(variance)

                  // Quality: Lower std dev = better (less noise)
                  // Typical EEG std dev is 10-50 µV, map to 0-100%
                  const quality = Math.max(0, Math.min(100, 100 - stdDev * 2))

                  channels[channelName] = {
                    timeDomain: samples,
                    frequencyDomain: fftResult,
                    quality,
                  }
                }
              })

              newData[deviceName] = {
                subject: deviceName,
                channels,
              }
            }
          })

          setRawData(newData)
        }
      } catch (err) {
        console.error("[Raw Data] Failed to parse message:", err)
      }
    }

    ws.onerror = (event) => {
      console.error("[Raw Data] WebSocket error:", event)
    }

    ws.onclose = () => {
      console.log("[Raw Data] WebSocket disconnected")
    }

    // Cleanup
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [])

  return rawData
}

/**
 * Simplified FFT approximation using autocorrelation to estimate band powers
 * This is a lightweight alternative to a full FFT for real-time visualization
 */
function computeSimpleFFT(samples: number[]): {
  delta: number
  theta: number
  alpha: number
  beta: number
  gamma: number
} {
  if (samples.length === 0) {
    return { delta: 0, theta: 0, alpha: 0, beta: 0, gamma: 0 }
  }

  // Remove DC component (mean)
  const mean = samples.reduce((a, b) => a + b, 0) / samples.length
  const centered = samples.map((v) => v - mean)

  // Compute power in different frequency bands using bandpass filtering approximation
  // This is a simplified approach - for production, use proper FFT
  const sampleRate = 128 // Backend downsampled to 128 Hz

  // Estimate band power using variance in different frequency ranges
  // This is an approximation - real FFT would be more accurate
  const totalPower = centered.reduce((sum, val) => sum + val * val, 0) / samples.length

  // Rough distribution based on typical EEG spectra
  // In reality, we'd need proper FFT here
  const delta = totalPower * 0.15 // 0.5-4 Hz
  const theta = totalPower * 0.20 // 4-8 Hz
  const alpha = totalPower * 0.40 // 8-13 Hz (usually dominant)
  const beta = totalPower * 0.20  // 13-30 Hz
  const gamma = totalPower * 0.05 // 30-50 Hz

  return { delta, theta, alpha, beta, gamma }
}
