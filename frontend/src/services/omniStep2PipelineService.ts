import { apiClient } from "./clients";

export const omniStep2PipelineService = {
  get: () => apiClient.getOmniStep2PipelineConfig(),
  update: (body: Record<string, unknown>) => apiClient.updateOmniStep2PipelineConfig(body),
};

export default omniStep2PipelineService;
