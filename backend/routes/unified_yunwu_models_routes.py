#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聚合模型配置 API（后端持久化；前端可后续对接）。
支持多平台 + 三档配置（low / medium / high），更新时按平台+档位合并。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.ai import AIModelConfig, get_provider_class
from modules.config.unified_yunwu_models_config import (
    PlatformSettings,
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


def _mask_tier_dict(tier_dict: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(tier_dict, dict) and tier_dict.get("api_key"):
        return {**tier_dict, "api_key": _mask_key(str(tier_dict["api_key"]))}
    return tier_dict


def _platform_to_public_dict(p: PlatformSettings) -> Dict[str, Any]:
    d = p.model_dump()
    tiers = d.get("tiers") or {}
    if isinstance(tiers, dict):
        d["tiers"] = {tk: _mask_tier_dict(td) if isinstance(td, dict) else td for tk, td in tiers.items()}
    return d


def _root_to_public_dict(root: UnifiedYunwuModelsRoot) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "use_custom_models": root.use_custom_models,
        "active_platform": root.active_platform,
        "platforms": {},
    }
    for pk, pv in root.platforms.items():
        d["platforms"][pk] = _platform_to_public_dict(pv)
    return d


class PlatformUpdateBody(BaseModel):
    """单个平台的可选更新字段。"""
    display_name: Optional[str] = None
    office_web: Optional[str] = None
    tiers: Optional[Dict[str, Any]] = Field(default=None, description="low/medium/high 三档，可部分字段")


class UnifiedYunwuModelsUpdateRequest(BaseModel):
    """聚合模型配置更新请求。"""
    use_custom_models: Optional[bool] = None
    active_platform: Optional[str] = None
    platforms: Optional[Dict[str, PlatformUpdateBody]] = Field(default=None, description="各平台配置")
    # 兼容旧版：前端可能直接传 yunwu 平面字段
    yunwu: Optional[Dict[str, Any]] = Field(default=None, description="兼容旧版：直接传 yunwu 三档字段")


@router.get("/unified-yunwu", summary="获取聚合模型配置")
async def get_unified_yunwu_models(request: Request):
    try:
        await unified_yunwu_models_config_manager.ensure_remote_synced(request.headers.get("Authorization"))
        root = unified_yunwu_models_config_manager.get_root()
        return {"success": True, "data": _root_to_public_dict(root)}
    except Exception as e:
        logger.error("获取聚合模型配置失败: %s", e)
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


def _merge_platform_tiers(
    tier_updates: Dict[str, Any],
    existing_tiers: Dict[str, YunwuTierSettings],
) -> Dict[str, YunwuTierSettings]:
    """合并一个平台的三档更新。"""
    merged_tiers: Dict[str, Dict[str, Any]] = {}
    if tier_updates:
        for tier_key, tier_val in tier_updates.items():
            if tier_key in ("low", "medium", "high") and isinstance(tier_val, dict):
                _merge_tier_inplace(merged_tiers, tier_key, tier_val, existing_tiers)
            else:
                _merge_tier_inplace(merged_tiers, "high", {tier_key: tier_val}, existing_tiers)

    for tk in ("low", "medium", "high"):
        if tk not in merged_tiers:
            merged_tiers[tk] = existing_tiers.get(tk, YunwuTierSettings()).model_dump()

    new_tiers: Dict[str, YunwuTierSettings] = {}
    for tk, td in merged_tiers.items():
        new_tiers[tk] = YunwuTierSettings.model_validate(td)
    return new_tiers


@router.put("/unified-yunwu", summary="更新聚合模型配置")
async def put_unified_yunwu_models(body: UnifiedYunwuModelsUpdateRequest, request: Request):
    try:
        await unified_yunwu_models_config_manager.ensure_remote_synced(request.headers.get("Authorization"))
        cur = unified_yunwu_models_config_manager.get_root()

        new_use_custom = cur.use_custom_models if body.use_custom_models is None else bool(body.use_custom_models)
        new_active_platform = cur.active_platform if body.active_platform is None else body.active_platform.strip()

        # 复制现有平台
        new_platforms: Dict[str, PlatformSettings] = {}
        for pk, pv in cur.platforms.items():
            new_platforms[pk] = pv.model_copy(deep=True)

        # 处理新版 platforms 更新
        if body.platforms:
            for plat_key, plat_update in body.platforms.items():
                existing_plat = new_platforms.get(plat_key, PlatformSettings())
                updated_tiers = _merge_platform_tiers(
                    plat_update.tiers if plat_update.tiers else {},
                    existing_plat.tiers,
                )
                new_display = existing_plat.display_name if plat_update.display_name is None else plat_update.display_name
                new_office = existing_plat.office_web if plat_update.office_web is None else plat_update.office_web
                new_platforms[plat_key] = PlatformSettings(
                    display_name=new_display,
                    office_web=new_office,
                    tiers=updated_tiers,
                )

        # 兼容旧版：直接传 yunwu 字段 → 更新当前激活平台
        if body.yunwu and not body.platforms:
            active_key = new_active_platform or "yunwu"
            existing_plat = new_platforms.get(active_key, PlatformSettings())
            updated_tiers = _merge_platform_tiers(body.yunwu, existing_plat.tiers)
            new_platforms[active_key] = PlatformSettings(
                display_name=existing_plat.display_name,
                office_web=existing_plat.office_web,
                tiers=updated_tiers,
            )

        new_root = UnifiedYunwuModelsRoot(
            use_custom_models=new_use_custom,
            active_platform=new_active_platform,
            platforms=new_platforms,
        )
        unified_yunwu_models_config_manager.update_root(new_root)
        return {"success": True, "data": _root_to_public_dict(new_root)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("更新聚合模型配置失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/unified-yunwu/platforms", summary="获取可用平台列表")
async def list_platforms(request: Request):
    """返回所有可用平台标识、显示名称和官网地址。"""
    try:
        await unified_yunwu_models_config_manager.ensure_remote_synced(request.headers.get("Authorization"))
        root = unified_yunwu_models_config_manager.get_root()
        platforms: List[Dict[str, str]] = []
        for pk, pv in root.platforms.items():
            platforms.append({
                "key": pk,
                "display_name": pv.display_name or pk,
                "office_web": pv.office_web,
            })
        return {"success": True, "data": {"active_platform": root.active_platform, "platforms": platforms}}
    except Exception as e:
        logger.error("获取平台列表失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/unified-yunwu/test", summary="测试当前激活平台连接")
async def test_unified_yunwu_models(request: Request):
    """使用整合配置中「文案生成」模型名做一次连通性探测。"""
    try:
        await unified_yunwu_models_config_manager.ensure_remote_synced(request.headers.get("Authorization"))
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
        logger.error("测试聚合模型失败: %s", e)
        return {"success": False, "data": {"error": str(e)}}
