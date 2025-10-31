"use client"

import { useState, useEffect, useRef } from "react"
import type { RawEEGData } from "@/types"

export function useRawEEGData() {
  const [rawData, setRawData] = useState<Record<string, RawEEGData>>({})
  const intervalRef = useRef<NodeJS.Timeout>()

  useEffect(() => {
    // Generate mock raw EEG data at 10 Hz
    intervalRef.current = setInterval(() => {
      const subjects = ["Muse_1", "Muse_2", "Muse_3", "Muse_4"]
      const newData: Record<string, RawEEGData> = {}

      subjects.forEach((subject) => {
        newData[subject] = {
          subject,
          channels: {
            TP9: generateChannelData(),
            AF7: generateChannelData(),
            AF8: generateChannelData(),
            TP10: generateChannelData(),
          },
        }
      })

      setRawData(newData)
    }, 100) // 10 Hz update rate

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  return rawData
}

function generateChannelData() {
  // Generate realistic EEG waveform (256 samples = 1 second at 256Hz)
  const samples = 256
  const timeDomain: number[] = []

  // Combine multiple frequency components for realistic EEG
  for (let i = 0; i < samples; i++) {
    const t = i / 256 // Time in seconds
    // Alpha wave (10 Hz) - dominant
    const alpha = 15 * Math.sin(2 * Math.PI * 10 * t)
    // Theta wave (6 Hz)
    const theta = 8 * Math.sin(2 * Math.PI * 6 * t + Math.random() * 0.5)
    // Beta wave (20 Hz)
    const beta = 5 * Math.sin(2 * Math.PI * 20 * t + Math.random() * 0.3)
    // Random noise
    const noise = (Math.random() - 0.5) * 3

    timeDomain.push(alpha + theta + beta + noise)
  }

  // Generate frequency domain data (power in each band)
  const frequencyDomain = {
    delta: Math.random() * 20 + 10, // 10-30 µV²
    theta: Math.random() * 30 + 20, // 20-50 µV²
    alpha: Math.random() * 40 + 40, // 40-80 µV² (typically highest)
    beta: Math.random() * 25 + 15, // 15-40 µV²
    gamma: Math.random() * 10 + 5, // 5-15 µV²
  }

  return {
    timeDomain,
    frequencyDomain,
    quality: Math.random() * 30 + 70, // 70-100% quality
  }
}
