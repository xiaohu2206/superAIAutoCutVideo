import { Copy, Pause, Play, RefreshCw, Trash2 } from "lucide-react"
import React, { useEffect, useMemo, useRef, useState } from "react"
import AppSelect from "@/components/ui/AppSelect"
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
    <section className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 backdrop-blur-sm lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold tracking-[0.02em] text-slate-900">后端日志</div>
            <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${statusCls}`}>{statusText}</span>
            <span className="inline-flex items-center rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
              {items.length} 条
            </span>
          </div>
          <div className="text-xs text-slate-500">实时查看后端运行状态、错误信息与任务进度。</div>
          {error && <div className="max-w-full truncate text-xs font-medium text-red-600">{error}</div>}
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <button
            onClick={() => setPaused(!paused)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
            title={paused ? "恢复自动滚动" : "暂停自动滚动"}
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
            <span>{paused ? "继续" : "暂停"}</span>
          </button>
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
            title="复制当前过滤后的日志"
          >
            <Copy className="h-3.5 w-3.5" />
            <span>复制</span>
          </button>
          <button
            onClick={() => reload()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
            title="重新拉取历史并重连 SSE"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>重连</span>
          </button>
          <button
            onClick={() => clear()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100"
            title="清空后端日志"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span>清空</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200/80 bg-white/80 p-3 backdrop-blur-sm">
        <AppSelect
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
          className="min-w-[140px] rounded-xl border-slate-200 bg-white px-3 py-2 pr-9 text-xs text-slate-700 shadow-none focus:ring-2 focus:ring-blue-100"
          iconClassName="right-3 h-3.5 w-3.5"
        >
          <option value="all">全部类型</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </AppSelect>
        <AppSelect
          value={selectedScope}
          onChange={(e) => setSelectedScope(e.target.value)}
          className="min-w-[140px] rounded-xl border-slate-200 bg-white px-3 py-2 pr-9 text-xs text-slate-700 shadow-none focus:ring-2 focus:ring-blue-100"
          iconClassName="right-3 h-3.5 w-3.5"
        >
          <option value="all">全部范围</option>
          {scopes.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </AppSelect>
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索 message/detail/error 或任意字段"
          className="min-w-[220px] flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
        />
        {(selectedType !== "all" || selectedScope !== "all" || keyword.trim()) && (
          <button
            onClick={() => {
              setSelectedType("all")
              setSelectedScope("all")
              setKeyword("")
            }}
            className="inline-flex items-center rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100"
          >
            重置过滤
          </button>
        )}
      </div>

      <div
        ref={scrollerRef}
        className="max-h-96 overflow-y-auto rounded-2xl border border-slate-800 bg-[#020617] text-xs text-slate-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
      >
        {filtered.length === 0 ? (
          <div className="px-4 py-10 text-center text-slate-500">暂无日志</div>
        ) : (
          filtered.slice(-800).map((l) => (
            <div
              key={String(l.id)}
              className="flex items-start gap-3 border-b border-white/5 px-4 py-2 font-mono last:border-b-0 hover:bg-white/[0.03]"
            >
              <span className="shrink-0 pt-0.5 text-[11px] text-slate-500">{formatTime(l.timestamp)}</span>
              <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-600" />
              <span className={l.level === "error" ? "break-all text-red-300" : l.level === "warn" ? "break-all text-amber-300" : "break-all text-slate-100"}>
                {l.text || JSON.stringify(l.raw)}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}

export default LogConsolePanel

