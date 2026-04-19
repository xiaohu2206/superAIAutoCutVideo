# -*- coding: utf-8 -*-
"""
Omni 解说脚本生成：分块提示词、合并与 VideoScript 转换（与 visual/script_generation 无 import 耦合）。
语义对齐 aiSearchShot Step4.9；核心时间轴/分块逻辑来自 `_runner_core`（demo runner 抽取）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ._runner_core import (
    CHUNK_TASK_SUFFIX,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TEMPLATE,
    _build_copywriting_outline,
    _build_retrieval_candidates,
    _build_timeline_scenes,
    _compute_chunk_time_windows,
    _compute_copywriting_chunk_ranges,
    _compute_copywriting_chunk_ranges_balanced_shots,
    _expand_timeline_shots_by_shot_id_redundancy,
    _filter_shots_by_time_window,
    _format_ts,
    _post_check_items,
    _video_end_seconds,
)


@dataclass
class OmniNarrationParams:
    """与 demo `highlight_narration_script` / Step4.9 对齐的可调参数。"""

    max_items_for_retrieval: int = 999999
    chunk_target_size: int = 20
    chunk_balance_mode: str = "balanced_shots"
    chunk_min_lines: int = 1
    chunk_overlap_ratio: float = 0.1
    timeline_window_mode: str = "proportional"
    timeline_gap_median_multiplier: float = 4.0
    timeline_gap_min_seconds: float = 30.0
    timeline_shot_id_redundancy_ratio: float = 0.1
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    script_language: str = "zh"


def parse_timestamp_pair_seconds(ts_range: str) -> Tuple[float, float]:
    """与 `ScriptGenerationService.to_video_script` 一致：解析 HH:MM:SS,mmm-HH:MM:SS,mmm。"""

    def _to_seconds(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    parts = re.split(r"\s*[-–]\s*", (ts_range or "").strip())
    if len(parts) != 2:
        raise ValueError(f"时间戳范围格式错误: {ts_range}")
    return _to_seconds(parts[0]), _to_seconds(parts[1])


def _language_system_addon(script_language: str) -> str:
    lang = str(script_language or "zh").strip().lower()
    if lang in {"en", "en-us", "英文", "english"}:
        return "You must write all 'narration' text strictly in English; do not output Chinese or other languages."
    if lang in {"zh", "zh-cn", "中文", "chinese"}:
        return "你必须将所有 'narration' 文本严格用中文撰写；不得输出英文或其他语言。"
    return ""


def build_chunk_metas_and_prompts(
    results: List[Dict[str, Any]],
    all_shots: List[Dict[str, Any]],
    params: OmniNarrationParams,
) -> List[Dict[str, Any]]:
    """
    为每个分块生成 meta + user_prompt + system_prompt。
    results：与全局路径搜索输出一致，每项含 text、matches[] 等。
    """
    if not results:
        raise ValueError("results 为空")
    if not all_shots:
        raise ValueError("shots 为空")

    n = len(results)
    video_end = _video_end_seconds(all_shots)
    mode = str(params.chunk_balance_mode or "balanced_shots").strip().lower()
    if mode in {"balanced_shots", "shot_balance", "equal_shots"}:
        chunk_ranges = _compute_copywriting_chunk_ranges_balanced_shots(
            n, params.chunk_target_size, video_end, all_shots, params.chunk_min_lines
        )
    else:
        chunk_ranges = _compute_copywriting_chunk_ranges(n, params.chunk_target_size)

    chunk_metas = _compute_chunk_time_windows(
        results,
        chunk_ranges,
        params.chunk_overlap_ratio,
        video_end,
        window_mode=params.timeline_window_mode,
        gap_median_mult=params.timeline_gap_median_multiplier,
        gap_min_seconds=params.timeline_gap_min_seconds,
    )
    total_chunks = len(chunk_metas)
    tpl = params.user_prompt_template or DEFAULT_USER_PROMPT_TEMPLATE
    sys_base = params.system_prompt or DEFAULT_SYSTEM_PROMPT
    lang_hint = _language_system_addon(params.script_language)
    system_prompt = f"{lang_hint}\n{sys_base}".strip() if lang_hint else sys_base

    out: List[Dict[str, Any]] = []
    for meta in chunk_metas:
        user_prompt = _build_user_prompt_for_chunk(
            meta,
            results,
            all_shots,
            params,
            total_chunks,
            tpl,
        )
        out.append(
            {
                "chunk_index": int(meta["chunk_index"]),
                "meta": meta,
                "user_prompt": user_prompt,
                "system_prompt": system_prompt,
            }
        )
    return out


def _build_user_prompt_for_chunk(
    meta: Dict[str, Any],
    results: List[Dict[str, Any]],
    all_shots: List[Dict[str, Any]],
    params: OmniNarrationParams,
    total_chunks: int,
    user_prompt_template: str,
) -> str:
    a, b = meta["slice"]
    chunk_results = results[a:b]
    chunk_copy = "\n".join([str(item.get("text", "") or "") for item in chunk_results]).strip()
    if not chunk_copy:
        raise ValueError(f"第 {meta['chunk_index'] + 1} 批文案为空")

    retrieval_text_c = _build_retrieval_candidates(
        chunk_results,
        item_limit=min(params.max_items_for_retrieval, len(chunk_results)),
    )
    w_start, w_end = meta["window_start"], meta["window_end"]
    filtered_shots = _filter_shots_by_time_window(all_shots, w_start, w_end)
    if not filtered_shots:
        pass
    timeline_shots = _filter_shots_by_time_window(
        _expand_timeline_shots_by_shot_id_redundancy(
            all_shots, filtered_shots, params.timeline_shot_id_redundancy_ratio
        ),
        w_start,
        w_end,
    )
    timeline_text_c = _build_timeline_scenes(
        timeline_shots, max_scenes=len(timeline_shots), step=1
    )
    outline_text_c = _build_copywriting_outline(chunk_results)

    chunk_suffix_c = CHUNK_TASK_SUFFIX.format(
        batch_cur=meta["chunk_index"] + 1,
        batch_total=total_chunks,
        line_start=meta["line_start_1based"],
        line_end=meta["line_end_1based"],
        line_count=meta["line_count"],
        win_start_fmt=_format_ts(w_start),
        win_end_fmt=_format_ts(w_end),
        win_start_sec=w_start,
        win_end_sec=w_end,
    )

    copy_block = (
        "\n## 本批解说文案正文（须完整拆分，仅可拆分不得改写）\n"
        "<chunk_copywriting>\n"
        f"{chunk_copy}\n"
        "</chunk_copywriting>\n"
    )
    retrieval_block_c = (
        "## 检索候选摘要（每条仅 Top1）\n"
        "<retrieval_candidates>\n"
        f"{retrieval_text_c}\n"
        "</retrieval_candidates>\n"
    )
    timeline_block_c = (
        "\n## 全片镜头列表（本批时间窗口内）\n"
        "<timeline_scenes>\n"
        f"{timeline_text_c}\n"
        "</timeline_scenes>\n"
    )
    dynamic_sections_c = "\n" + copy_block + retrieval_block_c + chunk_suffix_c + timeline_block_c

    fmt_kw = dict(
        copywriting=chunk_copy,
        copywriting_outline=outline_text_c,
        retrieval_candidates=retrieval_text_c,
        timeline_scenes=timeline_text_c,
        dynamic_sections=dynamic_sections_c,
    )
    user_prompt_c = user_prompt_template.format(**fmt_kw)
    if "{dynamic_sections}" not in user_prompt_template:
        user_prompt_c += chunk_suffix_c
    return user_prompt_c


def post_check_chunk_items(items: List[Dict[str, Any]]) -> None:
    """校验单批模型输出（会原地修正 id、过短片段等）。"""
    _post_check_items(items)


def merge_chunk_items(chunk_items_in_order: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """按批顺序拼接各批 items，并重编号 _id。"""
    merged_raw: List[Dict[str, Any]] = []
    for items in chunk_items_in_order:
        merged_raw.extend(items)
    out: List[Dict[str, Any]] = []
    for idx, item in enumerate(merged_raw, start=1):
        out.append(
            {
                "_id": idx,
                "timestamp": str(item.get("timestamp", "")),
                "narration": str(item.get("narration", "")),
                "OST": 1 if item.get("OST") == 1 else 0,
            }
        )
    return out


def normalize_items_for_validation(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"items": items}


def omni_items_to_video_script(items: List[Dict[str, Any]], total_duration: float) -> Dict[str, Any]:
    """
    与 `ScriptGenerationService.to_video_script` 一致，生成项目 `script` 字段结构。
    items：已通过 validate_script_items 或 merge_chunk_items 的列表元素。
    """
    segments: List[Dict[str, Any]] = []
    for it in items:
        start_s, end_s = parse_timestamp_pair_seconds(str(it.get("timestamp")))
        text = str(it.get("narration", "")).strip()
        seg = {
            "id": str(it.get("_id", len(segments) + 1)),
            "start_time": float(start_s),
            "end_time": float(end_s),
            "text": text,
            "OST": it.get("OST", 0),
        }
        segments.append(seg)

    now = datetime.now()
    generated_time = now.isoformat()
    version = f"{now.strftime('%Y%m%d%H%M%S')}"
    return {
        "生成时间": generated_time,
        "条数": len(segments),
        "version": version,
        "total_duration": float(total_duration or 0.0),
        "segments": segments,
        "metadata": {
            "created_at": generated_time,
        },
    }
