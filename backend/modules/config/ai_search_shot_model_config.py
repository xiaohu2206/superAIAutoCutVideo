#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量模型 配置管理
当前仅开放云雾平台下的向量模型与召回模型配置。
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class AiSearchShotModelConfig(BaseModel):
    """向量模型 模型配置"""

    provider: str = Field("yunwu", description="模型平台")
    api_key: str = Field("xxx", description="API 密钥")
    embedding_base_url: str = Field(
        "https://yunwu.ai/v1/embeddings", description="向量模型接口地址"
    )
    embedding_model: str = Field(
        "gemini-embedding-2-preview", description="向量模型名称"
    )
    rerank_base_url: str = Field(
        "https://yunwu.ai/v1/rerank", description="召回/重排模型接口地址"
    )
    rerank_model: str = Field("qwen3-rerank", description="召回/重排模型名称")
    timeout_seconds: int = Field(300, description="超时时间（秒）", ge=1, le=10000)
    max_retries: int = Field(5, description="最大重试次数", ge=3, le=20)
    retry_sleep_seconds: float = Field(2.0, description="重试间隔秒数", ge=0.1, le=60.0)
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(
        "向量模型 向量与召回模型配置（当前仅支持云雾）",
        description="配置描述",
    )

    @validator("provider")
    def validate_provider(cls, v: str) -> str:
        provider = (v or "").strip().lower()
        if provider != "yunwu":
            raise ValueError("当前仅支持云雾平台")
        return provider

    @validator("api_key")
    def validate_api_key(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("API密钥不能为空")
        return value

    @validator("embedding_base_url", "rerank_base_url")
    def validate_url(cls, v: str) -> str:
        value = (v or "").strip().strip("`")
        if not value:
            raise ValueError("接口地址不能为空")
        return value

    @validator("embedding_model", "rerank_model")
    def validate_model_name(cls, v: str) -> str:
        value = (v or "").strip().strip("`")
        if not value:
            raise ValueError("模型名称不能为空")
        return value


class AiSearchShotModelConfigManager:
    """向量模型 模型配置管理器"""

    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            from ..app_paths import user_config_dir

            config_file = user_config_dir() / "ai_search_shot_model_config.json"

        self.config_file = Path(config_file)
        self.config: AiSearchShotModelConfig = self._default_config()
        self.load_config()

    def _default_config(self) -> AiSearchShotModelConfig:
        return AiSearchShotModelConfig()

    def load_config(self):
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                raw_config = data.get("config", data)
                self.config = AiSearchShotModelConfig(**raw_config)
                logger.info("向量模型 模型配置加载成功")
            else:
                self.save_config()
        except Exception as e:
            logger.error(f"加载 向量模型 模型配置失败: {e}")
            self.config = self._default_config()
            self.save_config()

    def save_config(self):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"config": self.config.dict()}
        self.config_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("向量模型 模型配置保存成功")

    def get_config(self) -> AiSearchShotModelConfig:
        return self.config.copy(deep=True)

    def update_config(self, config: AiSearchShotModelConfig) -> AiSearchShotModelConfig:
        self.config = config
        self.save_config()
        return self.get_config()


ai_search_shot_model_config_manager = AiSearchShotModelConfigManager()
