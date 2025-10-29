#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI服务调用模块
提供统一的AI服务调用接口，支持多种AI模型提供商
"""

from typing import Dict, List, Optional, Any, AsyncGenerator
import logging
from contextlib import asynccontextmanager

from modules.ai import (
    AIProviderBase, AIModelConfig, ChatMessage, ChatResponse,
    get_provider_class, get_available_providers
)
from modules.config import ai_config_manager, AIConfigModel

logger = logging.getLogger(__name__)


class AIService:
    """AI服务管理器"""
    
    def __init__(self):
        self._providers: Dict[str, AIProviderBase] = {}
        self._active_provider: Optional[AIProviderBase] = None
        self._active_config_id: Optional[str] = None
    
    async def initialize(self):
        """初始化AI服务"""
        try:
            # 加载活跃配置
            await self._load_active_provider()
            logger.info("AI服务初始化完成")
        except Exception as e:
            logger.error(f"AI服务初始化失败: {e}")
            raise
    
    async def _load_active_provider(self):
        """加载活跃的AI提供商"""
        try:
            active_config = ai_config_manager.get_active_config()
            active_config_id = ai_config_manager.get_active_config_id()
            
            if not active_config or not active_config_id:
                logger.warning("没有找到活跃的AI配置")
                return
            
            # 创建提供商实例
            provider_class = get_provider_class(active_config.provider)
            if not provider_class:
                raise ValueError(f"不支持的AI提供商: {active_config.provider}")
            
            # 转换配置
            ai_model_config = ai_config_manager.to_ai_model_config(active_config_id)
            if not ai_model_config:
                raise ValueError("无法转换AI模型配置")
            
            # 创建提供商实例
            provider = provider_class(ai_model_config)
            
            # 关闭旧的提供商
            if self._active_provider:
                await self._active_provider.close()
            
            self._active_provider = provider
            self._active_config_id = active_config_id
            self._providers[active_config_id] = provider
            
            logger.info(f"加载AI提供商成功: {active_config.provider} ({active_config_id})")
            
        except Exception as e:
            logger.error(f"加载AI提供商失败: {e}")
            raise
    
    async def switch_provider(self, config_id: str) -> bool:
        """
        切换AI提供商
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否切换成功
        """
        try:
            # 设置为活跃配置
            if not ai_config_manager.set_active_config(config_id):
                return False
            
            # 重新加载提供商
            await self._load_active_provider()
            
            logger.info(f"切换AI提供商成功: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"切换AI提供商失败: {e}")
            return False
    
    def get_provider(self, config_id: Optional[str] = None) -> Optional[AIProviderBase]:
        """
        获取AI提供商实例
        
        Args:
            config_id: 配置ID，如果为None则返回活跃提供商
            
        Returns:
            AIProviderBase: 提供商实例
        """
        if config_id is None:
            return self._active_provider
        
        return self._providers.get(config_id)
    
    async def create_provider(self, config_id: str) -> Optional[AIProviderBase]:
        """
        创建新的AI提供商实例
        
        Args:
            config_id: 配置ID
            
        Returns:
            AIProviderBase: 提供商实例
        """
        try:
            config = ai_config_manager.get_config(config_id)
            if not config:
                raise ValueError(f"配置不存在: {config_id}")
            
            if not config.enabled:
                raise ValueError(f"配置未启用: {config_id}")
            
            # 获取提供商类
            provider_class = get_provider_class(config.provider)
            if not provider_class:
                raise ValueError(f"不支持的AI提供商: {config.provider}")
            
            # 转换配置
            ai_model_config = ai_config_manager.to_ai_model_config(config_id)
            if not ai_model_config:
                raise ValueError("无法转换AI模型配置")
            
            # 创建提供商实例
            provider = provider_class(ai_model_config)
            self._providers[config_id] = provider
            
            logger.info(f"创建AI提供商成功: {config.provider} ({config_id})")
            return provider
            
        except Exception as e:
            logger.error(f"创建AI提供商失败: {e}")
            return None
    
    async def chat_completion(
        self, 
        messages: List[ChatMessage], 
        config_id: Optional[str] = None
    ) -> ChatResponse:
        """
        聊天完成接口
        
        Args:
            messages: 聊天消息列表
            config_id: 配置ID，如果为None则使用活跃提供商
            
        Returns:
            ChatResponse: 聊天响应
        """
        try:
            provider = self.get_provider(config_id)
            if not provider:
                if config_id:
                    provider = await self.create_provider(config_id)
                
                if not provider:
                    raise ValueError("没有可用的AI提供商")
            
            return await provider.chat_completion(messages)
            
        except Exception as e:
            logger.error(f"AI聊天完成请求失败: {e}")
            raise
    
    async def stream_chat_completion(
        self, 
        messages: List[ChatMessage], 
        config_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天完成接口
        
        Args:
            messages: 聊天消息列表
            config_id: 配置ID，如果为None则使用活跃提供商
            
        Yields:
            str: 流式响应内容片段
        """
        try:
            provider = self.get_provider(config_id)
            if not provider:
                if config_id:
                    provider = await self.create_provider(config_id)
                
                if not provider:
                    raise ValueError("没有可用的AI提供商")
            
            async for chunk in provider.stream_chat_completion(messages):
                yield chunk
                
        except Exception as e:
            logger.error(f"AI流式聊天完成请求失败: {e}")
            raise
    
    async def test_connection(self, config_id: Optional[str] = None) -> Dict[str, Any]:
        """
        测试AI提供商连接
        
        Args:
            config_id: 配置ID，如果为None则测试活跃提供商
            
        Returns:
            Dict: 测试结果
        """
        try:
            provider = self.get_provider(config_id)
            if not provider:
                if config_id:
                    provider = await self.create_provider(config_id)
                
                if not provider:
                    return {
                        "success": False,
                        "message": "没有可用的AI提供商",
                        "config_id": config_id
                    }
            
            result = await provider.test_connection()
            result["config_id"] = config_id or self._active_config_id
            return result
            
        except Exception as e:
            logger.error(f"AI连接测试失败: {e}")
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "config_id": config_id,
                "error": str(e)
            }
    
    async def test_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """
        测试所有启用配置的连接
        
        Returns:
            Dict: 所有配置的测试结果
        """
        results = {}
        enabled_configs = ai_config_manager.get_enabled_configs()
        
        for config_id in enabled_configs.keys():
            results[config_id] = await self.test_connection(config_id)
        
        return results
    
    def get_available_providers(self) -> List[str]:
        """获取所有可用的AI提供商"""
        return get_available_providers()
    
    def get_provider_info(self) -> Dict[str, Any]:
        """获取当前提供商信息"""
        if not self._active_provider or not self._active_config_id:
            return {
                "active": False,
                "message": "没有活跃的AI提供商"
            }
        
        config = ai_config_manager.get_config(self._active_config_id)
        if not config:
            return {
                "active": False,
                "message": "活跃配置不存在"
            }
        
        return {
            "active": True,
            "config_id": self._active_config_id,
            "provider": config.provider,
            "model_name": config.model_name,
            "description": config.description,
            "base_url": config.base_url
        }
    
    async def close(self):
        """关闭所有AI提供商连接"""
        try:
            for provider in self._providers.values():
                await provider.close()
            
            self._providers.clear()
            self._active_provider = None
            self._active_config_id = None
            
            logger.info("AI服务已关闭")
            
        except Exception as e:
            logger.error(f"关闭AI服务失败: {e}")


# 全局AI服务实例
ai_service = AIService()


@asynccontextmanager
async def get_ai_service():
    """获取AI服务实例的上下文管理器"""
    try:
        if not ai_service._active_provider:
            await ai_service.initialize()
        yield ai_service
    except Exception as e:
        logger.error(f"获取AI服务失败: {e}")
        raise