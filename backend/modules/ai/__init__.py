#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模块
提供AI模型调用和管理功能
"""

from .base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse
from .providers import (
    QwenProvider,
    DoubaoProvider,
    DeepSeekProvider,
    OpenRouterProvider,
    PROVIDER_REGISTRY,
    get_provider_class,
    get_available_providers
)

__all__ = [
    "AIProviderBase",
    "AIModelConfig", 
    "ChatMessage",
    "ChatResponse",
    "QwenProvider",
    "DoubaoProvider",
    "DeepSeekProvider",
    "OpenRouterProvider",
    "PROVIDER_REGISTRY",
    "get_provider_class",
    "get_available_providers"
]
