export type Primitive = "go_to_tag"

export type TaskState = "accepted" | "running" | "succeeded" | "failed"

export interface Task {
  id: string
  device_id: string
  primitive: Primitive
  target: number[]
  deadline_ms: number | null
}

export interface TaskView {
  task: Task
  state: TaskState
  progress: number
  phase: string
}

export interface TaskStateChanged {
  task_id: string
  state: TaskState
}

export interface TaskEvent {
  sequence: number
  event: {
    TaskStateChanged?: TaskStateChanged
  }
}
