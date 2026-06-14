#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni Step2 / 镜头视觉分析 / 文本 LLM 共用的本地模型参数配置。

持久化：user_config_dir() / omni_step2_pipeline_config.json
- use_local_vision_model：只控制视觉模型批大小、超时和 API 并发。
- use_local_text_model：只控制文案、脚本等文本 LLM 的 API 并发。

旧版 use_local_model_pipeline / local.api_concurrency 会在加载时自动迁移为两套配置。
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
    """本地模型模式下的视觉与文本参数（可在设置页调整）。"""

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
    vision_api_concurrency: int = Field(
        1,
        ge=1,
        le=64,
        description="视觉模型 API 并发上限",
    )
    text_api_concurrency: int = Field(
        1,
        ge=1,
        le=64,
        description="文案、脚本等文本 LLM API 并发上限",
    )


class OmniStep2PipelineRoot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    use_local_vision_model: bool = Field(
        False,
        description="视觉模型是否使用本地部署的低并发、长超时参数",
    )
    use_local_text_model: bool = Field(
        False,
        description="文案、脚本等文本 LLM 是否使用本地部署的低并发参数",
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
    api_c = max(1, int(local.vision_api_concurrency))
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
                    migrated = self._migrate_legacy_data(data)
                    self.root = OmniStep2PipelineRoot(**migrated)
                    if migrated != data:
                        self.save()
            else:
                self.save()
        except Exception as e:
            logger.error("加载 omni_step2_pipeline_config 失败: %s", e)
            self.root = OmniStep2PipelineRoot()
            self.save()

    @staticmethod
    def _migrate_legacy_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """把旧版单开关、单并发配置无损展开为视觉与文本两套配置。"""
        migrated = dict(data)
        legacy_enabled = migrated.get("use_local_model_pipeline")
        if "use_local_vision_model" not in migrated and legacy_enabled is not None:
            migrated["use_local_vision_model"] = bool(legacy_enabled)
        if "use_local_text_model" not in migrated and legacy_enabled is not None:
            migrated["use_local_text_model"] = bool(legacy_enabled)

        local_raw = migrated.get("local")
        if isinstance(local_raw, dict):
            local = dict(local_raw)
            legacy_concurrency = local.get("api_concurrency")
            if "vision_api_concurrency" not in local and legacy_concurrency is not None:
                local["vision_api_concurrency"] = legacy_concurrency
            if "text_api_concurrency" not in local and legacy_concurrency is not None:
                local["text_api_concurrency"] = legacy_concurrency
            migrated["local"] = local
        return migrated

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self.root.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_root(self) -> OmniStep2PipelineRoot:
        return self.root.model_copy(deep=True)

    def resolve_runtime_params(self) -> OmniStep2RuntimeParams:
        """解析视觉模型运行参数；不受文本模型开关影响。"""
        if self.root.use_local_vision_model:
            return _local_runtime_params(self.root.local)
        return _cloud_runtime_params()

    def resolve_llm_api_concurrency(self, default_cloud: int = 3) -> int:
        """解析文本 LLM 并发；不受视觉模型开关影响。"""
        if self.root.use_local_text_model:
            return max(1, int(self.root.local.text_api_concurrency))
        return max(1, int(default_cloud))

    def is_local_vision_model_enabled(self) -> bool:
        return bool(self.root.use_local_vision_model)

    def is_local_text_model_enabled(self) -> bool:
        return bool(self.root.use_local_text_model)

    def snapshot(self) -> Dict[str, Any]:
        effective = self.resolve_runtime_params()
        return {
            "use_local_vision_model": self.root.use_local_vision_model,
            "use_local_text_model": self.root.use_local_text_model,
            "local": self.root.local.model_dump(),
            "effective": {
                "source": effective.source,
                "vision_source": effective.source,
                "text_source": "local" if self.root.use_local_text_model else "cloud",
                "vl_batch_size": effective.vl_batch_size,
                "frames_per_shot": effective.frames_per_shot,
                "vl_batch_images": effective.vl_batch_images,
                "infer_wall_sec": effective.infer_wall_sec,
                "max_concurrency": effective.max_concurrency,
                "extract_concurrency": effective.extract_concurrency,
                "api_concurrency": effective.api_concurrency,
                "vision_api_concurrency": effective.api_concurrency,
                "text_api_concurrency": self.resolve_llm_api_concurrency(),
                "bge_encode_concurrency": effective.bge_encode_concurrency,
            },
        }

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.get_root()
        if "use_local_vision_model" in payload and payload["use_local_vision_model"] is not None:
            cur.use_local_vision_model = bool(payload["use_local_vision_model"])
        if "use_local_text_model" in payload and payload["use_local_text_model"] is not None:
            cur.use_local_text_model = bool(payload["use_local_text_model"])

        # 兼容尚未升级的调用方：旧开关仍表示视觉与文本同时切换。
        if "use_local_model_pipeline" in payload and payload["use_local_model_pipeline"] is not None:
            legacy_enabled = bool(payload["use_local_model_pipeline"])
            cur.use_local_vision_model = legacy_enabled
            cur.use_local_text_model = legacy_enabled
        if isinstance(payload.get("local"), dict):
            local_patch = dict(payload["local"])
            legacy_concurrency = local_patch.pop("api_concurrency", None)
            if legacy_concurrency is not None:
                local_patch.setdefault("vision_api_concurrency", legacy_concurrency)
                local_patch.setdefault("text_api_concurrency", legacy_concurrency)
            merged = {**cur.local.model_dump(), **local_patch}
            cur.local = OmniStep2LocalSettings(**merged)
        self.root = cur
        self.save()
        return self.snapshot()


omni_step2_pipeline_config_manager = OmniStep2PipelineConfigManager()
