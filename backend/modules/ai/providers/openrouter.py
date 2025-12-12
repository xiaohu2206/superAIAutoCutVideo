#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenRouter AI模型提供商实现
遵循 OpenAI Chat Completions 接口规范，支持结构化输出（response_format）
"""

from typing import Dict, List, Any, Optional
import logging

from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class OpenRouterProvider(AIProviderBase):
    """OpenRouter AI模型提供商"""

    def __init__(self, config: AIModelConfig):
        # 设置默认配置
        if not config.base_url:
            config.base_url = "https://openrouter.ai/api/v1/chat/completions"
        else:
            if not config.base_url.endswith("/chat/completions"):
                config.base_url = config.base_url.rstrip("/") + "/chat/completions"

        if not config.model_name:
            config.model_name = "openai/gpt-4o-mini"

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
            logger.error(f"解析OpenRouter响应失败: {e}")
            raise ValueError(f"解析响应失败: {e}")

    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 清理不被 OpenRouter 接受的自定义字段
            thinking = payload.pop("thinking", None)
            _ = thinking  # 防止未使用变量告警

            # 处理可选的额外请求头（HTTP-Referer、X-Title 等）
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
            response_data = response.json()
            if response.status_code >= 400:
                err = response_data.get("error") if isinstance(response_data, dict) else None
                if isinstance(err, dict):
                    raise Exception(f"OpenRouter API错误: {err.get('message') or response.text}")
                else:
                    raise Exception(f"OpenRouter API请求失败: {response.text}")

            if "error" in response_data:
                error_info = response_data["error"]
                raise Exception(f"OpenRouter API错误: {error_info.get('message', 'Unknown error')}")

            return response_data
        except Exception as e:
            logger.error(f"OpenRouter API请求失败: {e}")
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
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-1.5-pro",
        ]

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "model_name": "openai/gpt-4o-mini",
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        使用结构化输出（JSON Schema）测试连接
        """
        try:
            test_messages = [
                ChatMessage(role="system", content="你是结构化输出测试助手。请严格以json输出。"),
                ChatMessage(
                    role="user",
                    content="返回一个对象，包含字段：ok(bool)、provider(string)、model(string)、timestamp(ISO8601)。仅输出JSON。"
                ),
            ]
            schema = {
                "name": "connectivity_check",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean", "description": "连接是否正常"},
                        "provider": {"type": "string", "description": "提供商名称"},
                        "model": {"type": "string", "description": "模型名称"},
                        "timestamp": {"type": "string", "description": "ISO8601时间戳"},
                    },
                    "required": ["ok", "provider", "model", "timestamp"],
                    "additionalProperties": False,
                },
            }
            response = await self.chat_completion(
                test_messages,
                extra_params={
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": schema,
                    },
                    "extra_headers": {
                        "HTTP-Referer": "http://localhost",
                        "X-Title": "SuperAutoCutVideoApp",
                    },
                },
            )
            structured_output: Optional[Dict[str, Any]] = None
            raw_content = response.content or ""
            try:
                import json as _json
                structured_output = _json.loads(raw_content)
            except Exception:
                structured_output = None
            return {
                "success": True,
                "message": "连接测试成功",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "response_preview": raw_content[:100] + "..." if len(raw_content) > 100 else raw_content,
                "structured_output": structured_output,
                "raw_content": raw_content,
            }
        except Exception as e:
            logger.error(f"OpenRouter连接测试失败: {e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "error": str(e),
            }
