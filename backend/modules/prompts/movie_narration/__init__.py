#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from .script_generation import MovieScriptGenerationPrompt
from ..prompt_manager import PromptManager


def register_prompts() -> None:
    script_generation_prompt = MovieScriptGenerationPrompt()
    PromptManager.register_prompt_cls(script_generation_prompt, is_default=True)


__all__ = [
    "MovieScriptGenerationPrompt",
    "register_prompts",
]
