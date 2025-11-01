"use client"

import { useState, useEffect, useRef } from "react"
import type { DeviceMetrics } from "@/types"

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws"
const RECONNECT_DELAY = 3000 // 3 seconds

export function useRealtimeData() {
  const [metrics, setMetrics] = useState<Record<string, DeviceMetrics>>({})
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const shouldReconnectRef = useRef(true)

  const connect = () => {
    try {
      console.log(`[WebSocket] Connecting to ${WS_URL}...`)

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        console.log("[WebSocket] Connected successfully")
        setIsConnected(true)
        setError(null)

        // Clear any pending reconnection attempts
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          // Handle different message types
          if (message.type === "feedback_update" && message.devices) {
            // Backend sends: { type: "feedback_update", timestamp: ..., devices: {...} }
            setMetrics(message.devices)
          } else if (Array.isArray(message)) {
            // Backend might send array of device metrics directly
            const devicesObj: Record<string, DeviceMetrics> = {}
            message.forEach((device: DeviceMetrics) => {
              devicesObj[device.subject] = device
            })
            setMetrics(devicesObj)
          } else {
            console.warn("[WebSocket] Unknown message format:", message)
          }
        } catch (err) {
          console.error("[WebSocket] Failed to parse message:", err)
        }
      }

      ws.onerror = (event) => {
        console.error("[WebSocket] Error:", event)
        setError("WebSocket connection error")
      }

      ws.onclose = (event) => {
        console.log(`[WebSocket] Disconnected (code: ${event.code}, reason: ${event.reason})`)
        setIsConnected(false)
        wsRef.current = null

        // Attempt to reconnect if we should
        if (shouldReconnectRef.current) {
          console.log(`[WebSocket] Reconnecting in ${RECONNECT_DELAY}ms...`)
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, RECONNECT_DELAY)
        }
      }
    } catch (err) {
      console.error("[WebSocket] Connection failed:", err)
      setError("Failed to connect to WebSocket")
      setIsConnected(false)
    }
  }

  useEffect(() => {
    // Enable reconnection
    shouldReconnectRef.current = true

    // Initial connection
    connect()

    // Cleanup on unmount
    return () => {
      shouldReconnectRef.current = false

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }

      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [])

  return { metrics, isConnected, error }
}
