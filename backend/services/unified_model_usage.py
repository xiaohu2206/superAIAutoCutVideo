#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型使用总控：根据「是否自定义模型」在
- 自定义：沿用 content_model_config / video_model_config 的当前启用项；
- 整合（云雾）：用 unified_yunwu_models_config 的单一 Key + 分角色模型名。

在线向量 / 召回相关配置已弃用，不在此模块处理。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from modules.config.content_model_config import ContentModelConfig, content_model_config_manager
from modules.config.unified_yunwu_models_config import (
    DEFAULT_YUNWU_CHAT_URL,
    unified_yunwu_models_config_manager,
)
from modules.config.video_model_config import VideoModelConfig, video_model_config_manager


class LlmModelUsage(str, Enum):
    """走 Chat Completions 的 LLM 调用场景（content 配置形态）。"""

    COPYWRITING = "copywriting"
    SCRIPT_GENERATION = "script_generation"
    LLM_RERANK = "llm_rerank"


def unified_mode_enabled() -> bool:
    return not unified_yunwu_models_config_manager.get_root().use_custom_models


def _unified_api_key_valid(key: str) -> bool:
    s = (key or "").strip()
    if not s or s.lower() == "xxx":
        return False
    return True


def _unified_yunwu_content_cfg(*, model_name: str) -> ContentModelConfig:
    root = unified_yunwu_models_config_manager.get_root()
    y = root.yunwu
    if not _unified_api_key_valid(y.api_key):
        raise RuntimeError(
            "已关闭「自定义模型」并启用云雾整合，但未配置有效的云雾 API Key。"
            "请在整合模型设置中填写 Key，或重新开启自定义模型。"
        )
    base = (y.base_url or "").strip().strip("`") or DEFAULT_YUNWU_CHAT_URL
    return ContentModelConfig(
        provider="yunwu",
        api_key=y.api_key.strip(),
        base_url=base,
        model_name=(model_name or "").strip(),
        temperature=0.7,
        timeout=180,
        extra_params={},
        stream_output=False,
        enabled=True,
        description="云雾整合模型（由 unified_model_usage 合成）",
    )


def resolve_unified_yunwu_for_integration_connection_test() -> ContentModelConfig:
    """
    「整合模型设置」里「测试连接」专用：始终读取 unified_yunwu_models 的云雾 Key / base_url /
    copywriting_model_name，与 use_custom_models 以及当前激活的文案自定义模型无关。
    """
    y = unified_yunwu_models_config_manager.get_root().yunwu
    if not _unified_api_key_valid(y.api_key):
        raise RuntimeError(
            "请先在整合模型设置中填写有效的云雾 API Key（占位符 xxx 或空值无效）。"
        )
    return _unified_yunwu_content_cfg(model_name=y.copywriting_model_name)


def resolve_content_model_for_llm(usage: LlmModelUsage) -> ContentModelConfig:
    """
    返回一次 LLM 调用应使用的 ContentModelConfig（形态与原有文案模型一致，便于走现有 Provider）。
    """
    if unified_yunwu_models_config_manager.get_root().use_custom_models:
        cfg = content_model_config_manager.get_active_config()
        if not cfg:
            raise RuntimeError("没有激活的文案生成模型配置，请先在设置中启用一个配置")
        return cfg

    y = unified_yunwu_models_config_manager.get_root().yunwu
    if usage == LlmModelUsage.COPYWRITING:
        return _unified_yunwu_content_cfg(model_name=y.copywriting_model_name)
    if usage == LlmModelUsage.SCRIPT_GENERATION:
        return _unified_yunwu_content_cfg(model_name=y.script_generation_model_name)
    if usage == LlmModelUsage.LLM_RERANK:
        return _unified_yunwu_content_cfg(model_name=y.llm_rerank_model_name)
    raise RuntimeError(f"未知 LLM 使用场景: {usage}")


def resolve_video_model_for_online_vision() -> Optional[VideoModelConfig]:
    """
    在线视觉 / 多模态 / 文案结构化里「与视频理解共用」的 VL 配置。
    自定义模式：与原先一致，返回当前启用的 video_model。
    整合模式：用云雾 Key + video_analysis 模型名合成一条（enabled 恒为 True 语义，仅用于调用）。
    """
    if unified_yunwu_models_config_manager.get_root().use_custom_models:
        return video_model_config_manager.get_active_config()

    root = unified_yunwu_models_config_manager.get_root()
    y = root.yunwu
    if not _unified_api_key_valid(y.api_key):
        raise RuntimeError(
            "已关闭「自定义模型」并启用云雾整合，但未配置有效的云雾 API Key。"
            "请在整合模型设置中填写 Key，或重新开启自定义模型。"
        )
    base = (y.base_url or "").strip().strip("`") or DEFAULT_YUNWU_CHAT_URL
    return VideoModelConfig(
        provider="yunwu",
        api_key=y.api_key.strip(),
        base_url=base,
        model_name=(y.video_analysis_model_name or "").strip(),
        temperature=0.7,
        timeout=600,
        extra_params={},
        stream_output=False,
        enabled=True,
        description="云雾整合视频理解模型（由 unified_model_usage 合成）",
    )
