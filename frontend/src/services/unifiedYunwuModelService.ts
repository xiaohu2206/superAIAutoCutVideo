import { apiClient } from "./clients";

export const unifiedYunwuModelService = {
  get: () => apiClient.getUnifiedYunwuModels(),
  update: (body: Record<string, unknown>) => apiClient.updateUnifiedYunwuModels(body),
  getPlatforms: () => apiClient.getUnifiedYunwuPlatforms(),
  test: () => apiClient.testUnifiedYunwuModels(),
  forceSync: () => apiClient.forceSyncUnifiedYunwuModels(),
};

export default unifiedYunwuModelService;
