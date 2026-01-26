export type ApiOk<T> = {
  success: boolean;
  data?: T;
  message?: string;
  [key: string]: any;
};

export type Qwen3TtsModelStatus = {
  key: string;
  path: string;
  exists: boolean;
  valid: boolean;
  missing: string[];
};

export type Qwen3TtsVoiceStatus = "uploaded" | "cloning" | "ready" | "failed" | string;

export type Qwen3TtsVoice = {
  id: string;
  name: string;
  model_key: string;
  language: string;
  ref_audio_path: string;
  ref_audio_url?: string | null;
  ref_text?: string | null;
  instruct?: string | null;
  x_vector_only_mode: boolean;
  status: Qwen3TtsVoiceStatus;
  progress: number;
  last_error?: string | null;
  meta?: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type Qwen3TtsDownloadProvider = "hf" | "modelscope";

export type Qwen3TtsUploadVoiceInput = {
  file: File;
  name?: string;
  model_key: string;
  language: string;
  ref_text?: string;
  instruct?: string;
  x_vector_only_mode: boolean;
};

export type Qwen3TtsPatchVoiceInput = Partial<Pick<
  Qwen3TtsVoice,
  "name" | "model_key" | "language" | "ref_text" | "instruct" | "x_vector_only_mode"
>>;

