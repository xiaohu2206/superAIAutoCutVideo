#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
提示词管理器
负责：
- 管理静态模板（来自 config/prompts.json）与动态模块化提示词（如 short_drama_editing）
- 统一注册、查询、渲染与消息构建
- 自动发现并注册各提示词子模块（支持后续扩展如 short_drama_narration）
- 使用示例：prompt_manager.build_chat_messages("short_drama_editing:subtitle_analysis", {"subtitle_content": "...", "custom_clips": 3})
"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict

from .base import BasePrompt

logger = logging.getLogger(__name__)


class PromptTemplate(BaseModel):
    """通用提示词模板（来自配置文件或代码动态创建）"""
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    template: str
    variables: List[str] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    version: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    enabled: bool = True

    def render(self, variables: Dict[str, Any]) -> str:
        """渲染模板，使用 `${var}` 占位符"""
        missing = [v for v in self.variables if v not in variables]
        if missing:
            raise ValueError(f"缺少必要的模板变量: {', '.join(missing)}")
        return Template(self.template).substitute(**variables)


class VideoAnalysisPrompts:
    """内置的常用提示词键集合（可扩展）"""
    # 完整键（category:name）便于跨分类检索
    SUBTITLE_ANALYSIS = "short_drama_editing:subtitle_analysis"
    PLOT_EXTRACTION = "short_drama_editing:plot_extraction"


