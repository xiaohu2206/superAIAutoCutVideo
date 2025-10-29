#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模型提供商模块
包含各种AI模型提供商的实现
"""

from .qwen import QwenProvider
from .doubao import DoubaoProvider
from .deepseek import DeepSeekProvider

__all__ = [
    "QwenProvider",
    "DoubaoProvider", 
    "DeepSeekProvider"
]

# 提供商注册表
PROVIDER_REGISTRY = {
    "qwen": QwenProvider,
    "doubao": DoubaoProvider,
    "deepseek": DeepSeekProvider
}

def get_provider_class(provider_name: str):
    """根据提供商名称获取提供商类"""
    return PROVIDER_REGISTRY.get(provider_name.lower())

def get_available_providers():
    """获取所有可用的提供商列表"""
    return list(PROVIDER_REGISTRY.keys())