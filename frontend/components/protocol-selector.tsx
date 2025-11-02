"use client"

import { useState, useEffect } from "react"
import { Clock, Layers, Eye, Loader2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { Protocol } from "@/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

interface ProtocolSelectorProps {
  onSelectProtocol: (protocol: Protocol) => void
}

export function ProtocolSelector({ onSelectProtocol }: ProtocolSelectorProps) {
  const [protocols, setProtocols] = useState<Protocol[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchProtocols = async () => {
      try {
        const response = await fetch(`${API_URL}/api/protocols`)
        const data = await response.json()

        if (data.success && data.protocols) {
          // Transform backend protocol format to frontend format
          const transformedProtocols: Protocol[] = data.protocols.map((p: any) => ({
            id: p.name.toLowerCase().replace(/\s+/g, "-"),
            name: p.name,
            description: p.description,
            phases: p.num_phases,
            duration: p.duration_seconds,
            feedbackEnabled: p.num_phases > 1, // Heuristic: multi-phase protocols typically have feedback
            timescales: 3, // Default to 3 timescales (1s, 2s, 4s)
            minDevices: p.min_devices,
            maxDevices: p.max_devices,
          }))
          setProtocols(transformedProtocols)
          setError(null)
        } else {
          setError("Failed to load protocols")
        }
      } catch (err) {
        console.error("Error fetching protocols:", err)
        setError("Failed to fetch protocols from server")
      } finally {
        setIsLoading(false)
      }
    }

    fetchProtocols()
  }, [])

  if (isLoading) {
    return (
      <div className="p-8 max-w-6xl mx-auto flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary mx-auto mb-3" />
          <p className="text-muted-foreground">Loading protocols...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8 max-w-6xl mx-auto">
        <Card className="p-6 border-red-200 bg-red-50 dark:bg-red-950/20">
          <p className="text-red-600 dark:text-red-400">{error}</p>
        </Card>
      </div>
    )
  }
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-foreground mb-2">Select Experimental Protocol</h2>
        <p className="text-muted-foreground">
          Choose a pre-configured protocol or create a custom one for your experiment
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {protocols.map((protocol) => (
          <Card
            key={protocol.id}
            className="p-6 cursor-pointer hover:border-primary hover:shadow-lg transition-all"
            onClick={() => onSelectProtocol(protocol)}
          >
            <div className="space-y-4">
              <div>
                <h3 className="text-xl font-bold text-foreground mb-2">{protocol.name}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{protocol.description}</p>
              </div>

              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary" className="gap-1.5">
                  <Layers className="h-3 w-3" />
                  {protocol.phases} {protocol.phases === 1 ? "phase" : "phases"}
                </Badge>
                <Badge variant="secondary" className="gap-1.5">
                  <Clock className="h-3 w-3" />
                  {formatDuration(protocol.duration)}
                </Badge>
                <Badge variant="secondary" className="gap-1.5">
                  <Eye className="h-3 w-3" />
                  {protocol.feedbackEnabled ? "Feedback ON" : "Recording Only"}
                </Badge>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Button variant="outline" className="w-full bg-transparent">
        Create Custom Protocol
      </Button>
    </div>
  )
}
