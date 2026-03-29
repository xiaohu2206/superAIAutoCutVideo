#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Description: 短剧解说提示词模块
"""

from .plot_analysis import PlotAnalysisPrompt
from .script_generation import ScriptGenerationPrompt
from ..common.humor import HumorScriptGenerationPrompt
from ..common.style_script_prompt import register_common_style_prompts_for_category
from ..prompt_manager import PromptManager


def register_prompts():
    """注册短剧解说相关的提示词"""
    
    # 注册剧情分析提示词
    plot_analysis_prompt = PlotAnalysisPrompt()
    PromptManager.register_prompt_cls(plot_analysis_prompt, is_default=True)
    
    # 注册解说脚本生成提示词（中文为默认）
    script_generation_prompt_zh = ScriptGenerationPrompt(language="zh", name="script_generation")
    PromptManager.register_prompt_cls(script_generation_prompt_zh, is_default=True)
    # 注册英文版本
    script_generation_prompt_en = ScriptGenerationPrompt(language="en", name="script_generation_en")
    PromptManager.register_prompt_cls(script_generation_prompt_en, is_default=False)
    # 幽默搞笑（与 common/humor/humor.md 一致）
    humor_prompt = HumorScriptGenerationPrompt(category="short_drama_narration", label="短剧")
    PromptManager.register_prompt_cls(humor_prompt, is_default=False)
    register_common_style_prompts_for_category("short_drama_narration", "短剧")


__all__ = [
    "PlotAnalysisPrompt",
    "ScriptGenerationPrompt",
    "HumorScriptGenerationPrompt",
    "register_prompts",
]
