#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频分析和文案生成模型配置API路由
提供视频分析模型和文案生成模型的配置管理接口
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from modules.config.video_model_config import VideoModelConfig, video_model_config_manager
from modules.config.content_model_config import ContentModelConfig, content_model_config_manager

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/models", tags=["模型配置"])


# 请求/响应模型
class VideoModelConfigRequest(BaseModel):
    """视频分析模型配置请求"""
    config: VideoModelConfig = Field(..., description="视频分析模型配置数据")


class ContentModelConfigRequest(BaseModel):
    """文案生成模型配置请求"""
    config: ContentModelConfig = Field(..., description="文案生成模型配置数据")


class ModelTestRequest(BaseModel):
    """模型测试请求"""
    config_id: str = Field(..., description="配置ID")

def _is_unset_api_key(v: Optional[str]) -> bool:
    s = (v or "").strip()
    return (not s) or s.lower() == "xxx"

def _equivalent_providers_for_sync(provider: Optional[str]) -> List[str]:
    """
    不同模块对同一平台的 provider 命名可能不同，这里做等价映射。
    - 视频: custom_openai_vision
    - 文案: custom_openai
    """
    p = (provider or "").strip().lower()
    if not p:
        return []
    mapping = {
        "custom_openai_vision": ["custom_openai"],
        "custom_openai": ["custom_openai_vision"],
    }
    return [p, *mapping.get(p, [])]


def _is_custom_openai_cross_sync_provider(provider: Optional[str]) -> bool:
    p = (provider or "").strip().lower()
    return p in ("custom_openai_vision", "custom_openai")


def _read_stream_output_flag(model: Any) -> bool:
    """与 AIModelConfig 一致：优先读顶层 stream_output，否则读 extra_params。"""
    if model is None:
        return False
    v = getattr(model, "stream_output", None)
    if v is not None:
        return bool(v)
    ep = getattr(model, "extra_params", None) or {}
    if isinstance(ep, dict):
        return bool(ep.get("stream_output", False))
    return False


def _sync_pydantic_copy(model: Any, updates: Dict[str, Any]) -> Any:
    """Pydantic v2 用 model_copy；否则退回 v1 的 copy(update=...)。"""
    mc = getattr(model, "model_copy", None)
    if callable(mc):
        return mc(update=updates)
    copy_fn = getattr(model, "copy", None)
    if callable(copy_fn):
        return copy_fn(update=updates)
    raise TypeError("配置模型不支持 model_copy/copy")


def _video_custom_fields_changed(
    old: Optional[VideoModelConfig], new_cfg: VideoModelConfig
) -> bool:
    if old is None:
        return True
    return (
        str(getattr(old, "api_key", "") or "").strip()
        != str(new_cfg.api_key or "").strip()
        or str(getattr(old, "base_url", "") or "").strip()
        != str(new_cfg.base_url or "").strip()
        or _read_stream_output_flag(old) != _read_stream_output_flag(new_cfg)
        or str(getattr(old, "model_name", "") or "").strip()
        != str(new_cfg.model_name or "").strip()
    )


def _merge_video_into_content_custom(
    src: VideoModelConfig, dst: ContentModelConfig
) -> ContentModelConfig:
    """自定义 OpenAI 兼容：视频侧字段合并到文案侧（api_key / base_url / stream / model_name）。"""
    cleaned_base = (src.base_url or "").strip().strip("`")
    cleaned_model = (src.model_name or "").strip().strip("`")
    stream_on = _read_stream_output_flag(src)
    ep = dict(dst.extra_params or {})
    ep["stream_output"] = stream_on
    return _sync_pydantic_copy(
        dst,
        {
            "api_key": str(src.api_key or "").strip(),
            "base_url": cleaned_base,
            "model_name": cleaned_model,
            "stream_output": stream_on,
            "extra_params": ep,
        },
    )


# ==================== 视频分析模型配置接口 ====================

