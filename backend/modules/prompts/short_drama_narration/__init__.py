#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Description: 短剧解说提示词模块
"""

from .plot_analysis import PlotAnalysisPrompt
from .script_generation import ScriptGenerationPrompt
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


__all__ = [
    "PlotAnalysisPrompt",
    "ScriptGenerationPrompt",
    "register_prompts"
]
