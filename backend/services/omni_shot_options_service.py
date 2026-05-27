#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omni script segment shot options for the manual shot picker UI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.projects_store import projects_store
from services.asr.extract_subtitle_service import _resolve_path
from services.omni_internal.multimodal_json_crypto import read_multimodal_json

_PREFERRED_LIMIT = 30
_OST_NEARBY_LIMIT = 10


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _shot_key(value: Any) -> str:
    return str(value).strip()


def _normalize_text(value: Any) -> str:
    text = str(value or "")
    return re.sub(r"\s+", "", text).strip().lower()


def _is_ost_segment(segment: Dict[str, Any]) -> bool:
    raw = segment.get("OST")
    if isinstance(raw, bool):
        return raw
    return str(raw if raw is not None else "").strip() in {"1", "true", "True", "yes", "原声"}


def _result_text(result: Dict[str, Any]) -> str:
    for key in ("text", "copywriting", "narration", "content"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _score_for_sort(shot: Dict[str, Any]) -> float:
    for key in ("final_score", "score", "rerank_score", "embedding_score"):
        value = shot.get(key)
        if value is not None:
            return _to_float(value, 0.0)
    return 0.0


def _read_plain_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("候选镜头 JSON 根节点必须为对象")
    return payload


def _existing_web_path(*paths: Optional[str]) -> Optional[str]:
    for path in paths:
        web_path = str(path or "").strip()
        if not web_path:
            continue
        try:
            if _resolve_path(web_path).exists():
                return web_path
        except Exception:
            continue
    return None


def _build_shot_lookup(shots: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = shot.get("shot_id")
        if sid is None:
            continue
        out[_shot_key(sid)] = shot
    return out


def _subtitle_text(source: Dict[str, Any], fallback: Dict[str, Any]) -> str:
    value = source.get("subtitle_full_text")
    if isinstance(value, str) and value.strip():
        return value
    value = fallback.get("subtitle_full_text")
    if isinstance(value, str) and value.strip():
        return value
    subtitle = fallback.get("subtitle")
    if isinstance(subtitle, dict):
        value = subtitle.get("full_text")
        if isinstance(value, str):
            return value
    return ""


def _selectable_shot(
    source: Dict[str, Any],
    shot_lookup: Dict[str, Dict[str, Any]],
    *,
    option_source: str,
) -> Optional[Dict[str, Any]]:
    sid = source.get("shot_id")
    fallback = shot_lookup.get(_shot_key(sid)) if sid is not None else {}
    fallback = fallback if isinstance(fallback, dict) else {}

    start_raw = source.get("start", fallback.get("start"))
    end_raw = source.get("end", fallback.get("end"))
    if start_raw is None or end_raw is None:
        return None

    start = _to_float(start_raw, 0.0)
    end = _to_float(end_raw, 0.0)
    duration = source.get("duration", fallback.get("duration"))
    duration_f = _to_float(duration, max(0.0, end - start))
    if duration_f <= 0:
        duration_f = max(0.0, end - start)

    visual = source.get("visual") if isinstance(source.get("visual"), dict) else None
    if visual is None:
        visual = fallback.get("visual") if isinstance(fallback.get("visual"), dict) else None

    out_sid = sid if sid is not None else fallback.get("shot_id")
    if out_sid is None:
        return None

    out: Dict[str, Any] = {
        "shot_id": out_sid,
        "start": start,
        "end": end,
        "duration": duration_f,
        "subtitle_full_text": _subtitle_text(source, fallback),
        "visual": visual or {},
        "summary": source.get("summary") or fallback.get("summary") or "",
        "option_source": option_source,
    }

    for key in ("score", "final_score", "embedding_score", "rerank_score", "continuity_score", "reason"):
        if key in source and source.get(key) is not None:
            out[key] = source.get(key)
    return out


def _dedupe_sort_preferred(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        sid = item.get("shot_id")
        key = _shot_key(sid) if sid is not None else f"{item.get('start')}:{item.get('end')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=_score_for_sort, reverse=True)
    return deduped[:_PREFERRED_LIMIT]


def _map_non_ost_results(segments: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    non_ost_indexes = [i for i, seg in enumerate(segments) if isinstance(seg, dict) and not _is_ost_segment(seg)]
    result_items = [r for r in results if isinstance(r, dict)]
    mapped: Dict[int, Dict[str, Any]] = {}
    if not non_ost_indexes or not result_items:
        return mapped

    if len(non_ost_indexes) == len(result_items):
        return {seg_i: result_items[pos] for pos, seg_i in enumerate(non_ost_indexes)}

    used: Set[int] = set()
    normalized_results = [_normalize_text(_result_text(r)) for r in result_items]
    for seg_i in non_ost_indexes:
        segment_text = _normalize_text(segments[seg_i].get("text"))
        if not segment_text:
            continue
        for result_i, result_text in enumerate(normalized_results):
            if result_i in used or not result_text:
                continue
            if segment_text in result_text or result_text in segment_text:
                mapped[seg_i] = result_items[result_i]
                used.add(result_i)
                break

    next_result = 0
    for seg_i in non_ost_indexes:
        if seg_i in mapped:
            continue
        while next_result in used and next_result < len(result_items):
            next_result += 1
        if next_result >= len(result_items):
            break
        mapped[seg_i] = result_items[next_result]
        used.add(next_result)
        next_result += 1
    return mapped


def _nearby_shots_for_segment(
    segment: Dict[str, Any],
    all_shots: List[Dict[str, Any]],
    shot_lookup: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    start = _to_float(segment.get("start_time"), 0.0)
    end = _to_float(segment.get("end_time"), start)
    mid = (start + end) / 2.0

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for shot in all_shots:
        if not isinstance(shot, dict):
            continue
        s = _to_float(shot.get("start"), 0.0)
        e = _to_float(shot.get("end"), s)
        shot_mid = (s + e) / 2.0
        overlap = max(0.0, min(end, e) - max(start, s))
        distance = 0.0 if overlap > 0 else abs(shot_mid - mid)
        scored.append((distance, shot))
    scored.sort(key=lambda x: (x[0], _to_float(x[1].get("start"), 0.0)))

    options: List[Dict[str, Any]] = []
    for _, shot in scored[:_OST_NEARBY_LIMIT]:
        opt = _selectable_shot(shot, shot_lookup, option_source="preferred")
        if opt:
            options.append(opt)
    return options


def _other_shots(
    all_shots: List[Dict[str, Any]],
    shot_lookup: Dict[str, Dict[str, Any]],
    preferred: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    preferred_ids = {_shot_key(x.get("shot_id")) for x in preferred if x.get("shot_id") is not None}
    out: List[Dict[str, Any]] = []
    for shot in all_shots:
        if not isinstance(shot, dict):
            continue
        sid = shot.get("shot_id")
        if sid is not None and _shot_key(sid) in preferred_ids:
            continue
        opt = _selectable_shot(shot, shot_lookup, option_source="other")
        if opt:
            out.append(opt)
    out.sort(key=lambda x: (_to_float(x.get("start"), 0.0), _to_float(x.get("end"), 0.0)))
    return out


class OmniShotOptionsService:
    def get_options(self, project_id: str) -> Dict[str, Any]:
        project = projects_store.get_project(project_id)
        if not project:
            raise ValueError("项目不存在")
        if str(getattr(project, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可获取候选镜头")

        script = getattr(project, "script", None) or {}
        segments = script.get("segments") if isinstance(script, dict) else []
        if not isinstance(segments, list) or not segments:
            return {"segments": []}

        mm_web = str(getattr(project, "omni_multimodal_json_path", None) or "").strip()
        if not mm_web:
            raise ValueError("缺少多模态镜头 JSON：请先完成 Omni 多模态管线")
        mm_abs = _resolve_path(mm_web)
        if not mm_abs.exists():
            raise FileNotFoundError(f"多模态镜头 JSON 不存在: {mm_web}")
        mm_payload = read_multimodal_json(mm_abs)
        all_shots = mm_payload.get("shots") if isinstance(mm_payload, dict) else []
        if not isinstance(all_shots, list):
            all_shots = []
        all_shots = [shot for shot in all_shots if isinstance(shot, dict)]
        shot_lookup = _build_shot_lookup(all_shots)

        candidate_payload: Dict[str, Any] = {}
        candidate_web = _existing_web_path(
            getattr(project, "omni_global_path_search_path", None),
            getattr(project, "omni_shot_match_rerank_path", None),
        )
        if candidate_web:
            candidate_payload = _read_plain_json(_resolve_path(candidate_web))
        results = candidate_payload.get("results") if isinstance(candidate_payload, dict) else []
        if not isinstance(results, list):
            results = []

        result_by_segment = _map_non_ost_results(segments, results)
        response_segments: List[Dict[str, Any]] = []

        for idx, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            segment_id = str(segment.get("id") or idx + 1)
            preferred: List[Dict[str, Any]] = []

            if _is_ost_segment(segment):
                preferred = _nearby_shots_for_segment(segment, all_shots, shot_lookup)
            else:
                result = result_by_segment.get(idx) or {}
                matches = result.get("matches") if isinstance(result, dict) else []
                if isinstance(matches, list):
                    for match in matches:
                        if not isinstance(match, dict):
                            continue
                        opt = _selectable_shot(match, shot_lookup, option_source="preferred")
                        if opt:
                            preferred.append(opt)
                preferred = _dedupe_sort_preferred(preferred)

            response_segments.append(
                {
                    "segment_id": segment_id,
                    "preferred_shots": preferred,
                    "other_shots": _other_shots(all_shots, shot_lookup, preferred),
                }
            )

        return {"segments": response_segments}


omni_shot_options_service = OmniShotOptionsService()
