import { apiClient } from "@/services/clients";
import type { ApiOk, MoondreamModelStatus, MoondreamTestResult, MoondreamDownloadTask } from "../types";

export const moondreamService = {
  listModels(): Promise<ApiOk<MoondreamModelStatus[]>> {
    return apiClient.get("/api/vision/moondream/models");
  },

  validateModel(key: string): Promise<ApiOk<MoondreamModelStatus>> {
    return apiClient.post("/api/vision/moondream/models/validate", { key });
  },

  async openModelDirInExplorer(): Promise<void> {
    const base = `${apiClient.getBaseUrl()}/api/vision/moondream/models/open-path`;
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

  testModel(prompt: string): Promise<ApiOk<MoondreamTestResult>> {
    return apiClient.post("/api/vision/moondream/test", { prompt });
  },

  downloadModel(provider: string): Promise<ApiOk<MoondreamDownloadTask>> {
    return apiClient.post("/api/vision/moondream/models/download", { provider });
  },

  listDownloads(): Promise<ApiOk<MoondreamDownloadTask[]>> {
    return apiClient.get("/api/vision/moondream/models/downloads");
  },

  stopDownload(key: string): Promise<ApiOk<any>> {
    return apiClient.post("/api/vision/moondream/models/downloads/stop", { key });
  },
};
