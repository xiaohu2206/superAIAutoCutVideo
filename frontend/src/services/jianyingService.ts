import { apiClient } from "./clients";

export const jianyingService = {
  getDraftPath: () => apiClient.getJianyingDraftPath(),
  setDraftPath: (path: string) => apiClient.updateJianyingDraftPath(path),
  detectDraftPath: () => apiClient.detectJianyingDraftPath(),
};

export default jianyingService;

