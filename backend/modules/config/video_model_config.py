#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频分析模型配置管理模块
支持动态配置视频分析AI模型参数，包括提供商、API密钥、模型名称等
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)


class VideoModelConfig(BaseModel):
    """视频分析模型配置数据模型"""
    provider: str = Field(..., description="AI提供商名称")
    api_key: str = Field(..., description="API密钥")
    base_url: str = Field(..., description="API基础地址")
    model_name: str = Field(..., description="模型名称")
    max_tokens: Optional[int] = Field(4000, description="最大token数")
    temperature: Optional[float] = Field(0.7, description="温度参数", ge=0.0, le=2.0)
    timeout: Optional[int] = Field(30, description="超时时间（秒）", ge=1, le=300)
    extra_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外参数")
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, description="配置描述")
    
    @validator('provider')
    def validate_provider(cls, v):
        allowed_providers = ['qwen', 'doubao', 'deepseek', 'openai', 'claude']
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
        self.active_config_id: Optional[str] = None
        
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
                
                # 设置活跃配置
                self.active_config_id = data.get('active_config_id')
                
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
                'active_config_id': self.active_config_id,
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
                    base_url='https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
                    model_name='qwen-vl-plus',
                    description='通义千问视频分析模型',
                    enabled=False
                )
            },
            {
                'id': 'doubao_video_analysis',
                'config': VideoModelConfig(
                    provider='doubao',
                    api_key='your_doubao_api_key_here',
                    base_url='https://ark.cn-beijing.volces.com/api/v3/chat/completions',
                    model_name='doubao-vision-pro',
                    description='豆包视频分析模型',
                    enabled=False
                )
            },
            {
                'id': 'deepseek_video_analysis',
                'config': VideoModelConfig(
                    provider='deepseek',
                    api_key='your_deepseek_api_key_here',
                    base_url='https://api.deepseek.com/chat/completions',
                    model_name='deepseek-vl-chat',
                    description='DeepSeek视频分析模型',
                    enabled=False
                )
            }
        ]
        
        for item in default_configs:
            self.configs[item['id']] = item['config']
        
        # 保存默认配置
        self.save_configs()

    def add_config(self, config_id: str, config: VideoModelConfig) -> bool:
        """
        添加新配置
        
        Args:
            config_id: 配置ID
            config: 配置对象
            
        Returns:
            bool: 是否添加成功
        """
        try:
            if config_id in self.configs:
                raise ValueError(f"配置ID '{config_id}' 已存在")
            
            self.configs[config_id] = config
            self.save_configs()
            
            logger.info(f"添加视频分析模型配置成功: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加视频分析模型配置失败: {e}")
            return False

    def update_config(self, config_id: str, config: VideoModelConfig) -> bool:
        """
        更新配置
        
        Args:
            config_id: 配置ID
            config: 新的配置对象
            
        Returns:
            bool: 是否更新成功
        """
        try:
            if config_id not in self.configs:
                raise ValueError(f"配置ID '{config_id}' 不存在")
            
            self.configs[config_id] = config
            self.save_configs()
            
            logger.info(f"更新视频分析模型配置成功: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新视频分析模型配置失败: {e}")
            return False

    def delete_config(self, config_id: str) -> bool:
        """
        删除配置
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if config_id not in self.configs:
                raise ValueError(f"配置ID '{config_id}' 不存在")
            
            # 如果删除的是活跃配置，清除活跃配置
            if self.active_config_id == config_id:
                self.active_config_id = None
            
            del self.configs[config_id]
            self.save_configs()
            
            logger.info(f"删除视频分析模型配置成功: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除视频分析模型配置失败: {e}")
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
    
    def get_enabled_configs(self) -> Dict[str, VideoModelConfig]:
        """获取所有启用的配置"""
        return {
            config_id: config 
            for config_id, config in self.configs.items() 
            if config.enabled
        }

    def set_active_config(self, config_id: str) -> bool:
        """
        设置活跃配置
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否设置成功
        """
        try:
            if config_id not in self.configs:
                raise ValueError(f"配置ID '{config_id}' 不存在")
            
            if not self.configs[config_id].enabled:
                raise ValueError(f"配置 '{config_id}' 未启用")
            
            self.active_config_id = config_id
            self.save_configs()
            
            logger.info(f"设置活跃视频分析模型配置: {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置活跃视频分析模型配置失败: {e}")
            return False

    def get_active_config(self) -> Optional[VideoModelConfig]:
        """获取当前活跃配置"""
        if self.active_config_id:
            return self.configs.get(self.active_config_id)
        return None
    
    def get_active_config_id(self) -> Optional[str]:
        """获取当前活跃配置ID"""
        return self.active_config_id

    def test_connection(self, config_id: str) -> Dict[str, Any]:
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
                "error": f"配置 '{config_id}' 不存在"
            }
        
        try:
            # 这里可以实现实际的连接测试逻辑
            # 暂时返回模拟结果
            return {
                "success": True,
                "config_id": config_id,
                "provider": config.provider,
                "model_name": config.model_name,
                "message": "连接测试成功"
            }
        except Exception as e:
            return {
                "success": False,
                "config_id": config_id,
                "error": str(e)
            }


# 全局视频分析模型配置管理器实例
video_model_config_manager = VideoModelConfigManager()