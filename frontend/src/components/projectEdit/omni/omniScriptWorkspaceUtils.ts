import type { OmniSelectableShot } from "../../../types/omniMultimodal";
import type { ScriptSegment, VideoScript } from "../../../types/project";

export const pad2 = (n: number) => String(n).padStart(2, "0");

export const secondsToTime = (seconds: number) => {
  const totalSec = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const sec = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const min = totalMin % 60;
  const hour = Math.floor(totalMin / 60);
  return `${pad2(hour)}:${pad2(min)}:${pad2(sec)}`;
};

export const durationLabel = (start?: number, end?: number) => {
  const value = segmentDurationSec(start, end);
  return `${value.toFixed(2)}s`;
};

export const MIN_SEGMENT_DURATION = 0.1;
export const DURATION_SLIDER_STEP = 0.1;
export const DURATION_ADJUST_STEPS = [-1, -0.5, -0.1, 0.1, 0.5, 1] as const;
const DEFAULT_MAX_SEGMENT_DURATION = 300;

export const segmentDurationSec = (start?: number, end?: number) => {
  const s = Math.max(0, Number(start) || 0);
  const e = Math.max(s, Number(end) || s);
  return Math.max(MIN_SEGMENT_DURATION, e - s);
};

export const roundSegmentTime = (t: number) => Math.round(Math.max(0, t) * 10) / 10;

export const getVideoTimeMax = (videoDuration?: number) => {
  if (videoDuration && videoDuration > 0) return videoDuration;
  return DEFAULT_MAX_SEGMENT_DURATION;
};

export const clampSegmentTimes = (
  start: number,
  end: number,
  videoDuration?: number
): { start_time: number; end_time: number } => {
  const maxT = getVideoTimeMax(videoDuration);
  let s = roundSegmentTime(start);
  let e = roundSegmentTime(end);
  s = Math.max(0, Math.min(s, maxT - MIN_SEGMENT_DURATION));
  e = Math.max(s + MIN_SEGMENT_DURATION, Math.min(e, maxT));
  if (e - s < MIN_SEGMENT_DURATION) {
    e = Math.min(maxT, s + MIN_SEGMENT_DURATION);
    if (e - s < MIN_SEGMENT_DURATION) {
      s = Math.max(0, e - MIN_SEGMENT_DURATION);
    }
  }
  return { start_time: s, end_time: e };
};

export const getStartTimeBounds = (endTime: number, videoDuration?: number) => {
  const end = Math.max(MIN_SEGMENT_DURATION, Number(endTime) || MIN_SEGMENT_DURATION);
  const maxT = getVideoTimeMax(videoDuration);
  return { min: 0, max: Math.max(0, Math.min(end - MIN_SEGMENT_DURATION, maxT - MIN_SEGMENT_DURATION)) };
};

export const getEndTimeBounds = (startTime: number, videoDuration?: number) => {
  const start = Math.max(0, Number(startTime) || 0);
  const maxT = getVideoTimeMax(videoDuration);
  return {
    min: Math.min(maxT, start + MIN_SEGMENT_DURATION),
    max: maxT,
  };
};

export const isOriginalAudio = (segment: ScriptSegment) => {
  const raw = segment.OST;
  if (typeof raw === "boolean") return raw;
  return String(raw ?? "").trim() === "1";
};

