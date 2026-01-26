import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWsScopeProgress } from "@/hooks/useWsScopeProgress";
import { message } from "@/services/message";
import { qwen3TtsService } from "../services/qwen3TtsService";
import type { Qwen3TtsDownloadProvider, Qwen3TtsModelStatus } from "../types";

type DownloadState = {
  key: string;
  provider: Qwen3TtsDownloadProvider;
  progress: number;
  phase?: string;
  message?: string;
  type?: string;
};

export function useQwen3Models() {
  const [models, setModels] = useState<Qwen3TtsModelStatus[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [download, setDownload] = useState<DownloadState | null>(null);
  const activeDownloadKeyRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await qwen3TtsService.listModels();
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

  const validate = useCallback(async (key: string) => {
    try {
      const res = await qwen3TtsService.validateModel(key);
      if (!res?.success) {
        message.error(res?.message || "校验失败");
        return;
      }
      await refresh();
      if (res.data?.valid) {
        message.success("校验通过");
      } else {
        message.warning("校验未通过，请检查缺失文件");
      }
    } catch (e: any) {
      message.error(e?.message || "校验失败");
    }
  }, [refresh]);

  const getModelPath = useCallback(async (key: string): Promise<string> => {
    const res = await qwen3TtsService.getModelPath(key);
    if (!res?.success || !res.data?.path) {
      throw new Error(res?.message || "获取路径失败");
    }
    return res.data.path;
  }, []);

  const downloadModel = useCallback(async (key: string, provider: Qwen3TtsDownloadProvider) => {
    setDownload({ key, provider, progress: 0, phase: "download_start", message: "准备下载…" });
    activeDownloadKeyRef.current = key;
    try {
      const res = await qwen3TtsService.downloadModel(key, provider);
      if (!res?.success) {
        message.error(res?.message || "下载失败");
        return;
      }
      await refresh();
    } catch (e: any) {
      message.error(e?.message || "下载失败");
    } finally {
      activeDownloadKeyRef.current = null;
    }
  }, [refresh]);

  const matchDownloadMsg = useCallback((wsMsg: any) => {
    const activeKey = activeDownloadKeyRef.current;
    if (!activeKey) return false;
    const text = String(wsMsg?.message || "");
    return text.includes(activeKey);
  }, []);

  useWsScopeProgress({
    scope: "qwen3_tts_models",
    match: matchDownloadMsg,
    onProgress: (p) => {
      setDownload((prev) => {
        if (!prev) return prev;
        return { ...prev, progress: p };
      });
    },
    onLog: (log) => {
      setDownload((prev) => {
        if (!prev) return prev;
        return { ...prev, message: log.message, phase: log.phase, type: log.type };
      });
    },
    onCompleted: async () => {
      await refresh();
    },
    onError: async () => {
      await refresh();
    },
  });

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const modelByKey = useMemo(() => {
    const m = new Map<string, Qwen3TtsModelStatus>();
    models.forEach((it) => m.set(it.key, it));
    return m;
  }, [models]);

  return {
    models,
    modelByKey,
    loading,
    error,
    download,
    refresh,
    validate,
    getModelPath,
    downloadModel,
  };
}

