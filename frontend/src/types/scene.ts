
export interface Scene {
  id: number;
  start_frame: number;
  end_frame: number;
  start_time: number;
  end_time: number;
  time_range: string;
  subtitle: string;
  vision?: string | VisionSegment[];
  vision_status?: "ok" | "empty" | "no_frame" | "error" | "infer_timeout";
  vision_analyzed?: boolean;
}

export interface VisionStructured {
  desc?: unknown;
  objects?: unknown;
  action?: unknown;
  scene?: unknown;
  emotion?: unknown;
}

export interface VisionSegment {
  start_time: number;
  end_time: number;
  status: "ok" | "empty" | "no_frame" | "error";
  text?: string | null;
  structured?: VisionStructured;
  error?: string | null;
  frame_error?: any;
}

export interface SceneResult {
  scenes: Scene[];
  fps: number;
  total_frames: number;
  created_at: string;
}
