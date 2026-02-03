import { Minus, Plus, RotateCcw } from "lucide-react";
import React from "react";

import { clamp } from "./timelineMath";

export type TimelineToolbarProps = {
  disabled: boolean;
  snapEnabled: boolean;
  msPerPxText: string;
  viewportPerScreenText: string;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
  onToggleSnap: () => void;
  onAddRange: () => void;
};

export const TrimTimelineToolbar: React.FC<TimelineToolbarProps> = ({
  disabled,
  snapEnabled,
  msPerPxText,
  viewportPerScreenText,
  onZoomOut,
  onZoomIn,
  onFit,
  onToggleSnap,
  onAddRange,
}) => {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onZoomOut}
          disabled={disabled}
          className="inline-flex items-center justify-center h-9 w-9 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50"
          aria-label="缩小"
        >
          <Minus className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onZoomIn}
          disabled={disabled}
          className="inline-flex items-center justify-center h-9 w-9 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50"
          aria-label="放大"
        >
          <Plus className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onFit}
          disabled={disabled}
          className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-50"
        >
          <RotateCcw className="h-4 w-4" />
          <span className="text-sm">Fit</span>
        </button>
        <button
          type="button"
          onClick={onToggleSnap}
          disabled={disabled}
          className={`inline-flex items-center gap-2 h-9 px-3 rounded-lg border ${snapEnabled ? "border-violet-200 bg-violet-50 text-violet-700" : "border-gray-200 bg-white text-gray-700"} hover:bg-gray-50 disabled:opacity-50`}
        >
          <span className="text-sm">吸附</span>
          <span className={`text-xs ${snapEnabled ? "text-violet-700" : "text-gray-500"}`}>{snapEnabled ? "开" : "关"}</span>
        </button>
        <button
          type="button"
          onClick={onAddRange}
          disabled={disabled}
          className="inline-flex items-center h-9 px-3 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
        >
          <span className="text-sm">添加区间</span>
        </button>
      </div>
      <div className="text-xs text-gray-600 font-mono">
        {msPerPxText} · {viewportPerScreenText}
      </div>
    </div>
  );
};

export type TimelineOverviewProps = {
  overviewRef: React.RefObject<HTMLDivElement>;
  disabled: boolean;
  durationMs: number;
  viewportStartMs: number;
  viewportMs: number;
  currentMs: number;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onWindowPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onWindowPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
  onWindowPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void;
};

export const TrimTimelineOverview: React.FC<TimelineOverviewProps> = ({
  overviewRef,
  disabled,
  durationMs,
  viewportStartMs,
  viewportMs,
  currentMs,
  onPointerDown,
  onWindowPointerDown,
  onWindowPointerMove,
  onWindowPointerUp,
}) => {
  return (
    <div
      ref={overviewRef}
      className={`relative h-7 rounded-md border ${disabled ? "bg-gray-100 border-gray-200" : "bg-gray-50 border-gray-200"} select-none`}
      onPointerDown={onPointerDown}
    >
      <div
        className="absolute top-0 bottom-0 rounded bg-violet-500/25 border border-violet-300 cursor-grab active:cursor-grabbing"
        style={{
          left: `${durationMs > 0 ? (viewportStartMs / durationMs) * 100 : 0}%`,
          width: `${durationMs > 0 ? (viewportMs / durationMs) * 100 : 100}%`,
        }}
        onPointerDown={onWindowPointerDown}
        onPointerMove={onWindowPointerMove}
        onPointerUp={onWindowPointerUp}
      />
      <div
        className="absolute top-0 bottom-0 w-[2px] bg-red-500"
        style={{ left: `${durationMs > 0 ? (clamp(currentMs, 0, durationMs) / durationMs) * 100 : 0}%` }}
      />
    </div>
  );
};

export type TimelineRulerTick = { ms: number; kind: "major" | "minor" };

export type TimelineRulerProps = {
  rulerRef: React.RefObject<HTMLDivElement>;
  ticks: TimelineRulerTick[];
  ratioFromMs: (ms: number) => number;
  formatLabel: (ms: number) => string;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
};

export const TrimTimelineRuler: React.FC<TimelineRulerProps> = ({
  rulerRef,
  ticks,
  ratioFromMs,
  formatLabel,
  onPointerDown,
}) => {
  return (
    <div
      ref={rulerRef}
      className="relative h-6 rounded-md border border-gray-200 bg-white select-none overflow-hidden"
      onPointerDown={onPointerDown}
    >
      {ticks.map((t) => {
        const ratio = ratioFromMs(t.ms);
        const left = ratio * 100;
        if (left < -2 || left > 102) return null;
        const isMajor = t.kind === "major";
        return (
          <div key={`${t.kind}_${t.ms}`} className="absolute top-0 bottom-0" style={{ left: `${left}%` }}>
            <div className={`absolute bottom-0 w-px ${isMajor ? "h-6 bg-gray-300" : "h-3 bg-gray-200"}`} />
            {isMajor && (
              <div className="absolute top-0 left-1 text-[10px] text-gray-600 font-mono">{formatLabel(t.ms)}</div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export type TimelineTrackProps = {
  trackRef: React.RefObject<HTMLDivElement>;
  disabled: boolean;
  playheadRatio: number;
  playheadHot: boolean;
  playheadHitSlopPx: number;
  renderRanges: React.ReactNode;
  snapLineRatio: number | null;
  tooltipText: string | null;
  tooltipRatio: number | null;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerCancel: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerLeave: () => void;
  onWheel: (e: React.WheelEvent<HTMLDivElement>) => void;
};

export const TrimTimelineTrack: React.FC<TimelineTrackProps> = ({
  trackRef,
  disabled,
  playheadRatio,
  playheadHot,
  playheadHitSlopPx,
  renderRanges,
  snapLineRatio,
  tooltipText,
  tooltipRatio,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  onPointerLeave,
  onWheel,
}) => {
  return (
    <div
      ref={trackRef}
      className={`relative h-20 rounded-lg border ${disabled ? "bg-gray-100 border-gray-200" : "bg-gray-50 border-gray-200"} select-none overflow-hidden ${!disabled && playheadHot ? "cursor-ew-resize" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onPointerLeave={onPointerLeave}
      onWheel={onWheel}
    >
      <div className="absolute inset-0">
        {renderRanges}
        <div
          className="absolute top-0 bottom-0 -translate-x-1/2 pointer-events-none"
          style={{ left: `${playheadRatio * 100}%` }}
        >
          <div
            className={`absolute top-0 bottom-0 ${playheadHot ? "bg-red-500/10" : ""}`}
            style={{ width: `${Math.max(18, playheadHitSlopPx * 2)}px`, left: "50%", transform: "translateX(-50%)" }}
          />
          <div className="absolute top-0 bottom-0 left-1/2 w-[2px] bg-red-500 -translate-x-1/2" />
        </div>
        {snapLineRatio != null && <div className="absolute top-0 bottom-0 w-px bg-amber-500/80" style={{ left: `${snapLineRatio * 100}%` }} />}
      </div>

      {tooltipText != null && tooltipRatio != null && (
        <div
          className="absolute top-2 -translate-x-1/2 px-2 py-1 rounded bg-gray-900 text-white text-xs font-mono pointer-events-none shadow"
          style={{ left: `${tooltipRatio * 100}%` }}
        >
          {tooltipText}
        </div>
      )}
    </div>
  );
};
