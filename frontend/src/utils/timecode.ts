const pad2 = (n: number) => String(n).padStart(2, "0");
const pad3 = (n: number) => String(n).padStart(3, "0");

export const formatMs = (ms: number) => {
  const safe = Math.max(0, Number.isFinite(ms) ? Math.round(ms) : 0);
  const milli = safe % 1000;
  const totalSec = Math.floor(safe / 1000);
  const sec = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const min = totalMin % 60;
  const hour = Math.floor(totalMin / 60);
  return `${pad2(hour)}:${pad2(min)}:${pad2(sec)}.${pad3(milli)}`;
};

export const parseToMs = (value: string): number | null => {
  const s = String(value || "").trim();
  if (!s) return null;
  if (/^\d+(\.\d+)?$/.test(s)) {
    const sec = Number(s);
    if (!Number.isFinite(sec)) return null;
    return Math.round(sec * 1000);
  }
  const parts = s.split(":");
  if (parts.length < 2 || parts.length > 3) return null;
  const [a, b, c] = parts.length === 2 ? ["0", parts[0], parts[1]] : parts;
  const [secStr, msStr] = String(c).split(".");
  const hh = Number(a);
  const mm = Number(b);
  const ss = Number(secStr);
  const mmm = msStr ? Number(msStr.padEnd(3, "0").slice(0, 3)) : 0;
  if (![hh, mm, ss, mmm].every((x) => Number.isFinite(x))) return null;
  return Math.max(0, Math.round(hh * 3600000 + mm * 60000 + ss * 1000 + mmm));
};

