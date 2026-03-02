import { apiClient } from "@/services/clients";
import type {
  ApiOk,
  FunAsrAccelerationStatus,
  FunAsrDownloadProvider,
  FunAsrDownloadTask,
  FunAsrModelStatus,
  FunAsrTestResult,
  FunAsrValidateResult,
} from "../types";

export const funAsrService = {
  getAccelerationStatus(): Promise<ApiOk<FunAsrAccelerationStatus>> {
    return apiClient.get("/api/asr/funasr/acceleration-status");
  },

  listModels(): Promise<ApiOk<FunAsrModelStatus[]>> {
    return apiClient.get("/api/asr/funasr/models");
  },

  validateModel(key: string): Promise<ApiOk<FunAsrValidateResult>> {
    return apiClient.post("/api/asr/funasr/models/validate", { key });
  },

  downloadModel(key: string, provider: FunAsrDownloadProvider): Promise<ApiOk<any>> {
    return apiClient.post("/api/asr/funasr/models/download", { key, provider });
  },

  stopDownload(key: string): Promise<ApiOk<any>> {
    return apiClient.post("/api/asr/funasr/models/downloads/stop", { key });
  },

  listDownloadTasks(): Promise<ApiOk<FunAsrDownloadTask[]>> {
    return apiClient.get("/api/asr/funasr/models/downloads");
  },

  async openModelDirInExplorer(key: string): Promise<void> {
    const base = `${apiClient.getBaseUrl()}/api/asr/funasr/models/open-path?key=${encodeURIComponent(key)}`;
    const res = await fetch(base);
    if (!res.ok) {
      let msg = `打开文件管理器失败: ${res.statusText}`;
      try {
        const ct = res.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
          const j = await res.json();
          if (typeof j === "string") msg = j;
          else if ((j as any)?.detail) msg = (j as any).detail;
          else if ((j as any)?.message) msg = (j as any).message;
        } else {
          const t = await res.text();
          if (t) msg = t;
        }
      } catch (e) {
        void e;
      }
      throw new Error(msg);
    }
  },

  testModel(input: { key: string; device?: string | null; language: string; itn: boolean }): Promise<ApiOk<FunAsrTestResult>> {
    return apiClient.post("/api/asr/funasr/test", {
      key: input.key,
      device: input.device || undefined,
      language: input.language,
      itn: Boolean(input.itn),
    });
  },
};

