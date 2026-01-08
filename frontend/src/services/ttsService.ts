import { apiClient } from "./clients";

export const ttsService = {
  getEngines: () => apiClient.getTtsEngines(),
  getConfigs: () => apiClient.getTtsConfigs(),
  patchConfig: (configId: string, data: any) => apiClient.patchTtsConfig(configId, data),
  activateConfig: (configId: string) => apiClient.activateTtsConfig(configId),
  getVoices: (provider: string) => apiClient.getTtsVoices(provider),
  previewVoice: (voiceId: string, data: any) => apiClient.previewTtsVoice(voiceId, data),
  testConnection: (configId: string, proxyUrl?: string) => apiClient.testTtsConnection(configId, proxyUrl),
};

export default ttsService;
