#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI模型提供商抽象基类
定义统一的接口规范，支持多种AI模型提供商
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator
from pydantic import BaseModel
import httpx
import json
import logging

logger = logging.getLogger(__name__)


class AIModelConfig(BaseModel):
    """AI模型配置"""
    provider: str  # 提供商名称：qwen, doubao, deepseek
    api_key: str  # API密钥
    base_url: str  # API基础地址
    model_name: str  # 模型名称
    max_tokens: Optional[int] = None  # 最大token数
    temperature: Optional[float] = 0.7  # 温度参数
    timeout: Optional[int] = 600  # 超时时间（秒）
    extra_params: Optional[Dict[str, Any]] = {}  # 额外参数


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str  # system, user, assistant
    content: Any  # 消息内容，支持字符串或多模态内容块列表


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str  # 响应内容
    usage: Optional[Dict[str, int]] = None  # token使用情况
    model: Optional[str] = None  # 使用的模型
    finish_reason: Optional[str] = None  # 完成原因


class AIProviderBase(ABC):
    """AI模型提供商抽象基类"""
    
    def __init__(self, config: AIModelConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout or 600),
            headers=self._get_headers()
        )
    
    @abstractmethod
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        pass
    
    @abstractmethod
    def _format_messages(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """格式化消息为提供商特定格式"""
        pass
    
    @abstractmethod
    def _parse_response(self, response_data: Dict[str, Any]) -> ChatResponse:
        """解析响应数据"""
        pass
    
    @abstractmethod
    async def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送请求到AI服务"""
        pass
    
    async def chat_completion(self, messages: List[ChatMessage], extra_params: Optional[Dict[str, Any]] = None) -> ChatResponse:
        """
        聊天完成接口
        
        Args:
            messages: 聊天消息列表
            
        Returns:
            ChatResponse: 聊天响应
        """
        try:
            # 格式化消息
            payload = self._format_messages(messages)
            # 合并额外参数（用于控制结构化输出等）
            if extra_params:
                try:
                    payload.update(extra_params)
                except Exception:
                    pass
            
            # 发送请求
            response_data = await self._make_request(payload)
            
            # 解析响应
            return self._parse_response(response_data)
            
        except Exception as e:
            logger.error(f"AI聊天完成请求失败: {e}")
            raise
    
    async def stream_chat_completion(self, messages: List[ChatMessage], extra_params: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        """
        流式聊天完成接口
        
        Args:
            messages: 聊天消息列表
            
        Yields:
            str: 流式响应内容片段
        """
        try:
            # 格式化消息（流式）
            payload = self._format_messages(messages)
            payload["stream"] = True
            if extra_params:
                try:
                    payload.update(extra_params)
                except Exception:
                    pass
            
            # 发送流式请求
            headers = self._get_headers()
            try:
                eh = payload.get("extra_headers")
                if isinstance(eh, dict):
                    headers.update({k: str(v) for k, v in eh.items()})
            except Exception:
                pass
            async with self.client.stream("POST", self.config.base_url, json=payload, headers=headers) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # 移除 "data: " 前缀
                        if data == "[DONE]":
                            break
                        
                        try:
                            chunk_data = json.loads(data)
                            content = self._extract_stream_content(chunk_data)
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"AI流式聊天完成请求失败: {e}")
            raise
    
    @abstractmethod
    def _extract_stream_content(self, chunk_data: Dict[str, Any]) -> Optional[str]:
        """从流式响应块中提取内容"""
        pass
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接是否正常
        
        Returns:
            Dict: 测试结果
        """
        try:
            # 使用结构化输出进行连通性测试，尽量返回合法JSON
            test_messages = [
                ChatMessage(role="system", content="你是结构化输出测试助手。请严格以json输出。"),
                ChatMessage(
                    role="user",
                    content="请以json输出，返回一个对象，包含字段：ok(bool)、provider(string)、model(string)、timestamp(ISO8601)。仅输出JSON。"
                )
            ]
            response = await self.chat_completion(
                test_messages,
                extra_params={
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"}
                }
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
                "raw_content": raw_content
            }
            
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "provider": self.config.provider,
                "model": self.config.model_name,
                "error": str(e)
            }
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()
    
    def __del__(self):
        """析构函数，确保连接被关闭"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.close())
        except:
            pass
