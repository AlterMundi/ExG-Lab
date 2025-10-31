"use client"

import { Bluetooth, Battery, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import type { Device } from "@/types"

interface DevicePanelProps {
  devices: Device[]
  isScanning: boolean
  onScan: () => void
  onConnect: (mac: string) => void
  onDisconnect: (mac: string) => void
  disabled?: boolean
}

export function DevicePanel({ devices, isScanning, onScan, onConnect, onDisconnect, disabled }: DevicePanelProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Devices</h2>
        <Bluetooth className="h-5 w-5 text-muted-foreground" />
      </div>

      <Button onClick={onScan} disabled={isScanning || disabled} className="w-full">
        {isScanning ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Scanning...
          </>
        ) : (
          "Scan for Devices"
        )}
      </Button>

      <div className="space-y-3">
        {devices.map((device) => (
          <Card
            key={device.mac}
            className={`p-4 transition-all ${
              device.status === "connected"
                ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20"
                : device.status === "streaming"
                  ? "border-green-500 bg-green-50 dark:bg-green-950/20 animate-pulse-subtle"
                  : "border-border"
            }`}
          >
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="font-semibold text-sm text-foreground">{device.name}</p>
                  <p className="text-xs font-mono text-muted-foreground">{device.mac}</p>
                </div>
                <Badge
                  variant={
                    device.status === "connected" ? "default" : device.status === "streaming" ? "default" : "secondary"
                  }
                  className={device.status === "streaming" ? "bg-green-500" : ""}
                >
                  {device.status}
                </Badge>
              </div>

              {device.battery && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Battery className="h-3.5 w-3.5" />
                  <span>{device.battery}%</span>
                </div>
              )}

              {device.streamName && <p className="text-xs font-medium text-primary">Stream: {device.streamName}</p>}

              <Button
                size="sm"
                variant={device.status === "connected" ? "destructive" : "default"}
                className="w-full"
                onClick={() => (device.status === "connected" ? onDisconnect(device.mac) : onConnect(device.mac))}
                disabled={disabled}
              >
                {device.status === "connected" ? "Disconnect" : "Connect"}
              </Button>
            </div>
          </Card>
        ))}

        {devices.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">
            No devices found. Click scan to discover Muse devices.
          </p>
        )}
      </div>
    </div>
  )
}
