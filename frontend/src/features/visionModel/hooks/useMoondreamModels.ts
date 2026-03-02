import { useCallback, useEffect, useMemo, useState } from "react";
import { message } from "@/services/message";
import { moondreamService } from "../services/moondreamService";
import type { MoondreamModelStatus, MoondreamDownloadTask } from "../types";
import { wsClient, type WebSocketMessage } from "@/services/clients";

export function useMoondreamModels() {
  const [models, setModels] = useState<MoondreamModelStatus[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  const [downloadTask, setDownloadTask] = useState<MoondreamDownloadTask | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await moondreamService.listModels();
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
        const res = await moondreamService.validateModel(key);
        if (!res?.success) {
          message.error(res?.message || "校验失败");
          return;
        }
        const data = res.data;
        if (!data) return;

        setModels((prev) =>
          prev.map((m) =>
            m.key === key ? { ...m, valid: Boolean(data.valid), missing: data.missing || [] } : m
          )
        );
        
        if (data.valid) {
          message.success("校验通过");
        } else {
          message.warning("校验未通过，请检查缺失文件");
        }
      } catch (e: any) {
        message.error(e?.message || "校验失败");
      }
    },
    []
  );
  
  const refreshDownloads = useCallback(async () => {
    try {
      const res = await moondreamService.listDownloads();
      if (res?.success && res.data && res.data.length > 0) {
        setDownloadTask(res.data[0]);
      } else {
        setDownloadTask(null);
      }
    } catch (e) {
      // ignore
    }
  }, []);

  const downloadModel = useCallback(async (provider: string) => {
      try {
          const res = await moondreamService.downloadModel(provider);
          if (res?.success && res.data) {
              setDownloadTask(res.data);
              message.success("已启动下载");
          } else {
              message.error(res?.message || "启动下载失败");
          }
      } catch (e: any) {
          message.error(e?.message || "启动下载失败");
      }
  }, []);

  const stopDownload = useCallback(async (key: string) => {
      try {
          await moondreamService.stopDownload(key);
          message.info("已请求停止下载");
      } catch (e: any) {
          message.error(e?.message || "停止下载失败");
      }
  }, []);

  const openModelDirInExplorer = useCallback(async (): Promise<void> => {
    try {
      await moondreamService.openModelDirInExplorer();
    } catch (e: any) {
        message.error(e?.message || "打开目录失败");
    }
  }, []);

  useEffect(() => {
    void refresh();
    void refreshDownloads();
  }, [refresh, refreshDownloads]);

  // WebSocket progress listener
  useEffect(() => {
    const handler = (data: WebSocketMessage) => {
      if (!data) return;
      if (data.type !== "progress" && data.type !== "completed" && data.type !== "error" && data.type !== "cancelled") return;
      const scope = (data as any).scope as string | undefined;
      if (scope !== "moondream_download") return;

      if (data.type === "progress" || (data as any).type === "running") {
        setDownloadTask(prev => ({
          key: (data as any).key || "moondream2_gguf",
          provider: prev?.provider || "modelscope",
          status: "running",
          progress: typeof data.progress === "number" ? data.progress : prev?.progress || 0,
          message: data.message,
          downloaded_bytes: (data as any).downloaded_bytes,
          total_bytes: (data as any).total_bytes
        }));
      } else if (data.type === "completed") {
        setDownloadTask(null);
        message.success("下载完成");
        void refresh();
      } else if (data.type === "error") {
        setDownloadTask(null);
        message.error(`下载失败: ${data.message || "未知错误"}`);
      } else if (data.type === "cancelled") {
        setDownloadTask(null);
        message.info("下载已取消");
      }
    };
    wsClient.on("*", handler);
    return () => {
      wsClient.off("*", handler);
    };
  }, [refresh]);

  const modelByKey = useMemo(() => {
    const m = new Map<string, MoondreamModelStatus>();
    models.forEach((it) => m.set(it.key, it));
    return m;
  }, [models]);

  return {
    models,
    modelByKey,
    loading,
    error,
    downloadTask,
    refresh,
    validate,
    openModelDirInExplorer,
    downloadModel,
    stopDownload
  };
}
