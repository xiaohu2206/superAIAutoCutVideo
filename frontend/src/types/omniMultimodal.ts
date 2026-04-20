/** Omni 管线 Step2 多模态 JSON（与后端 shots_multimodal.json 对齐的子集类型） */

export interface OmniMultimodalShotVisual {
  brief?: string;
  desc?: string;
  action?: string;
  emotion?: string;
}

export interface OmniMultimodalShot {
  shot_id?: number;
  start: number;
  end: number;
  duration?: number;
  /** Step2 占位：pending / error；完成段通常无此字段 */
  omni_step2_status?: string;
  subtitle_full_text?: string;
  subtitle?: { full_text?: string; segments?: unknown[] };
  visual?: OmniMultimodalShotVisual;
  summary?: string;
  embedding?: number[];
}

export interface OmniMultimodalResult {
  shots?: OmniMultimodalShot[];
  total_shots?: number;
  total_duration?: number;
  omni_pipeline_meta?: Record<string, unknown>;
  [key: string]: unknown;
}