class PromptManager:
    """提示词管理器：统一管理模板与模块化提示词"""

    def __init__(self, config_file: Optional[str] = None):
        # 建立单例引用，便于类方法在初始化期间正常工作
        type(self)._instance = self
        self._templates: Dict[str, PromptTemplate] = {}
        self._prompts: Dict[str, BasePrompt] = {}
        self._category_index: Dict[str, List[str]] = {}
        self._default_by_category: Dict[str, str] = {}

        # 配置文件路径（可选）
        if config_file is None:
            backend_dir = Path(__file__).parent.parent.parent
            config_file = backend_dir / "config" / "prompts.json"
        self._config_file = Path(config_file)

        # 加载模板 + 自动发现模块
        self._load_templates_from_config()
        self._auto_discover_and_register()

    # ------------------------
    # 注册与查询
    # ------------------------
    def add_template(self, template: PromptTemplate) -> None:
        if not template.enabled:
            logger.debug(f"模板未启用，跳过注册: {template.id}")
            return
        self._templates[template.id] = template
        if template.category:
            self._category_index.setdefault(template.category, []).append(template.id)
        logger.info(f"已注册模板: {template.id}")

    def register_prompt(self, prompt: BasePrompt, is_default: bool = False) -> None:
        key = f"{prompt.metadata.category}:{prompt.metadata.name}"
        self._prompts[key] = prompt
        self._category_index.setdefault(prompt.metadata.category, []).append(key)
        if is_default:
            self._default_by_category[prompt.metadata.category] = key
        logger.info(f"已注册提示词模块: {key}")

    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        return self._templates.get(template_id)

    def get_prompt(self, key_or_name: str, category: Optional[str] = None) -> Optional[BasePrompt]:
        """
        获取提示词模块：支持两种键形式
        - 完整键："category:name"
        - 简单名："name"（需提供 category 或从默认表中解析）
        """
        if ":" in key_or_name:
            return self._prompts.get(key_or_name)
        if category:
            return self._prompts.get(f"{category}:{key_or_name}")
        # 尝试在各分类中唯一匹配
        candidates = [k for k in self._prompts if k.endswith(f":{key_or_name}")]
        if len(candidates) == 1:
            return self._prompts[candidates[0]]
        return None

    def list_categories(self) -> List[str]:
        return sorted(self._category_index.keys())

    def list_items(self, category: Optional[str] = None) -> Dict[str, List[str]]:
        """列出所有模板与模块键（按分类）"""
        if category:
            return {category: self._category_index.get(category, [])}
        return {c: sorted(items) for c, items in self._category_index.items()}

    def get_default(self, category: str) -> Optional[str]:
        return self._default_by_category.get(category)

    # ------------------------
    # 渲染与消息构建
    # ------------------------
    def render_prompt(self, key_or_id: str, variables: Dict[str, Any], category: Optional[str] = None) -> Dict[str, Any]:
        """
        渲染提示词（模板或模块），返回统一结构：
        {
          "system": Optional[str],
          "user": str
        }
        """
        # 先尝试模板
        tpl = self.get_template(key_or_id)
        if tpl:
            user_text = tpl.render(variables)
            return {"system": tpl.system_prompt, "user": user_text}

        # 再尝试模块化提示词
        prompt = self.get_prompt(key_or_id, category=category)
        if not prompt:
            raise KeyError(f"未找到提示词或模板: {key_or_id}")
        user_text = prompt.render(variables)
        return {"system": prompt.get_system_prompt(), "user": user_text}

    def build_chat_messages(self, key_or_id: str, variables: Dict[str, Any], category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        构建适配聊天接口的 messages 列表
        [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
        """
        rendered = self.render_prompt(key_or_id, variables, category)
        messages: List[Dict[str, Any]] = []
        if rendered.get("system"):
            messages.append({"role": "system", "content": rendered["system"]})
        messages.append({"role": "user", "content": rendered["user"]})
        return messages

    # ------------------------
    # 内部：加载配置与自动发现
    # ------------------------
    def _load_templates_from_config(self) -> None:
        if not self._config_file.exists():
            logger.debug(f"未找到提示词配置文件，跳过加载: {self._config_file}")
            return
        try:
            data = json.loads(self._config_file.read_text(encoding="utf-8"))
            templates = data.get("templates", {})
            for tid, t in templates.items():
                try:
                    tpl = PromptTemplate(**t)
                    self.add_template(tpl)
                except Exception as e:
                    logger.warning(f"模板加载失败: {tid}, error={e}")
            logger.info(f"提示词配置加载完成，共 {len(self._templates)} 个模板")
        except Exception as e:
            logger.error(f"读取提示词配置失败: {self._config_file}, error={e}")

    def _auto_discover_and_register(self) -> None:
        """
        自动发现并注册子模块（需在其包内实现 `register_prompts()`）
        约定：目录为 <当前包前缀>.prompts.*，并强制使用与本模块一致的包前缀，避免出现多实例导致注册丢失。
        """
        base_path = Path(__file__).parent
        # 统一使用当前模块的包前缀（例如 'modules.prompts' 或 'backend.modules.prompts'）
        base_pkg = __package__ or "modules.prompts"
        if base_pkg.endswith(".prompt_manager"):
            base_pkg = base_pkg.rsplit(".", 1)[0]

        discovered: List[str] = []
        for finder, name, ispkg in pkgutil.iter_modules([str(base_path)]):
            # 跳过自身与私有包
            if name in {"__pycache__", "__init__", "prompt_manager", "base"}:
                continue
            full_name = f"{base_pkg}.{name}"
            try:
                module = importlib.import_module(full_name)
                if hasattr(module, "register_prompts"):
                    module.register_prompts()  # 期望其内部调用 PromptManager.register_prompt
                    logger.info(f"已自动注册子模块提示词: {full_name}")
                    discovered.append(full_name)
                else:
                    logger.debug(f"子模块 {full_name} 未提供 register_prompts，跳过自动注册")
            except Exception as e:
                logger.warning(f"自动发现提示词子模块失败: {full_name}, error={e}")

        if discovered:
            logger.info(f"提示词子模块自动发现完成，共注册 {len(discovered)} 个: {discovered}")
        else:
            logger.info("提示词子模块自动发现完成，但未发现可注册的子模块")

    # ------------------------
    # 类方法代理（便于模块内直接使用）
    # ------------------------
    # 注意：为避免与实例方法同名产生覆盖，这里采用不同的方法名
    @classmethod
    def register_prompt_cls(cls, prompt: BasePrompt, is_default: bool = False) -> None:
        instance = getattr(cls, "_instance", None)
        if instance is None:
            raise RuntimeError("PromptManager 未初始化，无法注册提示词模块")
        # 调用实例方法
        instance.register_prompt(prompt, is_default=is_default)

    @classmethod
    def add_template_cls(cls, template: PromptTemplate) -> None:
        instance = getattr(cls, "_instance", None)
        if instance is None:
            raise RuntimeError("PromptManager 未初始化，无法添加模板")
        instance.add_template(template)

    @classmethod
    def build_chat_messages_cls(cls, key_or_id: str, variables: Dict[str, Any], category: Optional[str] = None) -> List[Dict[str, Any]]:
        instance = getattr(cls, "_instance", None)
        if instance is None:
            raise RuntimeError("PromptManager 未初始化，无法构建消息")
        return instance.build_chat_messages(key_or_id, variables, category)


# 全局管理器实例
prompt_manager = PromptManager()