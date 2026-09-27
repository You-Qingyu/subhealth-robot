import { useState } from "react"
import { createTask } from "../api/tasks"
import { useToast } from "../components/Toast"

interface Props {
  onCreated: () => void
}

export default function TaskNew({ onCreated }: Props) {
  const { toast } = useToast()
  const [deviceId, setDeviceId] = useState("mock_exec")
  const [tags, setTags] = useState("")
  const [deadline, setDeadline] = useState("")
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

      const deadlineMs = deadline ? Date.parse(deadline) : null
      if (deadline && !Number.isFinite(deadlineMs)) throw new Error("invalid deadline")
      if (deadlineMs !== null && deadlineMs <= Date.now()) {
        throw new Error("deadline must be in the future")
      }

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
        <label className="block text-sm font-medium mb-1">Device ID</label>
        <input
          type="text"
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
          className="w-full border rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">
          Target Tags <span className="text-gray-400">(comma or space separated)</span>
        </label>
        <input
          type="text"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="e.g. 42, 43, 44"
          className="w-full border rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Deadline</label>
        <input
          type="datetime-local"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
          className="w-full border rounded px-3 py-2 text-sm mt-2"
        />
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
