import { useEffect, useRef, useCallback } from "react"
import type { TaskEvent } from "../types/task"

type WsCallback = (event: TaskEvent) => void

const WS_URL = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/v1/events`
const MAX_RETRY_DELAY = 30000

export function useTaskWS(onMessage: WsCallback) {
  const wsRef = useRef<WebSocket | null>(null)
  const onMsgRef = useRef(onMessage)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  onMsgRef.current = onMessage

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    ws.onopen = () => {
      retryCountRef.current = 0
    }
    ws.onmessage = (e) => {
      try {
        const msg: TaskEvent = JSON.parse(e.data)
        onMsgRef.current(msg)
      } catch {
        /* ignore */
      }
    }
    ws.onclose = () => {
      wsRef.current = null
      if (!mountedRef.current) return
      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), MAX_RETRY_DELAY)
      retryCountRef.current++
      retryTimerRef.current = setTimeout(connect, delay)
    }
    ws.onerror = () => ws.close()
    wsRef.current = ws
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])
}
