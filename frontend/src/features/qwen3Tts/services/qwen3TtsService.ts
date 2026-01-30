import { apiClient } from "@/services/clients";
import type {
  ApiOk,
  Qwen3TtsDownloadProvider,
  Qwen3TtsModelStatus,
  Qwen3TtsPatchVoiceInput,
  Qwen3TtsUploadVoiceInput,
  Qwen3TtsCustomRoleCreateInput,
  Qwen3TtsDesignCloneCreateInput,
  Qwen3TtsDownloadTask,
  Qwen3TtsVoice,
} from "../types";

export const qwen3TtsService = {
  listModels(): Promise<ApiOk<Qwen3TtsModelStatus[]>> {
    return apiClient.get("/api/tts/qwen3/models");
  },

  validateModel(key: string): Promise<ApiOk<{ key: string; path: string; valid: boolean; missing: string[] }>> {
    return apiClient.post("/api/tts/qwen3/models/validate", { key });
  },

  downloadModel(key: string, provider: Qwen3TtsDownloadProvider): Promise<ApiOk<any>> {
    return apiClient.post("/api/tts/qwen3/models/download", { key, provider });
  },

  stopDownload(key: string): Promise<ApiOk<any>> {
    return apiClient.post(`/api/tts/qwen3/models/downloads/${encodeURIComponent(key)}/stop`);
  },

  listDownloadTasks(): Promise<ApiOk<Qwen3TtsDownloadTask[]>> {
    return apiClient.get("/api/tts/qwen3/models/downloads");
  },

  getModelPath(key: string): Promise<ApiOk<{ key: string; path: string }>> {
    return apiClient.get(`/api/tts/qwen3/models/open-path?key=${encodeURIComponent(key)}`);
  },

  listVoices(): Promise<ApiOk<Qwen3TtsVoice[]>> {
    return apiClient.get("/api/tts/qwen3/voices");
  },

  uploadVoice(input: Qwen3TtsUploadVoiceInput): Promise<ApiOk<Qwen3TtsVoice>> {
    const fd = new FormData();
    fd.append("file", input.file);
    fd.append("name", input.name || "");
    fd.append("model_key", input.model_key);
    fd.append("language", input.language);
    fd.append("ref_text", input.ref_text || "");
    fd.append("instruct", input.instruct || "");
    fd.append("x_vector_only_mode", String(Boolean(input.x_vector_only_mode)));
    return apiClient.postFormData("/api/tts/qwen3/voices/upload", fd);
  },

  createCustomRoleVoice(input: Qwen3TtsCustomRoleCreateInput): Promise<ApiOk<Qwen3TtsVoice>> {
    return apiClient.post("/api/tts/qwen3/voices/custom-role", input);
  },

  createDesignCloneVoice(input: Qwen3TtsDesignCloneCreateInput): Promise<ApiOk<{ voice_id: string; job_id: string }>> {
    return apiClient.post("/api/tts/qwen3/voices/design-clone", input);
  },

  getModelCapabilities(modelKey: string): Promise<ApiOk<{ languages: string[]; speakers: string[] }>> {
    return apiClient.get(`/api/tts/qwen3/models/${encodeURIComponent(modelKey)}/capabilities`);
  },

  getVoice(id: string): Promise<ApiOk<Qwen3TtsVoice>> {
    return apiClient.get(`/api/tts/qwen3/voices/${encodeURIComponent(id)}`);
  },

  patchVoice(id: string, partial: Qwen3TtsPatchVoiceInput): Promise<ApiOk<Qwen3TtsVoice>> {
    return apiClient.patch(`/api/tts/qwen3/voices/${encodeURIComponent(id)}`, partial);
  },

  deleteVoice(id: string, removeFiles: boolean): Promise<ApiOk<{ id: string; removed_files: boolean }>> {
    const q = `?remove_files=${removeFiles ? "1" : "0"}`;
    return apiClient.delete(`/api/tts/qwen3/voices/${encodeURIComponent(id)}${q}`);
  },

  startClone(id: string): Promise<ApiOk<{ voice_id: string; job_id: string }>> {
    return apiClient.post(`/api/tts/qwen3/voices/${encodeURIComponent(id)}/clone`);
  },

  getCloneStatus(id: string): Promise<ApiOk<{
    voice_id: string;
    status: string;
    progress: number;
    last_error?: string | null;
    ref_audio_path?: string | null;
    ref_audio_url?: string | null;
  }>> {
    return apiClient.get(`/api/tts/qwen3/voices/${encodeURIComponent(id)}/clone-status`);
  },
};
