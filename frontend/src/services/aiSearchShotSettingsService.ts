import type { AiSearchShotModelConfig } from "@/components/settingsPage/types";
import { apiClient } from "./clients";

export const aiSearchShotSettingsService = {
  getConfig: () => apiClient.getAiSearchShotModelConfig(),
  updateConfig: (data: any) => apiClient.updateAiSearchShotModelConfig(data),
  testEmbedding: (config: AiSearchShotModelConfig) =>
    apiClient.testAiSearchShotEmbedding(config),
  testRerank: (config: AiSearchShotModelConfig) =>
    apiClient.testAiSearchShotRerank(config),
};

export default aiSearchShotSettingsService;
