import { apiClient } from "./clients";

export const storageService = {
  getSettings: () => apiClient.getStorageSettings(),
  updateSettings: (uploadsRoot: string, migrate?: boolean) =>
    apiClient.updateStorageSettings({ uploads_root: uploadsRoot, migrate }),
};

export default storageService;
