# -*- coding: utf-8 -*-
"""Omni 解说脚本生成的提示词选项规则。"""

from __future__ import annotations

from typing import Optional


def normalize_script_language(value: Optional[str]) -> str:
    lang = str(value or "zh").strip().lower()
    if lang in {"en", "en-us", "英文", "english"}:
        return "en"
    if lang in {"zh", "zh-cn", "中文", "chinese"}:
        return "zh"
    return lang or "zh"


def build_language_system_addon(script_language: Optional[str]) -> str:
    lang = normalize_script_language(script_language)
    if lang == "en":
        return "You must write all 'narration' text strictly in English; do not output Chinese or other languages."
    if lang == "zh":
        return "你必须将所有 'narration' 文本严格用中文撰写；不得输出英文或其他语言。"
    return ""


def normalize_original_ratio(value: Optional[int]) -> int:
    try:
        num = int(value)
    except Exception:
        return 70
    if num < 0:
        return 0
    if num > 100:
        return 100
    return num


def normalize_interleave_mode(value: Optional[str]) -> str:
    if value is None:
        return "smart_interleave"
    s = str(value).strip().lower()
    if s in ("original_interleave", "原片穿插"):
        return "original_interleave"
    return "smart_interleave"


def build_original_ratio_system_addon(original_ratio: Optional[int], interleave_mode: Optional[str] = None) -> str:
    im = normalize_interleave_mode(interleave_mode)
    if im == "original_interleave":
        return (
            "穿插模式为原片穿插：按解说文案顺序生成脚本，在每段解说后穿插标注'播放原片N'的原声片段（N为序号递增）。"
            "OST=0表示解说，narration填写对应的解说文案内容；"
            "OST=1表示原声，narration使用'播放原片N'格式（N从1递增）。"
            "各条解说文案之间必须间隔原声片段，形成解说-原片-解说-原片的交替节奏。"
        )

    if original_ratio is None:
        return "原声片段（OST=1）占比约 40%，解说片段（OST=0）占比约 60%\n"

    ratio_val = normalize_original_ratio(original_ratio)
    if ratio_val <= 0:
        return (
            "本次只生成解说片段：所有条目的OST必须为0，且narration为解说文案；"
            "不得使用”播放原片+序号“格式，不得输出原声片段。"
        )
    if ratio_val >= 100:
        return (
            "本次只生成原声片段：所有条目的OST必须为1，且narration必须使用”播放原片+序号“格式；"
            "不得输出解说文案。"
        )
    return (
        f"原片占比范围：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
        "OST=1表示原声，narration使用”播放原片+序号“格式；"
        "OST=0表示解说，narration填写对应的解说文案内容。"
    )
