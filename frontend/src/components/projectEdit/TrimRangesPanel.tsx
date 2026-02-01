import React, { useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader, Trash2 } from "lucide-react";
import type { TrimMode } from "../../hooks/useTrimVideoModal";
import type { TrimRange } from "./TrimTimeline";
import { formatMs, parseToMs } from "../../utils/timecode";

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

export type TrimRangesPanelProps = {
  mode: TrimMode;
  durationMs: number;
  ranges: TrimRange[];
  activeRangeId: string | null;
  submitting: boolean;
  progress: number;
  statusText: string;
  errorText: string;
  onSwitchMode: (mode: TrimMode) => void;
  onAddRange: () => void;
  onActiveRangeChange: (id: string | null) => void;
  onSeek: (ms: number) => void;
  onRangesChange: (next: TrimRange[]) => void;
};

type DraftValue = { start: string; end: string };
type DraftMap = Record<string, DraftValue>;

const buildDrafts = (ranges: TrimRange[]): DraftMap =>
  ranges.reduce<DraftMap>((acc, r) => {
    acc[r.id] = { start: formatMs(r.startMs), end: formatMs(r.endMs) };
    return acc;
  }, {});

export const TrimRangesPanel: React.FC<TrimRangesPanelProps> = ({
  mode,
  durationMs,
  ranges,
  activeRangeId,
  submitting,
  progress,
  statusText,
  errorText,
  onSwitchMode,
  onAddRange,
  onActiveRangeChange,
  onSeek,
  onRangesChange,
}) => {
  const initialDrafts = useMemo(() => buildDrafts(ranges), [ranges]);
  const [drafts, setDrafts] = useState<DraftMap>(initialDrafts);

  useEffect(() => {
    setDrafts(buildDrafts(ranges));
  }, [ranges]);

  return (
    <div className="space-y-3">
      {errorText && (
        <div className="flex items-start gap-3 bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm border border-red-100">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span>{errorText}</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-gray-900">模式</div>
        <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
          <button
            type="button"
            disabled={submitting}
            onClick={() => onSwitchMode("keep")}
            className={`px-3 py-1.5 text-sm ${mode === "keep" ? "bg-violet-600 text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
          >
            保留区间
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => onSwitchMode("delete")}
            className={`px-3 py-1.5 text-sm ${mode === "delete" ? "bg-violet-600 text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
          >
            删除区间
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-gray-900">区间</div>
        <button
          type="button"
          onClick={onAddRange}
          disabled={submitting || durationMs <= 0}
          className="px-3 py-1.5 text-sm bg-gray-100 text-gray-800 rounded-lg hover:bg-gray-200 disabled:opacity-50"
        >
          添加区间
        </button>
      </div>

      <div className="max-h-[340px] overflow-auto border border-gray-200 rounded-lg">
        {ranges.length === 0 ? (
          <div className="p-3 text-xs text-gray-500">暂无区间。可在时间轴拖拽创建。</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {ranges.map((r, idx) => (
              <div
                key={r.id}
                className={`p-3 ${r.id === activeRangeId ? "bg-violet-50" : "bg-white"}`}
                onClick={() => {
                  onActiveRangeChange(r.id);
                  onSeek(r.startMs);
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="text-xs text-gray-500">#{idx + 1}</div>
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={(e) => {
                      e.stopPropagation();
                      onRangesChange(ranges.filter((x) => x.id !== r.id));
                      if (activeRangeId === r.id) onActiveRangeChange(null);
                    }}
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-red-200 text-red-700 bg-red-50 hover:bg-red-100 disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    删除
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <div className="text-[11px] text-gray-500 mb-1">开始</div>
                    <input
                      disabled={submitting}
                      value={drafts[r.id]?.start ?? formatMs(r.startMs)}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [r.id]: { start: e.target.value, end: prev[r.id]?.end ?? formatMs(r.endMs) },
                        }))
                      }
                      onBlur={(e) => {
                        const parsed = parseToMs(e.target.value);
                        if (parsed === null) {
                          setDrafts((prev) => ({
                            ...prev,
                            [r.id]: { start: formatMs(r.startMs), end: prev[r.id]?.end ?? formatMs(r.endMs) },
                          }));
                          return;
                        }
                        const nextStart = clamp(parsed, 0, r.endMs - 1);
                        onRangesChange(
                          ranges.map((x) =>
                            x.id === r.id ? { ...x, startMs: nextStart } : x
                          )
                        );
                        setDrafts((prev) => ({
                          ...prev,
                          [r.id]: { start: formatMs(nextStart), end: prev[r.id]?.end ?? formatMs(r.endMs) },
                        }));
                      }}
                      className="w-full text-xs font-mono px-2 py-1.5 rounded border border-gray-200"
                    />
                  </div>
                  <div>
                    <div className="text-[11px] text-gray-500 mb-1">结束</div>
                    <input
                      disabled={submitting}
                      value={drafts[r.id]?.end ?? formatMs(r.endMs)}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [r.id]: { start: prev[r.id]?.start ?? formatMs(r.startMs), end: e.target.value },
                        }))
                      }
                      onBlur={(e) => {
                        const parsed = parseToMs(e.target.value);
                        if (parsed === null) {
                          setDrafts((prev) => ({
                            ...prev,
                            [r.id]: { start: prev[r.id]?.start ?? formatMs(r.startMs), end: formatMs(r.endMs) },
                          }));
                          return;
                        }
                        const nextEnd = clamp(parsed, r.startMs + 1, durationMs);
                        onRangesChange(
                          ranges.map((x) =>
                            x.id === r.id ? { ...x, endMs: nextEnd } : x
                          )
                        );
                        setDrafts((prev) => ({
                          ...prev,
                          [r.id]: { start: prev[r.id]?.start ?? formatMs(r.startMs), end: formatMs(nextEnd) },
                        }));
                      }}
                      className="w-full text-xs font-mono px-2 py-1.5 rounded border border-gray-200"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {submitting && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-600">
            <span>{statusText || "处理中"}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full h-2 bg-gray-200 rounded">
            <div className="h-2 bg-violet-600 rounded transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-[11px] text-gray-500 flex items-center gap-2">
            <Loader className="h-3.5 w-3.5 animate-spin" />
            处理中请勿关闭
          </div>
        </div>
      )}
    </div>
  );
};
