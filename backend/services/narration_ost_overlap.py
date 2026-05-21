"""
配音延长与原片（播放原片）片段在素材时间轴上的相交处理。

当解说需要的素材时长向后延伸，与脚本中下一段「播放原片」区间相交时，
将下一段的起剪点设为解说延长后的素材终点，避免两段共用重叠素材。
若调整后「播放原片」剩余时长小于阈值则丢弃该段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def segment_is_play_original(seg: Optional[Dict[str, Any]]) -> bool:
    if not seg or not isinstance(seg, dict):
        return False
    text = str(seg.get("text") or "").strip()
    ost_flag = seg.get("OST")
    return (ost_flag == 1) or text.startswith("播放原")


@dataclass(frozen=True)
class NarrationExtendOstResolveResult:
    narration_start: float
    narration_duration: float
    skip_next_segment: bool
    """为 True 时表示应整体跳过下一段（通常为剩余过短的播放原片）。"""
    next_ost_start_override: Optional[float]
    """不为 None 且未跳过时，作为下一段播放原片的 start_time（秒，素材时间）。"""


def resolve_narration_extend_vs_following_play_original(
    *,
    narration_new_start: float,
    narration_new_dur: float,
    next_segment: Optional[Dict[str, Any]],
    video_duration: float,
    min_play_original_duration_s: float = 2.0,
    eps: float = 1e-3,
) -> NarrationExtendOstResolveResult:
    """
    在已根据配音时长算出解说段的素材起点与时长后，检测是否与下一段「播放原片」相交并做调整意图解析。

    规则：
    - 仅当下一段为播放原片且与当前解说素材区间 [start, start+dur) 在时间上相交时处理。
    - 将下一段播放原片的起始裁剪点对齐到当前解说素材区间的末尾（避免相交）。
    - 若对齐后播放原片剩余时长 < min_play_original_duration_s，则标记 skip_next_segment（丢弃）。

    返回值中的 narration_start / narration_duration 不会被缩短；丢弃的是下一段播放原片。
    """
    ns = max(0.0, float(narration_new_start))
    nd = max(0.0, float(narration_new_dur))
    narr_end = ns + nd

    if next_segment is None or not segment_is_play_original(next_segment):
        return NarrationExtendOstResolveResult(ns, nd, False, None)

    next_st = float(next_segment.get("start_time") or 0.0)
    next_et = float(next_segment.get("end_time") or 0.0)
    if video_duration and video_duration > 0 and next_et > video_duration:
        next_et = float(video_duration)
    if next_et <= next_st + eps:
        return NarrationExtendOstResolveResult(ns, nd, False, None)

    overlaps = narr_end > next_st + eps and ns < next_et - eps
    if not overlaps:
        return NarrationExtendOstResolveResult(ns, nd, False, None)

    ost_new_start = narr_end
    ost_new_dur = next_et - ost_new_start

    if ost_new_dur < float(min_play_original_duration_s) - eps:
        return NarrationExtendOstResolveResult(ns, nd, True, None)

    if ost_new_start >= next_et - eps:
        return NarrationExtendOstResolveResult(ns, nd, True, None)

    return NarrationExtendOstResolveResult(ns, nd, False, ost_new_start)
