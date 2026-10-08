import { useEffect, useRef } from "react"
import { Link } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useAgentChat } from "../hooks/useAgentChat"
import TaskStatusBadge from "./TaskStatusBadge"
import type { ChatMessage, TaskRef, ToolCallView } from "../types/agent"

const RESULT_PREVIEW_LIMIT = 1500
const ARGS_PREVIEW_LIMIT = 80

export default function AgentChat({
  onTaskSubmitted,
}: {
  onTaskSubmitted?: () => void
}) {
  const { messages, input, setInput, streaming, send, cancel } =
    useAgentChat(onTaskSubmitted)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  useEffect(() => {
    const element = scrollRef.current
    if (element && stickRef.current) {
      element.scrollTop = element.scrollHeight
    }
  }, [messages])

  const handleScroll = () => {
    const element = scrollRef.current
    if (!element) return
    stickRef.current =
      element.scrollHeight - element.scrollTop - element.clientHeight < 80
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void send()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] bg-white border rounded-lg shadow-sm overflow-hidden">
      <div className="border-b px-5 py-3">
        <h2 className="text-sm font-semibold text-gray-800">机器人智能助手</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          用自然语言描述任务，提交后自动查询执行结果
        </p>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-5 py-5 space-y-4 bg-gray-50"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((message) => (
            <MessageRow key={message.id} message={message} />
          ))
        )}
      </div>

      <div className="border-t bg-white px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="例如：让 mock_exec 依次前往 7、8、9"
            className="flex-1 resize-none border rounded-lg px-3 py-2 text-sm max-h-32 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
          />
          {streaming ? (
            <button
              type="button"
              onClick={cancel}
              className="bg-white border text-gray-600 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50"
            >
              取消
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void send()}
              disabled={!input.trim()}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              发送
            </button>
          )}
        </div>
        <p className="text-[11px] text-gray-400 mt-1.5">
          Enter 发送，Shift+Enter 换行
        </p>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center space-y-3">
      <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 text-sm font-semibold">
        AI
      </div>
      <p className="text-sm font-medium text-gray-600">机器人智能助手</p>
      <p className="text-xs text-gray-400 max-w-xs leading-relaxed">
        可以查询设备能力、按地点名称导航，并在提交后自动确认执行结果。
      </p>
    </div>
  )
}

function MessageRow({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    )
  }

  const isEmpty =
    !message.content &&
    message.toolCalls.length === 0 &&
    message.tasks.length === 0 &&
    !message.error

  return (
    <div className="flex justify-start">
      <div className="max-w-[88%] w-full bg-white border rounded-2xl rounded-bl-sm px-4 py-3 space-y-2.5">
        {message.content && (
          <div className="text-sm text-gray-800 leading-relaxed break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {message.toolCalls.map((tool, index) => (
          <ToolCallBlock key={`${tool.callId}-${index}`} tool={tool} />
        ))}
        {message.tasks.map((task) => (
          <TaskBlock key={task.taskId} task={task} />
        ))}
        {message.error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">
            {message.error}
          </p>
        )}
        {message.streaming && isEmpty && (
          <p className="text-sm text-gray-400">正在思考…</p>
        )}
        {!message.streaming && isEmpty && (
          <p className="text-sm text-gray-400">已取消</p>
        )}
      </div>
    </div>
  )
}

function ToolCallBlock({ tool }: { tool: ToolCallView }) {
  const statusLabel =
    tool.status === "running"
      ? "执行中"
      : tool.status === "error"
        ? "失败"
        : "完成"
  const statusClass =
    tool.status === "running"
      ? "text-blue-600 bg-blue-50"
      : tool.status === "error"
        ? "text-red-600 bg-red-50"
        : "text-green-600 bg-green-50"

  return (
    <div className="rounded-lg border bg-gray-50 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${statusClass}`}
        >
          {statusLabel}
        </span>
        <span className="font-mono text-xs font-medium text-gray-700">
          {tool.name}
        </span>
        <span className="text-[11px] text-gray-400 truncate">
          {formatPreview(JSON.stringify(tool.args), ARGS_PREVIEW_LIMIT)}
        </span>
      </div>
      {tool.result !== undefined && (
        <details className="border-t bg-white">
          <summary className="px-3 py-1.5 text-xs text-gray-500 cursor-pointer select-none hover:text-gray-700">
            查看返回结果
          </summary>
          <pre className="px-3 pb-2.5 pt-1 text-[11px] leading-relaxed text-gray-600 max-h-52 overflow-auto whitespace-pre-wrap break-all">
            {formatResult(tool.result)}
          </pre>
        </details>
      )}
    </div>
  )
}

function TaskBlock({ task }: { task: TaskRef }) {
  const progress = Math.round(
    Math.min(Math.max(task.progress, 0), 1) * 100,
  )
  return (
    <div className="rounded-lg border bg-white px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Link
          to={`/tasks/${task.taskId}`}
          className="font-mono text-xs text-blue-600 hover:underline"
        >
          {task.taskId}
        </Link>
        <TaskStatusBadge state={task.state} />
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            task.state === "failed" ? "bg-red-500" : "bg-blue-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
      {task.phase && (
        <p className="text-[11px] text-gray-400 truncate">
          {task.phase} · {progress}%
        </p>
      )}
    </div>
  )
}

function formatPreview(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function formatResult(result: unknown): string {
  const text =
    typeof result === "string" ? result : JSON.stringify(result, null, 2)
  return formatPreview(text, RESULT_PREVIEW_LIMIT)
}

const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  em: ({ children }: { children?: React.ReactNode }) => (
    <em className="italic">{children}</em>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="bg-gray-100 text-gray-800 rounded px-1 py-0.5 text-xs font-mono">
      {children}
    </code>
  ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="bg-gray-100 rounded-md p-2.5 my-2 overflow-x-auto text-xs">
      {children}
    </pre>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="list-disc list-inside my-1.5 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="list-decimal list-inside my-1.5 space-y-0.5">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="text-gray-700">{children}</li>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 hover:underline"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-gray-300 pl-3 my-2 text-gray-600">
      {children}
    </blockquote>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto my-2">
      <table className="text-xs border-collapse w-full">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border border-gray-200 px-2 py-1 bg-gray-50 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-gray-200 px-2 py-1">{children}</td>
  ),
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-base font-semibold mt-3 mb-1.5">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-sm font-semibold mt-2.5 mb-1">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-sm font-medium mt-2 mb-1">{children}</h3>
  ),
}
