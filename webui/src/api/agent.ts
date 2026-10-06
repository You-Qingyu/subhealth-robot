import { parseError } from "./error"

export type AgentEventName =
  | "assistant"
  | "tool_start"
  | "tool_result"
  | "task_submitted"
  | "task_state"
  | "done"
  | "error"

export interface StreamEvent {
  event: AgentEventName
  data: unknown
}

export async function streamAgent(
  prompt: string,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const res = await fetch("/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  })
  if (!res.ok || !res.body) throw await parseError(res)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = drainEvents(buffer, onEvent)
  }
  buffer += decoder.decode()
  drainEvents(buffer, onEvent)
}

function drainEvents(
  buffer: string,
  onEvent: (event: StreamEvent) => void,
): string {
  let rest = buffer
  let separator = rest.indexOf("\n\n")
  while (separator !== -1) {
    const rawEvent = rest.slice(0, separator)
    rest = rest.slice(separator + 2)
    const parsed = parseSseEvent(rawEvent)
    if (parsed) onEvent(parsed)
    separator = rest.indexOf("\n\n")
  }
  return rest
}

function parseSseEvent(raw: string): StreamEvent | null {
  let event = "message"
  const dataLines: string[] = []
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim()
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (dataLines.length === 0) return null
  try {
    return { event: event as AgentEventName, data: JSON.parse(dataLines.join("")) }
  } catch {
    return null
  }
}
