#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Step2 / 镜头视觉分析 共用参数配置（本地模型 / 云端模型两套策略）。

持久化：user_config_dir() / omni_step2_pipeline_config.json
- use_local_model_pipeline=False（默认）：沿用云端硬编码参数，行为与改造前一致。
- use_local_model_pipeline=True：使用 local 段可自定义的低并发 / 长超时参数。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

OMNI_STEP2_FRAMES_PER_SHOT = 2

# 云端默认（关闭「本地模型」开关时生效，与 omni_multimodal_pipeline_service 历史硬编码一致）
_CLOUD_VL_BATCH_IMAGES = 12
_CLOUD_VL_BATCH_SIZE = _CLOUD_VL_BATCH_IMAGES // OMNI_STEP2_FRAMES_PER_SHOT
_CLOUD_MAX_CONCURRENCY = 64
_CLOUD_INFER_WALL_SEC = 40.0


class OmniStep2LocalSettings(BaseModel):
    """本地模型模式下的 Step2 参数（可在设置页调整）。"""

    model_config = ConfigDict(extra="ignore")

    vl_batch_size: int = Field(
        1,
        ge=1,
        le=32,
        description="单次视觉模型调用包含的语义段数（每段固定 2 帧）",
    )
    infer_wall_sec: int = Field(
        1200,
        ge=30,
        le=7200,
        description="单次视觉模型调用墙钟超时（秒）",
    )
    api_concurrency: int = Field(
        1,
        ge=1,
        le=64,
        description="视觉模型 API 并发上限",
    )


class OmniStep2PipelineRoot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    use_local_model_pipeline: bool = Field(
        False,
        description="开启后使用 local 段参数（适合本地部署的视觉模型）",
    )
    local: OmniStep2LocalSettings = Field(default_factory=OmniStep2LocalSettings)


@dataclass(frozen=True)
class OmniStep2RuntimeParams:
    vl_batch_size: int
    frames_per_shot: int
    vl_batch_images: int
    infer_wall_sec: float
    max_concurrency: int
    extract_concurrency: int
    api_concurrency: int
    bge_encode_concurrency: Optional[int]
    source: str  # "cloud" | "local"


def _cloud_runtime_params() -> OmniStep2RuntimeParams:
    cap = max(1, _CLOUD_MAX_CONCURRENCY)
    return OmniStep2RuntimeParams(
        vl_batch_size=_CLOUD_VL_BATCH_SIZE,
        frames_per_shot=OMNI_STEP2_FRAMES_PER_SHOT,
        vl_batch_images=_CLOUD_VL_BATCH_IMAGES,
        infer_wall_sec=_CLOUD_INFER_WALL_SEC,
        max_concurrency=cap,
        extract_concurrency=min(8, cap),
        api_concurrency=min(64, cap),
        bge_encode_concurrency=None,
        source="cloud",
    )


def _local_runtime_params(local: OmniStep2LocalSettings) -> OmniStep2RuntimeParams:
    vl_batch = max(1, int(local.vl_batch_size))
    api_c = max(1, int(local.api_concurrency))
    cap = max(1, _CLOUD_MAX_CONCURRENCY)
    return OmniStep2RuntimeParams(
        vl_batch_size=vl_batch,
        frames_per_shot=OMNI_STEP2_FRAMES_PER_SHOT,
        vl_batch_images=vl_batch * OMNI_STEP2_FRAMES_PER_SHOT,
        infer_wall_sec=float(local.infer_wall_sec),
        max_concurrency=cap,
        extract_concurrency=min(8, cap),
        api_concurrency=min(api_c, cap),
        bge_encode_concurrency=None,
        source="local",
    )


class OmniStep2PipelineConfigManager:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        if config_file is None:
            from modules.app_paths import user_config_dir

            config_file = user_config_dir() / "omni_step2_pipeline_config.json"
        self.config_file = Path(config_file)
        self.root = OmniStep2PipelineRoot()
        self.load()

    def load(self) -> None:
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text("utf-8"))
                if isinstance(data, dict):
                    self.root = OmniStep2PipelineRoot(**data)
            else:
                self.save()
        except Exception as e:
            logger.error("加载 omni_step2_pipeline_config 失败: %s", e)
            self.root = OmniStep2PipelineRoot()
            self.save()

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self.root.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_root(self) -> OmniStep2PipelineRoot:
        return self.root.model_copy(deep=True)

    def resolve_runtime_params(self) -> OmniStep2RuntimeParams:
        if self.root.use_local_model_pipeline:
            return _local_runtime_params(self.root.local)
        return _cloud_runtime_params()

    def resolve_llm_api_concurrency(self, default_cloud: int = 3) -> int:
        """文案生成等 LLM 并行调用上限；本地模型模式使用 api_concurrency。"""
        params = self.resolve_runtime_params()
        if params.source == "local":
            return max(1, int(params.api_concurrency))
        return max(1, int(default_cloud))

    def snapshot(self) -> Dict[str, Any]:
        effective = self.resolve_runtime_params()
        return {
            "use_local_model_pipeline": self.root.use_local_model_pipeline,
            "local": self.root.local.model_dump(),
            "effective": {
                "source": effective.source,
                "vl_batch_size": effective.vl_batch_size,
                "frames_per_shot": effective.frames_per_shot,
                "vl_batch_images": effective.vl_batch_images,
                "infer_wall_sec": effective.infer_wall_sec,
                "max_concurrency": effective.max_concurrency,
                "extract_concurrency": effective.extract_concurrency,
                "api_concurrency": effective.api_concurrency,
                "bge_encode_concurrency": effective.bge_encode_concurrency,
            },
        }

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.get_root()
        if "use_local_model_pipeline" in payload and payload["use_local_model_pipeline"] is not None:
            cur.use_local_model_pipeline = bool(payload["use_local_model_pipeline"])
        if isinstance(payload.get("local"), dict):
            merged = {**cur.local.model_dump(), **payload["local"]}
            cur.local = OmniStep2LocalSettings(**merged)
        self.root = cur
        self.save()
        return self.snapshot()


omni_step2_pipeline_config_manager = OmniStep2PipelineConfigManager()
