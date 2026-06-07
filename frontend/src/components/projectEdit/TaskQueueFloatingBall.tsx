import { Layers, Loader, X, Clock, CheckCircle2, AlertCircle, Pause } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { projectService } from "../../services/projectService";

export const TASK_SUBMITTED_EVENT = "sacv-task-submitted";

interface TaskQueueData {
  active_project: string | null;
  active_project_name: string | null;
  active_task_count: number;
  active_tasks: Array<{
    scope: string;
    project_id: string;
    task_id: string;
    status: string;
    progress?: number;
    message?: string;
    phase?: string;
    timestamp?: string;
    project_name?: string;
  }>;
  waiting_projects: Array<{
    project_id: string;
    project_name: string;
    queue_position: number;
    tasks: Array<{
      project_id: string;
      project_name: string;
      scope: string;
      task_id: string;
      queue_status: string;
      task_state: any;
    }>;
  }>;
  total_waiting_projects: number;
}

const POLL_INTERVAL_MS = 3000;
/** 提交任务后队列 API 可能晚一拍才有数据；在此期间继续拉取，避免浮窗永远不出现 */
const CATCH_UP_MAX_TICKS = 40;

const SCOPE_LABELS: Record<string, string> = {
  one_click_generate: "一键生成",
  generate_copywriting: "文案生成",
  generate_script: "脚本生成",
  generate_video: "视频生成",
  generate_jianying_draft: "剪映草稿",
  extract_scene: "镜头提取",
  extract_subtitle: "提取字幕",
  omni_multimodal: "Omni 多模态",
  omni_copywriting_embed: "文案结构化",
  omni_shot_match: "镜头匹配",
  omni_global_path_search: "全局路径",
  omni_generate_script: "Omni 脚本",
  omni_full_narration_pipeline: "全链路编排",
};

function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] || scope;
}

function statusIcon(status: string) {
  switch (status) {
    case "processing":
    case "running":
      return <Loader className="h-3.5 w-3.5 animate-spin text-blue-500" />;
    case "completed":
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case "failed":
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
    case "cancelled":
      return <X className="h-3.5 w-3.5 text-gray-400" />;
    case "queued":
    case "pending":
    case "waiting":
      return <Clock className="h-3.5 w-3.5 text-amber-500" />;
    default:
      return <Pause className="h-3.5 w-3.5 text-gray-400" />;
  }
}

function statusText(status: string): string {
  switch (status) {
    case "processing":
    case "running":
      return "执行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    case "queued":
    case "pending":
      return "排队中";
    case "waiting":
      return "等待中";
    default:
      return status;
  }
}

function hasActive(queueData: TaskQueueData | null): boolean {
  if (!queueData) return false;
  if (queueData.active_project !== null || queueData.waiting_projects.length > 0) return true;
  return (queueData.active_tasks?.length ?? 0) > 0;
}

