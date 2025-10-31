import { Brain, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"

interface HeaderProps {
  isConnected: boolean
}

export function Header({ isConnected }: HeaderProps) {
  return (
    <header className="border-b border-border bg-card px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold text-foreground">ExG-Lab</h1>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div
              className={`h-2.5 w-2.5 rounded-full ${isConnected ? "bg-green-500 animate-pulse-subtle" : "bg-red-500"}`}
            />
            <span className="text-sm font-medium text-muted-foreground">
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>

          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  )
}
