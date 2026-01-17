import { Copy, Pause, Play, RefreshCw, Trash2 } from "lucide-react"
import React, { useEffect, useMemo, useRef, useState } from "react"
import { useLogStream } from "../../../hooks/useLogStream"
import type { LogItem } from "../../../services/logsService"

type LogLine = {
  id: number | string
  timestamp: string
  level: "error" | "warn" | "info"
  text: string
  raw: LogItem
}

const formatTime = (timestamp: string) => {
  try {
    return new Date(timestamp).toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    return timestamp
  }
}

const getLineLevel = (item: LogItem): LogLine["level"] => {
  const t = String(item?.type || "").toLowerCase()
  if (t.includes("error") || t === "exception") return "error"
  if (t.includes("warn")) return "warn"
  return "info"
}

const buildText = (item: LogItem) => {
  const scope = item?.scope ? `[${item.scope}] ` : ""
  const base = item?.message ?? item?.detail ?? item?.error ?? ""
  const extras = Object.entries(item || {})
    .filter(([k, v]) => !["id", "timestamp", "type", "scope", "project_id", "message", "detail", "error", "channel"].includes(k) && v !== undefined && v !== null && String(v) !== "")
    .slice(0, 6)
    .map(([k, v]) => `${k}=${String(v)}`)
  const suffix = extras.length ? `  ${extras.join(" ")}` : ""
  return `${scope}${base}${suffix}`.trim()
}

const toLines = (items: LogItem[]): LogLine[] =>
  items.map((it) => ({
    id: typeof it?.id === "number" ? it.id : `${it?.timestamp || ""}-${Math.random()}`,
    timestamp: it?.timestamp || "",
    level: getLineLevel(it),
    text: buildText(it),
    raw: it,
  }))

export interface LogConsolePanelProps {
  enabled: boolean
  projectId?: string | null
}

export const LogConsolePanel: React.FC<LogConsolePanelProps> = ({ enabled, projectId }) => {
  const { items, status, error, paused, setPaused, reload, clear } = useLogStream({ enabled, projectId, limit: 200 })

  const [selectedType, setSelectedType] = useState<string>("all")
  const [selectedScope, setSelectedScope] = useState<string>("all")
  const [keyword, setKeyword] = useState("")

  const scrollerRef = useRef<HTMLDivElement | null>(null)

  const types = useMemo(() => {
    const s = new Set<string>()
    items.forEach((it) => {
      if (it?.type) s.add(String(it.type))
    })
    return Array.from(s).sort()
  }, [items])

  const scopes = useMemo(() => {
    const s = new Set<string>()
    items.forEach((it) => {
      if (it?.scope) s.add(String(it.scope))
    })
    return Array.from(s).sort()
  }, [items])

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase()
    const list = items.filter((it) => {
      if (selectedType !== "all" && String(it.type) !== selectedType) return false
      if (selectedScope !== "all" && String(it.scope || "") !== selectedScope) return false
      if (!kw) return true
      const hay = JSON.stringify(it || {}).toLowerCase()
      return hay.includes(kw)
    })
    return toLines(list)
  }, [items, keyword, selectedScope, selectedType])

  useEffect(() => {
    if (paused) return
    const el = scrollerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [filtered.length, paused])

  const handleCopy = async () => {
    const text = filtered
      .map((l) => `${formatTime(l.timestamp)} ${l.text}`)
      .join("\n")
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const textarea = document.createElement("textarea")
      textarea.value = text
      textarea.style.position = "fixed"
      textarea.style.left = "-9999px"
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
    }
  }

  const statusText = status === "connected" ? "已连接" : status === "connecting" ? "连接中" : status === "error" ? "异常" : "未连接"
  const statusCls =
    status === "connected"
      ? "bg-green-50 text-green-700 ring-green-200"
      : status === "connecting"
        ? "bg-blue-50 text-blue-700 ring-blue-200"
        : status === "error"
          ? "bg-red-50 text-red-700 ring-red-200"
          : "bg-gray-50 text-gray-700 ring-gray-200"

  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <div className="px-4 py-3 border-b bg-gradient-to-r from-gray-50 to-white flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-sm font-medium text-gray-900">后端日志</div>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ring-1 ${statusCls}`}>{statusText}</span>
          <span className="px-2 py-0.5 text-xs font-medium rounded-full ring-1 bg-gray-50 text-gray-700 ring-gray-200">
            {items.length} 条
          </span>
          {error && <span className="text-xs text-red-600 truncate">{error}</span>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused(!paused)}
            className="px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-gray-200 bg-white hover:bg-gray-50 flex items-center gap-1"
            title={paused ? "恢复自动滚动" : "暂停自动滚动"}
          >
            {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
            <span>{paused ? "继续" : "暂停"}</span>
          </button>
          <button
            onClick={handleCopy}
            className="px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-gray-200 bg-white hover:bg-gray-50 flex items-center gap-1"
            title="复制当前过滤后的日志"
          >
            <Copy className="h-3 w-3" />
            <span>复制</span>
          </button>
          <button
            onClick={() => reload()}
            className="px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-gray-200 bg-white hover:bg-gray-50 flex items-center gap-1"
            title="重新拉取历史并重连 SSE"
          >
            <RefreshCw className="h-3 w-3" />
            <span>重连</span>
          </button>
          <button
            onClick={() => clear()}
            className="px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-red-200 bg-red-50 text-red-700 hover:bg-red-100 flex items-center gap-1"
            title="清空后端日志"
          >
            <Trash2 className="h-3 w-3" />
            <span>清空</span>
          </button>
        </div>
      </div>

      <div className="px-4 py-3 border-b bg-white">
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-200 rounded-md bg-white"
          >
            <option value="all">全部类型</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            value={selectedScope}
            onChange={(e) => setSelectedScope(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-200 rounded-md bg-white"
          >
            <option value="all">全部范围</option>
            {scopes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索 message/detail/error 或任意字段"
            className="px-3 py-1 text-xs border border-gray-200 rounded-md bg-white min-w-[220px] flex-1"
          />
          {(selectedType !== "all" || selectedScope !== "all" || keyword.trim()) && (
            <button
              onClick={() => {
                setSelectedType("all")
                setSelectedScope("all")
                setKeyword("")
              }}
              className="px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-gray-200 bg-white hover:bg-gray-50"
            >
              重置过滤
            </button>
          )}
        </div>
      </div>

      <div ref={scrollerRef} className="max-h-96 overflow-y-auto bg-gray-950 text-gray-100 font-mono text-xs">
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-400">暂无日志</div>
        ) : (
          filtered.slice(-800).map((l) => (
            <div key={String(l.id)} className="px-4 py-1 border-b border-gray-900/50">
              <span className="text-gray-400">{formatTime(l.timestamp)}</span>
              <span className="mx-2 text-gray-600">|</span>
              <span className={l.level === "error" ? "text-red-300" : l.level === "warn" ? "text-yellow-300" : "text-gray-100"}>
                {l.text || JSON.stringify(l.raw)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default LogConsolePanel

