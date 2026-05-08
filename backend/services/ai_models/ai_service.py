#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI统一调用服务
封装模型提供商选择、消息发送（普通/流式）、以及健康/配置信息查询。

注意：本服务只负责AI调用，不处理具体业务逻辑。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncGenerator

from modules.ai import AIModelConfig, ChatMessage, ChatResponse, LlmProviderResponseError, get_provider_class
from modules.config.content_model_config import ContentModelConfig, content_model_config_manager
from services.ai_models.unified_model_usage import LlmModelUsage, resolve_content_model_for_llm

logger = logging.getLogger(__name__)

# 文案/结构化等大模型 HTTP 调用：统一读超时与失败重试（避免单行 ReadTimeout 直接失败）
LLM_HTTP_TIMEOUT_SEC = 180
LLM_MAX_ATTEMPTS = 3  # 首次 + 最多 5 次重试
LLM_RETRY_BASE_DELAY_SEC = 1.0
_CHAT_FAILURE_LLM_RAW_MAX = 200_000


def _message_for_failure_log(m: ChatMessage) -> Dict[str, Any]:
    """
    尽量还原请求体中的 messages 用于排查；Pydantic model_dump 在部分多模态/Any
    场景下 content 可能空，回退为实例属性，并带 content 长度信息。
    """
    try:
        d = m.model_dump(mode="json", exclude_unset=False, exclude_none=False)
    except Exception:  # noqa: BLE001
        d = {"role": getattr(m, "role", None), "content": getattr(m, "content", None)}

    raw_c = getattr(m, "content", None)
    dumped = d.get("content")
    if (dumped in (None, "")) and raw_c not in (None, ""):
        d["content"] = raw_c
    if isinstance(d.get("content"), str) and d["content"]:
        d["content_len"] = len(d["content"])
    return d


class AIService:
    """统一AI服务入口"""

    def __init__(self) -> None:
        self._active_provider_name: Optional[str] = None
        self._active_model_name: Optional[str] = None

    def _get_model_config_for_llm(
        self,
        usage: LlmModelUsage,
        omni_effect_tier: Optional[str] = None,
    ) -> ContentModelConfig:
        return resolve_content_model_for_llm(usage, omni_effect_tier=omni_effect_tier)

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

    def get_provider_info(
        self,
        usage: LlmModelUsage = LlmModelUsage.COPYWRITING,
        omni_effect_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """返回指定 LLM 场景下实际使用的提供商与模型（尊重云雾整合总控）。"""
        try:
            cfg = self._get_model_config_for_llm(usage, omni_effect_tier=omni_effect_tier)
        except Exception:
            return {"active_provider": None, "active_model": None}
        return {
            "active_provider": cfg.provider,
            "active_model": cfg.model_name,
        }

    def _log_chat_failure(
        self,
        attempt: int,
        max_attempts: int,
        exception: Exception,
        messages: List[ChatMessage],
        ai_cfg: AIModelConfig,
        extra_params: Optional[Dict[str, Any]],
    ) -> None:
        """将失败的请求详情追加写入持久化日志，用于事后排查大模型返回或网络问题。"""
        try:
            # 持久化目录统一落到 backend/logs/，确保 programme 根目录可被任意包导入时都能找到
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
            os.makedirs(logs_dir, exist_ok=True)
            log_path = os.path.join(logs_dir, "chat_failure_logs.jsonl")

            serializable_messages: List[Dict[str, Any]] = []
            for m in messages:
                if isinstance(m, ChatMessage):
                    serializable_messages.append(_message_for_failure_log(m))
                elif hasattr(m, "model_dump"):
                    try:
                        serializable_messages.append(m.model_dump(mode="json", exclude_unset=False, exclude_none=False))  # type: ignore[union-attr]
                    except Exception:  # noqa: BLE001
                        serializable_messages.append(
                            {"role": getattr(m, "role", None), "content": getattr(m, "content", None)}
                        )
                elif hasattr(m, "dict"):
                    serializable_messages.append(m.dict())  # type: ignore[union-attr]
                else:
                    serializable_messages.append(
                        {"role": getattr(m, "role", None), "content": getattr(m, "content", None)}
                    )

            record: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "attempt": attempt,
                "max_attempts": max_attempts,
                "provider": ai_cfg.provider,
                "model": ai_cfg.model_name,
                "base_url": ai_cfg.base_url,
                "exception_type": type(exception).__name__,
                "exception_msg": str(exception),
                "messages": serializable_messages,
                "extra_params": extra_params,
            }

            if isinstance(exception, LlmProviderResponseError):
                body = exception.raw_body
                max_len = int(_CHAT_FAILURE_LLM_RAW_MAX)
                record["llm_response_raw"] = {
                    "http_status": exception.status_code,
                    "content_type": exception.content_type,
                    "body_length": len(body),
                    "body_text": (
                        body
                        if len(body) <= max_len
                        else f"{body[:max_len]}\n...<truncated total {len(body)} bytes>"
                    ),
                }

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as log_err:
            logger.error("_log_chat_failure 写入失败: %s", log_err)

    async def send_chat(
        self,
        messages: List[ChatMessage],
        response_format: Optional[Dict[str, Any]] = None,
        *,
        temperature: Optional[float] = None,
        usage: LlmModelUsage = LlmModelUsage.COPYWRITING,
        omni_effect_tier: Optional[str] = None,
        http_max_attempts: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> ChatResponse:
        """发送聊天请求；usage 指定业务场景以便在云雾整合模式下选用对应模型。

        http_max_attempts: 单次调用的 HTTP 层最大尝试次数（含首次）；默认 LLM_MAX_ATTEMPTS。
        业务侧若已有自己的退避重试（如分块脚本生成），可传 1 以避免与 send_chat 内层双重重试。
        """
        cfg = self._get_model_config_for_llm(usage, omni_effect_tier=omni_effect_tier)

        provider_cls = get_provider_class(cfg.provider)
        if not provider_cls:
            raise RuntimeError(f"不支持的AI提供商: {cfg.provider}")

        ai_cfg = self._to_ai_model_config(cfg).model_copy(update={"timeout": timeout if timeout is not None else LLM_HTTP_TIMEOUT_SEC})
        extra_params: Dict[str, Any] = {}
        if response_format:
            extra_params["response_format"] = response_format
        if temperature is not None:
            extra_params["temperature"] = float(temperature)
        extra_for_call = extra_params if extra_params else None

        attempts = http_max_attempts if http_max_attempts is not None else LLM_MAX_ATTEMPTS
        attempts = max(1, int(attempts))

        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            provider = provider_cls(ai_cfg)
            try:
                if attempt > 1:
                    logger.warning(
                        "send_chat 重试第 %s/%s 次（上次错误: %s）",
                        attempt,
                        attempts,
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
                    attempts,
                    e,
                )
                self._log_chat_failure(
                    attempt=attempt,
                    max_attempts=attempts,
                    exception=e,
                    messages=messages,
                    ai_cfg=ai_cfg,
                    extra_params=extra_for_call,
                )
            finally:
                await provider.close()
            if attempt < attempts:
                delay = min(30.0, LLM_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    async def send_chat_stream(
        self,
        messages: List[ChatMessage],
        *,
        usage: LlmModelUsage = LlmModelUsage.COPYWRITING,
        omni_effect_tier: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式聊天；usage 与 send_chat 一致。"""
        cfg = self._get_model_config_for_llm(usage, omni_effect_tier=omni_effect_tier)

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