const TaskQueueFloatingBall: React.FC = () => {
  const [queueData, setQueueData] = useState<TaskQueueData | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const queueDataRef = useRef<TaskQueueData | null>(null);
  const catchUpRef = useRef(false);
  const catchUpTicksRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    catchUpRef.current = false;
    catchUpTicksRef.current = 0;
  }, []);

  const pollTick = useCallback(async () => {
    try {
      const data = await projectService.getTaskQueue();
      if (!mountedRef.current) return;
      queueDataRef.current = data;
      setQueueData(data);

      if (hasActive(data)) {
        catchUpRef.current = false;
        catchUpTicksRef.current = 0;
        return;
      }

      if (catchUpRef.current) {
        catchUpTicksRef.current += 1;
        if (catchUpTicksRef.current >= CATCH_UP_MAX_TICKS) {
          stopPolling();
        }
        return;
      }

      stopPolling();
    } catch {
      // 静默失败
    }
  }, [stopPolling]);

  const startPolling = useCallback(() => {
    if (timerRef.current) return;
    timerRef.current = setInterval(() => void pollTick(), POLL_INTERVAL_MS);
  }, [pollTick]);

  /** 冷启动：仅一次请求；有任务才进入轮询 */
  const fetchInitial = useCallback(async () => {
    catchUpRef.current = false;
    catchUpTicksRef.current = 0;
    try {
      const data = await projectService.getTaskQueue();
      if (!mountedRef.current) return;
      queueDataRef.current = data;
      setQueueData(data);
      if (hasActive(data)) {
        startPolling();
      }
    } catch {
      // 静默失败
    }
  }, [startPolling]);

  /** 用户在本页提交了任务：允许队列 API 延迟出现数据，短时间持续拉取 */
  const fetchAfterTaskSubmitted = useCallback(async () => {
    catchUpRef.current = true;
    catchUpTicksRef.current = 0;
    await pollTick();
    if (hasActive(queueDataRef.current) || catchUpRef.current) {
      startPolling();
    }
  }, [pollTick, startPolling]);

  // 初始检查（无任务不轮询）
  useEffect(() => {
    mountedRef.current = true;
    void fetchInitial();
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, [fetchInitial, stopPolling]);

  // 监听全局任务提交通知
  useEffect(() => {
    const handler = () => {
      void fetchAfterTaskSubmitted();
    };
    window.addEventListener(TASK_SUBMITTED_EVENT, handler);
    return () => {
      window.removeEventListener(TASK_SUBMITTED_EVENT, handler);
    };
  }, [fetchAfterTaskSubmitted]);

  const activeCount = queueData?.active_task_count ?? 0;

  if (queueData == null || !hasActive(queueData)) return null;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed right-6 bottom-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg hover:bg-blue-700 transition-colors animate-fade-in"
        title="查看任务队列"
      >
        <Layers className="h-6 w-6" />
        {activeCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {activeCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-[60]" onClick={() => setIsOpen(false)}>
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm dark:bg-black/55" />
          <div className="fixed right-6 bottom-24 z-[61] w-[420px] max-h-[70vh] overflow-hidden rounded-xl bg-white shadow-[0_24px_80px_-12px_rgba(15,23,42,0.35)] ring-1 ring-slate-200/80 animate-slide-up dark:bg-[#1f1f1f] dark:shadow-black/50 dark:ring-[#2a2a2a]">
            <div
              className="flex flex-col max-h-[70vh]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5 dark:border-[#2a2a2a]">
                <div className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-blue-600" />
                  <h3 className="text-base font-semibold text-slate-900 dark:text-zinc-100">任务队列</h3>
                  {activeCount > 0 && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
                      {activeCount} 个任务运行中
                    </span>
                  )}
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="overflow-y-auto px-5 py-4 space-y-4">
                {(queueData.active_tasks?.length ?? 0) > 0 && (
                  <div>
                    <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-blue-600">
                      <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                      {queueData.active_project ? "正在执行" : "进行中"}
                    </div>
                    <div className="rounded-lg border border-blue-100 bg-blue-50/50 px-4 py-3 dark:border-blue-400/20 dark:bg-blue-500/10">
                      {queueData.active_project ? (
                        <div className="mb-2 text-sm font-medium text-slate-800 dark:text-zinc-100">
                          项目: {queueData.active_project_name || queueData.active_project}
                        </div>
                      ) : (
                        <div className="mb-2 text-xs text-slate-500 dark:text-zinc-400">
                          当前未占用全局项目队列；以下为后台运行中的任务。
                        </div>
                      )}
                      <div className="space-y-1.5">
                        {queueData.active_tasks.map((t, i) => (
                          <div
                            key={`${t.scope}-${t.task_id || i}`}
                            className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md bg-white px-3 py-2 text-xs shadow-sm dark:bg-[#242424] dark:shadow-black/30"
                          >
                            {statusIcon(t.status)}
                            {!queueData.active_project && (
                              <span className="font-medium text-slate-600 max-w-[140px] truncate dark:text-zinc-300" title={t.project_name || t.project_id}>
                                {t.project_name || t.project_id}
                              </span>
                            )}
                            <span className="font-medium text-slate-700 dark:text-zinc-200">{scopeLabel(t.scope)}</span>
                            <span className="text-slate-400 dark:text-zinc-500">{statusText(t.status)}</span>
                            {t.progress != null && t.progress > 0 && t.progress < 100 && (
                              <span className="ml-auto text-slate-500 dark:text-zinc-400">{Math.round(t.progress)}%</span>
                            )}
                            {t.message && (
                              <span className="truncate text-slate-400 max-w-[140px] basis-full sm:basis-auto dark:text-zinc-500" title={t.message}>
                                - {t.message}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* 排队项目 */}
                {queueData?.waiting_projects.map((wp) => (
                  <div key={wp.project_id}>
                    <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-amber-600">
                      <Clock className="h-3 w-3" />
                      排队中 · 第 {wp.queue_position} 位
                    </div>
                    <div className="rounded-lg border border-amber-100 bg-amber-50/50 px-4 py-3 dark:border-amber-400/20 dark:bg-amber-500/10">
                      <div className="mb-2 text-sm font-medium text-slate-800 dark:text-zinc-100">
                        项目: {wp.project_name || wp.project_id}
                      </div>
                      <div className="space-y-1.5">
                        {wp.tasks.map((t, i) => (
                          <div
                            key={t.task_id || i}
                            className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs shadow-sm dark:bg-[#242424] dark:shadow-black/30"
                          >
                            <Clock className="h-3.5 w-3.5 text-amber-500" />
                            <span className="font-medium text-slate-700 dark:text-zinc-200">{scopeLabel(t.scope)}</span>
                            <span className="text-amber-600">等待中</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}

                {/* 空队列状态 */}
                {!queueData?.active_project &&
                  queueData?.waiting_projects.length === 0 &&
                  (queueData.active_tasks?.length ?? 0) === 0 && (
                  <div className="py-8 text-center text-sm text-slate-400 dark:text-zinc-500">
                    <Layers className="mx-auto mb-2 h-8 w-8 opacity-40" />
                    当前没有排队的任务
                  </div>
                )}
              </div>

              <div className="border-t border-slate-200 px-5 py-2.5 dark:border-[#2a2a2a]">
                <p className="text-xs text-slate-400 dark:text-zinc-500">
                  每 {POLL_INTERVAL_MS / 1000}s 自动刷新 · 点击外部关闭
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default TaskQueueFloatingBall;
