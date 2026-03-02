export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

export const clamp01 = (v: number) => clamp(v, 0, 1);

export type TrimRange = {
  id: string;
  startMs: number;
  endMs: number;
};

export const mergeRanges = (ranges: TrimRange[]): TrimRange[] => {
  const ordered = [...ranges]
    .map((r) => ({ ...r, startMs: Math.floor(r.startMs), endMs: Math.floor(r.endMs) }))
    .filter((r) => Number.isFinite(r.startMs) && Number.isFinite(r.endMs) && r.endMs > r.startMs)
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);

  const merged: TrimRange[] = [];
  for (const r of ordered) {
    const last = merged[merged.length - 1];
    if (!last) {
      merged.push(r);
      continue;
    }
    if (r.startMs <= last.endMs) {
      last.endMs = Math.max(last.endMs, r.endMs);
    } else {
      merged.push(r);
    }
  }
  return merged;
};

export const findClosest = (values: number[], target: number, maxDelta: number) => {
  let best: number | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (const v of values) {
    const d = Math.abs(v - target);
    if (d <= maxDelta && d < bestDelta) {
      best = v;
      bestDelta = d;
    }
  }
  return best;
};

export const formatRulerLabel = (ms: number, majorStepMs: number) => {
  const safe = Math.max(0, Number.isFinite(ms) ? Math.round(ms) : 0);
  const milli = safe % 1000;
  const totalSec = Math.floor(safe / 1000);
  const sec = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const min = totalMin % 60;
  const hour = Math.floor(totalMin / 3600);
  const pad2 = (n: number) => String(n).padStart(2, "0");
  const pad3 = (n: number) => String(n).padStart(3, "0");

  if (majorStepMs < 1000) return `${pad2(hour)}:${pad2(min)}:${pad2(sec)}.${pad3(milli)}`;
  if (hour >= 1) return `${pad2(hour)}:${pad2(min)}:${pad2(sec)}`;
  return `${pad2(min)}:${pad2(sec)}`;
};

export type RulerTick = { ms: number; kind: "major" | "minor" };

const pickNiceMajorStepMs = (targetMs: number) => {
  const stepsSec = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  const targetSec = Math.max(0.001, targetMs / 1000);
  const picked = stepsSec.find((s) => s >= targetSec) ?? stepsSec[stepsSec.length - 1];
  return Math.max(1, Math.round(picked * 1000));
};

export const buildRulerTicks = (viewportStartMs: number, viewportMs: number, msPerPx: number) => {
  const viewportEndMs = viewportStartMs + viewportMs;
  const majorStepMs = pickNiceMajorStepMs(msPerPx * 100);
  const minorStepMs = Math.max(1, Math.round(majorStepMs / 5));

  const startMajor = Math.floor(viewportStartMs / majorStepMs) * majorStepMs;
  const ticks: RulerTick[] = [];
  for (let ms = startMajor; ms <= viewportEndMs + majorStepMs; ms += majorStepMs) {
    if (ms >= viewportStartMs - majorStepMs && ms <= viewportEndMs + majorStepMs) {
      ticks.push({ ms, kind: "major" });
    }
    for (let i = 1; i < 5; i += 1) {
      const m = ms + i * minorStepMs;
      if (m > viewportEndMs + minorStepMs) break;
      if (m >= viewportStartMs - minorStepMs && m <= viewportEndMs + minorStepMs) {
        ticks.push({ ms: m, kind: "minor" });
      }
    }
  }
  ticks.sort((a, b) => a.ms - b.ms || (a.kind === "major" ? -1 : 1));
  return { ticks, majorStepMs, minorStepMs };
};

