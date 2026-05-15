# -*- coding: utf-8 -*-
"""Top1-shot based timeline window selection for omni narration chunks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Top1WindowConfig:
    cluster_gap_min_seconds: float = 60.0
    cluster_gap_median_multiplier: float = 4.0
    main_cluster_ratio: float = 0.7
    pad_ratio: float = 0.1
    pad_min_seconds: float = 30.0
    pad_max_seconds: float = 180.0


@dataclass(frozen=True)
class Top1SpanWindow:
    window_start: float
    window_end: float
    raw_min: float
    raw_max: float
    top1_span: float
    pad_seconds: float
    gap_threshold: float
    anchor_count: int
    selected_anchor_count: int
    cluster_count: int
    selected_cluster_ratio: float


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return default


def _clamp(v: float, lo: float, hi: float) -> float:
    if hi < lo:
        return lo
    return max(lo, min(hi, v))


def _median_float(values: List[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2:
        return float(xs[mid])
    return (xs[mid - 1] + xs[mid]) / 2.0


def _collect_top1_anchors(chunk_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    for item in chunk_results:
        matches = item.get("matches") or []
        if not matches:
            continue
        m = matches[0]
        start = _safe_float(m.get("start"))
        end = _safe_float(m.get("end"))
        if end <= start:
            continue
        anchors.append(
            {
                "start": start,
                "end": end,
                "mid": (start + end) * 0.5,
                "shot_id": m.get("shot_id"),
            }
        )
    anchors.sort(key=lambda x: x["mid"])
    return anchors


def _split_by_large_gap(
    anchors: List[Dict[str, Any]],
    config: Top1WindowConfig,
) -> tuple[List[List[Dict[str, Any]]], float]:
    if not anchors:
        return [], float(config.cluster_gap_min_seconds)
    if len(anchors) == 1:
        return [anchors[:]], float(config.cluster_gap_min_seconds)

    gaps = [
        anchors[i]["mid"] - anchors[i - 1]["mid"]
        for i in range(1, len(anchors))
        if anchors[i]["mid"] >= anchors[i - 1]["mid"]
    ]
    median_gap = _median_float(gaps)
    threshold = max(
        float(config.cluster_gap_min_seconds),
        median_gap * float(config.cluster_gap_median_multiplier),
    )

    clusters: List[List[Dict[str, Any]]] = [[anchors[0]]]
    for anchor in anchors[1:]:
        gap = anchor["mid"] - clusters[-1][-1]["mid"]
        if gap > threshold:
            clusters.append([anchor])
        else:
            clusters[-1].append(anchor)
    return clusters, threshold


def compute_top1_span_window(
    chunk_results: List[Dict[str, Any]],
    video_end: float,
    config: Optional[Top1WindowConfig] = None,
) -> Optional[Top1SpanWindow]:
    """Return a padded timeline window around the chunk's valid Top1 matches."""
    cfg = config or Top1WindowConfig()
    anchors = _collect_top1_anchors(chunk_results)
    if not anchors:
        return None

    clusters, gap_threshold = _split_by_large_gap(anchors, cfg)
    if not clusters:
        return None

    main_cluster = max(clusters, key=len)
    main_ratio = len(main_cluster) / float(len(anchors))
    selected = main_cluster if main_ratio >= float(cfg.main_cluster_ratio) else anchors
    selected_ratio = len(selected) / float(len(anchors))

    raw_min = min(x["start"] for x in selected)
    raw_max = max(x["end"] for x in selected)
    span = max(raw_max - raw_min, 1.0)
    pad = _clamp(
        span * float(cfg.pad_ratio),
        float(cfg.pad_min_seconds),
        float(cfg.pad_max_seconds),
    )

    window_start = max(0.0, raw_min - pad)
    window_end = raw_max + pad
    ve = max(0.0, _safe_float(video_end))
    if ve > 0:
        window_start = max(0.0, min(window_start, max(ve - 1.0, 0.0)))
        window_end = min(ve, window_end)
    if window_end <= window_start:
        window_end = window_start + 1.0

    return Top1SpanWindow(
        window_start=window_start,
        window_end=window_end,
        raw_min=raw_min,
        raw_max=raw_max,
        top1_span=span,
        pad_seconds=pad,
        gap_threshold=gap_threshold,
        anchor_count=len(anchors),
        selected_anchor_count=len(selected),
        cluster_count=len(clusters),
        selected_cluster_ratio=selected_ratio,
    )
