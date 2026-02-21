
export interface Scene {
  id: number;
  start_frame: number;
  end_frame: number;
  start_time: number;
  end_time: number;
  time_range: string;
  subtitle: string;
}

export interface SceneResult {
  scenes: Scene[];
  fps: number;
  total_frames: number;
  created_at: string;
}
