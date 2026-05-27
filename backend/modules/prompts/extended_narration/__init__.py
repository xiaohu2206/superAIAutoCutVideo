#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from .script_generation import ExtendedNarrationScriptGenerationPrompt


_EXTENDED_VALUES = set()


def register_prompts() -> None:
    """Legacy module kept for import compatibility.

    Extended narration categories now live in their own prompt packages
    (tv_drama_narration, variety_narration, documentary_narration, etc.),
    so this package intentionally does not register duplicate defaults.
    """
    return None


__all__ = [
    "ExtendedNarrationScriptGenerationPrompt",
    "register_prompts",
]
