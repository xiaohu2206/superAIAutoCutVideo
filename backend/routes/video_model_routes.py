#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频分析和文案生成模型配置API路由
提供视频分析模型和文案生成模型的配置管理接口
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
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
            return {
                "success": True,
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