def safe_config_dict_hide_apikey(config: VideoModelConfig) -> dict:
    """
    转换为 dict 且隐藏 api_key 的中间部分，仅用于返回给前端
    """
    config_dict = config.dict()
    api_key = config_dict.get("api_key")
    if api_key and len(api_key) > 8:
        config_dict["api_key"] = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
    return config_dict

@router.get("/video-analysis/configs", summary="获取视频分析模型配置")
async def get_video_analysis_configs():
    """获取所有视频分析模型配置"""
    try:
        configs = video_model_config_manager.get_all_configs()
        active_config_id = video_model_config_manager.get_active_config_id()

        # 转换为字典格式，隐藏API密钥
        config_data = {config_id: safe_config_dict_hide_apikey(config) for config_id, config in configs.items()}

        return {
            "success": True,
            "data": {
                "configs": config_data,
                "active_config_id": active_config_id
            },
            "message": f"获取到 {len(configs)} 个视频分析模型配置"
        }
    except Exception as e:
        logger.error(f"获取视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/video-analysis/configs/{config_id}", summary="更新视频分析模型配置")
async def update_video_analysis_config(config_id: str, request: VideoModelConfigRequest):
    """更新视频分析模型配置"""
    try:
        # --------- 修正前端带马赛克串时自动用老明文 ---------
        old_config = video_model_config_manager.get_config(config_id)
        new_config = request.config
        if old_config and new_config.api_key and "*" in new_config.api_key and old_config.api_key[:4] == new_config.api_key[:4] and old_config.api_key[-4:] == new_config.api_key[-4:]:
            # 只要头尾能对上 且中间是星号，则还用老密钥
            new_config.api_key = old_config.api_key
        # ------------------------------------------

        success = video_model_config_manager.update_config(config_id, new_config)
        if success:
            synced_content_config_ids: List[str] = []
            try:
                old_api_key = (old_config.api_key if old_config else None)
                api_key_changed = (old_api_key is None) or (
                    str(old_api_key).strip() != str(new_config.api_key).strip()
                )
                providers = set(_equivalent_providers_for_sync(new_config.provider))
                is_custom = _is_custom_openai_cross_sync_provider(new_config.provider)
                custom_changed = is_custom and _video_custom_fields_changed(
                    old_config, new_config
                )

                for cid, cfg in content_model_config_manager.get_all_configs().items():
                    try:
                        if (cfg.provider or "").lower() not in providers:
                            continue
                        if not _is_unset_api_key(cfg.api_key):
                            continue
                        if is_custom and custom_changed:
                            updated_cfg = _merge_video_into_content_custom(
                                new_config, cfg
                            )
                        elif (
                            api_key_changed
                            and (not _is_unset_api_key(new_config.api_key))
                        ):
                            updated_cfg = cfg.copy(
                                update={
                                    "api_key": str(new_config.api_key).strip(),
                                }
                            )
                        else:
                            continue
                        if content_model_config_manager.update_config(
                            cid, updated_cfg
                        ):
                            synced_content_config_ids.append(cid)
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"同步文案模型 API Key 失败（忽略，不影响保存）: {e}")

            return {
                "success": True,
                "data": {
                    "synced_content_config_ids": synced_content_config_ids,
                    "provider": new_config.provider,
                },
                "message": f"视频分析模型配置 '{config_id}' 更新成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置更新失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/video-analysis/test", summary="测试当前激活的视频分析模型配置")
async def test_active_video_analysis_config():
    """测试当前激活的视频分析模型配置的连接（enabled=True的配置）"""
    try:
        result = await video_model_config_manager.test_active_connection()
        
        return {
            "success": result.get("success", False),
            "data": result,
            "message": result.get("message", "测试完成")
        }
    except Exception as e:
        logger.error(f"测试视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video-analysis/test/{config_id}", summary="测试指定的视频分析模型配置")
async def test_video_analysis_config(config_id: str):
    """测试指定的视频分析模型配置的连接"""
    try:
        result = await video_model_config_manager.test_connection(config_id)
        return {
            "success": result.get("success", False),
            "data": result
        }
    except Exception as e:
        logger.error(f"测试视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

