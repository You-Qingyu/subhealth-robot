import { useEffect, useState } from "react"
import { listTasks } from "../api/tasks"
import type { TaskView } from "../types/task"
import TaskStatusBadge from "../components/TaskStatusBadge"

interface Props {
  refreshKey: number
  onSelect: (id: string) => void
  wsUpdates: Record<string, { state: TaskView["state"] }>
}

export default function TaskList({ refreshKey, onSelect, wsUpdates }: Props) {
  const [tasks, setTasks] = useState<TaskView[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    listTasks()
      .then(setTasks)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [refreshKey])

  const merged = tasks.map((t) => {
    const update = wsUpdates[t.task.id]
    return update ? { ...t, state: update.state } : t
  })

  if (loading) return <p className="text-gray-400 text-sm">Loading...</p>

  return (
    <div className="space-y-2">
      <h2 className="text-lg font-bold">Tasks ({merged.length})</h2>
      {merged.length === 0 && <p className="text-gray-400 text-sm">No tasks yet.</p>}
      {merged.map((t) => (
        <div
          key={t.task.id}
          onClick={() => onSelect(t.task.id)}
          className="border rounded p-3 cursor-pointer hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-gray-500">{t.task.id}</span>
            <div className="flex items-center gap-2">
              <TaskStatusBadge state={t.state} />
            </div>
          </div>
          <div className="text-sm mt-1">
            <span className="font-medium">
              📍 {t.task.primitive}
            </span>
            {t.task.target.length > 0 && (
              <span className="text-gray-500 ml-2">→ tag {t.task.target.join(", ")}</span>
            )}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {t.task.device_id} · {t.phase}
          </div>
        </div>
      ))}
    </div>
  )
}
