#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen AI模型提供商实现
支持通义千问系列模型
"""

from typing import Dict, List, Any, Optional
import json
import logging

from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class QwenProvider(AIProviderBase):
    """Qwen AI模型提供商"""
    
    def __init__(self, config: AIModelConfig):
        # 设置默认配置
        if not config.base_url:
            config.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        
        if not config.model_name:
            config.model_name = "qwen-turbo"
            
        super().__init__(config)
    
    def _get_headers(self) -> Dict[str, str]:
        """获取Qwen API请求头"""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def _format_messages(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """格式化消息为Qwen API格式"""
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        payload = {
            "model": self.config.model_name,
            "input": {
                "messages": formatted_messages
            },
            "parameters": {
                "max_tokens": self.config.max_tokens or 4000,
                "temperature": self.config.temperature or 0.7,
                "top_p": 0.8,
                "repetition_penalty": 1.1
            }
        }
        
        # 添加额外参数
        if self.config.extra_params:
            payload["parameters"].update(self.config.extra_params)
        
        return payload
    
    def _parse_response(self, response_data: Dict[str, Any]) -> ChatResponse:
        """解析Qwen API响应"""
        try:
            output = response_data.get("output", {})
            content = output.get("text", "")
            
            usage = response_data.get("usage", {})
            
            return ChatResponse(
                content=content,
                usage={
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                },
                model=self.config.model_name,
                finish_reason=output.get("finish_reason")
            )
            
        except Exception as e:
            logger.error(f"解析Qwen响应失败: {e}")
            raise ValueError(f"解析响应失败: {e}")
    
    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到Qwen API"""
        try:
            response = await self.client.post(
                self.config.base_url,
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            
            response_data = response.json()
            
            # 检查API错误
            if "error" in response_data:
                error_info = response_data["error"]
                raise Exception(f"Qwen API错误: {error_info.get('message', 'Unknown error')}")
            
            return response_data
            
        except Exception as e:
            logger.error(f"Qwen API请求失败: {e}")
            raise
    
    def _extract_stream_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        """从Qwen流式响应块中提取内容"""
        try:
            output = chunk_data.get("output", {})
            return output.get("text", "")
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
            "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            "model_name": "qwen-turbo",
            "max_tokens": 4000,
            "temperature": 0.7,
            "timeout": 30
        }