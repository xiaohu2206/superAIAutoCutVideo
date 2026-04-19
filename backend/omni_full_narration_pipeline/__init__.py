# -*- coding: utf-8 -*-
"""Omni 全链路解说脚本编排（与 visual 生成脚本、各单步路由逻辑隔离，仅顺序调用既有服务）。"""

from .service import omni_full_narration_pipeline_service

__all__ = ["omni_full_narration_pipeline_service"]
