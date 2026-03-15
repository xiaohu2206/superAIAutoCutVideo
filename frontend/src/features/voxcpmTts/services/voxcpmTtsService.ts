import { apiClient } from "@/services/clients";
import type {
  ApiOk,
  VoxcpmTtsDownloadProvider,
  VoxcpmTtsModelStatus,
  VoxcpmTtsPatchVoiceInput,
  VoxcpmTtsUploadVoiceInput,
  VoxcpmTtsDownloadTask,
  VoxcpmTtsVoice,
} from "../types";

export const voxcpmTtsService = {
  getRuntimeStatus(): Promise<ApiOk<any>> {
    return apiClient.get("/api/tts/voxcpm/runtime-status");
  },

  listModels(): Promise<ApiOk<VoxcpmTtsModelStatus[]>> {
    return apiClient.get("/api/tts/voxcpm/models");
  },

  validateModel(key: string): Promise<ApiOk<{ key: string; path: string; valid: boolean; missing: string[] }>> {
    return apiClient.post("/api/tts/voxcpm/models/validate", { key });
  },

  downloadModel(key: string, provider: VoxcpmTtsDownloadProvider): Promise<ApiOk<any>> {
    return apiClient.post("/api/tts/voxcpm/models/download", { key, provider });
  },

  stopDownload(key: string): Promise<ApiOk<any>> {
    return apiClient.post(`/api/tts/voxcpm/models/downloads/${encodeURIComponent(key)}/stop`);
  },

  listDownloadTasks(): Promise<ApiOk<VoxcpmTtsDownloadTask[]>> {
    return apiClient.get("/api/tts/voxcpm/models/downloads");
  },

  async openModelDirInExplorer(key: string): Promise<void> {
    const base = `${apiClient.getBaseUrl()}/api/tts/voxcpm/models/open-path?key=${encodeURIComponent(
      key
    )}`;
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

  listVoices(): Promise<ApiOk<VoxcpmTtsVoice[]>> {
    return apiClient.get("/api/tts/voxcpm/voices");
  },

  uploadVoice(input: VoxcpmTtsUploadVoiceInput): Promise<ApiOk<VoxcpmTtsVoice>> {
    const fd = new FormData();
    fd.append("file", input.file);
    fd.append("name", input.name || "");
    fd.append("model_key", input.model_key);
    fd.append("language", input.language);
    fd.append("ref_text", input.ref_text || "");
    return apiClient.postFormData("/api/tts/voxcpm/voices/upload", fd);
  },

  getVoice(id: string): Promise<ApiOk<VoxcpmTtsVoice>> {
    return apiClient.get(`/api/tts/voxcpm/voices/${encodeURIComponent(id)}`);
  },

  patchVoice(id: string, partial: VoxcpmTtsPatchVoiceInput): Promise<ApiOk<VoxcpmTtsVoice>> {
    return apiClient.patch(`/api/tts/voxcpm/voices/${encodeURIComponent(id)}`, partial);
  },

  deleteVoice(id: string, removeFiles: boolean): Promise<ApiOk<{ id: string; removed_files: boolean }>> {
    const q = `?remove_files=${removeFiles ? "1" : "0"}`;
    return apiClient.delete(`/api/tts/voxcpm/voices/${encodeURIComponent(id)}${q}`);
  },

  startClone(id: string): Promise<ApiOk<{ voice_id: string; job_id: string }>> {
    return apiClient.post(`/api/tts/voxcpm/voices/${encodeURIComponent(id)}/clone`);
  },

  getCloneStatus(id: string): Promise<ApiOk<{
    voice_id: string;
    status: string;
    progress: number;
    last_error?: string | null;
    ref_audio_path?: string | null;
    ref_audio_url?: string | null;
  }>> {
    return apiClient.get(`/api/tts/voxcpm/voices/${encodeURIComponent(id)}/clone-status`);
  },
};
