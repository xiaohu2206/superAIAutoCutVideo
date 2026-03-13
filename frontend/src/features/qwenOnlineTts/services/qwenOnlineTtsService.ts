import { apiClient } from "@/services/clients";
import type {
  QwenOnlineTtsVoice,
  QwenOnlineTtsUploadVoiceInput,
  QwenOnlineTtsPatchVoiceInput,
} from "../types";

export const qwenOnlineTtsService = {
  listVoices: () =>
    apiClient.get<{ success: boolean; data: QwenOnlineTtsVoice[] }>(
      "/api/tts/qwen-online/voices"
    ),

  getVoice: (voiceId: string) =>
    apiClient.get<{ success: boolean; data: QwenOnlineTtsVoice }>(
      `/api/tts/qwen-online/voices/${encodeURIComponent(voiceId)}`
    ),

  uploadVoice: async (
    input: QwenOnlineTtsUploadVoiceInput,
    configId?: string
  ) => {
    const formData = new FormData();
    formData.append("file", input.file);
    if (input.name) formData.append("name", input.name);
    if (input.model) formData.append("model", input.model);
    if (input.ref_text) formData.append("ref_text", input.ref_text);
    const q = configId ? `?config_id=${encodeURIComponent(configId)}` : "";
    return apiClient.postFormData<{
      success: boolean;
      data: QwenOnlineTtsVoice;
    }>(`/api/tts/qwen-online/voices/upload${q}`, formData, 1000 * 180);
  },

  patchVoice: (voiceId: string, partial: QwenOnlineTtsPatchVoiceInput) => {
    const formData = new FormData();
    if (partial.name !== undefined) formData.append("name", partial.name);
    if (partial.ref_text !== undefined)
      formData.append("ref_text", partial.ref_text || "");
    if (partial.model !== undefined) formData.append("model", partial.model);
    return apiClient.patch<{ success: boolean; data: QwenOnlineTtsVoice }>(
      `/api/tts/qwen-online/voices/${encodeURIComponent(voiceId)}`,
      {
        method: "PATCH",
        body: formData,
      }
    );
  },

  deleteVoice: (voiceId: string, removeFiles: boolean = false) => {
    const q = removeFiles ? `?remove_files=true` : "";
    return apiClient.delete<{ success: boolean }>(
      `/api/tts/qwen-online/voices/${encodeURIComponent(voiceId)}${q}`
    );
  },
};

export default qwenOnlineTtsService;
