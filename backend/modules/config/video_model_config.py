#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频分析模型配置管理模块
支持动态配置视频分析AI模型参数，包括提供商、API密钥、模型名称等
"""

import json
from pathlib import Path
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)


class VideoModelConfig(BaseModel):
    """视频分析模型配置数据模型"""
    provider: str = Field(..., description="AI提供商名称")
    api_key: str = Field(..., description="API密钥")
    base_url: str = Field(..., description="API基础地址")
    model_name: str = Field(..., description="模型名称")
    max_tokens: Optional[int] = Field(100000, description="最大token数")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    timeout: Optional[int] = Field(600, description="超时时间（秒）", ge=1, le=10000)
    extra_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外参数")
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, description="配置描述")
    
    @validator('provider')
    def validate_provider(cls, v):
        allowed_providers = ['qwen', 'doubao', 'deepseek', 'openai', 'claude', 'openrouter']
        if v.lower() not in allowed_providers:
            raise ValueError(f'提供商必须是以下之一: {allowed_providers}')
        return v.lower()
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('API密钥不能为空')
        return v.strip()


class VideoModelConfigManager:
    """视频分析模型配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，默认为 backend/config/video_model_config.json
        """
        if config_file is None:
            # 默认配置文件路径
            backend_dir = Path(__file__).parent.parent.parent
            config_dir = backend_dir / "config"
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "video_model_config.json"
        
        self.config_file = Path(config_file)
        self.configs: Dict[str, VideoModelConfig] = {}
        
        # 加载配置
        self.load_configs()

    def load_configs(self):
        """从文件加载配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 加载配置项
                configs_data = data.get('configs', {})
                for config_id, config_data in configs_data.items():
                    try:
                        self.configs[config_id] = VideoModelConfig(**config_data)
                    except Exception as e:
                        logger.error(f"加载视频分析模型配置 {config_id} 失败: {e}")
                
                logger.info(f"成功加载 {len(self.configs)} 个视频分析模型配置")
            else:
                # 创建默认配置
                self._create_default_configs()
                
        except Exception as e:
            logger.error(f"加载视频分析模型配置失败: {e}")
            self._create_default_configs()

    def save_configs(self):
        """保存配置到文件"""
        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 准备数据
            data = {
                'configs': {}
            }
            
            for config_id, config in self.configs.items():
                data['configs'][config_id] = config.dict()
            
            # 写入文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("视频分析模型配置保存成功")
            
        except Exception as e:
            logger.error(f"保存视频分析模型配置失败: {e}")
            raise

    def _create_default_configs(self):
        """创建默认配置"""
        default_configs = [
            {
                'id': 'qwen_video_analysis',
                'config': VideoModelConfig(
                    provider='qwen',
                    api_key='your_qwen_api_key_here',
                    base_url='https://dashscope.aliyuncs.com/api/v1/chat/completions',
                    model_name='qwen-vl-plus',
                    description='通义千问视频分析模型',
                    enabled=True
                )
            },
            {
                'id': 'doubao_video_analysis',
                'config': VideoModelConfig(
                    provider='doubao',
                    api_key='your_doubao_api_key_here',
                    base_url='https://ark.cn-beijing.volces.com/api/v3/chat/completions',
                    model_name='doubao-seed-1-6-vision-250815',
                    description='豆包视频分析模型',
                    enabled=False
                )
            }
        ]
        
        for item in default_configs:
            self.configs[item['id']] = item['config']
        
        # 保存默认配置
        self.save_configs()

    def update_config(self, config_id: str, config: VideoModelConfig) -> bool:
        """
        更新配置，确保同时只有一个配置被启用
        
        Args:
            config_id: 配置ID
            config: 新的配置对象
            
        Returns:
            bool: 是否更新成功
        """
        try:
            if config_id not in self.configs:
                raise ValueError(f"配置ID '{config_id}' 不存在")
            
            # 如果当前配置被设置为启用，则禁用其他所有配置
            if config.enabled:
                for other_id, other_config in self.configs.items():
                    if other_id != config_id and other_config.enabled:
                        # 创建新的配置对象，将enabled设置为False
                        updated_config = other_config.copy(update={'enabled': False})
                        self.configs[other_id] = updated_config
                        logger.info(f"自动禁用配置: {other_id}")
            
            self.configs[config_id] = config
            self.save_configs()
            
            logger.info(f"更新视频分析模型配置成功: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新视频分析模型配置失败: {e}")
            return False

    def get_config(self, config_id: str) -> Optional[VideoModelConfig]:
        """
        获取指定配置
        
        Args:
            config_id: 配置ID
            
        Returns:
            VideoModelConfig: 配置对象，如果不存在返回None
        """
        return self.configs.get(config_id)

    def get_all_configs(self) -> Dict[str, VideoModelConfig]:
        """获取所有配置"""
        return self.configs.copy()
    
    def get_active_config(self) -> Optional[VideoModelConfig]:
        """获取当前启用的配置（只会有一个）"""
        for config in self.configs.values():
            if config.enabled:
                return config
        return None
    
    def get_active_config_id(self) -> Optional[str]:
        """获取当前启用的配置ID（只会有一个）"""
        for config_id, config in self.configs.items():
            if config.enabled:
                return config_id
        return None

    async def test_connection(self, config_id: str) -> Dict[str, Any]:
        """
        测试指定配置的连接
        
        Args:
            config_id: 配置ID
            
        Returns:
            Dict: 测试结果
        """
        config = self.get_config(config_id)
        if not config:
            return {
                "success": False,
                "config_id": config_id,
                "error": f"配置 '{config_id}' 不存在"
            }
        
        try:
            # 导入必要的模块
            from modules.ai import get_provider_class, AIModelConfig
            
            # 获取提供商类
            provider_class = get_provider_class(config.provider)
            if not provider_class:
                return {
                    "success": False,
                    "config_id": config_id,
                    "provider": config.provider,
                    "error": f"不支持的AI提供商: {config.provider}"
                }
            
            # 转换为AIModelConfig
            ai_model_config = AIModelConfig(
                provider=config.provider,
                api_key=config.api_key,
                base_url=config.base_url,
                model_name=config.model_name,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                timeout=config.timeout,
                extra_params=config.extra_params or {}
            )
            
            # 创建提供商实例并测试连接
            provider = provider_class(ai_model_config)
            result = await provider.test_connection()
            
            # 添加配置信息
            result["config_id"] = config_id
            result["description"] = config.description
            
            # 关闭连接
            await provider.close()
            
            return result
            
        except Exception as e:
            logger.error(f"测试配置 {config_id} 连接失败: {e}")
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "model_name": config.model_name,
                "error": str(e)
            }
    
    async def test_active_connection(self) -> Dict[str, Any]:
        """
        测试当前激活配置的连接（enabled=True的配置，永远只有一个）
        
        Returns:
            Dict: 测试结果
        """
        # 获取当前激活的配置ID
        active_config_id = self.get_active_config_id()
        
        if not active_config_id:
            return {
                "success": False,
                "message": "没有找到激活的配置",
                "error": "当前没有启用的视频分析模型配置"
            }
        
        active_config = self.get_active_config()
        logger.info(f"正在测试激活配置: {active_config_id} ({active_config.provider} - {active_config.model_name})")
        
        # 测试连接
        result = await self.test_connection(active_config_id)
        return result


# 全局视频分析模型配置管理器实例
video_model_config_manager = VideoModelConfigManager()
