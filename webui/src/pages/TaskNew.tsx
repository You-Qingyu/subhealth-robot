import { useState } from "react"
import { createTask } from "../api/tasks"
import { useToast } from "../components/Toast"

interface Props {
  onCreated: () => void
}

function deadlineFromMinutes(value: string): number | null {
  if (!value.trim()) return null

  const minutes = Number(value)
  if (!Number.isFinite(minutes) || minutes <= 0) {
    throw new Error("执行时限必须为大于 0 的分钟数")
  }

  const now = Date.now()
  const deadlineMs = now + Math.round(minutes * 60_000)
  if (!Number.isSafeInteger(deadlineMs) || deadlineMs <= now) {
    throw new Error("执行时限超出有效范围")
  }
  return deadlineMs
}

export default function TaskNew({ onCreated }: Props) {
  const { toast } = useToast()
  const [deviceId, setDeviceId] = useState("")
  const [tags, setTags] = useState("")
  const [timeoutMinutes, setTimeoutMinutes] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")

    try {
      const targetTags = tags
        .split(/[,\s]+/)
        .map((s) => Number(s.trim()))
        .filter((n) => !isNaN(n))

      if (!deviceId.trim()) throw new Error("device ID is required")
      if (targetTags.length === 0) throw new Error("at least one Tag is required")

      const deadlineMs = deadlineFromMinutes(timeoutMinutes)

      await createTask(deviceId.trim(), targetTags, deadlineMs)
      setTags("")
      toast("Task created!", "success")
      onCreated()
    } catch (err: any) {
      setError(err.message || "create task failed")
      toast(err.message || "create task failed", "error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h2 className="text-lg font-bold">New Task</h2>

      <div>
        <label htmlFor="device-id" className="block text-sm font-medium mb-1">Device ID</label>
        <input
          id="device-id"
          type="text"
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          placeholder="请输入设备 ID"
          className="w-full border rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label htmlFor="target-tags" className="block text-sm font-medium mb-1">
          Target Tags
        </label>
        <input
          id="target-tags"
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="例如：1, 2, 3"
          aria-describedby="target-tags-hint"
          className="w-full border rounded px-3 py-2 text-sm"
        />
        <p id="target-tags-hint" className="text-xs text-gray-500 mt-1">
          按执行顺序填写 Tag ID，用英文逗号或空格分隔；后台自动补全路线。
        </p>
      </div>

      <div>
        <label htmlFor="timeout-minutes" className="block text-sm font-medium mb-1">执行时限（分钟）</label>
        <input
          id="timeout-minutes"
          type="number"
          step="any"
          value={timeoutMinutes}
          onChange={(e) => setTimeoutMinutes(e.target.value)}
          placeholder="例如：5"
          aria-describedby="timeout-minutes-hint"
          className="w-full border rounded px-3 py-2 text-sm"
        />
        <p id="timeout-minutes-hint" className="text-xs text-gray-500 mt-1">
          可选，支持小数，从点击提交时开始计时；留空使用设备默认行为。
        </p>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button
        type="submit"
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Submitting..." : "Submit Task"}
      </button>
    </form>
  )
}
