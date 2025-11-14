import { apiClient } from "./clients";

export const contentModelService = {
  getConfigs: () => apiClient.getContentGenerationConfigs(),
  updateConfig: (configId: string, data: any) => apiClient.updateContentGenerationConfig(configId, data),
  testConnection: (configId: string) => apiClient.testContentGenerationConfig(configId),
};

export default contentModelService;