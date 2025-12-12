#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen AI模型提供商实现（OpenAI兼容模式）
支持通义千问系列模型（DashScope Compatible Mode）
"""

from typing import Dict, List, Any, Optional
import json
import logging

from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class QwenProvider(AIProviderBase):
    """Qwen AI模型提供商"""
    
    def __init__(self, config: AIModelConfig):
        # 设置默认配置（OpenAI兼容端点）
        if not config.base_url:
            config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        else:
            # 确保base_url末尾有/chat/completions
            if not config.base_url.endswith('/chat/completions'):
                config.base_url = config.base_url.rstrip('/') + '/chat/completions'
        
        if not config.model_name:
            config.model_name = "qwen-plus"
            
        super().__init__(config)
    
    def _get_headers(self) -> Dict[str, str]:
        """获取Qwen API请求头"""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def _format_messages(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """格式化消息为OpenAI兼容格式"""
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        payload = {
            "model": self.config.model_name,
            "messages": formatted_messages,
            "temperature": self.config.temperature,
        }
        
        if self.config.extra_params:
            payload.update(self.config.extra_params)
        thinking_param = payload.pop("thinking", None)
        if thinking_param is not None:
            enable_val: Optional[bool] = None
            type_val = None
            if isinstance(thinking_param, dict):
                type_val = thinking_param.get("type")
            else:
                type_val = thinking_param
            if isinstance(type_val, str):
                t = type_val.strip().lower()
                if t in ("enabled", "enable", "on", "true"):
                    enable_val = True
                elif t in ("disabled", "disable", "off", "false"):
                    enable_val = False
            elif isinstance(type_val, bool):
                enable_val = type_val
            if enable_val is not None:
                extra_body = payload.get("extra_body")
                if not isinstance(extra_body, dict):
                    extra_body = {}
                extra_body["enable_thinking"] = enable_val
                payload["extra_body"] = extra_body
                payload["enable_thinking"] = enable_val
        
        return payload
    
    def _parse_response(self, response_data: Dict[str, Any]) -> ChatResponse:
        """解析Qwen响应（OpenAI兼容格式）"""
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise ValueError("响应中没有choices字段")
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            usage = response_data.get("usage", {})
            return ChatResponse(
                content=content,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                },
                model=response_data.get("model", self.config.model_name),
                finish_reason=choice.get("finish_reason")
            )
        except Exception as e:
            logger.error(f"解析Qwen响应失败: {e}")
            raise ValueError(f"解析响应失败: {e}")
    
    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到Qwen API"""
        try:
            is_stream = bool(payload.get("stream"))
            thinking_param = payload.pop("thinking", None)
            if thinking_param is not None:
                enable_val: Optional[bool] = None
                type_val = None
                if isinstance(thinking_param, dict):
                    type_val = thinking_param.get("type")
                else:
                    type_val = thinking_param
                if isinstance(type_val, str):
                    t = type_val.strip().lower()
                    if t in ("enabled", "enable", "on", "true"):
                        enable_val = True
                    elif t in ("disabled", "disable", "off", "false"):
                        enable_val = False
                elif isinstance(type_val, bool):
                    enable_val = type_val
                if enable_val is not None:
                    extra_body = payload.get("extra_body")
                    if not isinstance(extra_body, dict):
                        extra_body = {}
                    extra_body["enable_thinking"] = enable_val
                    payload["extra_body"] = extra_body
                    payload["enable_thinking"] = enable_val
            if not is_stream:
                extra_body = payload.get("extra_body")
                if not isinstance(extra_body, dict):
                    extra_body = {}
                extra_body["enable_thinking"] = False
                payload["extra_body"] = extra_body
                payload["enable_thinking"] = False
            
            
            
            constant_headers = self._get_headers()
            response = await self.client.post(
                self.config.base_url,
                json=payload,
                headers=constant_headers
            )
            response_data = response.json()
            if response.status_code >= 400:
                err = response_data.get("error") if isinstance(response_data, dict) else None
                if isinstance(err, dict):
                    raise Exception(f"Qwen API错误: {err.get('message') or response.text}")
                else:
                    raise Exception(f"Qwen API请求失败: {response.text}")
            
            # 检查API错误
            if "error" in response_data:
                error_info = response_data["error"]
                raise Exception(f"Qwen API错误: {error_info.get('message', 'Unknown error')}")
            
            return response_data
            
        except Exception as e:
            logger.error(f"Qwen API请求失败: {e}")
            raise
    
    def _extract_stream_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        """从Qwen流式响应块中提取内容（OpenAI兼容）"""
        try:
            choices = chunk_data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                return delta.get("content", "")
            return None
        except:
            return None
    
    @classmethod
    def get_available_models(cls) -> List[str]:
        """获取可用的Qwen模型列表"""
        return [
            "qwen-turbo",
            "qwen-plus",
            "qwen-max",
            "qwen-max-1201",
            "qwen-max-longcontext",
            "qwen1.5-72b-chat",
            "qwen1.5-14b-chat",
            "qwen1.5-7b-chat"
        ]
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "provider": "qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "model_name": "qwen-plus",
        }
