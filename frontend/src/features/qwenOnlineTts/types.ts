export type QwenOnlineTtsVoiceStatus = "cloning" | "ready" | "failed" | string;

export type QwenOnlineTtsVoice = {
  id: string;
  name: string;
  model: string;
  voice?: string | null;
  ref_audio_url?: string | null;
  ref_text?: string | null;
  status: QwenOnlineTtsVoiceStatus;
  progress: number;
  last_error?: string | null;
  meta?: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type QwenOnlineTtsUploadVoiceInput = {
  file: File;
  name?: string;
  model?: string;
  ref_text?: string;
};

export type QwenOnlineTtsPatchVoiceInput = Partial<
  Pick<QwenOnlineTtsVoice, "name" | "ref_text" | "model">
>;
