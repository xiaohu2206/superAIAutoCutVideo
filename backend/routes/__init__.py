#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由模块初始化
"""

from .health_routes import router as health_router
from .log_routes import router as log_router

__all__ = ["health_router", "log_router"]