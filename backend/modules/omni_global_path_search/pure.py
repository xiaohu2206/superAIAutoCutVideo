# -*- coding: utf-8 -*-
"""Omni 全局路径搜索纯函数（Beam + 转场 + zigzag + refine；与 visual / .trae demo 无 import 耦合）。"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_RED = "\033[31m"
_RESET = "\033[0m"


def _red(text: str) -> str:
    return f"{_RED}{text}{_RESET}"


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if x != x:  # NaN
            return default
        return x
    except Exception:
        return default


def _strategy_enabled(cfg: Dict[str, Any], key: str, default: bool = True) -> bool:
    return bool(cfg.get(key, default))


def _rank_in_search_pool(row: List[Dict[str, Any]], shot_id: Any) -> Tuple[Optional[int], int]:
    """在 Step4.8 构建的候选矩阵行（已按基础分降序）中，选中镜头的 1-based 名次；找不到则为 None。"""
    n = len(row)
    if shot_id is None:
        return None, n
    for j, m in enumerate(row):
        if isinstance(m, dict) and m.get("shot_id") == shot_id:
            return j + 1, n
    return None, n


def _base_score(match_item: Dict[str, Any]) -> float:
    # 优先使用 Step4.5 的 final_score；退化到 score / rerank_score / embedding_score
    for k in ["final_score", "score", "rerank_score", "embedding_score"]:
        if k in match_item:
            return _to_float(match_item.get(k), 0.0)
    return 0.0


def _duration(shot: Dict[str, Any]) -> float:
    return max(0.0, _to_float(shot.get("end"), 0.0) - _to_float(shot.get("start"), 0.0))


def _shot_midpoint(shot: Dict[str, Any]) -> float:
    start = _to_float(shot.get("start"), 0.0)
    end = _to_float(shot.get("end"), 0.0)
    return max(0.0, start + max(0.0, end - start) / 2.0)


def _copy_point_ratio(index: int, total: int) -> float:
    if total <= 1:
        return 0.0
    return float(index) / float(total - 1)


def _progressive_penalty(
    value: float,
    threshold: float,
    step: float,
    max_penalty: float,
    base_penalty: float = 0.0,
) -> float:
    """
    当 value 超过 threshold 时，按 step 线性累加惩罚，直到 max_penalty。
    返回值恒为 <= 0。
    """
    if value <= threshold:
        return 0.0
    step = max(1e-6, step)
    max_penalty = abs(max_penalty)
    base_penalty = abs(base_penalty)
    exceed = value - threshold
    penalty = base_penalty + exceed / step
    return -min(max_penalty, penalty)


def _transition_score_breakdown(
    prev_shot: Optional[Dict[str, Any]], cur_shot: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    与 _transition_score 一致，额外返回每项子分的说明（用于日志）。
    规则：gap = cur_start - prev_end；正向大跳不单独罚；若 gap<0（时间轴回退）则按回退幅度扣分。
    连续三段的 zigzag 摆动在全局项 timeline_zigzag 处理。
    """
    if prev_shot is None:
        return 0.0, {
            "role": "首段",
            "note": "无上一镜头，衔接分=0",
            "transition_total": 0.0,
        }

    score = 0.0
    prev_end = _to_float(prev_shot.get("end"), 0.0)
    cur_start = _to_float(cur_shot.get("start"), 0.0)
    gap = cur_start - prev_end

    time_continuity = 0.0
    score += time_continuity

    gap_penalty = 0.0
    score += gap_penalty

    overlap_penalty = 0.0
    score += overlap_penalty

    backward_jump_penalty = 0.0
    if gap < 0 and _strategy_enabled(cfg or {}, "enable_backward_jump_penalty", True):
        rollback_sec = -gap
        backward_jump_penalty = _progressive_penalty(
            value=rollback_sec,
            threshold=0.0,
            step=8.0,
            max_penalty=8.0,
            base_penalty=1,
        )
    score += backward_jump_penalty

    prev_dur = _duration(prev_shot)
    cur_dur = _duration(cur_shot)

    detail: Dict[str, Any] = {
        "prev_shot_id": prev_shot.get("shot_id"),
        "cur_shot_id": cur_shot.get("shot_id"),
        "prev_end": prev_end,
        "cur_start": cur_start,
        "gap_seconds": gap,
        "time_continuity": time_continuity,
        "time_continuity_rule": "该项固定 0.0；时间方向由 backward_jump_penalty 表示",
        "gap_penalty": gap_penalty,
        "gap_penalty_rule": "允许跨时间跳；该项固定 0.0",
        "overlap_penalty": overlap_penalty,
        "overlap_penalty_rule": "允许跨时间跳；该项固定 0.0",
        "backward_jump_penalty": backward_jump_penalty,
        "backward_jump_penalty_rule": "gap<0 时按回退秒数渐进惩罚，最多 -8.0（cur_start 早于 prev_end）",
        "prev_duration_sec": prev_dur,
        "cur_duration_sec": cur_dur,
        "transition_total": score,
    }
    return score, detail


