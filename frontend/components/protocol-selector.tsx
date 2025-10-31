"use client"

import { Clock, Layers, Eye, Hash } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { Protocol } from "@/types"

interface ProtocolSelectorProps {
  onSelectProtocol: (protocol: Protocol) => void
}

const PROTOCOLS: Protocol[] = [
  {
    id: "meditation-baseline",
    name: "Meditation Baseline",
    description: "Pure data recording without feedback. Ideal for establishing participant baselines.",
    phases: 1,
    duration: 300,
    feedbackEnabled: false,
    timescales: 1,
  },
  {
    id: "neurofeedback-training",
    name: "Neurofeedback Training",
    description: "Standard 3-phase protocol: pre-baseline, active training with full feedback, post-assessment.",
    phases: 3,
    duration: 800,
    feedbackEnabled: true,
    timescales: 3,
  },
  {
    id: "multi-subject-sync",
    name: "Multi-Subject Synchronized",
    description: "4-person synchronized training session with group baseline and coordinated feedback.",
    phases: 2,
    duration: 1080,
    feedbackEnabled: true,
    timescales: 1,
  },
  {
    id: "ab-test-timescale",
    name: "A/B Test: Timescale Comparison",
    description: "Compare effectiveness of different feedback timescales across experimental groups.",
    phases: 2,
    duration: 780,
    feedbackEnabled: true,
    timescales: 0,
  },
]

export function ProtocolSelector({ onSelectProtocol }: ProtocolSelectorProps) {
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
        {PROTOCOLS.map((protocol) => (
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
                {protocol.timescales > 0 && (
                  <Badge variant="secondary" className="gap-1.5">
                    <Hash className="h-3 w-3" />
                    {protocol.timescales} timescale{protocol.timescales > 1 ? "s" : ""}
                  </Badge>
                )}
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
