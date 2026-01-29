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
  model_type: "base" | "custom_voice" | "voice_design" | string;
  size: string;
  display_names: string[];
  sources?: Record<string, string>;
};

export type Qwen3TtsVoiceStatus = "uploaded" | "cloning" | "ready" | "failed" | string;

export type Qwen3TtsVoice = {
  id: string;
  name: string;
  kind: "clone" | "custom_role" | "design_clone" | string;
  model_key: string;
  language: string;
  speaker?: string | null;
  ref_audio_path?: string | null;
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

export type Qwen3TtsCustomRoleCreateInput = {
  name: string;
  model_key: string;
  language: string;
  speaker: string;
  instruct?: string;
};

export type Qwen3TtsDesignCloneCreateInput = {
  name: string;
  model_key: string;
  voice_design_model_key: string;
  language: string;
  text: string;
  instruct: string;
};

export type Qwen3TtsPatchVoiceInput = Partial<Pick<
  Qwen3TtsVoice,
  "name" | "model_key" | "language" | "ref_text" | "instruct" | "x_vector_only_mode" | "speaker"
>>;

