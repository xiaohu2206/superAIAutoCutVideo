import { apiClient } from "./clients";

export const videoModelService = {
  getConfigs: () => apiClient.getVideoAnalysisConfigs(),
  updateConfig: (configId: string, data: any) => apiClient.updateVideoAnalysisConfig(configId, data),
  testConnection: (configId: string) => apiClient.testVideoAnalysisConfig(configId),
  testActiveConnection: () => apiClient.testActiveVideoAnalysisConfig(),
};

export default videoModelService;