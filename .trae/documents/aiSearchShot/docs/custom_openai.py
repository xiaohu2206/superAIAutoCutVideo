#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 OpenAI 兼容 Chat Completions 接口（与 qwen / yunwu 相同，使用 httpx 直连）
用户可配置任意兼容该协议的 base_url、模型名与 API Key；不依赖 PyPI 的 openai 包。
"""

from __future__ import annotations

import base64
import json
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
            body.pop("stream_output", None)
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

            response_data = await self._make_stream_request(body, headers)

            if isinstance(response_data, dict) and "error" in response_data:
                error_info = response_data["error"]
                if isinstance(error_info, dict):
                    raise Exception(error_info.get("message", "Unknown error"))
                raise Exception(str(error_info))

            try:
                choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
                first_choice = choices[0] if choices else {}
                message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
                content = message.get("content") if isinstance(message, dict) else None
                if content is not None:
                    logged_content = content if isinstance(content, str) else str(content)
                    if len(logged_content) > 100:
                        logged_content = f"{logged_content[:100]}..."
                    logger.info(
                        "自定义 OpenAI 兼容模型输出内容: %s",
                        logged_content,
                    )
                else:
                    logger.info("自定义 OpenAI 兼容接口响应: %s", response_data)
            except Exception as log_error:
                logger.warning("记录自定义 OpenAI 兼容模型输出失败: %s", log_error)

            return response_data
        except Exception as e:
            logger.error(f"自定义 OpenAI 兼容 API 请求失败: {e}")
            raise

    async def _make_stream_request(self, body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        stream_body = dict(body)
        stream_body["stream"] = True
        aggregated_content: List[str] = []
        final_chunk: Optional[Dict[str, Any]] = None
        response_model: Optional[str] = None
        finish_reason: Optional[str] = None
        usage: Dict[str, Any] = {}

        async with self.client.stream(
            "POST",
            self.config.base_url,
            json=stream_body,
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk_data = json.loads(data)
                except Exception:
                    continue

                if not isinstance(chunk_data, dict):
                    continue

                final_chunk = chunk_data
                response_model = chunk_data.get("model") or response_model
                if isinstance(chunk_data.get("usage"), dict):
                    usage = chunk_data.get("usage") or usage

                choices = chunk_data.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    finish_reason = choices[0].get("finish_reason") or finish_reason

                content = self._extract_stream_content(chunk_data)
                if content:
                    aggregated_content.append(content)

        merged_content = "".join(aggregated_content)
        message: Dict[str, Any] = {"role": "assistant", "content": merged_content}
        choice_payload: Dict[str, Any] = {
            "index": 0,
            "message": message,
            "finish_reason": finish_reason or "stop",
        }

        result: Dict[str, Any] = {
            "id": (final_chunk or {}).get("id") or "chatcmpl-stream-aggregated",
            "object": "chat.completion",
            "created": (final_chunk or {}).get("created"),
            "model": response_model or self.config.model_name,
            "choices": [choice_payload],
            "usage": usage,
        }
        return result

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
        优先使用 JPEG，兼容性通常比 PNG data URI 更好。
        """
        from PIL import Image

        buf = BytesIO()
        img = Image.new("RGB", (64, 64), color=(200, 200, 200))
        img.save(buf, format="JPEG", quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    async def test_connection(self) -> Dict[str, Any]:
        try:
            data_uri = self._test_image_data_uri()
            test_messages = [
                ChatMessage(
                    role="user",
                    content=[
                        {
                            "type": "text",
                            "text": "请只根据这张图片本身回答：这是一张什么样的测试图？如果你能看到图片，请明确提到颜色或画面内容；如果看不到，再说明原因。回答不超过30字。",
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
                raw_text = raw.strip()
            else:
                raw_text = str(raw).strip()

            lowered = raw_text.lower()
            vision_failure_markers = [
                "无法直接处理这张图像",
                "无法处理这张图像",
                "无法查看图片",
                "无法看到图片",
                "看不到图片",
                "无法访问图像",
                "无法识别图像",
                "cannot view the image",
                "can't view the image",
                "cannot access the image",
            ]
            if any(marker in raw_text or marker in lowered for marker in vision_failure_markers):
                return {
                    "success": False,
                    "message": "连接已建立，但模型未正确识别测试图片，请检查接口是否真的支持视觉输入格式",
                    "provider": self.config.provider,
                    "model": self.config.model_name,
                    "response_preview": raw_text[:120] + "..." if len(raw_text) > 120 else raw_text,
                    "raw_content": raw_text,
                    "error": "vision_input_not_effective",
                }

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
