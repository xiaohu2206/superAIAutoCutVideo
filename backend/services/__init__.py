#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务模块
提供各种业务服务的实现
"""

from .ai_service import AIService, ai_service, get_ai_service

__all__ = [
    "AIService",
    "ai_service", 
    "get_ai_service"
]