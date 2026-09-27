import { useEffect, useState } from "react"
import { getTask } from "../api/tasks"
import type { TaskView } from "../types/task"
import TaskStatusBadge from "../components/TaskStatusBadge"

interface Props {
  taskId: string | null
  onBack: () => void
  liveUpdates: Record<string, { state: TaskView["state"] }>
}

export default function TaskDetail({ taskId, onBack, liveUpdates }: Props) {
  const [task, setTask] = useState<TaskView | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!taskId) return
    setLoading(true)
    getTask(taskId)
      .then(setTask)
      .catch(() => setTask(null))
      .finally(() => setLoading(false))
  }, [taskId])

  const update = taskId ? liveUpdates[taskId] : undefined
  const rec = task && update ? { ...task, state: update.state } : task

  if (!taskId) return null
  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>
  if (!rec) return <p className="text-red-500 text-sm">Task not found.</p>

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-blue-600 hover:underline">
        &larr; Back
      </button>

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Task Detail</h2>
        <TaskStatusBadge state={rec.state} />
      </div>

      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>进度</span>
          <span>{rec.progress != null ? `${(rec.progress * 100).toFixed(0)}%` : "-"}</span>
        </div>
        <div className="h-2 rounded bg-gray-200 overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all"
            style={{ width: `${rec.progress != null ? rec.progress * 100 : 0}%` }}
          />
        </div>
      </div>

      <table className="w-full text-sm">
        <tbody>
          {[
            ["ID", rec.task.id],
            ["Device", rec.task.device_id],
            ["Primitive", rec.task.primitive],
            ["Target Tags", rec.task.target.join(", ")],
            ["Phase", rec.phase],
            ["Progress", `${(rec.progress * 100).toFixed(0)}%`],
            ["Deadline", rec.task.deadline_ms ? new Date(rec.task.deadline_ms).toISOString() : "-"],
          ].map(([label, val]) => (
            <tr key={label} className="border-b">
              <td className="py-1 pr-4 text-gray-500 font-medium">{label}</td>
              <td className="py-1">{val}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
