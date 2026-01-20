import type { ScriptLengthOption } from "../../../types/project";

export const DEFAULT_SCRIPT_LENGTH: ScriptLengthOption = "30～40条";

export const SCRIPT_LENGTH_OPTIONS: Array<{
  value: ScriptLengthOption;
  title: string;
  subtitle: string;
}> = [
  { value: "15～20条", title: "15～20 条", subtitle: "预计最少 2 次模型调用" },
  { value: "30～40条", title: "30～40 条", subtitle: "预计最少 4 次模型调用" },
  { value: "40～60条", title: "40～60 条", subtitle: "预计最少 5 次模型调用" },
  { value: "60～80条", title: "60～80 条", subtitle: "预计最少 6 次模型调用" },
  { value: "80～100条", title: "80～100 条", subtitle: "预计最少 7 次模型调用" },
];

export const CUSTOM_SCRIPT_LENGTH_MIN = 5;
export const CUSTOM_SCRIPT_LENGTH_MAX = 200;
export const ORIGINAL_RATIO_MIN = 10;
export const ORIGINAL_RATIO_MAX = 90;
export const DEFAULT_ORIGINAL_RATIO = 70;

export const normalizeRangeSeparators = (value: string) =>
  value
    .replace(/\s+/g, "")
    .replace("~", "～")
    .replace("-", "～")
    .replace("—", "～")
    .replace("–", "～");

export const parseRangeFromString = (value: string): { min: number; max: number } | null => {
  const cleaned = normalizeRangeSeparators(value);
  const match = cleaned.match(/(\d+)\D+(\d+)/);
  if (!match) return null;
  const a = Number(match[1]);
  const b = Number(match[2]);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const min = Math.min(a, b);
  const max = Math.max(a, b);
  if (min <= 0 || max <= 0) return null;
  return { min, max };
};

export const computeCustomRange = (target: number): { min: number; max: number } | null => {
  if (!Number.isFinite(target)) return null;
  const safe = Math.max(CUSTOM_SCRIPT_LENGTH_MIN, Math.min(CUSTOM_SCRIPT_LENGTH_MAX, Math.round(target)));
  if (safe <= 0) return null;
  const min = Math.max(CUSTOM_SCRIPT_LENGTH_MIN, Math.floor(safe * 0.8));
  const max = Math.max(min, Math.ceil(safe * 1.2));
  return { min, max: Math.min(CUSTOM_SCRIPT_LENGTH_MAX, max) };
};

export const formatRangeValue = (range: { min: number; max: number }): ScriptLengthOption =>
  `${range.min}～${range.max}条`;

export const formatRangeTitle = (range: { min: number; max: number }) => `${range.min}～${range.max} 条`;

export const estimateCallsForDisplay = (maxCount: number) => {
  if (maxCount <= 20) return 2;
  if (maxCount <= 40) return 4;
  if (maxCount <= 60) return 5;
  if (maxCount <= 80) return 6;
  if (maxCount <= 100) return 7;
  return 7 + Math.ceil((maxCount - 100) / 20);
};

export const normalizeScriptLengthString = (value: string): ScriptLengthOption | null => {
  const cleaned = normalizeRangeSeparators(value);
  if (!cleaned) return null;
  const presetRange = parseRangeFromString(cleaned);
  if (presetRange) return formatRangeValue(presetRange);
  const numMatch = cleaned.match(/(\d+)/);
  if (numMatch) {
    const range = computeCustomRange(Number(numMatch[1]));
    return range ? formatRangeValue(range) : null;
  }
  return null;
};

export const normalizeScriptLength = (value: unknown): ScriptLengthOption => {
  const v = typeof value === "string" ? value : "";
  const allowed = new Set<ScriptLengthOption>([
    "15～20条",
    "30～40条",
    "40～60条",
    "60～80条",
    "80～100条",
  ]);
  if (allowed.has(v as ScriptLengthOption)) return v as ScriptLengthOption;
  if (v === "短篇") return "15～20条";
  if (v === "中偏") return "40～60条";
  if (v === "长偏") return "80～100条";
  const normalized = normalizeScriptLengthString(v);
  if (normalized) return normalized;
  return DEFAULT_SCRIPT_LENGTH;
};

export const normalizeOriginalRatio = (value: unknown): number => {
  const num = Number(value);
  if (!Number.isFinite(num)) return DEFAULT_ORIGINAL_RATIO;
  const rounded = Math.round(num);
  return Math.min(ORIGINAL_RATIO_MAX, Math.max(ORIGINAL_RATIO_MIN, rounded));
};
