#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
提示词基础抽象
提供提示词元数据、类型枚举、以及通用渲染逻辑。

该模块为各提示词子模块（如 short_drama_editing、short_drama_narration 等）
提供统一的工程化基础接口，确保逻辑与视图（模板）的分离、模块化与低耦合。
"""

from __future__ import annotations

import re
from enum import Enum
from string import Template
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelType(str, Enum):
    """模型类型枚举"""
    TEXT = "text"
    MULTIMODAL = "multimodal"


class OutputFormat(str, Enum):
    """输出格式枚举"""
    JSON = "json"
    TEXT = "text"


class PromptMetadata(BaseModel):
    """提示词元数据"""
    name: str
    category: str
    version: str
    description: str
    model_type: ModelType
    output_format: OutputFormat
    tags: List[str] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)

    def key(self) -> str:
        """生成用于注册的唯一键（category:name）"""
        return f"{self.category}:{self.name}"


class BasePrompt:
    """提示词基础类，所有提示词实现应继承此类"""

    def __init__(self, metadata: PromptMetadata):
        self.metadata = metadata
        self._system_prompt: Optional[str] = None

    def get_template(self) -> str:
        """返回用户提示词模板（需由子类实现）"""
        raise NotImplementedError

    def get_system_prompt(self) -> Optional[str]:
        """返回系统提示词（可选）"""
        return self._system_prompt

    def render(self, variables: Dict[str, Any]) -> str:
        """
        渲染模板

        使用 `${var}` 形式的占位符；当缺少变量时抛出 ValueError。
        """
        template_str = self.get_template()

        # 找出模板中所有占位符
        placeholders = set(re.findall(r"\$\{([a-zA-Z0-9_]+)\}", template_str))
        missing = [p for p in placeholders if p not in variables]
        if missing:
            raise ValueError(f"缺少必要的模板变量: {', '.join(missing)}")

        # 执行替换
        return Template(template_str).substitute(**variables)


class TextPrompt(BasePrompt):
    """文本提示词（面向纯文本模型）"""
    pass