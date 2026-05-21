#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from modules.narration_types import NARRATION_TYPE_CONFIG
from .script_generation import ExtendedNarrationScriptGenerationPrompt
from ..common.humor import HumorScriptGenerationPrompt
from ..prompt_manager import PromptManager


_EXTENDED_VALUES = {
    "电视剧解说",
    "综艺解说",
    "纪录片解说",
    "体育解说",
    "通用解说",
    "自定义解说",
}


def register_prompts() -> None:
    for value in _EXTENDED_VALUES:
        cfg = NARRATION_TYPE_CONFIG[value]
        script_generation_prompt_zh = ExtendedNarrationScriptGenerationPrompt(
            category=cfg.category,
            work_kind=cfg.work_kind,
            language="zh",
            name="script_generation",
        )
        PromptManager.register_prompt_cls(script_generation_prompt_zh, is_default=True)
        script_generation_prompt_en = ExtendedNarrationScriptGenerationPrompt(
            category=cfg.category,
            work_kind=cfg.work_kind,
            language="en",
            name="script_generation_en",
        )
        PromptManager.register_prompt_cls(script_generation_prompt_en, is_default=False)
        humor_prompt = HumorScriptGenerationPrompt(category=cfg.category, label=cfg.work_kind)
        PromptManager.register_prompt_cls(humor_prompt, is_default=False)


__all__ = [
    "ExtendedNarrationScriptGenerationPrompt",
    "register_prompts",
]
