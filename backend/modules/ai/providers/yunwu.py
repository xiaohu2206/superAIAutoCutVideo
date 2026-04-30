#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整合平台模型提供商实现
遵循 OpenAI Chat Completions 接口规范，支持结构化输出（response_format）
"""

from typing import Dict, List, Any, Optional
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse, LlmProviderResponseError

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
_YUNWU_HTTP_DEBUG_DIR = _BACKEND_DIR / "logs"


def _write_yunwu_http_debug_file(
    *,
    status_code: int,
    request_url: str,
    model_name: str,
    content_type: str,
    body_text: str,
) -> None:
    """在同步上下文中将原始 HTTP 信息写入文件，供 asyncio.to_thread 调用以免阻塞事件循环。"""
    try:
        _YUNWU_HTTP_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = f"yunwu_http_{status_code}_{ts}.txt"
        path = _YUNWU_HTTP_DEBUG_DIR / fn
        text = "\n".join(
            [
                f"status_code={status_code}",
                f"url={request_url}",
                f"model={model_name}",
                f"content_type={content_type}",
                f"body_length={len(body_text)}",
                "",
                "--- body (truncated 500k) ---",
                (body_text or "")[:500000],
            ]
        )
        path.write_text(text, encoding="utf-8")
    except Exception as werr:  # noqa: BLE001
        logger.warning("写入 yunwu HTTP 调试文件失败: %s", werr)


class YunwuProvider(AIProviderBase):
    """整合平台模型提供商"""

    def __init__(self, config: AIModelConfig):
        if not config.base_url:
            config.base_url = "https://yunwu.ai/v1/chat/completions"
        else:
            if not config.base_url.endswith("/chat/completions"):
                config.base_url = config.base_url.rstrip("/") + "/chat/completions"

        if not config.model_name:
            config.model_name = "gemini-3.1-pro-preview"

        super().__init__(config)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _format_messages(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        formatted_messages: List[Dict[str, Any]] = []
        for msg in messages:
            formatted_messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )

        payload: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": formatted_messages,
            "temperature": self.config.temperature,
        }

        if self.config.extra_params:
            try:
                payload.update(self.config.extra_params)
            except Exception:
                pass

        return payload

    def _parse_response(self, response_data: Dict[str, Any]) -> ChatResponse:
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise ValueError("响应中没有choices字段")
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            usage = response_data.get("usage", {}) or {}
            return ChatResponse(
                content=content,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                model=response_data.get("model", self.config.model_name),
                finish_reason=choice.get("finish_reason"),
            )
        except Exception as e:
            logger.error(f"解析整合平台API响应失败: {e}")
            raise ValueError(f"解析响应失败: {e}")

    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            try:
                _closed = bool(getattr(self.client, "is_closed", False))
            except Exception:
                _closed = False
            logger.debug(
                "[yunwu] POST chat/completions self_id=%s client_id=%s client_closed=%s model=%s",
                id(self),
                id(self.client),
                _closed,
                self.config.model_name,
            )
            thinking = payload.pop("thinking", None)
            _ = thinking

            extra_headers = {}
            eh = payload.pop("extra_headers", None)
            if isinstance(eh, dict):
                extra_headers = {k: str(v) for k, v in eh.items()}

            headers = self._get_headers()
            if extra_headers:
                try:
                    headers.update(extra_headers)
                except Exception:
                    pass

            response = await self.client.post(
                self.config.base_url,
                json=payload,
                headers=headers,
            )
            status_code = int(response.status_code)
            raw_text = response.text or ""
            ct = (response.headers.get("content-type") or "").split(";")[0].strip()

            response_data: Any
            if not raw_text.strip():
                if status_code >= 400:
                    await asyncio.to_thread(
                        _write_yunwu_http_debug_file,
                        status_code=status_code,
                        request_url=str(self.config.base_url),
                        model_name=self.config.model_name,
                        content_type=ct,
                        body_text="(empty body)",
                    )
                    raise LlmProviderResponseError(
                        f"整合平台API 错误: HTTP {status_code} 响应体为空或仅空白"
                        "（常见于 5xx；已写入 backend/logs/ 下 yunwu_http_*.txt 便于对比网关/HTML 页）",
                        status_code=status_code,
                        raw_body="",
                        content_type=ct,
                    )
                response_data = {}
            else:
                try:
                    response_data = json.loads(raw_text)
                except json.JSONDecodeError as je:
                    await asyncio.to_thread(
                        _write_yunwu_http_debug_file,
                        status_code=status_code,
                        request_url=str(self.config.base_url),
                        model_name=self.config.model_name,
                        content_type=ct,
                        body_text=raw_text,
                    )
                    logger.error(
                        "整合平台API 响应体非 JSON: status=%s content_type=%s len=%s preview=%r",
                        status_code,
                        ct,
                        len(raw_text),
                        raw_text[:800],
                    )
                    raise LlmProviderResponseError(
                        f"整合平台API 响应体非有效 JSON (HTTP {status_code}): {je!s}；"
                        f"已写入 backend/logs/ 下 yunwu_http_*.txt",
                        status_code=status_code,
                        raw_body=raw_text,
                        content_type=ct,
                    ) from je

            if status_code >= 400:
                err = response_data.get("error") if isinstance(response_data, dict) else None
                if isinstance(err, dict):
                    raise LlmProviderResponseError(
                        f"整合平台API错误: {err.get('message') or raw_text[:2000]}",
                        status_code=status_code,
                        raw_body=raw_text,
                        content_type=ct,
                    )
                # 非标准 JSON 错误体已在上方 json.loads 分支处理
                if not (isinstance(response_data, dict) and response_data.get("error")):
                    await asyncio.to_thread(
                        _write_yunwu_http_debug_file,
                        status_code=status_code,
                        request_url=str(self.config.base_url),
                        model_name=self.config.model_name,
                        content_type=ct,
                        body_text=raw_text,
                    )
                raise LlmProviderResponseError(
                    f"整合平台API请求失败: {raw_text[:2000]}",
                    status_code=status_code,
                    raw_body=raw_text,
                    content_type=ct,
                )

            if isinstance(response_data, dict) and "error" in response_data:
                error_info = response_data["error"]
                if isinstance(error_info, dict):
                    raise LlmProviderResponseError(
                        f"整合平台API错误: {error_info.get('message', 'Unknown error')}",
                        status_code=status_code,
                        raw_body=raw_text,
                        content_type=ct,
                    )
                raise LlmProviderResponseError(
                    f"整合平台API错误: {str(error_info)}",
                    status_code=status_code,
                    raw_body=raw_text,
                    content_type=ct,
                )

            return response_data
        except Exception as e:
            logger.error(f"整合平台API请求失败: {e}")
            raise

    def _extract_stream_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        try:
            choices = chunk_data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                return delta.get("content", "")
            return None
        except Exception:
            return None

    @classmethod
    def get_available_models(cls) -> List[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-3.1-pro-preview",
            "claude-sonnet-4-20250514",
        ]

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "provider": "yunwu",
            "base_url": "https://yunwu.ai/v1/chat/completions",
            "model_name": "gemini-3.1-pro-preview",
        }

    async def test_connection(self) -> Dict[str, Any]:
        try:
            test_messages = [
                ChatMessage(role="user", content="请回复'连接成功-SUCCESS'。"),
            ]
            response = await self.chat_completion(test_messages)
            raw_content = response.content or ""
            if not raw_content.strip():
                return {
                    "success": False,
                    "message": "连接已建立，但模型返回内容为空，请检查模型配置或接口状态",
                    "provider": self.config.provider,
                    "model": self.config.model_name,
                    "response_preview": "",
                    "raw_content": raw_content,
                    "error": "empty_response",
                }
            return {
                "success": True,
                "message": raw_content[:100] + "..." if len(raw_content) > 100 else raw_content,
                "provider": self.config.provider,
                "model": self.config.model_name,
                "response_preview": raw_content[:100] + "..." if len(raw_content) > 100 else raw_content,
                "raw_content": raw_content,
            }
        except Exception as e:
            logger.error(f"整合平台API连接测试失败: {e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "error": str(e),
            }

