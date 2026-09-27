import type { TaskState } from "../types/task"

const colorMap: Record<TaskState, string> = {
  accepted: "text-yellow-600 bg-yellow-100",
  running: "text-blue-600 bg-blue-100",
  succeeded: "text-green-600 bg-green-100",
  failed: "text-red-600 bg-red-100",
}

export default function TaskStatusBadge({ state }: { state: TaskState }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colorMap[state] || "bg-gray-100"}`}
    >
      {state}
    </span>
  )
}
