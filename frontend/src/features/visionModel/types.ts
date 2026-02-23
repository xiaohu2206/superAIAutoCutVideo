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