def _transition_score(prev_shot: Optional[Dict[str, Any]], cur_shot: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> float:
    return _transition_score_breakdown(prev_shot, cur_shot, cfg)[0]


def _beam_width(i: int, total: int, cfg: Dict[str, Any]) -> int:
    if not _strategy_enabled(cfg, "enable_dynamic_beam_width", True):
        mid = int(cfg.get("beam_width_mid", 5) or 5)
        return max(1, mid)

    early = int(cfg.get("beam_width_early", 8) or 8)
    mid = int(cfg.get("beam_width_mid", 5) or 5)
    late = int(cfg.get("beam_width_late", 3) or 3)

    if total <= 0:
        return max(1, mid)
    ratio = float(i) / float(total)
    if ratio < 0.3:
        return max(1, early)
    if ratio < 0.7:
        return max(1, mid)
    return max(1, late)


def _repair_short_outlier_runs(
    shots: List[Dict[str, Any]],
    matrix: List[List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    smoothing_detail: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not bool(cfg.get("enable_short_outlier_run_repair", True)):
        return shots, {"enabled": False, "repaired_count": 0, "runs": [], "replacements": []}

    total = len(shots)
    if total < 3:
        return shots, {"enabled": True, "repaired_count": 0, "runs": [], "replacements": []}

    disallow_repeat = bool(cfg.get("disallow_repeat_shot", True))
    candidate_top_k = int(cfg.get("short_outlier_run_candidate_top_k", cfg.get("smooth_candidate_top_k", 12)) or 12)
    max_run_length = max(1, int(cfg.get("short_outlier_run_max_length", 3) or 3))
    residual_threshold = max(0.0, _to_float(cfg.get("short_outlier_run_residual_threshold", cfg.get("smooth_outlier_residual_threshold", 120.0)), 120.0))
    padding = max(0.0, _to_float(cfg.get("short_outlier_run_time_padding", 45.0), 45.0))

    best_shots = list(shots)
    best_score = _path_score(best_shots, cfg)
    run_indices: List[List[int]] = []

    repair_runs: List[Dict[str, Any]] = []
    replacements: List[Dict[str, Any]] = []

    for run in run_indices:
        left = run[0] - 1
        right = run[-1] + 1
        if left < 0 or right >= total:
            continue

        left_mid = _shot_midpoint(best_shots[left])
        right_mid = _shot_midpoint(best_shots[right])
        span = right - left
        if span <= 0:
            continue

        expected_midpoints: List[float] = []
        current_residuals: List[float] = []
        should_repair = False
        for idx in run:
            ratio = float(idx - left) / float(span)
            expected_mid = left_mid + (right_mid - left_mid) * ratio
            expected_midpoints.append(expected_mid)
            cur_mid = _shot_midpoint(best_shots[idx])
            residual = abs(cur_mid - expected_mid)
            current_residuals.append(residual)
            if residual >= residual_threshold:
                should_repair = True
        if not should_repair:
            continue

        trial = list(best_shots)
        run_replacements: List[Dict[str, Any]] = []
        failed = False
        for offset, idx in enumerate(run):
            expected_mid = expected_midpoints[offset]
            current = trial[idx]
            current_sid = current.get("shot_id")
            current_mid = _shot_midpoint(current)
            current_residual = abs(current_mid - expected_mid)
            window_min = min(left_mid, right_mid) - padding
            window_max = max(left_mid, right_mid) + padding

            alternatives = matrix[idx] if idx < len(matrix) else []
            if candidate_top_k > 0:
                alternatives = alternatives[:candidate_top_k]

            best_alt = None
            best_alt_key = None
            for alt in alternatives:
                alt_sid = alt.get("shot_id")
                if alt_sid == current_sid:
                    continue
                if disallow_repeat and alt_sid is not None:
                    duplicated = any(j != idx and trial[j].get("shot_id") == alt_sid for j in range(len(trial)))
                    if duplicated:
                        continue

                alt_mid = _shot_midpoint(alt)
                if alt_mid < window_min or alt_mid > window_max:
                    continue
                alt_residual = abs(alt_mid - expected_mid)
                if alt_residual >= current_residual:
                    continue

                alt_score = _base_score(alt)
                sort_key = (alt_residual, -alt_score)
                if best_alt_key is None or sort_key < best_alt_key:
                    best_alt_key = sort_key
                    best_alt = alt

            if best_alt is None:
                failed = True
                break

            trial[idx] = best_alt
            run_replacements.append(
                {
                    "index": idx,
                    "from_shot_id": current_sid,
                    "to_shot_id": best_alt.get("shot_id"),
                    "expected_mid": expected_mid,
                    "residual_before": current_residual,
                    "residual_after": abs(_shot_midpoint(best_alt) - expected_mid),
                }
            )

        if failed:
            continue

        trial_score = _path_score(trial, cfg)
        if trial_score + 1e-6 < best_score:
            continue

        best_shots = trial
        best_score = trial_score
        replacements.extend(run_replacements)
        repair_runs.append(
            {
                "run_indices": run,
                "left_anchor_index": left,
                "right_anchor_index": right,
                "left_anchor_shot_id": best_shots[left].get("shot_id"),
                "right_anchor_shot_id": best_shots[right].get("shot_id"),
                "expected_midpoints": expected_midpoints,
                "residuals_before": current_residuals,
                "trial_score": trial_score,
            }
        )

    detail = {
        "enabled": True,
        "repaired_count": len(replacements),
        "runs": repair_runs,
        "replacements": replacements,
        "score_after_repair": best_score,
    }
    if isinstance(smoothing_detail, dict):
        replaced_idx = set(int(x.get("index", -1)) for x in replacements)
        merged_replacements = list(smoothing_detail.get("replacements") or [])
        remaining_replacements = [x for x in merged_replacements if int(x.get("index", -1)) not in replaced_idx]
        detail["merged_from_polyline_smoothing"] = len(remaining_replacements)
    return best_shots, detail


def _smooth_polyline_outliers(
    shots: List[Dict[str, Any]],
    matrix: List[List[Dict[str, Any]]],
    cfg: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not bool(cfg.get("enable_polyline_smoothing", True)):
        return shots, {"enabled": False, "replaced_count": 0, "outlier_indices": [], "replacements": []}

    def _local_curvature_cost(prev_mid: float, cur_mid: float, next_mid: float) -> float:
        return abs((cur_mid - prev_mid) - (next_mid - cur_mid))

    best_shots = list(shots)
    best_score = _path_score(best_shots, cfg)
    refine_top_k = int(cfg.get("smooth_candidate_top_k", cfg.get("refine_candidate_top_k", 12)) or 12)
    disallow_repeat = bool(cfg.get("disallow_repeat_shot", True))
    min_improve = _to_float(cfg.get("smooth_min_score_improve", 1e-6), 1e-6)
    curvature_weight = max(0.0, _to_float(cfg.get("smooth_curvature_penalty_weight", cfg.get("smooth_residual_penalty_weight", 0.05)), 0.05))
    residual_weight = max(0.0, _to_float(cfg.get("smooth_residual_penalty_weight", 0.05), 0.05))
    residual_improve_ratio = min(1.0, max(0.0, _to_float(cfg.get("smooth_residual_improve_ratio", 0.25), 0.25)))
    residual_hard_cap = max(0.0, _to_float(cfg.get("smooth_residual_hard_cap", 0.0), 0.0))

    outlier_indices: List[int] = []
    outlier_details: Dict[int, Dict[str, Any]] = {}
    replacements: List[Dict[str, Any]] = []

    for i in outlier_indices:
        alternatives = matrix[i] if i < len(matrix) else []
        if refine_top_k > 0:
            alternatives = alternatives[:refine_top_k]
        if not alternatives:
            continue

        current = best_shots[i]
        current_sid = current.get("shot_id")
        prev_mid = _shot_midpoint(best_shots[i - 1])
        next_mid = _shot_midpoint(best_shots[i + 1])
        baseline_mid = (prev_mid + next_mid) / 2.0
        current_mid = _shot_midpoint(current)
        current_residual = abs(current_mid - baseline_mid)
        current_curvature = _local_curvature_cost(prev_mid, current_mid, next_mid)
        residual_target = current_residual * (1.0 - residual_improve_ratio)

        best_local_shots = best_shots
        best_local_score = best_score
        best_local_curvature = current_curvature
        best_local_residual = current_residual
        chosen_alt: Optional[Dict[str, Any]] = None

        for alt in alternatives:
            alt_sid = alt.get("shot_id")
            if alt_sid == current_sid:
                continue

            if disallow_repeat and alt_sid is not None:
                duplicated = any(j != i and best_shots[j].get("shot_id") == alt_sid for j in range(len(best_shots)))
                if duplicated:
                    continue

            alt_mid = _shot_midpoint(alt)
            alt_curvature = _local_curvature_cost(prev_mid, alt_mid, next_mid)
            if alt_curvature >= best_local_curvature:
                continue

            alt_residual = abs(alt_mid - baseline_mid)
            if alt_residual >= current_residual:
                continue
            if alt_residual > residual_target:
                continue
            if residual_hard_cap > 0.0 and alt_residual > residual_hard_cap:
                continue

            trial = list(best_shots)
            trial[i] = alt
            trial_score = _path_score(trial, cfg)
            adjusted_trial_score = trial_score - alt_curvature * curvature_weight - alt_residual * residual_weight
            adjusted_best_score = best_local_score - best_local_curvature * curvature_weight - best_local_residual * residual_weight
            if adjusted_trial_score <= adjusted_best_score + min_improve:
                continue

            best_local_shots = trial
            best_local_score = trial_score
            best_local_curvature = alt_curvature
            best_local_residual = alt_residual
            chosen_alt = alt

        if chosen_alt is not None:
            replacements.append(
                {
                    "index": i,
                    "from_shot_id": current_sid,
                    "to_shot_id": chosen_alt.get("shot_id"),
                    "baseline_mid": baseline_mid,
                    "residual_before": current_residual,
                    "residual_after": best_local_residual,
                    "residual_target": residual_target,
                    "residual_hard_cap": residual_hard_cap,
                    "curvature_before": current_curvature,
                    "curvature_after": best_local_curvature,
                    "score_after": best_local_score,
                }
            )
            best_shots = best_local_shots
            best_score = best_local_score

    return best_shots, {
        "enabled": True,
        "replaced_count": len(replacements),
        "outlier_indices": outlier_indices,
        "outlier_details": outlier_details,
        "replacements": replacements,
        "score_after_smoothing": best_score,
    }


def _global_adjustment_breakdown(shots: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> Tuple[float, Dict[str, Any]]:
    if not shots:
        return -9999.0, {"note": "空路径", "global_adjustment_total": -9999.0}

    adjust = 0.0
    detail: Dict[str, Any] = {"shot_count": len(shots)}

    # 只惩罚 zigzag：允许单次跨时间跳；对“前跳→回跳”与“回跳→前跳”两种摆动都处罚
    gaps: List[float] = []
    for i in range(1, len(shots)):
        prev_end = _to_float(shots[i - 1].get("end"), 0.0)
        cur_start = _to_float(shots[i].get("start"), 0.0)
        gaps.append(cur_start - prev_end)

    zigzag_threshold_out = 45.0
    zigzag_threshold_back = 20.0
    zigzag_penalty_total = 0.0
    zigzag_events: List[Dict[str, Any]] = []
    if _strategy_enabled(cfg or {}, "enable_timeline_zigzag_penalty", True):
        for i in range(1, len(gaps)):
            jump_out = gaps[i - 1]
            jump_back = gaps[i]
            forward_then_back = jump_out > zigzag_threshold_out and jump_back < -zigzag_threshold_back
            back_then_forward = jump_out < -zigzag_threshold_back and jump_back > zigzag_threshold_out
            if not (forward_then_back or back_then_forward):
                continue

            # 按“摆动两侧”中较小的有效跳幅计罚，避免单边异常放大
            zigzag_strength = min(abs(jump_out) - zigzag_threshold_back, abs(jump_back) - zigzag_threshold_out)
            event_penalty = _progressive_penalty(
                value=zigzag_strength,
                threshold=0.0,
                step=10.0,
                max_penalty=10.0,
                base_penalty=2.0,
            )
            zigzag_penalty_total += event_penalty
            zigzag_events.append(
                {
                    "index_triplet": (i - 1, i, i + 1),
                    "jump_out_seconds": jump_out,
                    "jump_back_seconds": jump_back,
                    "zigzag_pattern": "forward_then_back" if forward_then_back else "back_then_forward",
                    "zigzag_strength": zigzag_strength,
                    "event_penalty": event_penalty,
                }
            )

    adjust += zigzag_penalty_total
    detail["timeline_zigzag"] = {
        "zigzag_count": len(zigzag_events),
        "zigzag_penalty_total": zigzag_penalty_total,
        "threshold_out_seconds": zigzag_threshold_out,
        "threshold_back_seconds": zigzag_threshold_back,
        "rule": "当连续三段出现「大幅前跳→明显回跳」或「明显回跳→大幅前跳」时按摆动强度渐进惩罚，单次事件最多 -10.0；单次跳跃不惩罚",
        "zigzag_examples": zigzag_events[:5],
    }

    detail["global_adjustment_total"] = adjust
    return adjust, detail


def _global_adjustment(shots: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> float:
    return _global_adjustment_breakdown(shots, cfg)[0]


def _path_score_breakdown(shots: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> Tuple[float, Dict[str, Any]]:
    if not shots:
        return -9999.0, {"note": "空路径", "path_total": -9999.0}

    local = 0.0
    prev = None
    segments: List[Dict[str, Any]] = []
    for idx, s in enumerate(shots):
        b = _base_score(s)
        t, td = _transition_score_breakdown(prev, s, cfg)
        seg = b + t
        local += seg
        segments.append(
            {
                "segment_index": idx,
                "shot_id": s.get("shot_id"),
                "base_score": b,
                "base_score_rule": "match 上 final_score → score → rerank_score → embedding_score",
                "transition_detail": td,
                "segment_subtotal_base_plus_transition": seg,
            }
        )
        prev = s

    gadj, gdetail = _global_adjustment_breakdown(shots, cfg)
    total = local + gadj
    return total, {
        "formula": "path_total = Σ(base_score + transition) + global_adjustment",
        "local_sum": local,
        "global_adjustment_detail": gdetail,
        "global_adjustment_total": gadj,
        "path_total": total,
        "segments": segments,
    }


def _path_score(shots: List[Dict[str, Any]], cfg: Optional[Dict[str, Any]] = None) -> float:
    if not shots:
        return -9999.0
    return _path_score_breakdown(shots, cfg)[0]


# 衔接分项 key → 中文说明（用于日志加分/扣分明细）
_LOCAL_TRANSITION_LABELS: Dict[str, str] = {
    "time_continuity": "时间轴连续性（或回跳惩罚，依符号）",
    "gap_penalty": "相邻镜时间间隔过大惩罚",
    "overlap_penalty": "相邻镜时间重叠过大惩罚",
    "backward_jump_penalty": "时间轴回退惩罚（当前镜起点早于上一镜终点）",
}


def _local_bonus_penalty_items(
    base: float, td: Dict[str, Any]
) -> Tuple[float, float, List[Tuple[str, float]], List[Tuple[str, float]]]:
    """
    将「基分 + 衔接分项」拆成加分合计、扣分合计，以及带中文标签的分项列表。
    扣分列表中数值均为惩罚的绝对值（正数）。
    """
    bonus = 0.0
    penalty = 0.0
    bonus_items: List[Tuple[str, float]] = []
    penalty_items: List[Tuple[str, float]] = []

    if base > 0:
        bonus += base
        bonus_items.append(("文案-镜头匹配基分（Step4.5 语义相似度）", base))
    elif base < 0:
        ap = abs(base)
        penalty += ap
        penalty_items.append(("文案-镜头匹配基分（负值，极少见）", ap))

    part_keys = (
        "time_continuity",
        "gap_penalty",
        "overlap_penalty",
        "backward_jump_penalty",
    )
    for k in part_keys:
        v = _to_float(td.get(k), 0.0)
        if v == 0:
            continue
        label = _LOCAL_TRANSITION_LABELS.get(k, k)
        if v > 0:
            bonus += v
            bonus_items.append((label, v))
        else:
            ap = abs(v)
            penalty += ap
            penalty_items.append((label, ap))

    return bonus, penalty, bonus_items, penalty_items


def _format_labeled_items(items: List[Tuple[str, float]], kind: str) -> str:
    """kind: 'bonus' 显示 +x.xxxx；'penalty' 显示幅度 x.xxxx。"""
    if not items:
        return "（无）"
    parts: List[str] = []
    for lab, val in items:
        if kind == "bonus":
            parts.append(f"{lab} +{val:.4f}")
        else:
            parts.append(f"{lab} {val:.4f}")
    return "；".join(parts)


def _global_bonus_penalty_items(gdetail: Dict[str, Any]) -> Tuple[float, float, List[Tuple[str, float]], List[Tuple[str, float]]]:
    """全局项分项（中文标签）与合计。"""
    bonus = 0.0
    penalty = 0.0
    bonus_items: List[Tuple[str, float]] = []
    penalty_items: List[Tuple[str, float]] = []

    zz = gdetail.get("timeline_zigzag") or {}
    zpt = _to_float(zz.get("zigzag_penalty_total"), 0.0)
    if zpt > 0:
        bonus += zpt
        bonus_items.append(("时间线 zigzag（先跳远再跳回）相关", zpt))
    elif zpt < 0:
        ap = abs(zpt)
        penalty += ap
        penalty_items.append(("时间线 zigzag 拉扯惩罚（渐进罚分累加）", ap))

    return bonus, penalty, bonus_items, penalty_items


def _log_path_score_breakdown(
    best_shots: List[Dict[str, Any]],
    refine_global_score: float,
    matrix: List[List[Dict[str, Any]]],
    results: List[Dict[str, Any]],
    compare_top: int = 3,
) -> None:
    """
    每条文案（item）输出前 compare_top 个候选的加分/扣分对比；末尾输出整条路径的全局项加分/扣分。
    局部对比固定使用「当前全局最优路径里上一镜」作为上一镜头，仅反映该段的基分+衔接，不含换候选后全局项变化。
    """
    _, bd = _path_score_breakdown(best_shots)
    path_total = _to_float(bd.get("path_total"), -9999.0)
    local_sum = _to_float(bd.get("local_sum"), 0.0)
    gadj = _to_float(bd.get("global_adjustment_total"), 0.0)

    logger.info(
        "======== Step4.8 评分日志（每项候选对比 + 全局汇总）========"
    )
    logger.info(
        "【加分 / 扣分在局部对比里分别指什么】\n"
        "  · 加分合计：本段内所有「正向」得分的总和。主要包括：① 基分——来自 Step4.5 重排序的 final_score（"
        "或 score / rerank_score / embedding_score），表示文案与该镜头语义、画面的匹配程度，越高越贴合。\n"
        "  · 扣分合计：本段内所有「惩罚」的绝对值之和（日志里用正数表示惩罚幅度）。主要包括：① 基分为负时"
        "（极少见）计入；② 时间轴回退——当前镜起点早于上一镜终点（gap<0）时按回退幅度扣分。\n"
        "  · 三项对比：同一文案段取重排序后的前 %d 个候选镜头，在「上一镜已固定为当前全局最优路径中的上一镜」"
        "前提下，分别计算各候选的加分合计与扣分合计，便于并排比较；标有「★已选」者为 Beam+回溯后本段最终采用的镜头。",
        max(1, compare_top),
    )
    logger.info(
        "【整条路径】refine_global_score=%.6f | 分解 path_total=%.6f | "
        "局部小计 Σ(基分+衔接)=%.6f | 全局调整 global_adjustment=%.6f",
        refine_global_score,
        path_total,
        local_sum,
        gadj,
    )

    if abs(path_total - refine_global_score) > 1e-4:
        logger.warning(
            "refine_global_score 与 path_total 差异超过 1e-4: refine=%.6f path_total=%.6f",
            refine_global_score,
            path_total,
        )

    n = min(len(best_shots), len(matrix), len(results))
    for i in range(n):
        prev = best_shots[i - 1] if i > 0 else None
        prev_sid = prev.get("shot_id") if isinstance(prev, dict) else None
        chosen = best_shots[i]
        chosen_sid = chosen.get("shot_id") if isinstance(chosen, dict) else None

        row = results[i] if isinstance(results[i], dict) else {}
        raw_text = str(row.get("text") or row.get("copywriting") or "")
        text_preview = raw_text.replace("\n", " ")[:48]
        if len(raw_text) > 48:
            text_preview += "…"

        cands = matrix[i][: max(1, compare_top)] if i < len(matrix) else []
        logger.info(
            "---- 文案段 #%d | 上一镜 shot_id=%s | 文案摘要: %s",
            i,
            prev_sid if prev_sid is not None else "（首段无）",
            text_preview or "（无文案字段）",
        )

        if not cands:
            logger.info("  （无候选，跳过三项对比）")
            continue

        for rank, cand in enumerate(cands, start=1):
            sid = cand.get("shot_id")
            b = _base_score(cand)
            _, td = _transition_score_breakdown(prev, cand)
            bonus, pen_mag, b_items, p_items = _local_bonus_penalty_items(b, td)
            tag = " ★已选" if sid is not None and sid == chosen_sid else ""
            logger.info(
                "  候选%d | shot_id=%s%s | 加分合计 +%.4f | 扣分合计 %.4f",
                rank,
                sid,
                tag,
                bonus,
                pen_mag,
            )
            logger.info("    加分项：%s", _format_labeled_items(b_items, "bonus"))
            rollback_hit = _to_float(td.get("backward_jump_penalty"), 0.0) < 0
            local_penalty_line = "    扣分项：%s"
            if rollback_hit:
                local_penalty_line = _red(local_penalty_line)
            logger.info(local_penalty_line, _format_labeled_items(p_items, "penalty"))

    gdetail = bd.get("global_adjustment_detail") or {}
    gb, gp, g_b_items, g_p_items = _global_bonus_penalty_items(gdetail)
    logger.info("---- 全局项（作用于整条已选路径，不拆到单段）----")
    logger.info(
        "【全局加分/扣分含义】\n"
        "  · 时间 zigzag 惩罚：若连续三段出现「先大幅向前跳再回跳」或「先回跳再大幅向前跳」的模式，认为叙事在时间线上"
        "来回拉扯，按事件累加惩罚（具体阈值与渐进罚分见配置与 timeline_zigzag）。"
    )
    logger.info(
        "  全局加分合计 +%.4f | 全局扣分合计 %.4f | 全局调整代数和 %.4f",
        gb,
        gp,
        gadj,
    )
    logger.info("  全局加分项：%s", _format_labeled_items(g_b_items, "bonus"))
    zz = gdetail.get("timeline_zigzag") or {}
    zigzag_hit = _to_float(zz.get("zigzag_penalty_total"), 0.0) < 0
    global_penalty_line = "  全局扣分项：%s"
    if zigzag_hit:
        global_penalty_line = _red(global_penalty_line)
    logger.info(global_penalty_line, _format_labeled_items(g_p_items, "penalty"))


def _build_candidate_matrix(
    results: List[Dict[str, Any]],
    candidate_top_k: int,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[List[Dict[str, Any]]]:
    matrix: List[List[Dict[str, Any]]] = []
    if not _strategy_enabled(cfg or {}, "enable_candidate_truncation", True):
        candidate_top_k = 0
    for r in results:
        matches = r.get("matches") if isinstance(r, dict) else []
        if not isinstance(matches, list):
            matches = []
        items = [m for m in matches if isinstance(m, dict)]
        items.sort(key=lambda x: _base_score(x), reverse=True)
        if candidate_top_k > 0:
            items = items[:candidate_top_k]
        matrix.append(items)
    return matrix


def _init_paths(first_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    paths: List[Dict[str, Any]] = []
    for c in first_candidates:
        sid = c.get("shot_id")
        used = set()
        if sid is not None:
            used.add(sid)
        paths.append(
            {
                "shots": [c],
                "score": _base_score(c),
                "used_shot_ids": used,
            }
        )
    return paths


def _expand_paths(
    paths: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    i: int,
    total: int,
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not paths:
        return []
    if not _strategy_enabled(cfg, "enable_path_expansion", True):
        # 不调 Beam 多分支扩展时，仍须把本段候选接到路径上，否则 shots 长度永远为 1。
        # 行为：对保留的每条父路径，只接一个镜头——优先第一个满足「不重复 shot」的候选，否则用候选列表首项。
        beam = max(1, _beam_width(i, total, cfg))
        disallow_repeat = bool(cfg.get("disallow_repeat_shot", True))
        expanded_greedy: List[Dict[str, Any]] = []
        for p in paths[:beam]:
            prev = p["shots"][-1] if p["shots"] else None
            chosen: Optional[Dict[str, Any]] = None
            for c in candidates:
                sid = c.get("shot_id")
                if disallow_repeat and sid is not None and sid in p["used_shot_ids"]:
                    continue
                chosen = c
                break
            if chosen is None and candidates:
                chosen = candidates[0]
            if chosen is None:
                continue
            t = _transition_score(prev, chosen, cfg)
            new_score = _to_float(p.get("score"), 0.0) + _base_score(chosen) + t
            new_used = set(p["used_shot_ids"])
            sid = chosen.get("shot_id")
            if sid is not None:
                new_used.add(sid)
            expanded_greedy.append(
                {
                    "shots": p["shots"] + [chosen],
                    "score": new_score,
                    "used_shot_ids": new_used,
                }
            )
        return expanded_greedy

    disallow_repeat = bool(cfg.get("disallow_repeat_shot", True))
    beam = _beam_width(i, total, cfg)
    expanded: List[Dict[str, Any]] = []

    for p in paths:
        prev = p["shots"][-1] if p["shots"] else None
        for c in candidates:
            sid = c.get("shot_id")
            if disallow_repeat and sid is not None and sid in p["used_shot_ids"]:
                continue
            t = _transition_score(prev, c, cfg)
            new_score = _to_float(p.get("score"), 0.0) + _base_score(c) + t
            new_used = set(p["used_shot_ids"])
            if sid is not None:
                new_used.add(sid)
            expanded.append(
                {
                    "shots": p["shots"] + [c],
                    "score": new_score,
                    "used_shot_ids": new_used,
                }
            )

    if not _strategy_enabled(cfg, "enable_repeat_shot_fallback", True):
        return expanded[:beam]

    # 若严格防重复导致无法扩展，则退化允许重复，保证搜索不断
    if not expanded and disallow_repeat:
        for p in paths:
            prev = p["shots"][-1] if p["shots"] else None
            for c in candidates:
                t = _transition_score(prev, c, cfg)
                new_score = _to_float(p.get("score"), 0.0) + _base_score(c) + t
                new_used = set(p["used_shot_ids"])
                sid = c.get("shot_id")
                if sid is not None:
                    new_used.add(sid)
                expanded.append(
                    {
                        "shots": p["shots"] + [c],
                        "score": new_score,
                        "used_shot_ids": new_used,
                    }
                )

    expanded.sort(key=lambda x: _to_float(x.get("score"), -9999.0), reverse=True)
    return expanded[:beam]


def _refine_path(path: Dict[str, Any], matrix: List[List[Dict[str, Any]]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    if not bool(cfg.get("enable_refine", True)):
        out = dict(path)
        smoothed_shots, smoothing_detail = _smooth_polyline_outliers(path.get("shots") or [], matrix, cfg)
        repaired_shots, short_run_detail = _repair_short_outlier_runs(smoothed_shots, matrix, cfg, smoothing_detail)
        out["shots"] = repaired_shots
        out["global_score"] = _path_score(repaired_shots, cfg)
        out["polyline_smoothing"] = smoothing_detail
        out["short_outlier_run_repair"] = short_run_detail
        return out

    shots = list(path.get("shots") or [])
    if not shots:
        out = dict(path)
        out["global_score"] = -9999.0
        out["polyline_smoothing"] = {"enabled": False, "replaced_count": 0, "outlier_indices": [], "replacements": []}
        out["short_outlier_run_repair"] = {"enabled": False, "repaired_count": 0, "runs": [], "replacements": []}
        return out

    refine_top_k = int(cfg.get("refine_candidate_top_k", 3) or 3)
    disallow_repeat = bool(cfg.get("disallow_repeat_shot", True))

    best_shots = shots
    best_score = _path_score(best_shots, cfg)

    for i in range(len(shots)):
        alternatives = matrix[i] if i < len(matrix) else []
        if refine_top_k > 0:
            alternatives = alternatives[:refine_top_k]
        current = best_shots[i]
        current_sid = current.get("shot_id")
        for alt in alternatives:
            alt_sid = alt.get("shot_id")
            if alt_sid == current_sid:
                continue

            if disallow_repeat and alt_sid is not None:
                duplicated = any(j != i and best_shots[j].get("shot_id") == alt_sid for j in range(len(best_shots)))
                if duplicated:
                    continue

            trial = list(best_shots)
            trial[i] = alt
            trial_score = _path_score(trial, cfg)
            if trial_score > best_score:
                best_score = trial_score
                best_shots = trial

    best_shots, smoothing_detail = _smooth_polyline_outliers(best_shots, matrix, cfg)
    best_shots, short_run_detail = _repair_short_outlier_runs(best_shots, matrix, cfg, smoothing_detail)
    best_score = _path_score(best_shots, cfg)

    out = {
        "shots": best_shots,
        "score": _to_float(path.get("score"), 0.0),
        "used_shot_ids": set(s.get("shot_id") for s in best_shots if s.get("shot_id") is not None),
        "global_score": best_score,
        "polyline_smoothing": smoothing_detail,
        "short_outlier_run_repair": short_run_detail,
    }
    return out


def build_global_path_payload(
    rerank_payload: Dict[str, Any],
    gs_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对镜头匹配重排结果（含每段 matches 候选池）做全局路径搜索。
    语义对齐 aiSearchShot Step4.8：Beam Search、转场分、时间线 zigzag、refine、平滑与短离群修复等。
    """
    gs_cfg = dict(gs_cfg or {})

    candidate_top_k = int(gs_cfg.get("candidate_top_k", 3) or 3)
    keep_top_paths = int(gs_cfg.get("keep_top_paths", 5) or 5)
    keep_all_matches = bool(gs_cfg.get("keep_all_matches", True))
    output_matches_limit = int(gs_cfg.get("output_matches_limit", 30) or 30)

    payload = rerank_payload
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError("rerank 结果格式不正确，必须包含非空 results 数组")

    matrix = _build_candidate_matrix(results, candidate_top_k=candidate_top_k, cfg=gs_cfg)
    if not matrix or not matrix[0]:
        raise RuntimeError("全局路径搜索失败：第 1 条文案没有候选镜头")

    paths = _init_paths(matrix[0])
    total = len(matrix)

    for i in range(1, total):
        paths = _expand_paths(paths, matrix[i], i, total, gs_cfg)
        if not paths:
            raise RuntimeError(f"全局路径搜索失败：第 {i + 1} 条文案无法扩展路径")

    refined: List[Dict[str, Any]] = []
    for p in paths:
        refined.append(_refine_path(p, matrix, gs_cfg))
    refined.sort(key=lambda x: _to_float(x.get("global_score"), -9999.0), reverse=True)

    if not refined:
        raise RuntimeError("全局路径搜索失败：未生成有效路径")

    top_paths = refined[: max(1, keep_top_paths)]
    best = top_paths[0]
    best_shots = best.get("shots") or []
    smoothing_detail = best.get("polyline_smoothing") or {}
    if len(best_shots) != len(results):
        raise RuntimeError("全局路径搜索结果长度与 results 不一致")

    _log_path_score_breakdown(
        best_shots,
        _to_float(best.get("global_score"), 0.0),
        matrix,
        results,
        compare_top=min(3, max(1, candidate_top_k)),
    )

    out_results: List[Dict[str, Any]] = []
    for i, r in enumerate(results):
        out_item = dict(r) if isinstance(r, dict) else {"item_index": i, "text": ""}
        original_matches = out_item.get("matches") or []
        if not isinstance(original_matches, list):
            original_matches = []

        selected = copy.deepcopy(best_shots[i]) if i < len(best_shots) else None
        if selected is None:
            out_results.append(out_item)
            continue

        selected_sid = selected.get("shot_id")
        selected["global_path_selected"] = True

        if keep_all_matches:
            rest = []
            for m in original_matches:
                if not isinstance(m, dict):
                    continue
                if m.get("shot_id") == selected_sid:
                    continue
                rest.append(m)
            if output_matches_limit > 0:
                rest = rest[: max(0, output_matches_limit - 1)]
            out_item["matches"] = [selected] + rest
        else:
            out_item["matches"] = [selected]

        pool_row = matrix[i] if i < len(matrix) else []
        cand_rank, cand_pool = _rank_in_search_pool(pool_row, selected_sid)
        out_item["global_path"] = {
            "selected_shot_id": selected_sid,
            "selected_score": _base_score(selected),
            "candidate_rank_in_search_pool": cand_rank,
            "candidate_search_pool_size": cand_pool,
        }
        if isinstance(smoothing_detail, dict):
            replacement_detail = next(
                (x for x in (smoothing_detail.get("replacements") or []) if int(x.get("index", -1)) == i),
                None,
            )
            if replacement_detail:
                out_item["global_path"]["polyline_smoothing"] = {"replacement_detail": replacement_detail}
        short_run_detail = best.get("short_outlier_run_repair") or {}
        if isinstance(short_run_detail, dict):
            run_replacement_detail = next(
                (x for x in (short_run_detail.get("replacements") or []) if int(x.get("index", -1)) == i),
                None,
            )
            out_item["global_path"]["short_outlier_run_repair"] = {
                "replacement_detail": run_replacement_detail,
            }
        out_results.append(out_item)

    out_payload = {
        "meta": {
            "source": "omni_global_path_search",
            "candidate_top_k": candidate_top_k,
            "enable_candidate_truncation": _strategy_enabled(gs_cfg, "enable_candidate_truncation", True),
            "beam_width_early": int(gs_cfg.get("beam_width_early", 8) or 8),
            "beam_width_mid": int(gs_cfg.get("beam_width_mid", 5) or 5),
            "beam_width_late": int(gs_cfg.get("beam_width_late", 3) or 3),
            "enable_dynamic_beam_width": _strategy_enabled(gs_cfg, "enable_dynamic_beam_width", True),
            "enable_path_expansion": _strategy_enabled(gs_cfg, "enable_path_expansion", True),
            "disallow_repeat_shot": bool(gs_cfg.get("disallow_repeat_shot", True)),
            "enable_repeat_shot_fallback": _strategy_enabled(gs_cfg, "enable_repeat_shot_fallback", True),
            "enable_backward_jump_penalty": _strategy_enabled(gs_cfg, "enable_backward_jump_penalty", True),
            "enable_refine": bool(gs_cfg.get("enable_refine", True)),
            "refine_candidate_top_k": int(gs_cfg.get("refine_candidate_top_k", 3) or 3),
            "enable_polyline_smoothing": bool(gs_cfg.get("enable_polyline_smoothing", True)),
            "enable_short_outlier_run_repair": bool(gs_cfg.get("enable_short_outlier_run_repair", True)),
            "short_outlier_run_max_length": int(gs_cfg.get("short_outlier_run_max_length", 3) or 3),
            "short_outlier_run_candidate_top_k": int(gs_cfg.get("short_outlier_run_candidate_top_k", gs_cfg.get("smooth_candidate_top_k", 12)) or 12),
            "short_outlier_run_residual_threshold": _to_float(gs_cfg.get("short_outlier_run_residual_threshold", gs_cfg.get("smooth_outlier_residual_threshold", 120.0)), 120.0),
            "short_outlier_run_time_padding": _to_float(gs_cfg.get("short_outlier_run_time_padding", 45.0), 45.0),
            "smooth_candidate_top_k": int(gs_cfg.get("smooth_candidate_top_k", gs_cfg.get("refine_candidate_top_k", 12)) or 12),
            "smooth_skip_head_ratio": _to_float(gs_cfg.get("smooth_skip_head_ratio", 0.05), 0.05),
            "smooth_skip_tail_ratio": _to_float(gs_cfg.get("smooth_skip_tail_ratio", 0.10), 0.10),
            "smooth_outlier_residual_threshold": _to_float(gs_cfg.get("smooth_outlier_residual_threshold", 120.0), 120.0),
            "smooth_outlier_neighbor_gap_threshold": _to_float(gs_cfg.get("smooth_outlier_neighbor_gap_threshold", 90.0), 90.0),
            "smooth_residual_penalty_weight": _to_float(gs_cfg.get("smooth_residual_penalty_weight", 0.05), 0.05),
            "smooth_curvature_penalty_weight": _to_float(gs_cfg.get("smooth_curvature_penalty_weight", gs_cfg.get("smooth_residual_penalty_weight", 0.05)), 0.05),
            "smooth_min_score_improve": _to_float(gs_cfg.get("smooth_min_score_improve", 1e-6), 1e-6),
            "enable_timeline_zigzag_penalty": _strategy_enabled(gs_cfg, "enable_timeline_zigzag_penalty", True),
            "keep_top_paths": keep_top_paths,
            "keep_all_matches": keep_all_matches,
            "output_matches_limit": output_matches_limit,
            "best_global_score": _to_float(best.get("global_score"), 0.0),
            "polyline_smoothing": smoothing_detail,
            "short_outlier_run_repair": best.get("short_outlier_run_repair") or {},
            "generated_at": datetime.now().isoformat(),
        },
        "results": out_results,
        "global_paths": [
            {
                "rank": i + 1,
                "global_score": _to_float(p.get("global_score"), 0.0),
                "shot_ids": [s.get("shot_id") for s in (p.get("shots") or [])],
            }
            for i, p in enumerate(top_paths)
        ],
    }

    selected_lines = []
    for idx, item in enumerate(out_results):
        item_index = item.get("item_index", idx) if isinstance(item, dict) else idx
        global_path = item.get("global_path") if isinstance(item, dict) else {}
        if not isinstance(global_path, dict):
            global_path = {}
        matches = item.get("matches") if isinstance(item, dict) else []
        top1 = matches[0] if isinstance(matches, list) and matches and isinstance(matches[0], dict) else {}
        start = _to_float(top1.get("start"), 0.0)
        end = _to_float(top1.get("end"), 0.0)
        rank = global_path.get("candidate_rank_in_search_pool")
        pool_sz = global_path.get("candidate_search_pool_size")
        tags: List[str] = []
        if rank is not None and pool_sz:
            tags.append(f"搜索池第{rank}/{pool_sz}名")
        ps = global_path.get("polyline_smoothing") if isinstance(global_path.get("polyline_smoothing"), dict) else {}
        if ps.get("replacement_detail"):
            tags.append("折线平滑已替换")
        sr = global_path.get("short_outlier_run_repair") if isinstance(global_path.get("short_outlier_run_repair"), dict) else {}
        if sr.get("replacement_detail"):
            tags.append("短离群段桥接已替换")
        tag_suffix = f" | {'; '.join(tags)}" if tags else ""
        selected_lines.append(
            f"{item_index} => {global_path.get('selected_shot_id')} ({start:.3f}~{end:.3f}){tag_suffix}"
        )

    logger.info(
        "Omni 全局路径搜索完成；item_index => shot_id（搜索池名次=矩阵基分排序位）：\n%s",
        "\n".join(selected_lines),
    )
    return out_payload

