export type ApiOk<T> = {
  success: boolean;
  data?: T;
  message?: string;
};

export type FunAsrDownloadProvider = "modelscope" | "hf";

export type FunAsrModelStatus = {
  key: string;
  path: string;
  exists: boolean;
  valid: boolean;
  missing?: string[];
  display_name?: string;
  languages?: string[];
  sources?: Record<string, string>;
  description?: string;
};

export type FunAsrDownloadTask = {
  key: string;
  provider: FunAsrDownloadProvider;
  status: string;
  phase?: string;
  progress?: number;
  message?: string;
  downloaded_bytes?: number;
  total_bytes?: number | null;
};

export type FunAsrAccelerationStatus = {
  acceleration: Record<string, any>;
  runtime: Record<string, any>;
};

export type FunAsrValidateResult = {
  key: string;
  path: string;
  valid: boolean;
  missing: string[];
};

export type FunAsrTestResult = {
  success: boolean;
  text?: string;
  utterances?: { start_time: number; end_time: number; text: string }[];
  audio_path?: string;
  audio_meta?: Record<string, any>;
};

