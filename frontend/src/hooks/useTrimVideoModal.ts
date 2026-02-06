import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TrimRange } from "../components/projectEdit/TrimTimeline";
import { wsClient, type WebSocketMessage } from "../services/clients";
import { message } from "../services/message";
import { projectService } from "../services/projectService";

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
  const [resolvedVideoWebPath, setResolvedVideoWebPath] = useState<string>(videoPath);
  const lastVideoPathRef = useRef<string | null>(null);
  const lastOpenRef = useRef(false);
  const preparedPathsRef = useRef<Set<string>>(new Set());
  const seekSeqRef = useRef(0);
  const seekStuckTimerRef = useRef<number | null>(null);
  const seekCleanupRef = useRef<(() => void) | null>(null);
  const rvfcIdRef = useRef<number | null>(null);
  const hardResetTimerRef = useRef<number | null>(null);
  const pendingResetSeekMsRef = useRef<number | null>(null);
  const seekCheckRafRef = useRef<number | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<number>(0);
  const [statusText, setStatusText] = useState<string>("");
  const [errorText, setErrorText] = useState<string>("");

  const isSeekDebugEnabled = () => {
    if (typeof window === "undefined") return false;
    try {
      return (window as any).__SAC_DEBUG_SEEK === true || window.localStorage?.getItem("SAC_DEBUG_SEEK") === "1";
    } catch {
      return (window as any).__SAC_DEBUG_SEEK === true;
    }
  };

  const seekDebugLog = (...args: any[]) => {
    if (!isSeekDebugEnabled()) return;
    try {
      console.log("[SAC][seek]", ...args);
    } catch {
      void 0;
    }
  };

  const isTauri =
    typeof window !== "undefined" &&
    (((window as any).__TAURI__ != null && (window as any).__TAURI__ !== undefined) ||
      ((window as any).__TAURI_INTERNALS__ != null && (window as any).__TAURI_INTERNALS__ !== undefined) ||
      window.location?.protocol === "tauri:");

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
      seekDebugLog("open/reset", { isNewOpen, isNewVideo, projectId, videoPath, isTauri });
      setCacheBust(String(Date.now()));
      setResolvedVideoWebPath(videoPath);
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
        seekDebugLog("prepare/start", { projectId, videoPath });
        const prepared = await projectService.prepareVideoPreview(projectId, videoPath);
        if (cancelled) return;
        if (prepared?.file_path) {
          setResolvedVideoWebPath(prepared.file_path);
        }
        seekDebugLog("prepare/done", { projectId, videoPath, preparedPath: prepared?.file_path ?? null });
        setCacheBust(String(Date.now()));
      } catch {
        if (cancelled) return;
        seekDebugLog("prepare/error", { projectId, videoPath });
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [isOpen, projectId, videoPath]);

  const srcUrl = useMemo(() => {
    const p = (resolvedVideoWebPath || videoPath || "").trim();
    if (!p) return "";
    if (/^https?:\/\//i.test(p)) {
      if (cacheBust === undefined || cacheBust === null) return p;
      const sep = p.includes("?") ? "&" : "?";
      return `${p}${sep}v=${encodeURIComponent(String(cacheBust))}`;
    }
    if (p.startsWith("/")) return projectService.getWebFileUrl(p, cacheBust);
    return "";
  }, [resolvedVideoWebPath, videoPath, cacheBust]);
  const normRanges = useMemo(() => normalizeRanges(ranges, durationMs), [ranges, durationMs]);
  const activeRange = useMemo(() => normRanges.find((r) => r.id === activeRangeId) || null, [normRanges, activeRangeId]);

  useEffect(() => {
    if (!isOpen || !videoPath) return;
    setIsVideoLoading(true);
    setIsPlaying(false);
  }, [isOpen, videoPath, srcUrl]);

  useEffect(() => {
    if (!isOpen) return;
    seekDebugLog("src/update", {
      projectId,
      videoPath,
      resolvedVideoWebPath,
      cacheBust,
      srcUrl,
      isTauri,
    });
  }, [isOpen, projectId, videoPath, resolvedVideoWebPath, cacheBust, srcUrl, isTauri]);

  const seekTo = useCallback(
    (ms: number) => {
      const v = getVideoEl();
      if (!v) return;
      if (seekCleanupRef.current) {
        seekCleanupRef.current();
        seekCleanupRef.current = null;
      }
      const nextMs = clamp(ms, 0, durationMs);
      seekDebugLog("seek/start", {
        reqMs: ms,
        nextMs,
        durationMs,
        currentTime: v.currentTime,
        paused: v.paused,
        readyState: v.readyState,
        networkState: v.networkState,
        src: v.currentSrc || v.src,
        errorCode: v.error?.code ?? null,
        isTauri,
      });
      setCurrentMs(nextMs);
      setIsVideoLoading(true);
      try {
        v.pause();
      } catch {
        void 0;
      }
      let finished = false;
      const seq = ++seekSeqRef.current;
      const finish = (reason: string) => {
        if (finished) return;
        finished = true;
        seekDebugLog("seek/finish", {
          seq,
          reason,
          targetMs: nextMs,
          currentTime: v.currentTime,
          paused: v.paused,
          readyState: v.readyState,
          networkState: v.networkState,
          src: v.currentSrc || v.src,
          errorCode: v.error?.code ?? null,
        });
        if (seekSeqRef.current === seq) {
          setIsVideoLoading(false);
        }
        if (seekStuckTimerRef.current != null) {
          window.clearTimeout(seekStuckTimerRef.current);
          seekStuckTimerRef.current = null;
        }
        if (seekCheckRafRef.current != null) {
          window.cancelAnimationFrame(seekCheckRafRef.current);
          seekCheckRafRef.current = null;
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
        finish("event/seeked");
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
        if (seekCheckRafRef.current != null) {
          window.cancelAnimationFrame(seekCheckRafRef.current);
          seekCheckRafRef.current = null;
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

      const startSeekCheck = () => {
        const startAt = typeof performance !== "undefined" ? performance.now() : Date.now();
        const maxWaitMs = isTauri ? 5000 : 3000;
        const thresholdMs = 40;
        const tick = () => {
          if (finished) return;
          const curSec = v.currentTime;
          if (Number.isFinite(curSec)) {
            const curMs = curSec * 1000;
            if (Math.abs(curMs - nextMs) <= thresholdMs) {
              finish("raf/threshold");
              return;
            }
          }
          const now = typeof performance !== "undefined" ? performance.now() : Date.now();
          if (now - startAt > maxWaitMs) {
            finish("raf/timeout");
            return;
          }
          seekCheckRafRef.current = window.requestAnimationFrame(tick);
        };
        seekCheckRafRef.current = window.requestAnimationFrame(tick);
      };
      startSeekCheck();

      const rvfc = (v as any)?.requestVideoFrameCallback;
      if (typeof rvfc === "function") {
        try {
          rvfcIdRef.current = rvfc(() => finish("rvfc"));
        } catch {
          void 0;
        }
      }
      seekStuckTimerRef.current = window.setTimeout(() => {
        if (finished) return;
        seekDebugLog("seek/nudge", {
          seq,
          targetMs: nextMs,
          currentTime: v.currentTime,
          readyState: v.readyState,
          networkState: v.networkState,
          src: v.currentSrc || v.src,
        });
        try {
          v.currentTime = Math.min(durationMs, nextMs + 1) / 1000;
        } catch {
          void 0;
        }
      }, 800);
      hardResetTimerRef.current = window.setTimeout(() => {
        if (finished) return;
        if (isTauri) {
          seekDebugLog("seek/hardReset/skip-tauri", { seq, targetMs: nextMs });
          return;
        }
        const noSource = v.networkState === (v as any).NETWORK_NO_SOURCE;
        const haveNothing = v.readyState === 0;
        if (!noSource && !haveNothing) {
          seekDebugLog("seek/hardReset/skip", { seq, targetMs: nextMs, noSource, haveNothing, readyState: v.readyState, networkState: v.networkState });
          return;
        }
        seekDebugLog("seek/hardReset/run", {
          seq,
          targetMs: nextMs,
          noSource,
          haveNothing,
          readyState: v.readyState,
          networkState: v.networkState,
          src: v.currentSrc || v.src,
        });
        pendingResetSeekMsRef.current = nextMs;
        try {
          v.pause();
        } catch {
          void 0;
        }
        setIsVideoLoading(true);
        setCacheBust(String(Date.now()));
      }, 6000);
    },
    [durationMs, getVideoEl, isTauri]
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
    seekDebugLog("video/loadedmetadata", { duration: v.duration, durationMs: Math.max(0, Math.round(dur * 1000)), src: v.currentSrc || v.src });
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
  const onLoadStart = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/loadstart", {
      currentTime: v?.currentTime ?? null,
      readyState: v?.readyState ?? null,
      networkState: v?.networkState ?? null,
      src: v ? v.currentSrc || v.src : null,
    });
    setIsVideoLoading(true);
  }, [getVideoEl]);
  const onLoadedData = useCallback(() => {
    const v = getVideoEl();
    if (v && pendingResetSeekMsRef.current != null) {
      seekDebugLog("video/loadeddata/applyPendingSeek", { ms: pendingResetSeekMsRef.current, src: v.currentSrc || v.src });
      try {
        v.currentTime = pendingResetSeekMsRef.current / 1000;
      } catch {
        void 0;
      } finally {
        pendingResetSeekMsRef.current = null;
      }
    }
    seekDebugLog("video/loadeddata", {
      currentTime: v?.currentTime ?? null,
      readyState: v?.readyState ?? null,
      networkState: v?.networkState ?? null,
      src: v ? v.currentSrc || v.src : null,
    });
    setIsVideoLoading(false);
  }, [getVideoEl]);
  const onCanPlay = useCallback(() => {
    const v = getVideoEl();
    if (v && pendingResetSeekMsRef.current != null) {
      seekDebugLog("video/canplay/applyPendingSeek", { ms: pendingResetSeekMsRef.current, src: v.currentSrc || v.src });
      try {
        v.currentTime = pendingResetSeekMsRef.current / 1000;
      } catch {
        void 0;
      } finally {
        pendingResetSeekMsRef.current = null;
      }
    }
    seekDebugLog("video/canplay", {
      currentTime: v?.currentTime ?? null,
      readyState: v?.readyState ?? null,
      networkState: v?.networkState ?? null,
      src: v ? v.currentSrc || v.src : null,
    });
    setIsVideoLoading(false);
  }, [getVideoEl]);
  const onWaiting = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/waiting", { currentTime: v?.currentTime ?? null, readyState: v?.readyState ?? null });
    setIsVideoLoading(true);
  }, [getVideoEl]);
  const onStalled = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/stalled", { currentTime: v?.currentTime ?? null, readyState: v?.readyState ?? null });
    setIsVideoLoading(true);
  }, [getVideoEl]);
  const onPlaying = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/playing", { currentTime: v?.currentTime ?? null, readyState: v?.readyState ?? null, src: v ? v.currentSrc || v.src : null });
    setIsVideoLoading(false);
    setIsPlaying(true);
  }, [getVideoEl]);
  const onError = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/error", {
      errorCode: v?.error?.code ?? null,
      currentTime: v?.currentTime ?? null,
      readyState: v?.readyState ?? null,
      networkState: v?.networkState ?? null,
      src: v ? v.currentSrc || v.src : null,
    });
    setIsVideoLoading(false);
    setIsPlaying(false);
  }, [getVideoEl]);
  const onSeeking = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/seeking", { currentTime: v?.currentTime ?? null, readyState: v?.readyState ?? null });
    setIsVideoLoading(true);
  }, [getVideoEl]);
  const onSeeked = useCallback(() => {
    const v = getVideoEl();
    seekDebugLog("video/seeked", { currentTime: v?.currentTime ?? null, readyState: v?.readyState ?? null });
    setIsVideoLoading(false);
  }, [getVideoEl]);

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
      const v = getVideoEl();
      if (v) {
        try {
          v.pause();
        } catch {
          void 0;
        }
        try {
          v.removeAttribute("src");
        } catch {
          void 0;
        }
        try {
          v.load();
        } catch {
          void 0;
        }
        await new Promise((r) => setTimeout(r, 80));
      }

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

        const handleSuccess = (outputVersion?: string | number, nextFilePath?: string | null) => {
          if (finished) return;
          finished = true;
          cleanup();
          if (typeof nextFilePath === "string" && nextFilePath.trim()) {
            setResolvedVideoWebPath(nextFilePath.trim());
          }
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
            handleSuccess(msg.output_version ?? Date.now(), typeof msg.file_path === "string" ? msg.file_path : null);
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
                handleSuccess(status.output_version ?? Date.now(), typeof status.file_path === "string" ? status.file_path : null);
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
  }, [canSubmit, mode, normRanges, projectId, videoPath, onClose, getVideoEl]);

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
