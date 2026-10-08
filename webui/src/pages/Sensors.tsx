import { useEffect, useState } from "react"
import { listSensors, readSensor } from "../api/sensors"
import type { SensorDescriptor, SensorSample } from "../types/sensor"

const POLL_INTERVAL_MS = 2000

function formatValue(sample: SensorSample | null, unit: string | null): string {
  if (!sample || sample.value === null) return "-"
  const raw = String(sample.value)
  return unit ? `${raw} ${unit}` : raw
}

function formatTime(sample: SensorSample | null): string {
  if (!sample) return "-"
  return new Date(sample.timestamp_ms).toLocaleTimeString()
}

async function fetchSamples(
  descriptors: SensorDescriptor[],
): Promise<Record<string, SensorSample | null>> {
  const readings = await Promise.all(
    descriptors.map((d) => readSensor(d.id).catch(() => null)),
  )
  const samples: Record<string, SensorSample | null> = {}
  for (const r of readings) {
    if (r) samples[r.descriptor.id] = r.sample
  }
  return samples
}

export default function Sensors() {
  const [descriptors, setDescriptors] = useState<SensorDescriptor[]>([])
  const [samples, setSamples] = useState<Record<string, SensorSample | null>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listSensors()
      .then((list) => {
        if (!cancelled) setDescriptors(list)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (descriptors.length === 0) return
    let cancelled = false
    const tick = () => {
      fetchSamples(descriptors).then((next) => {
        if (!cancelled) setSamples(next)
      })
    }
    tick()
    const timer = setInterval(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [descriptors])

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold">Sensors ({descriptors.length})</h2>
      {descriptors.length === 0 && (
        <p className="text-gray-400 text-sm">No sensors available.</p>
      )}
      {descriptors.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 pr-4">ID</th>
              <th className="py-2 pr-4">Type</th>
              <th className="py-2 pr-4">Value</th>
              <th className="py-2">Updated</th>
            </tr>
          </thead>
          <tbody>
            {descriptors.map((d) => {
              const sample = samples[d.id] ?? null
              return (
                <tr key={d.id} className="border-b">
                  <td className="py-2 pr-4 font-mono text-xs text-gray-500">{d.id}</td>
                  <td className="py-2 pr-4">
                    <span className="font-medium">{d.kind}</span>
                  </td>
                  <td className="py-2 pr-4 font-mono">{formatValue(sample, d.unit)}</td>
                  <td className="py-2 text-xs text-gray-400">{formatTime(sample)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
