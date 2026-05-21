#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import json
from typing import Optional


def _safe_ratio(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except Exception:
        return None
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


def build_output_format_block(
    language: str = "zh",
    original_ratio: Optional[int] = None,
    interleave_mode: Optional[str] = None,
    original_label: str = "原片",
    narration_sample_a: str = "...",
    narration_sample_b: str = "xxx",
) -> str:
    ratio = _safe_ratio(original_ratio)
    allow_ost_1 = ratio is None or ratio > 0
    allow_ost_0 = ratio is None or ratio < 100
    play_label = f"播放{original_label}"

    im = (interleave_mode or "").strip().lower()
    if im == "original_interleave":
        items = [
            {"_id": 1, "timestamp": "00:00:0x,000-00:00:0x,x00", "narration": narration_sample_a, "OST": 0},
            {"_id": 2, "timestamp": "00:00:0x,x00-00:00:0x,000", "narration": f"{play_label}1", "OST": 1},
            {"_id": 3, "timestamp": "00:00:0x,000-00:00:xx,000", "narration": narration_sample_b, "OST": 0},
            {"_id": 4, "timestamp": "00:00:xx,x00-00:00:xx,000", "narration": f"{play_label}2", "OST": 1},
        ]
    else:
        items = []
        if allow_ost_0 and allow_ost_1:
            items = [
                {"_id": 1, "timestamp": "00:00:0x,000-00:00:0x,x00", "narration": narration_sample_a, "OST": 0},
                {"_id": 2, "timestamp": "00:00:0x,x00-00:00:0x,000", "narration": f"{play_label}x", "OST": 1},
                {"_id": 3, "timestamp": "00:00:0x,000-00:00:xx,000", "narration": narration_sample_a, "OST": 0},
            ]
        elif allow_ost_0 and not allow_ost_1:
            items = [
                {"_id": 1, "timestamp": "00:00:0x,000-00:00:0x,x00", "narration": narration_sample_a, "OST": 0},
                {"_id": 2, "timestamp": "00:00:0x,000-00:00:xx,000", "narration": narration_sample_a, "OST": 0},
            ]
        elif allow_ost_1 and not allow_ost_0:
            items = [
                {"_id": 1, "timestamp": "00:00:0x,x00-00:00:0x,000", "narration": f"{play_label}x", "OST": 1},
                {"_id": 2, "timestamp": "00:00:xx,x00-00:00:xx,000", "narration": f"{play_label}x", "OST": 1},
            ]

    example = json.dumps({"items": items}, ensure_ascii=False, indent=2)

    if language.lower() == "en":
        original_section = (
            """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": "sequence_number",
  "timestamp": "start_time-end_time",
  "narration": "%s+序号",
  "OST": 1
}
```

""" % play_label
            if allow_ost_1
            else ""
        )
        return (
            original_section
            + "## 输出格式要求示例\n"
            + "请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：\n"
            + example
            + "\n"
        )

    original_section = (
        """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": 序号,
  "timestamp": "开始时间-结束时间",
  "narration": "%s+序号",
  "OST": 1
}
```

""" % play_label
        if allow_ost_1
        else ""
    )
    return (
        original_section
        + "## 输出格式要求示例\n"
        + "请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：\n"
        + example
        + "\n"
    )


def short_drama(language: str = "zh", original_ratio: Optional[int] = None, interleave_mode: Optional[str] = None) -> str:
    return build_output_format_block(
        language=language,
        original_ratio=original_ratio,
        interleave_mode=interleave_mode,
        original_label="原片",
    )


def movie(language: str = "zh", original_ratio: Optional[int] = None, interleave_mode: Optional[str] = None) -> str:
    def _n0() -> str:
        return "..." if language.lower() == "en" else "……"

    def _n1() -> str:
        return "..." if language.lower() == "en" else "xxx"
    return build_output_format_block(
        language=language,
        original_ratio=original_ratio,
        interleave_mode=interleave_mode,
        original_label="原片",
        narration_sample_a=_n0(),
        narration_sample_b=_n1(),
    )
