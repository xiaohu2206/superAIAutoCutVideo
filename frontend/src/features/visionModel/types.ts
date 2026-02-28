export type ApiOk<T> = {
  success: boolean;
  data?: T;
  message?: string;
};

export type MoondreamModelStatus = {
  key: string;
  path: string;
  exists: boolean;
  valid: boolean;
  missing?: string[];
  display_name?: string;
  description?: string;
};

export type MoondreamTestResult = {
  text: string;
};

export type MoondreamDownloadProvider = "modelscope" | "hf";

export type MoondreamDownloadTask = {
  key: string;
  provider: string;
  status: "running" | "completed" | "failed" | "cancelled";
  progress: number;
  message?: string;
  downloaded_bytes?: number;
  total_bytes?: number;
};

export type MoondreamInferenceSettings = {
  inference_device: string;
  n_gpu_layers: number | null;
};

export type MoondreamResolvedRuntime = {
  device: string;
  main_gpu: number | null;
  n_gpu_layers: number;
};

export type MoondreamRuntimeStatus = {
  loaded: boolean;
  model_dir?: string | null;
  device?: string | null;
  n_gpu_layers?: number | null;
  main_gpu?: number | null;
};

export type MoondreamAccelerationStatusData = {
  acceleration: any;
  settings: MoondreamInferenceSettings;
  resolved: MoondreamResolvedRuntime;
  resolved_meta?: any;
  runtime: MoondreamRuntimeStatus;
};

export type MoondreamSettingsResponseData = {
  settings: MoondreamInferenceSettings;
  resolved: MoondreamResolvedRuntime;
  meta?: any;
};
