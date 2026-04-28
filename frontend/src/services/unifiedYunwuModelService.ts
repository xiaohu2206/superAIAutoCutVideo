import { apiClient } from "./clients";

export const unifiedYunwuModelService = {
  get: () => apiClient.getUnifiedYunwuModels(),
  update: (body: Record<string, unknown>) => apiClient.updateUnifiedYunwuModels(body),
  getPlatforms: () => apiClient.getUnifiedYunwuPlatforms(),
  test: () => apiClient.testUnifiedYunwuModels(),
};

export default unifiedYunwuModelService;
