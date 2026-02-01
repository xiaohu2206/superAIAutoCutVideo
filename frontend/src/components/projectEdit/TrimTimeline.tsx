import React, { useMemo, useRef } from "react";

export type TrimRange = {
  id: string;
  startMs: number;
  endMs: number;
};

type DragState =
  | { type: "none" }
  | { type: "create"; startMs: number; tempId: string }
  | { type: "resize"; id: string; edge: "start" | "end" };

export type TrimTimelineProps = {
  durationMs: number;
  currentMs: number;
  ranges: TrimRange[];
  activeRangeId: string | null;
  disabled?: boolean;
  onSeek: (ms: number) => void;
  onRangesChange: (next: TrimRange[]) => void;
  onActiveRangeChange: (id: string | null) => void;
};

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

const mergeRanges = (ranges: TrimRange[]): TrimRange[] => {
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

const msFromClientX = (el: HTMLDivElement, clientX: number, durationMs: number) => {
  const rect = el.getBoundingClientRect();
  const x = clamp(clientX - rect.left, 0, rect.width);
  const ratio = rect.width > 0 ? x / rect.width : 0;
  return clamp(Math.round(ratio * durationMs), 0, durationMs);
};

export const TrimTimeline: React.FC<TrimTimelineProps> = ({
  durationMs,
  currentMs,
  ranges,
  activeRangeId,
  disabled,
  onSeek,
  onRangesChange,
  onActiveRangeChange,
}) => {
  const barRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState>({ type: "none" });

  const safeRanges = useMemo(() => {
    const d = Math.max(0, durationMs);
    return ranges
      .map((r) => ({
        ...r,
        startMs: clamp(r.startMs, 0, d),
        endMs: clamp(r.endMs, 0, d),
      }))
      .filter((r) => r.endMs > r.startMs);
  }, [ranges, durationMs]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const el = barRef.current;
    if (!el) return;

    const target = e.target as HTMLElement | null;
    const handleId = target?.getAttribute("data-handle-id") || "";
    const handleEdge = (target?.getAttribute("data-handle-edge") || "") as "start" | "end" | "";
    if (handleId && (handleEdge === "start" || handleEdge === "end")) {
      dragRef.current = { type: "resize", id: handleId, edge: handleEdge };
      try {
        (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
      } catch {
        void 0;
      }
      return;
    }

    const startMs = msFromClientX(el, e.clientX, durationMs);
    const tempId = `r_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    dragRef.current = { type: "create", startMs, tempId };
    onSeek(startMs);
    onActiveRangeChange(tempId);
    onRangesChange(mergeRanges([...safeRanges, { id: tempId, startMs, endMs: startMs + 1 }]));
    try {
      (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
    } catch {
      void 0;
    }
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const el = barRef.current;
    if (!el) return;
    const st = dragRef.current;
    if (st.type === "none") return;
    const ms = msFromClientX(el, e.clientX, durationMs);

    if (st.type === "create") {
      const a = st.startMs;
      const startMs = Math.min(a, ms);
      const endMs = Math.max(a, ms);
      const next = safeRanges
        .filter((r) => r.id !== st.tempId)
        .concat({ id: st.tempId, startMs, endMs });
      onRangesChange(mergeRanges(next));
      onSeek(ms);
      return;
    }

    if (st.type === "resize") {
      const next = safeRanges.map((r) => {
        if (r.id !== st.id) return r;
        if (st.edge === "start") return { ...r, startMs: clamp(ms, 0, r.endMs - 1) };
        return { ...r, endMs: clamp(ms, r.startMs + 1, durationMs) };
      });
      onRangesChange(mergeRanges(next));
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = dragRef.current;
    dragRef.current = { type: "none" };
    try {
      (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
    } catch {
      void 0;
    }
    if (disabled) return;
    if (st.type === "create") {
      const created = safeRanges.find((r) => r.id === st.tempId);
      if (!created) return;
      if (created.endMs - created.startMs < 200) {
        onRangesChange(safeRanges.filter((r) => r.id !== st.tempId));
        onActiveRangeChange(null);
      }
    }
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = { type: "none" };
    try {
      (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
    } catch {
      void 0;
    }
  };

  const handleBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disabled) return;
    const el = barRef.current;
    if (!el) return;
    const ms = msFromClientX(el, e.clientX, durationMs);
    onActiveRangeChange(null);
    onSeek(ms);
  };

  const renderRanges = useMemo(() => {
    const d = Math.max(1, durationMs);
    return safeRanges.map((r) => {
      const left = (r.startMs / d) * 100;
      const width = ((r.endMs - r.startMs) / d) * 100;
      const isActive = r.id === activeRangeId;
      return (
        <div
          key={r.id}
          className={`absolute top-1 bottom-1 rounded ${isActive ? "bg-violet-500/45 ring-2 ring-violet-300" : "bg-violet-400/35"}`}
          style={{ left: `${left}%`, width: `${width}%` }}
          onClick={(ev) => {
            ev.stopPropagation();
            onActiveRangeChange(r.id);
          }}
        >
          <div
            data-handle-id={r.id}
            data-handle-edge="start"
            className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize bg-violet-700/40 rounded-l"
          />
          <div
            data-handle-id={r.id}
            data-handle-edge="end"
            className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize bg-violet-700/40 rounded-r"
          />
        </div>
      );
    });
  }, [safeRanges, durationMs, activeRangeId, onActiveRangeChange]);

  const playheadLeft = durationMs > 0 ? (clamp(currentMs, 0, durationMs) / durationMs) * 100 : 0;

  return (
    <div className="space-y-2">
      <div
        ref={barRef}
        className={`relative h-10 rounded-lg border ${disabled ? "bg-gray-100 border-gray-200" : "bg-gray-50 border-gray-200"} select-none`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onClick={handleBarClick}
      >
        {renderRanges}
        <div className="absolute top-0 bottom-0 w-[2px] bg-red-500" style={{ left: `${playheadLeft}%` }} />
      </div>
      <div className="text-xs text-gray-500">拖拽空白处创建区间，拖拽区间两侧把手调整范围，点击时间轴可定位预览</div>
    </div>
  );
};
