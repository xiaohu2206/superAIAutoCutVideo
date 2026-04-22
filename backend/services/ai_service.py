#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI统一调用服务
封装模型提供商选择、消息发送（普通/流式）、以及健康/配置信息查询。

注意：本服务只负责AI调用，不处理具体业务逻辑。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, AsyncGenerator

from modules.ai import AIModelConfig, ChatMessage, ChatResponse, get_provider_class
from modules.config.content_model_config import content_model_config_manager, ContentModelConfig

logger = logging.getLogger(__name__)

# 文案/结构化等大模型 HTTP 调用：统一读超时与失败重试（避免单行 ReadTimeout 直接失败）
LLM_HTTP_TIMEOUT_SEC = 180
LLM_MAX_ATTEMPTS = 4  # 首次 + 最多 3 次重试
LLM_RETRY_BASE_DELAY_SEC = 1.0


class AIService:
    """统一AI服务入口"""

    def __init__(self) -> None:
        self._active_provider_name: Optional[str] = None
        self._active_model_name: Optional[str] = None

    def _get_active_model_config(self) -> Optional[ContentModelConfig]:
        cfg = content_model_config_manager.get_active_config()
        return cfg

    def _to_ai_model_config(self, cfg: ContentModelConfig) -> AIModelConfig:
        return AIModelConfig(
            provider=cfg.provider,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model_name=cfg.model_name,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
            extra_params=cfg.extra_params or {},
        )

    def get_provider_info(self) -> Dict[str, Any]:
        """返回当前激活的提供商与模型信息"""
        cfg = self._get_active_model_config()
        return {
            "active_provider": cfg.provider if cfg else None,
            "active_model": cfg.model_name if cfg else None,
        }

    async def send_chat(
        self,
        messages: List[ChatMessage],
        response_format: Optional[Dict[str, Any]] = None,
        *,
        temperature: Optional[float] = None,
    ) -> ChatResponse:
        """使用当前激活配置发送普通聊天请求"""
        cfg = self._get_active_model_config()
        if not cfg:
            raise RuntimeError("没有激活的文案生成模型配置，请先在设置中启用一个配置")

        provider_cls = get_provider_class(cfg.provider)
        if not provider_cls:
            raise RuntimeError(f"不支持的AI提供商: {cfg.provider}")

        ai_cfg = self._to_ai_model_config(cfg).model_copy(update={"timeout": LLM_HTTP_TIMEOUT_SEC})
        extra_params: Dict[str, Any] = {}
        if response_format:
            extra_params["response_format"] = response_format
        if temperature is not None:
            extra_params["temperature"] = float(temperature)
        extra_for_call = extra_params if extra_params else None

        last_exc: Optional[Exception] = None
        for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
            provider = provider_cls(ai_cfg)
            try:
                if attempt > 1:
                    logger.warning(
                        "send_chat 重试第 %s/%s 次（上次错误: %s）",
                        attempt,
                        LLM_MAX_ATTEMPTS,
                        last_exc,
                    )
                return await provider.chat_completion(messages, extra_params=extra_for_call)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_exc = e
                logger.warning(
                    "send_chat 失败 attempt=%s/%s: %s",
                    attempt,
                    LLM_MAX_ATTEMPTS,
                    e,
                )
            finally:
                await provider.close()
            if attempt < LLM_MAX_ATTEMPTS:
                delay = min(30.0, LLM_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def send_chat_stream(self, messages: List[ChatMessage]) -> AsyncGenerator[str, None]:
        """使用当前激活配置发送流式聊天请求"""
        cfg = self._get_active_model_config()
        if not cfg:
            raise RuntimeError("没有激活的文案生成模型配置，请先在设置中启用一个配置")

        provider_cls = get_provider_class(cfg.provider)
        if not provider_cls:
            raise RuntimeError(f"不支持的AI提供商: {cfg.provider}")

        ai_cfg = self._to_ai_model_config(cfg).model_copy(update={"timeout": LLM_HTTP_TIMEOUT_SEC})
        provider = provider_cls(ai_cfg)
        try:
            async for chunk in provider.stream_chat_completion(messages):
                yield chunk
        finally:
            await provider.close()

    async def test_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """测试所有配置的连接状态"""
        results: Dict[str, Dict[str, Any]] = {}
        configs = content_model_config_manager.get_all_configs()
        for cfg_id, cfg in configs.items():
            try:
                provider_cls = get_provider_class(cfg.provider)
                if not provider_cls:
                    results[cfg_id] = {
                        "success": False,
                        "error": f"不支持的AI提供商: {cfg.provider}",
                    }
                    continue
                ai_cfg = self._to_ai_model_config(cfg)
                provider = provider_cls(ai_cfg)
                try:
                    res = await provider.test_connection()
                    results[cfg_id] = res
                finally:
                    await provider.close()
            except Exception as e:
                logger.error(f"测试配置 {cfg_id} 失败: {e}")
                results[cfg_id] = {
                    "success": False,
                    "error": str(e),
                }
        return results


# 单例与便捷获取
_ai_service_singleton: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _ai_service_singleton
    if _ai_service_singleton is None:
        _ai_service_singleton = AIService()
    return _ai_service_singleton


ai_service = get_ai_service()

# 为兼容 health_routes 中的引用，暴露配置管理器别名
ai_config_manager = content_model_config_manager
