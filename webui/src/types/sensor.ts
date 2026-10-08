export interface SensorDescriptor {
  id: string
  kind: string
  unit: string | null
}

export interface SensorSample {
  sensor_id: string
  value: number | string | boolean | null
  timestamp_ms: number
}

export interface SensorReading {
  descriptor: SensorDescriptor
  sample: SensorSample | null
}
