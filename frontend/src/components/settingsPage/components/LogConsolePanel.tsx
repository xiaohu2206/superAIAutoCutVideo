import { Copy, Pause, Play, RefreshCw, Terminal, X } from "lucide-react"
import React, { useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
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
    .slice(0, 4)
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
  const { items, status, error, paused, setPaused, reload } = useLogStream({ enabled, projectId, limit: 200 })
  const [isOpen, setIsOpen] = useState(false)
  const scrollerRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => toLines(items), [items])
  const visibleLines = useMemo(() => filtered.slice(-300), [filtered])

  useEffect(() => {
    if (!isOpen || paused) return
    const el = scrollerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [isOpen, paused, visibleLines.length])

  useEffect(() => {
    if (!isOpen) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false)
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [isOpen])

  const handleCopy = async () => {
    const text = filtered.map((l) => `${formatTime(l.timestamp)} ${l.text}`).join("\n")
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

  const statusText = status === "connected" ? "实时中" : status === "connecting" ? "连接中" : status === "error" ? "异常" : "未连接"
  const statusCls =
    status === "connected"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "connecting"
        ? "bg-blue-50 text-blue-700 ring-blue-200"
        : status === "error"
          ? "bg-red-50 text-red-700 ring-red-200"
          : "bg-slate-100 text-slate-600 ring-slate-200"

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="group flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700"
        title="查看运行日志"
      >
        <Terminal className="h-4 w-4" />
      </button>

      {isOpen
        ? createPortal(
            <div className="fixed inset-0 z-50 overflow-y-auto">
              <div className="fixed inset-0 bg-slate-950/45 backdrop-blur-sm transition-opacity" onClick={() => setIsOpen(false)} />
              <div className="flex min-h-screen items-center justify-center p-4">
                <div className="relative flex max-h-[82vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_24px_80px_-24px_rgba(15,23,42,0.45)]">
                  <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-slate-900">运行日志</h3>
                        <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${statusCls}`}>{statusText}</span>
                        <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-slate-200">
                          {filtered.length} 条
                        </span>
                      </div>
                      {error ? <div className="mt-1 truncate text-xs text-red-600">{error}</div> : <div className="mt-1 text-xs text-slate-500">仅保留核心操作，支持暂停、复制和重连。</div>}
                    </div>

                    <div className="ml-4 flex items-center gap-2">
                      <button
                        onClick={() => setPaused(!paused)}
                        className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
                        title={paused ? "恢复滚动" : "暂停滚动"}
                      >
                        {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
                        <span>{paused ? "继续" : "暂停"}</span>
                      </button>
                      <button
                        onClick={handleCopy}
                        className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
                        title="复制日志"
                      >
                        <Copy className="h-3.5 w-3.5" />
                        <span>复制</span>
                      </button>
                      <button
                        onClick={() => reload()}
                        className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100"
                        title="重新连接日志流"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        <span>重连</span>
                      </button>
                      <button
                        onClick={() => setIsOpen(false)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                        title="关闭"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <div
                    ref={scrollerRef}
                    className="min-h-[320px] flex-1 overflow-y-auto bg-[#020617] px-4 py-3 text-xs text-slate-100"
                  >
                    {visibleLines.length === 0 ? (
                      <div className="flex h-full min-h-[320px] items-center justify-center text-slate-500">暂无日志</div>
                    ) : (
                      <div className="space-y-1.5">
                        {visibleLines.map((line) => (
                          <div
                            key={String(line.id)}
                            className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2 font-mono hover:bg-white/[0.04]"
                          >
                            <span className="shrink-0 pt-0.5 text-[11px] text-slate-500">{formatTime(line.timestamp)}</span>
                            <span
                              className={
                                line.level === "error"
                                  ? "mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-red-400"
                                  : line.level === "warn"
                                    ? "mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"
                                    : "mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400"
                              }
                            />
                            <span
                              className={
                                line.level === "error"
                                  ? "break-all text-red-200"
                                  : line.level === "warn"
                                    ? "break-all text-amber-200"
                                    : "break-all text-slate-100"
                              }
                            >
                              {line.text || JSON.stringify(line.raw)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  )
}

export default LogConsolePanel
