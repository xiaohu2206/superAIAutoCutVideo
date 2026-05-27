#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ..common.generic_script_generation_prompt import GenericNarrationScriptGenerationPrompt
from ..common.humor import HumorScriptGenerationPrompt
from ..common.style_script_prompt import register_common_style_prompts_for_category
from ..prompt_manager import PromptManager


def register_prompts() -> None:
    label = "纪录片"
    category = "documentary_narration"
    PromptManager.register_prompt_cls(
        GenericNarrationScriptGenerationPrompt(category=category, label=label, source_label="原片"),
        is_default=True,
    )
    PromptManager.register_prompt_cls(HumorScriptGenerationPrompt(category=category, label=label), is_default=False)
    register_common_style_prompts_for_category(category, label)


__all__ = ["register_prompts"]
