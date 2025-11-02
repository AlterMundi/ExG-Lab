"use client"

import { useState, useEffect, useRef } from "react"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const POLL_INTERVAL = 1000 // 1 second

export interface SessionStatus {
  isActive: boolean
  sessionId: string | null
  protocolName: string | null
  currentPhase: string
  phaseName: string | null
  elapsedSeconds: number
  remainingSeconds: number | null
  devices: string[]
  subjectIds: Record<string, string>
  connectedDevices: Array<{
    address: string
    name: string
    streamName: string
    status: string
    connectedAt: number
    disconnectedAt: number | null
  }>
  feedbackEnabled: boolean
  instructions: string | null
}

export function useSessionStatus(enabled: boolean = true) {
  const [status, setStatus] = useState<SessionStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      return
    }

    const fetchStatus = async () => {
      try {
        const response = await fetch(`${API_URL}/api/session/status`)
        const data = await response.json()

        if (data.success) {
          setStatus({
            isActive: data.is_active,
            sessionId: data.session_id,
            protocolName: data.protocol_name,
            currentPhase: data.current_phase,
            phaseName: data.phase_name,
            elapsedSeconds: data.elapsed_seconds,
            remainingSeconds: data.remaining_seconds,
            devices: data.devices,
            subjectIds: data.subject_ids,
            connectedDevices: data.connected_devices,
            feedbackEnabled: data.feedback_enabled,
            instructions: data.instructions,
          })
          setError(null)
        }
      } catch (err) {
        console.error("[Session Status] Failed to fetch:", err)
        setError("Failed to fetch session status")
      }
    }

    // Initial fetch
    fetchStatus()

    // Poll every second
    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [enabled])

  return { status, error }
}
