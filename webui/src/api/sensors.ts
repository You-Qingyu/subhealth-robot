import type { SensorDescriptor, SensorReading } from "../types/sensor"
import { parseError } from "./error"

const BASE = "/api/v1"

export async function listSensors(): Promise<SensorDescriptor[]> {
  const res = await fetch(`${BASE}/sensors`)
  if (!res.ok) throw await parseError(res)
  return res.json()
}

export async function readSensor(sensorId: string): Promise<SensorReading> {
  const res = await fetch(`${BASE}/sensors/${sensorId}`)
  if (!res.ok) throw await parseError(res)
  return res.json()
}
