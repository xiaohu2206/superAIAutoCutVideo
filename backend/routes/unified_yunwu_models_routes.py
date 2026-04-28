#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云雾整合模型配置 API（后端持久化；前端可后续对接）。
支持三档配置（low / medium / high），更新时按档位合并。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from modules.ai import AIModelConfig, get_provider_class
from modules.config.unified_yunwu_models_config import (
    UnifiedYunwuModelsRoot,
    YunwuTierSettings,
    unified_yunwu_models_config_manager,
)
from services.ai_models.unified_model_usage import (
    LlmModelUsage,
    resolve_unified_yunwu_for_integration_connection_test,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["模型配置"])


def _mask_key(api_key: str) -> str:
    if not api_key or len(api_key) <= 8:
        return api_key
    return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]


def _root_to_public_dict(root: UnifiedYunwuModelsRoot) -> Dict[str, Any]:
    d = root.model_dump()
    y = d.get("yunwu") or {}
    # yunwu 现在是 {low: {...}, medium: {...}, high: {...}}，逐档脱敏
    if isinstance(y, dict):
        masked: Dict[str, Any] = {}
        for tier_key, tier_dict in y.items():
            if isinstance(tier_dict, dict) and tier_dict.get("api_key"):
                masked[tier_key] = {**tier_dict, "api_key": _mask_key(str(tier_dict["api_key"]))}
            else:
                masked[tier_key] = tier_dict
        d["yunwu"] = masked
    return d


class UnifiedYunwuModelsUpdateRequest(BaseModel):
    """与 UnifiedYunwuModelsRoot 同结构；部分字段可选由调用方只传需要更新的项。"""

    use_custom_models: Optional[bool] = None
    # 顶层 yunwu 是三档 dict；前端可传完整 yunwu 或只传某档部分字段
    yunwu: Optional[Dict[str, Any]] = Field(default=None, description="云雾三档子配置，可部分字段")


@router.get("/unified-yunwu", summary="获取云雾整合模型配置")
async def get_unified_yunwu_models():
    try:
        root = unified_yunwu_models_config_manager.get_root()
        return {"success": True, "data": _root_to_public_dict(root)}
    except Exception as e:
        logger.error("获取云雾整合模型配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


def _merge_tier_inplace(
    merged_tiers: Dict[str, Dict[str, Any]],
    tier_key: str,
    tier_updates: Dict[str, Any],
    existing: Dict[str, YunwuTierSettings],
) -> None:
    """将前端传来的单档更新合并到 merged_tiers[tier_key] 中。"""
    cur = existing.get(tier_key, YunwuTierSettings())
    cur_dict = cur.model_dump()
    for k, v in tier_updates.items():
        if k == "api_key" and isinstance(v, str):
            if "*" in v and len(v) > 8:
                old = str(cur.api_key or "")
                if old and len(old) > 8 and old[:4] == v[:4] and old[-4:] == v[-4:]:
                    cur_dict["api_key"] = old
                else:
                    cur_dict["api_key"] = v
            else:
                cur_dict["api_key"] = v
        else:
            cur_dict[k] = v
    merged_tiers[tier_key] = cur_dict


@router.put("/unified-yunwu", summary="更新云雾整合模型配置")
async def put_unified_yunwu_models(body: UnifiedYunwuModelsUpdateRequest):
    try:
        cur = unified_yunwu_models_config_manager.get_root()
        existing_tiers = cur.yunwu  # Dict[str, YunwuTierSettings]

        merged_tiers: Dict[str, Dict[str, Any]] = {}
        if body.yunwu:
            # body.yunwu 可能是 {low: {...}, medium: {...}, high: {...}} 三档结构
            for tier_key, tier_val in body.yunwu.items():
                if tier_key in ("low", "medium", "high") and isinstance(tier_val, dict):
                    _merge_tier_inplace(merged_tiers, tier_key, tier_val, existing_tiers)
                else:
                    # 兼容旧版：body.yunwu 直接是平面字段（如 {api_key: ..., copywriting_model_name: ...}）
                    # 视为更新 high 档
                    _merge_tier_inplace(merged_tiers, "high", {tier_key: tier_val}, existing_tiers)

        # 确保三档齐全
        for tk in ("low", "medium", "high"):
            if tk not in merged_tiers:
                merged_tiers[tk] = existing_tiers.get(tk, YunwuTierSettings()).model_dump()

        # 校验每档
        new_yunwu: Dict[str, YunwuTierSettings] = {}
        for tk, td in merged_tiers.items():
            new_yunwu[tk] = YunwuTierSettings.model_validate(td)

        new_root = UnifiedYunwuModelsRoot(
            use_custom_models=cur.use_custom_models if body.use_custom_models is None else bool(body.use_custom_models),
            yunwu=new_yunwu,
        )
        unified_yunwu_models_config_manager.update_root(new_root)
        return {"success": True, "data": _root_to_public_dict(new_root)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("更新云雾整合模型配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/unified-yunwu/test", summary="测试云雾整合（文案槽位模型）连接")
async def test_unified_yunwu_models():
    """使用整合配置中「文案生成」模型名做一次连通性探测（与自定义文案测试语义接近）。"""
    try:
        cfg = resolve_unified_yunwu_for_integration_connection_test()
        provider_cls = get_provider_class(cfg.provider)
        if not provider_cls:
            return {"success": False, "data": {"error": f"不支持的提供商: {cfg.provider}"}}
        ai_cfg = AIModelConfig(
            provider=cfg.provider,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model_name=cfg.model_name,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
            extra_params={**(cfg.extra_params or {}), "stream_output": bool(cfg.stream_output)},
        )
        provider = provider_cls(ai_cfg)
        try:
            result = await provider.test_connection()
        finally:
            await provider.close()
        result["usage"] = LlmModelUsage.COPYWRITING.value
        result["model_name"] = cfg.model_name
        return {"success": bool(result.get("success")), "data": result}
    except Exception as e:
        logger.error("测试云雾整合模型失败: %s", e)
        return {"success": False, "data": {"error": str(e)}}
