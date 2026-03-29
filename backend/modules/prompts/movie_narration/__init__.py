#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from .script_generation import MovieScriptGenerationPrompt
from ..common.humor import HumorScriptGenerationPrompt
from ..common.style_script_prompt import register_common_style_prompts_for_category
from ..prompt_manager import PromptManager


def register_prompts() -> None:
    script_generation_prompt_zh = MovieScriptGenerationPrompt(language="zh", name="script_generation")
    PromptManager.register_prompt_cls(script_generation_prompt_zh, is_default=True)
    script_generation_prompt_en = MovieScriptGenerationPrompt(language="en", name="script_generation_en")
    PromptManager.register_prompt_cls(script_generation_prompt_en, is_default=False)
    humor_prompt = HumorScriptGenerationPrompt(category="movie_narration", label="电影")
    PromptManager.register_prompt_cls(humor_prompt, is_default=False)
    register_common_style_prompts_for_category("movie_narration", "电影")


__all__ = [
    "MovieScriptGenerationPrompt",
    "HumorScriptGenerationPrompt",
    "register_prompts",
]
