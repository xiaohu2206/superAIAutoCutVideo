#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from .script_generation import MovieScriptGenerationPrompt
from ..prompt_manager import PromptManager


def register_prompts() -> None:
    script_generation_prompt_zh = MovieScriptGenerationPrompt(language="zh", name="script_generation")
    PromptManager.register_prompt_cls(script_generation_prompt_zh, is_default=True)
    script_generation_prompt_en = MovieScriptGenerationPrompt(language="en", name="script_generation_en")
    PromptManager.register_prompt_cls(script_generation_prompt_en, is_default=False)


__all__ = [
    "MovieScriptGenerationPrompt",
    "register_prompts",
]
