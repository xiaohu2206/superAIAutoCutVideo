#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
提供AI配置、视频分析模型配置、文案生成模型配置等管理功能
"""


from .video_model_config import VideoModelConfig, VideoModelConfigManager, video_model_config_manager
from .content_model_config import ContentModelConfig, ContentModelConfigManager, content_model_config_manager

__all__ = [
    "AIConfigModel",
    "AIConfigManager", 
    "ai_config_manager",
    "VideoModelConfig",
    "VideoModelConfigManager",
    "video_model_config_manager",
    "ContentModelConfig",
    "ContentModelConfigManager",
    "content_model_config_manager"
]