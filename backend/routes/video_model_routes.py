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

@router.get("/video-analysis/configs", summary="获取视频分析模型配置")
async def get_video_analysis_configs():
    """获取所有视频分析模型配置"""
    try:
        configs = video_model_config_manager.get_all_configs()
        active_config_id = video_model_config_manager.get_active_config_id()
        
        # 转换为字典格式，隐藏API密钥
        config_data = {}
        for config_id, config in configs.items():
            config_dict = config.dict()
            # 隐藏API密钥的敏感部分
            if config_dict.get("api_key"):
                api_key = config_dict["api_key"]
                if len(api_key) > 8:
                    config_dict["api_key"] = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
            config_data[config_id] = config_dict
        
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
        success = video_model_config_manager.update_config(config_id, request.config)
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


@router.post("/video-analysis/configs", summary="创建视频分析模型配置")
async def create_video_analysis_config(config_id: str, request: VideoModelConfigRequest):
    """创建新的视频分析模型配置"""
    try:
        success = video_model_config_manager.add_config(config_id, request.config)
        if success:
            return {
                "success": True,
                "message": f"视频分析模型配置 '{config_id}' 创建成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置创建失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video-analysis/configs/{config_id}/activate", summary="激活视频分析模型配置")
async def activate_video_analysis_config(config_id: str):
    """激活指定的视频分析模型配置"""
    try:
        success = video_model_config_manager.set_active_config(config_id)
        if success:
            return {
                "success": True,
                "message": f"视频分析模型配置 '{config_id}' 激活成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置激活失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"激活视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/video-analysis/test/{config_id}", summary="测试视频分析模型配置")
async def test_video_analysis_config(config_id: str):
    """测试指定视频分析模型配置的连接"""
    try:
        result = video_model_config_manager.test_connection(config_id)
        return {
            "success": result["success"],
            "data": result
        }
    except Exception as e:
        logger.error(f"测试视频分析模型配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

