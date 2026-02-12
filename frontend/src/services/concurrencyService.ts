import { apiClient, ApiResponse } from "./clients";

export interface ScopeConcurrencyConfig {
  max_workers: number;
  override?: boolean;
}

export interface EffectiveConcurrencyConfig {
  max_workers: number;
  source: string;
}

export interface GenerateConcurrencyData {
  config: {
    generate_video: ScopeConcurrencyConfig;
    generate_jianying_draft: ScopeConcurrencyConfig;
    allow_same_project_parallel: boolean;
  };
  effective: {
    generate_video: EffectiveConcurrencyConfig;
    generate_jianying_draft: EffectiveConcurrencyConfig;
  };
}

export interface UpdateGenerateConcurrencyRequest {
  generate_video?: Partial<ScopeConcurrencyConfig>;
  generate_jianying_draft?: Partial<ScopeConcurrencyConfig>;
  allow_same_project_parallel?: boolean;
}

export const concurrencyService = {
  getConcurrency: () => apiClient.get<ApiResponse<GenerateConcurrencyData>>("/api/generate/concurrency"),
  updateConcurrency: (data: UpdateGenerateConcurrencyRequest) => apiClient.put<ApiResponse<GenerateConcurrencyData>>("/api/generate/concurrency", data),
  resizeConcurrency: (scopes?: string[]) => apiClient.post<ApiResponse<any>>("/api/generate/concurrency/resize", { scopes }),
};

export default concurrencyService;
