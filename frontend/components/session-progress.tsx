"use client"

import { Clock, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import type { SessionState } from "@/types"

interface SessionProgressProps {
  sessionState: SessionState
  onEndSession: () => void
}

export function SessionProgress({ sessionState, onEndSession }: SessionProgressProps) {
  // Mock phase progress
  const phaseProgress = 46 // 46% through current phase
  const elapsedTime = "7:42"
  const totalTime = "10:00"

  return (
    <Card className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">Session Progress</h3>
        <Clock className="h-5 w-5 text-muted-foreground" />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-foreground">Active Training</span>
          <Badge variant="secondary">Phase 2/3</Badge>
        </div>
        <Progress value={phaseProgress} className="h-2" />
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{elapsedTime}</span>
          <span>{totalTime}</span>
        </div>
      </div>

      <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">👁️ Current Instructions</p>
        <p className="text-sm text-blue-700 dark:text-blue-300">Try to increase the balanced (yellow) bar</p>
      </div>

      <div className="space-y-2">
        <Button variant="outline" size="sm" className="w-full bg-transparent">
          Insert Marker
        </Button>
        <Button variant="outline" size="sm" className="w-full bg-transparent">
          Adjust Parameters
        </Button>
      </div>

      <Button variant="destructive" size="sm" className="w-full" onClick={onEndSession}>
        <AlertTriangle className="mr-2 h-4 w-4" />
        End Session Early
      </Button>
    </Card>
  )
}
