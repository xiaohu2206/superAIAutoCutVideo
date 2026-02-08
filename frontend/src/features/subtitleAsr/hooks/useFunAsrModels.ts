import { useCallback, useEffect, useMemo, useState } from "react";
import { useWsScopeProgress } from "@/hooks/useWsScopeProgress";
import type { WebSocketMessage } from "@/services/clients";
import { message } from "@/services/message";
import { funAsrService } from "../services/funAsrService";
import type { FunAsrDownloadProvider, FunAsrDownloadTask, FunAsrModelStatus } from "../types";

const clampProgress = (v?: number) => Math.max(0, Math.min(100, typeof v === "number" ? v : 0));

type DownloadState = {
  key: string;
  provider: FunAsrDownloadProvider;
  progress: number;
  phase?: string;
  message?: string;
  type?: string;
  status?: string;
  downloadedBytes?: number;
  totalBytes?: number | null;
  ownerOptionId?: string;
};

export function useFunAsrModels() {
  const [models, setModels] = useState<FunAsrModelStatus[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadsByKey, setDownloadsByKey] = useState<Record<string, DownloadState>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await funAsrService.listModels();
      if (res?.success) {
        setModels(res.data || []);
      } else {
        setError(res?.message || "加载模型列表失败");
      }
    } catch (e: any) {
      setError(e?.message || "加载模型列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const validate = useCallback(
    async (key: string) => {
      try {
        const res = await funAsrService.validateModel(key);
        if (!res?.success) {
          message.error(res?.message || "校验失败");
          return;
        }
        setModels((prev) =>
          prev.map((m) => (m.key === key ? { ...m, valid: Boolean(res.data?.valid), missing: res.data?.missing || [] } : m))
        );
        await refresh();
        if (res.data?.valid) {
          message.success("校验通过");
        } else {
          message.warning("校验未通过，请检查缺失文件");
        }
      } catch (e: any) {
        message.error(e?.message || "校验失败");
      }
    },
    [refresh]
  );

  const openModelDirInExplorer = useCallback(async (key: string): Promise<void> => {
    await funAsrService.openModelDirInExplorer(key);
  }, []);

  const downloadModel = useCallback(
    async (key: string, provider: FunAsrDownloadProvider, ownerOptionId?: string) => {
      if (downloadsByKey[key]?.status === "running") return;
      setDownloadsByKey((prev) => ({
        ...prev,
        [key]: {
          key,
          provider,
          progress: 0,
          phase: "download_start",
          message: "准备下载…",
          status: "running",
          downloadedBytes: 0,
          totalBytes: null,
          ownerOptionId,
        },
      }));
      try {
        const res = await funAsrService.downloadModel(key, provider);
        if (!res?.success) {
          message.error(res?.message || "下载失败");
          setDownloadsByKey((prev) => {
            const next = { ...prev };
            delete next[key];
            return next;
          });
          return;
        }
        const totalBytes = (res as any)?.data?.total_bytes ?? (res as any)?.data?.totalBytes ?? null;
        if (totalBytes !== null && totalBytes !== undefined) {
          setDownloadsByKey((prev) => ({
            ...prev,
            [key]: {
              ...prev[key],
              totalBytes,
            },
          }));
        }
      } catch (e: any) {
        message.error(e?.message || "下载失败");
        setDownloadsByKey((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    },
    [downloadsByKey]
  );

  const stopDownload = useCallback(
    async (key: string) => {
      if (!downloadsByKey[key]) return;
      setDownloadsByKey((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          status: "cancelling",
          message: "正在停止下载…",
        },
      }));
      try {
        const res = await funAsrService.stopDownload(key);
        if (!res?.success) {
          message.error(res?.message || "停止下载失败");
          setDownloadsByKey((prev) => ({
            ...prev,
            [key]: {
              ...prev[key],
              status: "running",
            },
          }));
        }
      } catch (e: any) {
        message.error(e?.message || "停止下载失败");
        setDownloadsByKey((prev) => ({
          ...prev,
          [key]: {
            ...prev[key],
            status: "running",
          },
        }));
      }
    },
    [downloadsByKey]
  );

  const loadActiveDownloads = useCallback(async () => {
    try {
      const res = await funAsrService.listDownloadTasks();
      if (!res?.success || !Array.isArray(res.data)) return;
      const map: Record<string, DownloadState> = {};
      res.data.forEach((task: FunAsrDownloadTask) => {
        if (!task?.key) return;
        const downloadedBytes = Number((task as any).downloaded_bytes ?? (task as any).downloadedBytes ?? 0);
        const rawTotal = (task as any).total_bytes ?? (task as any).totalBytes ?? null;
        const totalBytes = rawTotal !== null ? Number(rawTotal) : null;
        map[task.key] = {
          key: task.key,
          provider: (task.provider as FunAsrDownloadProvider) || "modelscope",
          progress: clampProgress(task.progress),
          phase: task.phase,
          message: task.message,
          status: task.status || "running",
          downloadedBytes,
          totalBytes,
        };
      });
      setDownloadsByKey(map);
    } catch {
      return;
    }
  }, []);

  const resolveModelKey = useCallback((msg: any) => {
    const directKey = String(msg?.model_key || "").trim();
    if (directKey) return directKey;
    const maybe = String(msg?.key || "").trim();
    if (maybe) return maybe;
    return "";
  }, []);

  const resolveWsStatus = useCallback((wsMsg: WebSocketMessage, fallback?: string) => {
    const directStatus = String((wsMsg as any)?.status || "").trim();
    if (directStatus) return directStatus;
    const phase = String((wsMsg as any)?.phase || "").toLowerCase();
    if (phase.includes("cancel")) return "cancelled";
    if (phase.includes("error")) return "error";
    if (phase.includes("done") || phase.includes("complete")) return "completed";
    if (phase) return "running";
    if (wsMsg.type === "completed") return "completed";
    if (wsMsg.type === "error") return "error";
    if (wsMsg.type === "cancelled") return "cancelled";
    if (wsMsg.type === "progress") return "running";
    return fallback || "running";
  }, []);

  useWsScopeProgress({
    scope: "fun_asr_models",
    onMessage: (wsMsg) => {
      const key = resolveModelKey(wsMsg);
      if (!key) return;
      if (wsMsg.type === "completed" || wsMsg.type === "error" || wsMsg.type === "cancelled") {
        setDownloadsByKey((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        void refresh();
        return;
      }
      setDownloadsByKey((prev) => {
        const existing = prev[key];
        const provider = (wsMsg as any)?.provider || existing?.provider || "modelscope";
        const downloadedBytes = Number((wsMsg as any)?.downloaded_bytes ?? (wsMsg as any)?.downloadedBytes ?? existing?.downloadedBytes ?? 0);
        const rawTotal = (wsMsg as any)?.total_bytes ?? (wsMsg as any)?.totalBytes ?? existing?.totalBytes ?? null;
        const totalBytes = rawTotal !== null ? Number(rawTotal) : null;
        const resolvedProgress =
          typeof wsMsg.progress === "number"
            ? clampProgress(wsMsg.progress)
            : typeof downloadedBytes === "number" && typeof totalBytes === "number" && totalBytes > 0
              ? clampProgress((downloadedBytes / totalBytes) * 100)
              : clampProgress(existing?.progress ?? 0);

        const resolvedStatus = resolveWsStatus(wsMsg, existing?.status);
        return {
          ...prev,
          [key]: {
            key,
            provider,
            progress: resolvedProgress,
            phase: (wsMsg as any)?.phase || existing?.phase,
            message: wsMsg.message || existing?.message,
            type: wsMsg.type || existing?.type,
            status: resolvedStatus,
            downloadedBytes,
            totalBytes,
            ownerOptionId: existing?.ownerOptionId,
          },
        };
      });
    },
  });

  useEffect(() => {
    void refresh();
    void loadActiveDownloads();
  }, [refresh, loadActiveDownloads]);

  const modelByKey = useMemo(() => {
    const m = new Map<string, FunAsrModelStatus>();
    models.forEach((it) => m.set(it.key, it));
    return m;
  }, [models]);

  return {
    models,
    modelByKey,
    loading,
    error,
    downloadsByKey,
    refresh,
    validate,
    openModelDirInExplorer,
    downloadModel,
    stopDownload,
  };
}
