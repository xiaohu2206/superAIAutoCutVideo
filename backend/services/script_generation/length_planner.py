from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Tuple, List

from .constants import (
    CUSTOM_SCRIPT_LENGTH_MIN,
    CUSTOM_SCRIPT_LENGTH_MAX,
    DEFAULT_SCRIPT_LENGTH_SELECTION,
    SCRIPT_LENGTH_PRESETS,
)


@dataclass(frozen=True)
class ScriptTargetPlan:
    normalized_selection: str
    target_min: int
    target_max: int
    preferred_calls: int
    final_target_count: int


def _normalize_range_separators(value: str) -> str:
    return (
        value.replace(" ", "")
        .replace("~", "～")
        .replace("-", "～")
        .replace("—", "～")
        .replace("–", "～")
    )


def _format_range_key(a: int, b: int) -> str:
    return f"{int(a)}～{int(b)}条"


def _compute_custom_range(target: int) -> Optional[Tuple[int, int]]:
    if target <= 0:
        return None
    safe = max(CUSTOM_SCRIPT_LENGTH_MIN, min(CUSTOM_SCRIPT_LENGTH_MAX, int(target)))
    min_v = max(CUSTOM_SCRIPT_LENGTH_MIN, int(math.floor(safe * 0.8)))
    max_v = max(min_v, int(math.ceil(safe * 1.2)))
    max_v = min(CUSTOM_SCRIPT_LENGTH_MAX, max_v)
    return min_v, max_v


def _normalize_custom_range(a: int, b: int) -> str:
    min_v = max(CUSTOM_SCRIPT_LENGTH_MIN, min(int(a), int(b)))
    max_v = max(min_v, max(int(a), int(b)))
    max_v = min(CUSTOM_SCRIPT_LENGTH_MAX, max_v)
    return _format_range_key(min_v, max_v)


def _estimate_preferred_calls(target_max: int) -> int:
    if target_max <= 0:
        return 1
    return max(1, int(math.ceil(int(target_max) / 20)))


def normalize_script_length_selection(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    v = _normalize_range_separators(v)
    if not v.endswith("条") and re.search(r"\d", v):
        v = v + "条"
    if v in SCRIPT_LENGTH_PRESETS:
        return v
    m = re.search(r"(\d+)\D+(\d+)", v)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        key = _normalize_custom_range(a, b)
        if key in SCRIPT_LENGTH_PRESETS:
            return key
        return key
    m2 = re.search(r"(\d+)", v)
    if m2:
        target = int(m2.group(1))
        range_tuple = _compute_custom_range(target)
        if range_tuple:
            return _format_range_key(range_tuple[0], range_tuple[1])
    allowed = " | ".join(SCRIPT_LENGTH_PRESETS.keys())
    raise ValueError(f"script_length 无效，可选值: {allowed} 或自定义数字范围")


def parse_script_length_selection(value: Optional[str]) -> ScriptTargetPlan:
    try:
        normalized = normalize_script_length_selection(value) or DEFAULT_SCRIPT_LENGTH_SELECTION
    except ValueError:
        normalized = DEFAULT_SCRIPT_LENGTH_SELECTION
    if normalized in SCRIPT_LENGTH_PRESETS:
        target_min, target_max, calls = SCRIPT_LENGTH_PRESETS[normalized]
        final_target_count = int(target_max)
    else:
        m = re.search(r"(\d+)\D+(\d+)", normalized)
        if m:
            target_min = int(m.group(1))
            target_max = int(m.group(2))
        else:
            target_min = target_max = int(
                re.search(r"(\d+)", normalized).group(1) if re.search(r"(\d+)", normalized) else 0
            )
        if target_min > target_max:
            target_min, target_max = target_max, target_min
        target_min = max(CUSTOM_SCRIPT_LENGTH_MIN, int(target_min))
        target_max = max(target_min, int(target_max))
        calls = _estimate_preferred_calls(target_max)
        final_target_count = int(target_max)
    return ScriptTargetPlan(
        normalized_selection=normalized,
        target_min=int(target_min),
        target_max=int(target_max),
        preferred_calls=int(calls),
        final_target_count=final_target_count,
    )


def allocate_output_counts(total_target_count: int, chunk_count: int) -> List[int]:
    t = int(total_target_count or 0)
    c = int(chunk_count or 0)
    if c <= 0:
        return []
    if t <= 0:
        return [1] * c
    if c <= t:
        base = t // c
        rem = t % c
        out = [base + 1 if i < rem else base for i in range(c)]
        return [max(1, int(x)) for x in out]
    return [1] * c
