import { useCallback, useRef, useState } from "react"
import { streamAgent, type StreamEvent } from "../api/agent"
import type { ChatMessage, ToolCallStatus } from "../types/agent"
import type { TaskState } from "../types/task"

let sequence = 0
const nextId = () => `msg-${Date.now()}-${sequence++}`

export function useAgentChat(onTaskSubmitted?: () => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const patchAssistant = useCallback(
    (fn: (message: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        const index = prev.length - 1
        if (index < 0 || prev[index].role !== "assistant") return prev
        const copy = [...prev]
        copy[index] = fn(copy[index])
        return copy
      })
    },
    [],
  )

  const handleEvent = useCallback(
    ({ event, data }: StreamEvent) => {
      switch (event) {
        case "assistant": {
          const payload = data as { content: string }
          patchAssistant((m) => ({
            ...m,
            content: m.content ? `${m.content}\n${payload.content}` : payload.content,
          }))
          break
        }
        case "tool_start": {
          const payload = data as { call_id: string; name: string; args: Record<string, unknown> }
          patchAssistant((m) => ({
            ...m,
            toolCalls: [
              ...m.toolCalls,
              {
                callId: payload.call_id,
                name: payload.name,
                args: payload.args,
                status: "running" as ToolCallStatus,
              },
            ],
          }))
          break
        }
        case "tool_result": {
          const payload = data as { call_id: string; name: string; status: string; result: unknown }
          patchAssistant((m) => ({
            ...m,
            toolCalls: m.toolCalls.map((tool) =>
              tool.callId === payload.call_id
                ? {
                    ...tool,
                    status: (payload.status === "error"
                      ? "error"
                      : "success") as ToolCallStatus,
                    result: payload.result,
                  }
                : tool,
            ),
          }))
          break
        }
        case "task_submitted": {
          const payload = data as { task_id: string }
          patchAssistant((m) => ({
            ...m,
            tasks: [
              ...m.tasks,
              { taskId: payload.task_id, state: "accepted" as TaskState, progress: 0, phase: "" },
            ],
          }))
          onTaskSubmitted?.()
          break
        }
        case "task_state": {
          const payload = data as { task_id: string; state: string; progress: number; phase: string }
          patchAssistant((m) => ({
            ...m,
            tasks: m.tasks.map((task) =>
              task.taskId === payload.task_id
                ? {
                    ...task,
                    state: payload.state as TaskState,
                    progress: payload.progress,
                    phase: payload.phase,
                  }
                : task,
            ),
          }))
          break
        }
        case "done": {
          const payload = data as { final: string; tasks: unknown[] }
          patchAssistant((m) => ({
            ...m,
            streaming: false,
            content: payload.final || m.content,
          }))
          break
        }
        case "error": {
          const payload = data as { message: string }
          patchAssistant((m) => ({ ...m, streaming: false, error: payload.message }))
          break
        }
      }
    },
    [patchAssistant, onTaskSubmitted],
  )

  const send = useCallback(
    async (text?: string) => {
      const prompt = (text ?? input).trim()
      if (!prompt || streaming) return

      const userMessage: ChatMessage = {
        id: nextId(),
        role: "user",
        content: prompt,
        toolCalls: [],
        tasks: [],
        streaming: false,
      }
      const assistantMessage: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        toolCalls: [],
        tasks: [],
        streaming: true,
      }
      setMessages((prev) => [...prev, userMessage, assistantMessage])
      setInput("")
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller
      try {
        await streamAgent(prompt, controller.signal, handleEvent)
      } catch (err: any) {
        if (err?.name === "AbortError") {
          patchAssistant((m) => ({ ...m, streaming: false }))
        } else {
          patchAssistant((m) => ({
            ...m,
            streaming: false,
            error: err?.message || "agent request failed",
          }))
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
      }
    },
    [input, streaming, handleEvent, patchAssistant],
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { messages, input, setInput, streaming, send, cancel }
}
