import { apiClient } from "./clients";

export const ttsService = {
  getEngines: () => apiClient.getTtsEngines(),
  getConfigs: () => apiClient.getTtsConfigs(),
  patchConfig: (configId: string, data: any) => apiClient.patchTtsConfig(configId, data),
  activateConfig: (configId: string) => apiClient.activateTtsConfig(configId),
  getVoices: (provider: string) => apiClient.getTtsVoices(provider),
  previewVoice: (voiceId: string, data: any) => apiClient.previewTtsVoice(voiceId, data),
  testConnection: (configId: string, proxyUrl?: string) => apiClient.testTtsConnection(configId, proxyUrl),
  testActiveConnection: (proxyUrl?: string) => apiClient.testActiveTtsConnection(proxyUrl),

  getIndexTtsStatus: () => apiClient.getIndexTtsStatus(),
  connectIndexTts: (data: {
    host: string;
    port?: number;
    api_prefix?: string;
    scan_back?: number;
  }) => apiClient.connectIndexTts(data),
  disconnectIndexTts: () => apiClient.disconnectIndexTts(),
  uploadIndexTtsCloneVoice: (file: File) => apiClient.uploadIndexTtsCloneVoice(file),
  selectIndexTtsCloneVoice: (voiceId: string) => apiClient.selectIndexTtsCloneVoice(voiceId),
  deleteIndexTtsCloneVoice: (voiceId: string) => apiClient.deleteIndexTtsCloneVoice(voiceId),

  getOmniVoiceTtsStatus: () => apiClient.getOmniVoiceTtsStatus(),
  connectOmniVoiceTts: (data: {
    host: string;
    port?: number;
    api_prefix?: string;
    scan_back?: number;
  }) => apiClient.connectOmniVoiceTts(data),
  disconnectOmniVoiceTts: () => apiClient.disconnectOmniVoiceTts(),
  uploadOmniVoiceTtsCloneVoice: (file: File) => apiClient.uploadOmniVoiceTtsCloneVoice(file),
  selectOmniVoiceTtsCloneVoice: (voiceId: string) => apiClient.selectOmniVoiceTtsCloneVoice(voiceId),
  deleteOmniVoiceTtsCloneVoice: (voiceId: string) => apiClient.deleteOmniVoiceTtsCloneVoice(voiceId),
};

export default ttsService;
