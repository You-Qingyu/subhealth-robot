import type { TaskState } from "./task"

export type ToolCallStatus = "running" | "success" | "error"

export interface ToolCallView {
  callId: string
  name: string
  args: Record<string, unknown>
  status: ToolCallStatus
  result?: unknown
}

export interface TaskRef {
  taskId: string
  state: TaskState
  progress: number
  phase: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  toolCalls: ToolCallView[]
  tasks: TaskRef[]
  error?: string
  streaming: boolean
}
