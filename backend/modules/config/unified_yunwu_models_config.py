#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云雾「整合模型」配置：关闭自定义模型时，文案 / 脚本 / LLM 精排 / 在线视频理解
共用云雾 API Key，并按角色使用各自默认模型名（可由本配置文件调整）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_YUNWU_CHAT_URL = "https://yunwu.ai/v1/chat/completions"


class UnifiedYunwuModelsSettings(BaseModel):
    """云雾整合：单一 Key + 分角色模型名（仅 provider=yunwu）。"""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    api_key: str = Field("", description="云雾 API Key")
    base_url: str = Field(DEFAULT_YUNWU_CHAT_URL, description="Chat Completions 地址")
    copywriting_model_name: str = Field(
        "deepseek-v4-flash",
        description="文案生成 / 参考文案清洗等",
    )
    video_analysis_model_name: str = Field(
        "gemini-2.5-flash-lite",
        description="在线视频帧 / 多模态视觉理解",
    )
    llm_rerank_model_name: str = Field(
        "deepseek-v4-flash",
        description="Omni 镜头 LLM 精排",
    )
    script_generation_model_name: str = Field(
        "deepseek-v4-flash",
        description="脚本 JSON / 分镜脚本等",
    )

    @field_validator("base_url")
    @classmethod
    def _strip_base(cls, v: str) -> str:
        s = (v or "").strip().strip("`")
        return s or DEFAULT_YUNWU_CHAT_URL

    @field_validator(
        "copywriting_model_name",
        "video_analysis_model_name",
        "llm_rerank_model_name",
        "script_generation_model_name",
    )
    @classmethod
    def _strip_model(cls, v: str) -> str:
        s = (v or "").strip().strip("`")
        if not s:
            raise ValueError("模型名称不能为空")
        return s


class UnifiedYunwuModelsRoot(BaseModel):
    """根配置：是否使用自定义（分开展示）模型。"""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    use_custom_models: bool = Field(
        True,
        description="为 True 时文案/视频等仍走原 content_model / video_model；为 False 时走云雾整合",
    )
    yunwu: UnifiedYunwuModelsSettings = Field(default_factory=UnifiedYunwuModelsSettings)


class UnifiedYunwuModelsConfigManager:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        if config_file is None:
            from ..app_paths import user_config_dir

            config_file = user_config_dir() / "unified_yunwu_models_config.json"
        self.config_file = Path(config_file)
        self._root: UnifiedYunwuModelsRoot = UnifiedYunwuModelsRoot()
        self.load()

    def load(self) -> None:
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    raw: Dict[str, Any] = json.load(f)
                self._root = UnifiedYunwuModelsRoot.model_validate(raw)
                logger.info("已加载云雾整合模型配置")
            else:
                self._root = UnifiedYunwuModelsRoot()
                self.save()
        except Exception as e:
            logger.error("加载云雾整合模型配置失败，使用默认: %s", e)
            self._root = UnifiedYunwuModelsRoot()

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._root.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info("云雾整合模型配置已保存")

    def get_root(self) -> UnifiedYunwuModelsRoot:
        return self._root

    def update_root(self, root: UnifiedYunwuModelsRoot) -> None:
        self._root = root
        self.save()


unified_yunwu_models_config_manager = UnifiedYunwuModelsConfigManager()