export async function computeTtsTextHash(text: string): Promise<string> {
  const data = new TextEncoder().encode((text || "").trim());
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export type SegmentTtsFields = Pick<
  ScriptSegment,
  "tts_audio_path" | "tts_audio_duration" | "tts_source" | "tts_text_hash" | "tts_updated_at"
>;

export function pickSegmentTtsFields(seg: Partial<ScriptSegment>): SegmentTtsFields {
  const out: SegmentTtsFields = {};
  if (seg.tts_audio_path != null) out.tts_audio_path = seg.tts_audio_path;
  if (seg.tts_audio_duration != null) out.tts_audio_duration = seg.tts_audio_duration;
  if (seg.tts_source != null) out.tts_source = seg.tts_source;
  if (seg.tts_text_hash != null) out.tts_text_hash = seg.tts_text_hash;
  if (seg.tts_updated_at != null) out.tts_updated_at = seg.tts_updated_at;
  return out;
}

export function mergeSegmentTtsIntoScript(
  script: VideoScript,
  index: number,
  fields: SegmentTtsFields
): VideoScript {
  const segments = (script.segments || []).map((seg, i) => (i === index ? { ...seg, ...fields } : seg));
  return { ...script, segments };
}

export const isValidSegmentTts = (segment: ScriptSegment, currentTextHash?: string) => {
  if (isOriginalAudio(segment)) return false;
  const path = String(segment.tts_audio_path || "").trim();
  if (!path) return false;
  const stored = String(segment.tts_text_hash || "").trim();
  if (!stored) return false;
  if (!currentTextHash) return true;
  return stored === currentTextHash;
};

export const isStaleSegmentTts = (segment: ScriptSegment, currentTextHash?: string) => {
  if (isOriginalAudio(segment) || !segment.tts_audio_path) return false;
  if (!currentTextHash) return false;
  return String(segment.tts_text_hash || "") !== currentTextHash;
};

/** 有有效配音时以配音时长为准，否则用镜头 end_time */
export const getSegmentPlayEndTime = (
  segment: ScriptSegment,
  currentTextHash?: string,
  videoDuration?: number
) => {
  const start = Math.max(0, Number(segment.start_time) || 0);
  if (isOriginalAudio(segment)) {
    return Math.max(start, Number(segment.end_time) || start);
  }
  if (isValidSegmentTts(segment, currentTextHash)) {
    const dubDur = Number(segment.tts_audio_duration) || 0;
    if (dubDur > 0) {
      let end = start + dubDur;
      if (videoDuration && videoDuration > 0) {
        end = Math.min(end, videoDuration);
      }
      return Math.max(start, end);
    }
  }
  return Math.max(start, Number(segment.end_time) || start);
};

export const ttsStatusLabel = (segment: ScriptSegment, currentTextHash?: string) => {
  if (isOriginalAudio(segment)) return "原片播放";
  if (isStaleSegmentTts(segment, currentTextHash)) return "需重新配音";
  if (isValidSegmentTts(segment, currentTextHash)) {
    if (segment.tts_source === "manual") return "单条配音";
    if (segment.tts_source === "bulk") return "批量配音";
    return "已配音";
  }
  if (segment.tts_audio_path) return "需重新配音";
  return "未配音";
};

export const visualText = (shot?: OmniSelectableShot | null) => {
  if (!shot) return "";
  const parts = [shot.visual?.brief, shot.visual?.action, shot.visual?.emotion].filter(Boolean);
  return parts.join(" / ");
};

export const scoreText = (shot: OmniSelectableShot) => {
  const score = shot.final_score ?? shot.score;
  return typeof score === "number" ? score.toFixed(4) : "-";
};

export const isPlaybackOriginalLabel = (text?: string) =>
  /^播放原片\d*$/.test(String(text ?? "").trim());

export const makeScriptJson = (script: VideoScript) => JSON.stringify(script, null, 2);

/** 同步时忽略仅由保存时间戳引起的差异，避免自动保存后整表闪动 */
export function normalizeOmniScriptForCompare(script: VideoScript): VideoScript {
  const metadata = script.metadata ? { ...script.metadata } : undefined;
  if (metadata) {
    delete metadata.updated_at;
    if (Object.keys(metadata).length === 0) {
      return { ...script, metadata: undefined };
    }
  }
  return metadata ? { ...script, metadata } : script;
}

export function areOmniScriptsEquivalent(a: VideoScript, b: VideoScript): boolean {
  return (
    JSON.stringify(normalizeOmniScriptForCompare(a)) === JSON.stringify(normalizeOmniScriptForCompare(b))
  );
}

export function getOmniSegmentsTextSignature(segments: ScriptSegment[]): string {
  return segments
    .map((s, i) => `${i}|${isOriginalAudio(s) ? "ost" : (s.text ?? "").trim()}`)
    .join("\x1e");
}

export const SCRIPT_LIST_GRID =
  "grid grid-cols-[36px_108px_84px_minmax(140px,1fr)_88px_minmax(168px,auto)] gap-x-2";

export const ROW_SELECTED =
  "bg-blue-50 ring-1 ring-inset ring-blue-200 dark:bg-blue-950/50 dark:ring-blue-500/40";

export const ROW_IDLE = "hover:bg-gray-50 dark:hover:bg-gray-800/50";

export const PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4, 5, 7, 10];
