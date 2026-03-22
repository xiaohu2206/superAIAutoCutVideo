#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 OpenAI 兼容 Chat Completions 接口（与 qwen / yunwu 相同，使用 httpx 直连）
用户可配置任意兼容该协议的 base_url、模型名与 API Key；不依赖 PyPI 的 openai 包。
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class CustomOpenAIProvider(AIProviderBase):
    """自定义模型：OpenAI 兼容 Chat Completions，请求方式与云雾 / 通义一致（httpx）。"""

    def __init__(self, config: AIModelConfig):
        if not config.base_url:
            config.base_url = "https://api.openai.com/v1/chat/completions"
        else:
            bu = config.base_url.strip().strip("`").rstrip("/")
            if not bu.endswith("/chat/completions"):
                config.base_url = bu + "/chat/completions"
            else:
                config.base_url = bu

        if not config.model_name:
            config.model_name = "gpt-4o-mini"

        super().__init__(config)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _format_messages(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        formatted: List[Dict[str, Any]] = []
        for msg in messages:
            formatted.append({"role": msg.role, "content": msg.content})

        payload: Dict[str, Any] = {
            "model": self.config.model_name,
            "messages": formatted,
            "temperature": self.config.temperature,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens
        if self.config.extra_params:
            try:
                payload.update(self.config.extra_params)
            except Exception:
                pass
        return payload

    @staticmethod
    def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        body = dict(payload)
        for k in ("thinking", "extra_body", "enable_thinking"):
            body.pop(k, None)
        return body

    def _parse_response(self, response_data: Dict[str, Any]) -> ChatResponse:
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise ValueError("响应中没有 choices 字段")
            choice = choices[0]
            message = choice.get("message", {}) or {}
            content = message.get("content", "") or ""
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
            logger.error(f"解析自定义 OpenAI 兼容响应失败: {e}")
            raise ValueError(f"解析响应失败: {e}") from e

    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            body = self._sanitize_payload(dict(payload))
            body.pop("stream", None)

            extra_headers: Dict[str, str] = {}
            eh = body.pop("extra_headers", None)
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
                json=body,
                headers=headers,
            )
            response_data = response.json()
            if response.status_code >= 400:
                err = response_data.get("error") if isinstance(response_data, dict) else None
                if isinstance(err, dict):
                    raise Exception(err.get("message") or response.text)
                raise Exception(response.text)

            if isinstance(response_data, dict) and "error" in response_data:
                error_info = response_data["error"]
                if isinstance(error_info, dict):
                    raise Exception(error_info.get("message", "Unknown error"))
                raise Exception(str(error_info))

            return response_data
        except Exception as e:
            logger.error(f"自定义 OpenAI 兼容 API 请求失败: {e}")
            raise

    def _extract_stream_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        try:
            choices = chunk_data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {}) or {}
                return delta.get("content") or None
            return None
        except Exception:
            return None


class CustomOpenAIVisionProvider(CustomOpenAIProvider):
    """
    视频分析用自定义端点：协议与 CustomOpenAIProvider 相同，`content` 可为图文多模态列表。
    连接测试会发送一张内置小图，验证接口是否支持视觉输入。
    """

    @staticmethod
    def _test_image_data_uri() -> str:
        """
        生成满足常见 VL 接口最小边长要求（如通义要求宽高均 >10）的测试图，避免 1x1 被拒。
        """
        from PIL import Image

        buf = BytesIO()
        img = Image.new("RGB", (32, 32), color=(200, 200, 200))
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    async def test_connection(self) -> Dict[str, Any]:
        try:
            data_uri = self._test_image_data_uri()
            test_messages = [
                ChatMessage(
                    role="user",
                    content=[
                        {
                            "type": "text",
                            "text": "请根据图像用一句话描述你看到的内容（不超过30字）。若无法处理图像，请说明原因。",
                        },
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                )
            ]
            response = await self.chat_completion(
                test_messages,
                extra_params={"max_tokens": 128},
            )
            raw = response.content
            if raw is None:
                raw_text = ""
            elif isinstance(raw, str):
                raw_text = raw
            else:
                raw_text = str(raw)
            return {
                "success": True,
                "message": "连接测试成功（已发送测试图片，多模态可用）",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "response_preview": raw_text[:120] + "..." if len(raw_text) > 120 else raw_text,
                "raw_content": raw_text,
            }
        except Exception as e:
            logger.error(f"自定义视觉接口连接测试失败: {e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "error": str(e),
            }
