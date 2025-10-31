"use client"

import { useState, useEffect } from "react"

export function useWebSocket(url = "ws://localhost:8000/ws") {
  const [isConnected, setIsConnected] = useState(false)
  const [metrics, setMetrics] = useState<any>({})

  useEffect(() => {
    // Mock WebSocket connection
    setIsConnected(true)

    return () => {
      setIsConnected(false)
    }
  }, [url])

  return { metrics, isConnected }
}
