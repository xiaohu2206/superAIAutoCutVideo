import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import logsService, { LogItem } from "../services/logsService"

type StreamStatus = "idle" | "connecting" | "connected" | "error"

const safeParseJson = (text: string): any | null => {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (err && typeof err === "object") {
    const anyErr = err as any
    if (typeof anyErr.message === "string" && anyErr.message) return anyErr.message
    if (typeof anyErr.detail === "string" && anyErr.detail) return anyErr.detail
  }
  if (typeof err === "string" && err) return err
  return fallback
}

export interface UseLogStreamOptions {
  projectId?: string | null
  limit?: number
  enabled?: boolean
}

export interface UseLogStreamReturn {
  items: LogItem[]
  status: StreamStatus
  error: string | null
  lastId: number | null
  paused: boolean
  setPaused: (v: boolean) => void
  reload: () => Promise<void>
  clear: () => Promise<void>
  appendLocal: (item: LogItem) => void
}

export function useLogStream(options?: UseLogStreamOptions): UseLogStreamReturn {
  const projectId = options?.projectId ?? null
  const limit = options?.limit ?? 200
  const enabled = options?.enabled ?? true

  const [items, setItems] = useState<LogItem[]>([])
  const [status, setStatus] = useState<StreamStatus>("idle")
  const [error, setError] = useState<string | null>(null)
  const [paused, setPaused] = useState(false)

  const lastIdRef = useRef<number | null>(null)
  const sourceRef = useRef<EventSource | null>(null)

  const setLastId = useCallback((id: number | null) => {
    lastIdRef.current = id
  }, [])

  const appendLocal = useCallback((item: LogItem) => {
    setItems((prev) => {
      const next = [...prev, item]
      return next.length > 5000 ? next.slice(next.length - 5000) : next
    })
    if (typeof item?.id === "number") {
      const current = lastIdRef.current
      setLastId(current === null ? item.id : Math.max(current, item.id))
    }
  }, [setLastId])

  const closeSource = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
  }, [])

  const loadHistory = useCallback(async () => {
    setError(null)
    const resp = projectId
      ? await logsService.getProjectLogs(projectId, { limit })
      : await logsService.getGlobalLogs({ limit })
    const list = Array.isArray(resp.items) ? resp.items : []
    setItems(list)
    const maxId = list.reduce((m, it) => (typeof it?.id === "number" ? Math.max(m, it.id) : m), -1)
    const derived = maxId >= 0 ? maxId : null
    const cursor = typeof resp.next_after_id === "number" ? resp.next_after_id : derived
    setLastId(cursor)
  }, [limit, projectId, setLastId])

  const startStream = useCallback(() => {
    closeSource()
    if (!enabled) return

    const afterId = lastIdRef.current
    const params = afterId === null ? undefined : { after_id: afterId }
    const es = projectId
      ? logsService.createProjectLogsEventSource(projectId, params)
      : logsService.createGlobalLogsEventSource(params)

    sourceRef.current = es
    setStatus("connecting")

    es.onopen = () => {
      setStatus("connected")
      setError(null)
    }

    es.onmessage = (ev) => {
      const parsed = safeParseJson(ev.data)
      if (parsed && typeof parsed === "object") {
        appendLocal(parsed as LogItem)
      } else if (typeof ev.data === "string" && ev.data) {
        const now = new Date().toISOString()
        appendLocal({ id: Date.now(), timestamp: now, type: "ws_text", scope: "sse_raw", message: ev.data })
      }
    }

    es.onerror = () => {
      setStatus("error")
      setError("日志流连接异常，正在重试...")
    }
  }, [appendLocal, closeSource, enabled, projectId])

  const reload = useCallback(async () => {
    closeSource()
    setStatus("connecting")
    try {
      await loadHistory()
      startStream()
    } catch (e) {
      setStatus("error")
      setError(getErrorMessage(e, "加载日志失败"))
      throw e
    }
  }, [closeSource, loadHistory, startStream])

  const clear = useCallback(async () => {
    setError(null)
    if (projectId) {
      await logsService.clearProjectLogs(projectId)
    } else {
      await logsService.clearGlobalLogs()
    }
    setItems([])
    setLastId(null)
    startStream()
  }, [projectId, setLastId, startStream])

  useEffect(() => {
    if (!enabled) {
      closeSource()
      setStatus("idle")
      return
    }
    reload()
    return () => {
      closeSource()
    }
  }, [closeSource, enabled, reload])

  const lastId = useMemo(() => lastIdRef.current, [items.length])

  return {
    items,
    status,
    error,
    lastId,
    paused,
    setPaused,
    reload,
    clear,
    appendLocal,
  }
}
