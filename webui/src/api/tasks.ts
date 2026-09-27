import type { TaskView } from "../types/task"
import { parseError } from "./error"

const BASE = "/api/v1"

export async function createTask(
  deviceId: string,
  target: number[],
  deadlineMs: number | null,
): Promise<TaskView> {
  const res = await fetch(`${BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      primitive: "go_to_tag",
      target,
      deadline_ms: deadlineMs,
    }),
  })
  if (!res.ok) throw await parseError(res)
  return res.json()
}

export async function listTasks(): Promise<TaskView[]> {
  const res = await fetch(`${BASE}/tasks`)
  if (!res.ok) throw await parseError(res)
  return res.json()
}

export async function getTask(taskId: string): Promise<TaskView> {
  const res = await fetch(`${BASE}/tasks/${taskId}`)
  if (!res.ok) throw await parseError(res)
  return res.json()
}
