import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useElementWidth } from "../../hooks/useElementWidth";
import {
  buildRulerTicks,
  clamp,
  clamp01,
  findClosest,
  formatRulerLabel,
  mergeRanges,
  type TrimRange as TimelineTrimRange,
} from "./timeline/timelineMath";

import {
  TrimTimelineOverview,
  TrimTimelineRuler,
  TrimTimelineToolbar,
  TrimTimelineTrack,
} from "./timeline/TrimTimelineUi";

export type TrimRange = TimelineTrimRange;

type DragState =
  | { type: "none" }
  | { type: "create"; startMs: number; tempId: string; startClientX: number; msPerPx: number }
  | { type: "resize"; id: string; edge: "start" | "end" }
  | { type: "scrub"; startClientX: number; startMs: number; msPerPx: number }
  | { type: "playhead"; startClientX: number; startMs: number; msPerPx: number }
  | { type: "overview"; startClientX: number; startViewportStartMs: number; durationMs: number; widthPx: number };

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
  const overviewRef = useRef<HTMLDivElement>(null);
  const rulerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState>({ type: "none" });
  const seekRafRef = useRef<number | null>(null);
  const pendingSeekMsRef = useRef<number | null>(null);
  const onSeekRef = useRef(onSeek);

  const [viewportStartMs, setViewportStartMs] = useState(0);
  const [viewportMs, setViewportMs] = useState(() => Math.max(1, durationMs));
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [isHovering, setIsHovering] = useState(false);
  const [hoverClientX, setHoverClientX] = useState<number | null>(null);
  const [snapLineMs, setSnapLineMs] = useState<number | null>(null);

  const trackWidthPx = useElementWidth(trackRef);
  const overviewWidthPx = useElementWidth(overviewRef);

  useEffect(() => {
    onSeekRef.current = onSeek;
  }, [onSeek]);

  const scheduleSeek = useCallback((ms: number) => {
    pendingSeekMsRef.current = ms;
    if (seekRafRef.current != null) return;
    seekRafRef.current = window.requestAnimationFrame(() => {
      seekRafRef.current = null;
      const v = pendingSeekMsRef.current;
      pendingSeekMsRef.current = null;
      if (v == null) return;
      onSeekRef.current(v);
    });
  }, []);

  useEffect(() => {
    const d = Math.max(0, durationMs);
    const nextViewportMs = clamp(viewportMs, Math.min(d || 1, 2000), Math.max(1, d || 1));
    const nextStart = clamp(viewportStartMs, 0, Math.max(0, d - nextViewportMs));
    setViewportMs(nextViewportMs);
    setViewportStartMs(nextStart);
  }, [durationMs]);

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

  const msPerPx = trackWidthPx > 0 ? viewportMs / trackWidthPx : Math.max(1, viewportMs);

  const { ticks, majorStepMs } = useMemo(() => {
    const safeMsPerPx = Number.isFinite(msPerPx) && msPerPx > 0 ? msPerPx : 1;
    return buildRulerTicks(viewportStartMs, viewportMs, safeMsPerPx);
  }, [viewportStartMs, viewportMs, msPerPx]);

  const ratioFromMs = useCallback(
    (ms: number) => {
      if (viewportMs <= 0) return 0;
      return clamp01((ms - viewportStartMs) / viewportMs);
    },
    [viewportStartMs, viewportMs]
  );

  const msFromClientXInTrack = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      const x = clamp(clientX - rect.left, 0, rect.width);
      const ratio = rect.width > 0 ? x / rect.width : 0;
      return clamp(Math.round(viewportStartMs + ratio * viewportMs), 0, Math.max(0, durationMs));
    },
    [viewportStartMs, viewportMs, durationMs]
  );

  const msFromClientXInOverview = useCallback(
    (clientX: number) => {
      const el = overviewRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      const x = clamp(clientX - rect.left, 0, rect.width);
      const ratio = rect.width > 0 ? x / rect.width : 0;
      return clamp(Math.round(ratio * Math.max(0, durationMs)), 0, Math.max(0, durationMs));
    },
    [durationMs]
  );

  const snapCandidates = useMemo(() => {
    const d = Math.max(0, durationMs);
    const values: number[] = [0, d, clamp(currentMs, 0, d)];
    for (const r of safeRanges) {
      values.push(r.startMs, r.endMs);
    }
    for (const t of ticks) {
      if (t.ms >= 0 && t.ms <= d) values.push(t.ms);
    }
    values.sort((a, b) => a - b);
    const deduped: number[] = [];
    let last: number | null = null;
    for (const v of values) {
      if (last == null || Math.abs(v - last) > 0.5) {
        deduped.push(v);
        last = v;
      }
    }
    return deduped;
  }, [durationMs, currentMs, safeRanges, ticks]);

  const applySnap = useCallback(
    (rawMs: number, snapMs: number) => {
      if (!snapEnabled || snapMs <= 0) return { ms: rawMs, snapped: null as number | null };
      const best = findClosest(snapCandidates, rawMs, snapMs);
      if (best == null) return { ms: rawMs, snapped: null as number | null };
      return { ms: best, snapped: best };
    },
    [snapEnabled, snapCandidates]
  );

  const zoomTo = useCallback(
    (nextViewportMs: number, anchorMs: number, anchorRatio: number) => {
      const d = Math.max(1, durationMs);
      const minViewport = Math.min(d, 2000);
      const vMs = clamp(Math.round(nextViewportMs), minViewport, d);
      const start = clamp(Math.round(anchorMs - anchorRatio * vMs), 0, Math.max(0, d - vMs));
      setViewportMs(vMs);
      setViewportStartMs(start);
    },
    [durationMs]
  );

  const panByMs = useCallback(
    (deltaMs: number) => {
      const d = Math.max(0, durationMs);
      const start = clamp(Math.round(viewportStartMs + deltaMs), 0, Math.max(0, d - viewportMs));
      setViewportStartMs(start);
    },
    [durationMs, viewportStartMs, viewportMs]
  );

  const handleAddRange = useCallback(() => {
    if (disabled) return;
    const d = Math.max(0, durationMs);
    const startMs = clamp(Math.round(currentMs), 0, d);
    const endMs = clamp(startMs + 5000, startMs + 1, d);
    const id = `r_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    onActiveRangeChange(id);
    onRangesChange(mergeRanges([...safeRanges, { id, startMs, endMs }]));
  }, [disabled, durationMs, currentMs, onActiveRangeChange, onRangesChange, safeRanges]);

  const handleFit = useCallback(() => {
    const d = Math.max(1, durationMs);
    setViewportMs(d);
    setViewportStartMs(0);
  }, [durationMs]);

  const handleZoomIn = useCallback(() => {
    const d = Math.max(1, durationMs);
    const anchorMs = clamp(currentMs, 0, d);
    const anchorRatio = ratioFromMs(anchorMs);
    zoomTo(viewportMs / 1.25, anchorMs, anchorRatio);
  }, [durationMs, currentMs, ratioFromMs, viewportMs, zoomTo]);

  const handleZoomOut = useCallback(() => {
    const d = Math.max(1, durationMs);
    const anchorMs = clamp(currentMs, 0, d);
    const anchorRatio = ratioFromMs(anchorMs);
    zoomTo(viewportMs * 1.25, anchorMs, anchorRatio);
  }, [durationMs, currentMs, ratioFromMs, viewportMs, zoomTo]);

  const isDragging = dragRef.current.type !== "none";
  const playheadHitSlopPx = 14;

  const handleTrackPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const el = trackRef.current;
    if (!el) return;

    const target = e.target as HTMLElement | null;
    const handleEl = (target?.closest?.("[data-handle-id][data-handle-edge]") as HTMLElement | null) ?? null;
    const handleId = handleEl?.getAttribute("data-handle-id") || "";
    const handleEdge = (handleEl?.getAttribute("data-handle-edge") || "") as "start" | "end" | "";
    if (handleId && (handleEdge === "start" || handleEdge === "end")) {
      dragRef.current = { type: "resize", id: handleId, edge: handleEdge };
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        void 0;
      }
      return;
    }

    const rect = el.getBoundingClientRect();
    const x = clamp(e.clientX - rect.left, 0, rect.width);
    const playheadRatio = ratioFromMs(clamp(currentMs, 0, Math.max(0, durationMs)));
    const playheadX = playheadRatio * rect.width;
    const isHitPlayhead = Math.abs(x - playheadX) <= playheadHitSlopPx;

    const startMsAtPointer = msFromClientXInTrack(e.clientX);
    const mode: DragState["type"] = isHitPlayhead ? "playhead" : e.shiftKey ? "create" : "scrub";
    const startMs = startMsAtPointer;

    if (mode === "create") {
      const tempId = `r_${Date.now()}_${Math.random().toString(16).slice(2)}`;
      dragRef.current = { type: "create", startMs, tempId, startClientX: e.clientX, msPerPx };
      onActiveRangeChange(tempId);
      onRangesChange(mergeRanges([...safeRanges, { id: tempId, startMs, endMs: startMs + 1 }]));
      scheduleSeek(startMs);
    } else if (mode === "playhead") {
      dragRef.current = { type: "playhead", startClientX: e.clientX, startMs, msPerPx };
      scheduleSeek(startMs);
      onActiveRangeChange(null);
    } else {
      dragRef.current = { type: "scrub", startClientX: e.clientX, startMs, msPerPx };
      scheduleSeek(startMs);
      onActiveRangeChange(null);
    }

    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      void 0;
    }
  };

  const handleTrackPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;

    if (!isDragging) {
      setIsHovering(true);
      setHoverClientX(e.clientX);
      setSnapLineMs(null);
      return;
    }

    const st = dragRef.current;
    if (st.type === "none") return;
    const d = Math.max(0, durationMs);
    const slow = e.altKey ? 0.1 : 1;
    const snapPx = e.shiftKey ? 12 : 6;

    if (st.type === "scrub" || st.type === "playhead") {
      const deltaPx = (e.clientX - st.startClientX) * slow;
      const raw = clamp(Math.round(st.startMs + deltaPx * st.msPerPx), 0, d);
      const snapped = applySnap(raw, snapPx * st.msPerPx);
      setSnapLineMs(snapped.snapped);
      scheduleSeek(snapped.ms);
      return;
    }

    if (st.type === "create") {
      const deltaPx = (e.clientX - st.startClientX) * slow;
      const ms = clamp(Math.round(st.startMs + deltaPx * st.msPerPx), 0, d);
      const snapped = applySnap(ms, snapPx * st.msPerPx);
      setSnapLineMs(snapped.snapped);
      const a = st.startMs;
      const startMs = Math.min(a, snapped.ms);
      const endMs = Math.max(a, snapped.ms);
      const next = safeRanges
        .filter((r) => r.id !== st.tempId)
        .concat({ id: st.tempId, startMs, endMs });
      onRangesChange(mergeRanges(next));
      scheduleSeek(snapped.ms);
      return;
    }

    if (st.type === "resize") {
      const pointerMs = msFromClientXInTrack(e.clientX);
      const snapped = applySnap(pointerMs, snapPx * msPerPx);
      setSnapLineMs(snapped.snapped);
      const next = safeRanges.map((r) => {
        if (r.id !== st.id) return r;
        if (st.edge === "start") return { ...r, startMs: clamp(snapped.ms, 0, r.endMs - 1) };
        return { ...r, endMs: clamp(snapped.ms, r.startMs + 1, d) };
      });
      onRangesChange(mergeRanges(next));
    }
  };

  const finishDrag = useCallback(
    (st: DragState) => {
      setSnapLineMs(null);
      if (disabled) return;
      if (st.type === "create") {
        const created = safeRanges.find((r) => r.id === st.tempId);
        if (!created) return;
        if (created.endMs - created.startMs < 200) {
          onRangesChange(safeRanges.filter((r) => r.id !== st.tempId));
          onActiveRangeChange(null);
        }
      }
    },
    [disabled, onActiveRangeChange, onRangesChange, safeRanges]
  );

  const handleTrackPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = dragRef.current;
    dragRef.current = { type: "none" };
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      void 0;
    }
    finishDrag(st);
  };

  const handleTrackPointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = { type: "none" };
    setSnapLineMs(null);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      void 0;
    }
  };

  const handleTrackWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (durationMs <= 0) return;
    const el = trackRef.current;
    if (!el) return;
    e.preventDefault();

    const rect = el.getBoundingClientRect();
    const x = clamp(e.clientX - rect.left, 0, rect.width);
    const anchorRatio = rect.width > 0 ? x / rect.width : 0;
    const anchorMs = clamp(Math.round(viewportStartMs + anchorRatio * viewportMs), 0, Math.max(0, durationMs));

    if (e.ctrlKey) {
      const dir = e.deltaY < 0 ? 1 / 1.1 : 1.1;
      zoomTo(viewportMs * dir, anchorMs, anchorRatio);
      return;
    }

    const deltaPx = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    panByMs(deltaPx * msPerPx);
  };

  const handleTrackPointerLeave = () => {
    setIsHovering(false);
    setHoverClientX(null);
  };

  const handleRulerPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const ms = msFromClientXInTrack(e.clientX);
    scheduleSeek(ms);
    onActiveRangeChange(null);
  };

  const handleOverviewPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    const el = overviewRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = clamp(e.clientX - rect.left, 0, rect.width);
    const ratio = rect.width > 0 ? x / rect.width : 0;
    const clickedMs = clamp(Math.round(ratio * Math.max(0, durationMs)), 0, Math.max(0, durationMs));
    const nextStart = clamp(Math.round(clickedMs - viewportMs / 2), 0, Math.max(0, durationMs - viewportMs));
    setViewportStartMs(nextStart);
    scheduleSeek(clickedMs);
    onActiveRangeChange(null);
  };

  const handleOverviewWindowPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    e.stopPropagation();
    const d = Math.max(0, durationMs);
    if (d <= 0) return;
    dragRef.current = {
      type: "overview",
      startClientX: e.clientX,
      startViewportStartMs: viewportStartMs,
      durationMs: d,
      widthPx: Math.max(1, overviewWidthPx),
    };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      void 0;
    }
  };

  const handleOverviewWindowPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = dragRef.current;
    if (st.type !== "overview") return;
    if (disabled) return;
    const deltaPx = e.clientX - st.startClientX;
    const deltaMs = (deltaPx / st.widthPx) * st.durationMs;
    const nextStart = clamp(Math.round(st.startViewportStartMs + deltaMs), 0, Math.max(0, st.durationMs - viewportMs));
    setViewportStartMs(nextStart);
  };

  const handleOverviewWindowPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const st = dragRef.current;
    dragRef.current = { type: "none" };
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      void 0;
    }
    if (st.type !== "overview") return;
    const ms = msFromClientXInOverview(e.clientX);
    scheduleSeek(ms);
  };

  const renderRanges = useMemo(() => {
    const d = Math.max(0, durationMs);
    if (d <= 0 || viewportMs <= 0) return null;
    const visible = safeRanges
      .map((r) => {
        const leftRatio = ratioFromMs(r.startMs);
        const rightRatio = ratioFromMs(r.endMs);
        const left = clamp01(Math.min(leftRatio, rightRatio));
        const right = clamp01(Math.max(leftRatio, rightRatio));
        return { r, left, right };
      })
      .filter(({ right, left }) => right > 0 && left < 1);

    return visible.map(({ r, left, right }) => {
      const width = Math.max(0, right - left) * 100;
      const isActive = r.id === activeRangeId;
      return (
        <div
          key={r.id}
          className={`absolute top-2 bottom-2 rounded ${isActive ? "bg-violet-500/45 ring-2 ring-violet-300" : "bg-violet-400/35"}`}
          style={{ left: `${left * 100}%`, width: `${width}%` }}
          onClick={(ev) => {
            ev.stopPropagation();
            onActiveRangeChange(r.id);
          }}
        >
          <div
            data-handle-id={r.id}
            data-handle-edge="start"
            className="absolute -left-1 top-0 bottom-0 w-3 cursor-ew-resize"
          >
            <div className="absolute left-1 top-0 bottom-0 w-2 bg-violet-700/40 rounded-l" />
          </div>
          <div
            data-handle-id={r.id}
            data-handle-edge="end"
            className="absolute -right-1 top-0 bottom-0 w-3 cursor-ew-resize"
          >
            <div className="absolute right-1 top-0 bottom-0 w-2 bg-violet-700/40 rounded-r" />
          </div>
        </div>
      );
    });
  }, [activeRangeId, durationMs, onActiveRangeChange, ratioFromMs, safeRanges, viewportMs]);

  const playheadRatio = ratioFromMs(clamp(currentMs, 0, Math.max(0, durationMs)));

  const isPlayheadHot = useMemo(() => {
    if (!isHovering || hoverClientX == null) return false;
    const el = trackRef.current;
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const x = clamp(hoverClientX - rect.left, 0, rect.width);
    const playheadX = playheadRatio * rect.width;
    return Math.abs(x - playheadX) <= playheadHitSlopPx;
  }, [hoverClientX, isHovering, playheadHitSlopPx, playheadRatio]);

  const hoverMs = useMemo(() => {
    if (!isHovering || hoverClientX == null) return null;
    return msFromClientXInTrack(hoverClientX);
  }, [hoverClientX, isHovering, msFromClientXInTrack]);

  const tooltipMs = useMemo(() => {
    const st = dragRef.current;
    const d = Math.max(0, durationMs);
    if (st.type === "playhead" || st.type === "scrub") return clamp(currentMs, 0, d);
    if (st.type === "create") return clamp(currentMs, 0, d);
    if (st.type === "resize") return clamp(currentMs, 0, d);
    return hoverMs;
  }, [currentMs, durationMs, hoverMs]);

  const tooltipRatio = tooltipMs == null ? null : ratioFromMs(tooltipMs);

  return (
    <div className="space-y-2">
      <TrimTimelineToolbar
        disabled={Boolean(disabled)}
        snapEnabled={snapEnabled}
        msPerPxText={trackWidthPx > 0 ? `${Math.round(msPerPx)} ms/px` : "—"}
        viewportPerScreenText={`${formatRulerLabel(viewportMs, majorStepMs)} / 屏`}
        onZoomOut={handleZoomOut}
        onZoomIn={handleZoomIn}
        onFit={handleFit}
        onToggleSnap={() => setSnapEnabled((v) => !v)}
        onAddRange={handleAddRange}
      />

      <div className="space-y-1">
        <TrimTimelineOverview
          overviewRef={overviewRef}
          disabled={Boolean(disabled)}
          durationMs={durationMs}
          viewportStartMs={viewportStartMs}
          viewportMs={viewportMs}
          currentMs={currentMs}
          onPointerDown={handleOverviewPointerDown}
          onWindowPointerDown={handleOverviewWindowPointerDown}
          onWindowPointerMove={handleOverviewWindowPointerMove}
          onWindowPointerUp={handleOverviewWindowPointerUp}
        />

        <TrimTimelineRuler
          rulerRef={rulerRef}
          ticks={ticks}
          ratioFromMs={ratioFromMs}
          formatLabel={(ms) => formatRulerLabel(ms, majorStepMs)}
          onPointerDown={handleRulerPointerDown}
        />

        <TrimTimelineTrack
          trackRef={trackRef}
          disabled={Boolean(disabled)}
          playheadRatio={playheadRatio}
          playheadHot={isPlayheadHot}
          playheadHitSlopPx={playheadHitSlopPx}
          renderRanges={renderRanges}
          snapLineRatio={snapLineMs != null ? ratioFromMs(snapLineMs) : null}
          tooltipText={tooltipMs != null ? formatRulerLabel(tooltipMs, majorStepMs) : null}
          tooltipRatio={tooltipRatio}
          onPointerDown={handleTrackPointerDown}
          onPointerMove={handleTrackPointerMove}
          onPointerUp={handleTrackPointerUp}
          onPointerCancel={handleTrackPointerCancel}
          onPointerLeave={handleTrackPointerLeave}
          onWheel={handleTrackWheel}
        />
      </div>

      <div className="text-xs text-gray-500">
        拖拽红线或空白可定位（Alt 精细拖拽），Shift + 拖拽空白创建区间；滚轮平移视窗，Ctrl + 滚轮缩放。
      </div>
    </div>
  );
};
