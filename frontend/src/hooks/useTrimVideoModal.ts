import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { projectService } from "../services/projectService";
import { wsClient, type WebSocketMessage } from "../services/clients";
import { message } from "../services/message";
import type { TrimRange } from "../components/projectEdit/TrimTimeline";

export type TrimMode = "keep" | "delete";

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

export const normalizeRanges = (ranges: TrimRange[], durationMs: number) => {
  const d = Math.max(0, durationMs);
  const ordered = [...ranges]
    .map((r) => ({
      ...r,
      startMs: clamp(Math.round(r.startMs), 0, d),
      endMs: clamp(Math.round(r.endMs), 0, d),
    }))
    .filter((r) => r.endMs > r.startMs)
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const merged: TrimRange[] = [];
  for (const r of ordered) {
    const last = merged[merged.length - 1];
    if (!last) {
      merged.push(r);
      continue;
    }
    if (r.startMs <= last.endMs) {
      last.endMs = Math.max(last.endMs, r.endMs);
    } else {
      merged.push(r);
    }
  }
  return merged;
};

export type UseTrimVideoModalOptions = {
  isOpen: boolean;
  projectId: string;
  videoPath: string;
  onClose: () => void;
  getVideoEl: () => HTMLVideoElement | null;
};

export function useTrimVideoModal({ isOpen, projectId, videoPath, onClose, getVideoEl }: UseTrimVideoModalOptions) {
  const [durationMs, setDurationMs] = useState(0);
  const [currentMs, setCurrentMs] = useState(0);
  const [mode, setMode] = useState<TrimMode>("keep");
  const [ranges, setRanges] = useState<TrimRange[]>([]);
  const [activeRangeId, setActiveRangeId] = useState<string | null>(null);
  const [loopRange, setLoopRange] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isVideoLoading, setIsVideoLoading] = useState(false);
  const [cacheBust, setCacheBust] = useState<string>(String(Date.now()));
  const lastVideoPathRef = useRef<string | null>(null);
  const lastOpenRef = useRef(false);
  const preparedPathsRef = useRef<Set<string>>(new Set());
  const seekSeqRef = useRef(0);
  const seekStuckTimerRef = useRef<number | null>(null);
  const seekCleanupRef = useRef<(() => void) | null>(null);
  const rvfcIdRef = useRef<number | null>(null);
  const hardResetTimerRef = useRef<number | null>(null);
  const pendingResetSeekMsRef = useRef<number | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<number>(0);
  const [statusText, setStatusText] = useState<string>("");
  const [errorText, setErrorText] = useState<string>("");

  useEffect(() => {
    if (!isOpen) {
      lastOpenRef.current = false;
      return;
    }
    const isNewOpen = !lastOpenRef.current;
    const isNewVideo = videoPath !== lastVideoPathRef.current;
    lastOpenRef.current = true;
    lastVideoPathRef.current = videoPath;
    setDurationMs(0);
    setCurrentMs(0);
    setMode("keep");
    setRanges([]);
    setActiveRangeId(null);
    setLoopRange(false);
    setIsPlaying(false);
    setIsVideoLoading(isNewOpen || isNewVideo);
    setSubmitting(false);
    setProgress(0);
    setStatusText("");
    setErrorText("");
    if (isNewOpen || isNewVideo) {
      setCacheBust(String(Date.now()));
    }
  }, [isOpen, videoPath]);

  useEffect(() => {
    if (!isOpen || !videoPath) return;
    const key = `${projectId}::${videoPath}`;
    if (preparedPathsRef.current.has(key)) return;
    preparedPathsRef.current.add(key);
    let cancelled = false;
    const run = async () => {
      try {
        await projectService.prepareVideoPreview(projectId, videoPath);
        if (cancelled) return;
        setCacheBust(String(Date.now()));
      } catch {
        if (cancelled) return;
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, projectId, videoPath]);

  const srcUrl = useMemo(() => projectService.getWebFileUrl(videoPath, cacheBust), [videoPath, cacheBust]);
  const normRanges = useMemo(() => normalizeRanges(ranges, durationMs), [ranges, durationMs]);
  const activeRange = useMemo(() => normRanges.find((r) => r.id === activeRangeId) || null, [normRanges, activeRangeId]);

  useEffect(() => {
    if (!isOpen || !videoPath) return;
    setIsVideoLoading(true);
    setIsPlaying(false);
  }, [isOpen, videoPath, srcUrl]);

  const seekTo = useCallback(
    (ms: number) => {
      const v = getVideoEl();
      if (!v) return;
      if (seekCleanupRef.current) {
        seekCleanupRef.current();
        seekCleanupRef.current = null;
      }
      const nextMs = clamp(ms, 0, durationMs);
      setCurrentMs(nextMs);
      setIsVideoLoading(true);
      try {
        v.pause();
      } catch {
        void 0;
      }
      let finished = false;
      const seq = ++seekSeqRef.current;
      const finish = () => {
        if (finished) return;
        finished = true;
        if (seekSeqRef.current === seq) {
          setIsVideoLoading(false);
        }
        if (seekStuckTimerRef.current != null) {
          window.clearTimeout(seekStuckTimerRef.current);
          seekStuckTimerRef.current = null;
        }
        if (rvfcIdRef.current != null) {
          const cancel = (v as any)?.cancelVideoFrameCallback;
          if (typeof cancel === "function") {
            try {
              cancel(rvfcIdRef.current);
            } catch {
              void 0;
            }
          }
          rvfcIdRef.current = null;
        }
        if (hardResetTimerRef.current != null) {
          window.clearTimeout(hardResetTimerRef.current);
          hardResetTimerRef.current = null;
        }
      };
      const onSeekedOnce = () => {
        v.removeEventListener("seeked", onSeekedOnce);
        finish();
      };
      v.addEventListener("seeked", onSeekedOnce);
      seekCleanupRef.current = () => {
        try {
          v.removeEventListener("seeked", onSeekedOnce);
        } catch {
          void 0;
        }
        if (seekStuckTimerRef.current != null) {
          window.clearTimeout(seekStuckTimerRef.current);
          seekStuckTimerRef.current = null;
        }
        if (rvfcIdRef.current != null) {
          const cancel = (v as any)?.cancelVideoFrameCallback;
          if (typeof cancel === "function") {
            try {
              cancel(rvfcIdRef.current);
            } catch {
              void 0;
            }
          }
          rvfcIdRef.current = null;
        }
        if (hardResetTimerRef.current != null) {
          window.clearTimeout(hardResetTimerRef.current);
          hardResetTimerRef.current = null;
        }
      };
      try {
        v.currentTime = nextMs / 1000;
      } catch {
        void 0;
      }
      const rvfc = (v as any)?.requestVideoFrameCallback;
      if (typeof rvfc === "function") {
        try {
          rvfcIdRef.current = rvfc(() => finish());
        } catch {
          void 0;
        }
      }
      seekStuckTimerRef.current = window.setTimeout(() => {
        if (finished) return;
        try {
          v.currentTime = Math.min(durationMs, nextMs + 1) / 1000;
        } catch {
          void 0;
        }
      }, 800);
      hardResetTimerRef.current = window.setTimeout(() => {
        if (finished) return;
        pendingResetSeekMsRef.current = nextMs;
        try {
          v.pause();
        } catch {
          void 0;
        }
        setIsVideoLoading(true);
        setCacheBust(String(Date.now()));
      }, 2500);
    },
    [durationMs, getVideoEl]
  );

  const togglePlay = useCallback(async () => {
    const v = getVideoEl();
    if (!v) return;
    if (v.paused) {
      try {
        await v.play();
        setIsPlaying(true);
      } catch {
        setIsPlaying(false);
      }
    } else {
      v.pause();
      setIsPlaying(false);
    }
  }, [getVideoEl]);

  const addRangeFromCurrent = useCallback(() => {
    const id = `r_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const startMs = clamp(currentMs, 0, durationMs);
    const endMs = clamp(startMs + 5000, 0, durationMs);
    setRanges((prev) => normalizeRanges([...prev, { id, startMs, endMs }], durationMs));
    setActiveRangeId(id);
  }, [currentMs, durationMs]);

  const onLoadedMetadata = useCallback(() => {
    const v = getVideoEl();
    if (!v) return;
    const dur = Number.isFinite(v.duration) ? v.duration : 0;
    setDurationMs(Math.max(0, Math.round(dur * 1000)));
  }, [getVideoEl]);

  const onTimeUpdate = useCallback(() => {
    const v = getVideoEl();
    if (!v) return;
    const ms = Math.round((v.currentTime || 0) * 1000);
    setCurrentMs(ms);
    if (!activeRange) return;
    if (v.paused) return;
    if (ms >= activeRange.endMs - 20) {
      if (loopRange) {
        v.currentTime = activeRange.startMs / 1000;
      } else {
        v.pause();
        setIsPlaying(false);
        v.currentTime = activeRange.endMs / 1000;
      }
    }
  }, [getVideoEl, activeRange, loopRange]);

  const onPause = useCallback(() => setIsPlaying(false), []);
  const onPlay = useCallback(() => setIsPlaying(true), []);
  const onEnded = useCallback(() => setIsPlaying(false), []);
  const onLoadStart = useCallback(() => setIsVideoLoading(true), []);
  const onLoadedData = useCallback(() => {
    const v = getVideoEl();
    if (v && pendingResetSeekMsRef.current != null) {
      try {
        v.currentTime = pendingResetSeekMsRef.current / 1000;
      } catch {
        void 0;
      } finally {
        pendingResetSeekMsRef.current = null;
      }
    }
    setIsVideoLoading(false);
  }, [getVideoEl]);
  const onCanPlay = useCallback(() => {
    const v = getVideoEl();
    if (v && pendingResetSeekMsRef.current != null) {
      try {
        v.currentTime = pendingResetSeekMsRef.current / 1000;
      } catch {
        void 0;
      } finally {
        pendingResetSeekMsRef.current = null;
      }
    }
    setIsVideoLoading(false);
  }, [getVideoEl]);
  const onWaiting = useCallback(() => setIsVideoLoading(true), []);
  const onStalled = useCallback(() => setIsVideoLoading(true), []);
  const onPlaying = useCallback(() => {
    setIsVideoLoading(false);
    setIsPlaying(true);
  }, []);
  const onError = useCallback(() => {
    setIsVideoLoading(false);
    setIsPlaying(false);
  }, []);
  const onSeeking = useCallback(() => setIsVideoLoading(true), []);
  const onSeeked = useCallback(() => setIsVideoLoading(false), []);

  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (durationMs <= 0) return false;
    return normRanges.length > 0;
  }, [submitting, durationMs, mode, normRanges.length]);

  const close = useCallback(() => {
    if (submitting) return;
    onClose();
  }, [submitting, onClose]);

  const confirm = useCallback(async () => {
    if (!canSubmit) return;
    if (mode === "keep" && normRanges.length === 0) {
      message.error("请先在时间轴上创建区间");
      return;
    }
    const ok = window.confirm("处理成功后将不可逆替换原视频文件，无法恢复。确定继续吗？");
    if (!ok) return;

    setSubmitting(true);
    setErrorText("");
    setProgress(0);
    setStatusText("已提交，等待处理...");

    try {
      const start = await projectService.startTrimVideo(projectId, {
        file_path: videoPath,
        mode,
        ranges: normRanges.map((r) => ({ start_ms: r.startMs, end_ms: r.endMs })),
      });
      const taskId = start.task_id;

      await new Promise<void>((resolve, reject) => {
        let finished = false;
        let timeoutId: number | null = null;

        const cleanup = () => {
          if (timeoutId !== null) {
            window.clearTimeout(timeoutId);
            timeoutId = null;
          }
        };

        const handleSuccess = (outputVersion?: string | number) => {
          if (finished) return;
          finished = true;
          cleanup();
          if (outputVersion !== undefined && outputVersion !== null) {
            setCacheBust(String(outputVersion));
          }
          resolve();
        };

        const handleError = (msg: string) => {
          if (finished) return;
          finished = true;
          cleanup();
          reject(new Error(msg || "裁剪失败"));
        };

        const handler = (msg: WebSocketMessage & { [key: string]: any }) => {
          if (!msg) return;
          if ((msg.type !== "progress" && msg.type !== "completed" && msg.type !== "error") || msg.scope !== "trim_video") return;
          if (msg.project_id !== projectId || msg.task_id !== taskId) return;

          if (typeof msg.progress === "number") {
            setProgress(Math.max(0, Math.min(100, Math.round(msg.progress))));
          }
          if (typeof msg.message === "string") {
            setStatusText(msg.message);
          }
          if (msg.type === "completed") {
            wsClient.off("*", handler);
            handleSuccess(msg.output_version ?? Date.now());
          }
          if (msg.type === "error") {
            wsClient.off("*", handler);
            const m = String(msg.message || "裁剪失败");
            handleError(m);
          }
        };

        wsClient.on("*", handler);

        const pollStatus = async () => {
          while (!finished) {
            await new Promise((r) => setTimeout(r, 2000));
            if (finished) return;
            try {
              const status = await projectService.getTrimVideoStatus(projectId, taskId);
              if (!status) continue;
              if (typeof status.progress === "number") {
                setProgress(Math.max(0, Math.min(100, Math.round(status.progress))));
              }
              if (typeof status.message === "string") {
                setStatusText(status.message);
              }
              const st = String(status.status || "").toLowerCase();
              if (st === "completed") {
                wsClient.off("*", handler);
                handleSuccess(status.output_version ?? Date.now());
                return;
              }
              if (st === "failed") {
                wsClient.off("*", handler);
                const m = String(status.message || "裁剪失败");
                handleError(m);
                return;
              }
            } catch (err) {
              void err;
            }
          }
        };

        void pollStatus();

        timeoutId = window.setTimeout(() => {
          wsClient.off("*", handler);
          handleError("裁剪超时，请稍后重试");
        }, 5 * 60 * 1000);
      });

      message.success("裁剪完成，已替换原视频");
      setSubmitting(false);
      onClose();
    } catch (e: any) {
      setSubmitting(false);
      const msg = e?.message || "裁剪失败";
      setErrorText(msg);
      message.error(msg);
    }
  }, [canSubmit, mode, normRanges, projectId, videoPath, onClose]);

  const clearRanges = useCallback(() => {
    setRanges([]);
    setActiveRangeId(null);
  }, []);

  const switchMode = useCallback(
    (next: TrimMode) => {
      if (submitting) return;
      if (next === mode) return;
      const ok = window.confirm("切换模式会清空已选区间，继续吗？");
      if (!ok) return;
      setMode(next);
      clearRanges();
    },
    [submitting, mode, clearRanges]
  );

  return {
    srcUrl,
    durationMs,
    currentMs,
    mode,
    ranges: normRanges,
    rawRanges: ranges,
    activeRangeId,
    activeRange,
    loopRange,
    isPlaying,
    isVideoLoading,
    submitting,
    progress,
    statusText,
    errorText,
    setLoopRange,
    setActiveRangeId,
    setRanges: (next: TrimRange[]) => setRanges(normalizeRanges(next, durationMs)),
    seekTo,
    togglePlay,
    addRangeFromCurrent,
    onLoadedMetadata,
    onTimeUpdate,
    onPause,
    onPlay,
    onEnded,
    onLoadStart,
    onLoadedData,
    onCanPlay,
    onWaiting,
    onStalled,
    onPlaying,
    onError,
    onSeeking,
    onSeeked,
    canSubmit,
    confirm,
    close,
    switchMode,
    clearRanges,
  };
}
