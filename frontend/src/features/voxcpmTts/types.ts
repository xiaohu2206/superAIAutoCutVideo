export type ApiOk<T> = {
  success: boolean;
  data?: T;
  message?: string;
  [key: string]: any;
};

export type VoxcpmTtsModelStatus = {
  key: string;
  path: string;
  exists: boolean;
  valid: boolean;
  missing: string[];
  model_type: string;
  size: string;
  display_names: string[];
  sources?: Record<string, string>;
};

export type VoxcpmTtsVoiceStatus = "uploaded" | "cloning" | "ready" | "failed" | string;

export type VoxcpmTtsVoice = {
  id: string;
  name: string;
  kind: string;
  model_key: string;
  language: string;
  ref_audio_path?: string | null;
  ref_audio_url?: string | null;
  ref_text?: string | null;
  status: VoxcpmTtsVoiceStatus;
  progress: number;
  last_error?: string | null;
  meta?: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type VoxcpmTtsDownloadProvider = "modelscope";

export type VoxcpmTtsDownloadTask = {
  key: string;
  provider: VoxcpmTtsDownloadProvider;
  progress?: number;
  message?: string;
  phase?: string;
  status?: string;
  type?: string;
  downloaded_bytes?: number;
  total_bytes?: number | null;
  [key: string]: any;
};

export type VoxcpmTtsUploadVoiceInput = {
  file: File;
  name?: string;
  model_key: string;
  language: string;
  ref_text?: string;
};

export type VoxcpmTtsPatchVoiceInput = Partial<Pick<
  VoxcpmTtsVoice,
  "name" | "model_key" | "language" | "ref_text"
>>;

export type VoxcpmTtsRuntimeStatus = {
  loaded: boolean;
  model_key?: string | null;
  model_path?: string | null;
  device?: string;
  precision?: string;
  last_device_error?: string | null;
};
