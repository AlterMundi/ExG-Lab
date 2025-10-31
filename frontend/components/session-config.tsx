"use client"

import { useState } from "react"
import { ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { Protocol, Device } from "@/types"

interface SessionConfigProps {
  protocol: Protocol
  connectedDevices: Device[]
  onStartSession: (config: any) => void
  onCancel: () => void
}

export function SessionConfig({ protocol, connectedDevices, onStartSession, onCancel }: SessionConfigProps) {
  const [assignments, setAssignments] = useState(
    connectedDevices.map((device) => ({
      streamName: device.streamName!,
      participantName: "",
      role: "subject",
      group: "A",
    })),
  )

  const handleStartSession = () => {
    onStartSession({
      protocol,
      assignments,
    })
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <Button variant="ghost" onClick={onCancel} className="mb-6">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Change Protocol
      </Button>

      <div className="space-y-6">
        <Card className="p-6">
          <h3 className="text-xl font-bold text-foreground mb-2">{protocol.name}</h3>
          <p className="text-sm text-muted-foreground">{protocol.description}</p>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Device Assignment</h3>

          <div className="space-y-4">
            {assignments.map((assignment, index) => (
              <div key={assignment.streamName} className="grid grid-cols-4 gap-4 items-end">
                <div>
                  <Label className="text-xs text-muted-foreground">Device</Label>
                  <p className="font-mono text-sm font-semibold mt-1">{assignment.streamName}</p>
                </div>

                <div>
                  <Label htmlFor={`participant-${index}`}>Participant Name</Label>
                  <Input
                    id={`participant-${index}`}
                    value={assignment.participantName}
                    onChange={(e) => {
                      const newAssignments = [...assignments]
                      newAssignments[index].participantName = e.target.value
                      setAssignments(newAssignments)
                    }}
                    placeholder="Enter name"
                  />
                </div>

                <div>
                  <Label htmlFor={`role-${index}`}>Role</Label>
                  <Select
                    value={assignment.role}
                    onValueChange={(value) => {
                      const newAssignments = [...assignments]
                      newAssignments[index].role = value
                      setAssignments(newAssignments)
                    }}
                  >
                    <SelectTrigger id={`role-${index}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="subject">Subject</SelectItem>
                      <SelectItem value="control">Control</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor={`group-${index}`}>Group</Label>
                  <Select
                    value={assignment.group}
                    onValueChange={(value) => {
                      const newAssignments = [...assignments]
                      newAssignments[index].group = value
                      setAssignments(newAssignments)
                    }}
                  >
                    <SelectTrigger id={`group-${index}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="A">Group A</SelectItem>
                      <SelectItem value="B">Group B</SelectItem>
                      <SelectItem value="Control">Control</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="flex gap-4">
          <Button
            onClick={handleStartSession}
            className="flex-1 bg-green-600 hover:bg-green-700 text-white"
            size="lg"
            disabled={assignments.some((a) => !a.participantName)}
          >
            Start Session
          </Button>
          <Button onClick={onCancel} variant="outline" size="lg">
            Cancel
          </Button>
        </div>
      </div>
    </div>
  )
}
