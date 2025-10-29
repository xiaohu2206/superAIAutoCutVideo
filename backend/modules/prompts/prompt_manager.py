#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词管理模块
支持模板化提示词管理和动态配置
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import logging
from string import Template
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptTemplate(BaseModel):
    """提示词模板"""
    id: str = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")
    category: str = Field("general", description="模板分类")
    template: str = Field(..., description="模板内容")
    variables: List[str] = Field(default_factory=list, description="模板变量列表")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    user_prompt_template: Optional[str] = Field(None, description="用户提示词模板")
    examples: Optional[List[Dict[str, str]]] = Field(default_factory=list, description="示例")
    tags: List[str] = Field(default_factory=list, description="标签")
    version: str = Field("1.0", description="版本号")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    enabled: bool = Field(True, description="是否启用")


class VideoAnalysisPrompts:
    """视频分析相关的预定义提示词"""
    
    VIDEO_CONTENT_ANALYSIS = PromptTemplate(
        id="video_content_analysis",
        name="视频内容分析",
        description="分析视频内容，提取关键信息",
        category="video_analysis",
        template="""请分析以下视频内容：

视频信息：
- 时长：${duration}
- 分辨率：${resolution}
- 文件大小：${file_size}

请从以下几个方面进行分析：
1. 视频主题和内容概要
2. 关键场景和时间点
3. 适合剪辑的片段建议
4. 音频质量评估
5. 画面质量评估

分析结果请以JSON格式返回。""",
        variables=["duration", "resolution", "file_size"],
        system_prompt="你是一个专业的视频分析师，擅长分析视频内容并提供剪辑建议。",
        tags=["video", "analysis", "content"]
    )
    
    HIGHLIGHT_DETECTION = PromptTemplate(
        id="highlight_detection",
        name="精彩片段检测",
        description="检测视频中的精彩片段",
        category="video_analysis",
        template="""请分析视频并检测精彩片段：

视频描述：${video_description}
检测类型：${detection_type}
时长限制：${duration_limit}

请识别以下类型的精彩片段：
1. 高潮部分
2. 有趣的对话
3. 视觉效果突出的场景
4. 情感高涨的时刻

对每个片段，请提供：
- 开始时间
- 结束时间
- 片段描述
- 精彩程度评分（1-10）
- 推荐理由""",
        variables=["video_description", "detection_type", "duration_limit"],
        system_prompt="你是一个视频剪辑专家，能够准确识别视频中的精彩片段。",
        tags=["video", "highlight", "detection"]
    )
    
    AUTO_CUT_SUGGESTION = PromptTemplate(
        id="auto_cut_suggestion",
        name="自动剪辑建议",
        description="提供自动剪辑的建议方案",
        category="video_editing",
        template="""基于视频分析结果，请提供自动剪辑建议：

原视频时长：${original_duration}
目标时长：${target_duration}
剪辑风格：${editing_style}
目标受众：${target_audience}

请提供以下剪辑建议：
1. 保留片段列表（开始时间-结束时间）
2. 删除片段的理由
3. 转场效果建议
4. 音频处理建议
5. 字幕添加建议

请确保剪辑后的视频：
- 保持内容连贯性
- 符合目标时长要求
- 适合目标受众""",
        variables=["original_duration", "target_duration", "editing_style", "target_audience"],
        system_prompt="你是一个专业的视频剪辑师，能够提供高质量的剪辑建议。",
        tags=["video", "editing", "auto-cut"]
    )


class PromptManager:
    """提示词管理器"""
    
    def __init__(self, prompts_file: Optional[str] = None):
        """
        初始化提示词管理器
        
        Args:
            prompts_file: 提示词文件路径，默认为 backend/config/prompts.json
        """
        if prompts_file is None:
            # 默认提示词文件路径
            backend_dir = Path(__file__).parent.parent.parent
            config_dir = backend_dir / "config"
            config_dir.mkdir(exist_ok=True)
            prompts_file = config_dir / "prompts.json"
        
        self.prompts_file = Path(prompts_file)
        self.templates: Dict[str, PromptTemplate] = {}
        
        # 加载提示词模板
        self.load_templates()
    
    def load_templates(self):
        """从文件加载提示词模板"""
        try:
            if self.prompts_file.exists():
                with open(self.prompts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 加载模板
                templates_data = data.get('templates', {})
                for template_id, template_data in templates_data.items():
                    try:
                        self.templates[template_id] = PromptTemplate(**template_data)
                    except Exception as e:
                        logger.error(f"加载提示词模板 {template_id} 失败: {e}")
                
                logger.info(f"成功加载 {len(self.templates)} 个提示词模板")
            else:
                # 创建默认模板
                self._create_default_templates()
                
        except Exception as e:
            logger.error(f"加载提示词模板失败: {e}")
            self._create_default_templates()
    
    def save_templates(self):
        """保存提示词模板到文件"""
        try:
            # 确保目录存在
            self.prompts_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 准备数据
            data = {
                'templates': {},
                'metadata': {
                    'version': '1.0',
                    'updated_at': datetime.now().isoformat(),
                    'total_templates': len(self.templates)
                }
            }
            
            for template_id, template in self.templates.items():
                data['templates'][template_id] = template.dict()
            
            # 写入文件
            with open(self.prompts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("提示词模板保存成功")
            
        except Exception as e:
            logger.error(f"保存提示词模板失败: {e}")
            raise
    
    def _create_default_templates(self):
        """创建默认提示词模板"""
        # 添加预定义的视频分析提示词
        default_templates = [
            VideoAnalysisPrompts.VIDEO_CONTENT_ANALYSIS,
            VideoAnalysisPrompts.HIGHLIGHT_DETECTION,
            VideoAnalysisPrompts.AUTO_CUT_SUGGESTION
        ]
        
        for template in default_templates:
            # 设置创建时间
            template.created_at = datetime.now().isoformat()
            template.updated_at = template.created_at
            self.templates[template.id] = template
        
        # 保存默认模板
        self.save_templates()
    
    def add_template(self, template: PromptTemplate) -> bool:
        """
        添加新的提示词模板
        
        Args:
            template: 提示词模板
            
        Returns:
            bool: 是否添加成功
        """
        try:
            if template.id in self.templates:
                raise ValueError(f"模板ID '{template.id}' 已存在")
            
            # 设置时间戳
            template.created_at = datetime.now().isoformat()
            template.updated_at = template.created_at
            
            self.templates[template.id] = template
            self.save_templates()
            
            logger.info(f"添加提示词模板成功: {template.id}")
            return True
            
        except Exception as e:
            logger.error(f"添加提示词模板失败: {e}")
            return False
    
    def update_template(self, template_id: str, template: PromptTemplate) -> bool:
        """
        更新提示词模板
        
        Args:
            template_id: 模板ID
            template: 新的模板对象
            
        Returns:
            bool: 是否更新成功
        """
        try:
            if template_id not in self.templates:
                raise ValueError(f"模板ID '{template_id}' 不存在")
            
            # 保留创建时间，更新修改时间
            old_template = self.templates[template_id]
            template.created_at = old_template.created_at
            template.updated_at = datetime.now().isoformat()
            
            self.templates[template_id] = template
            self.save_templates()
            
            logger.info(f"更新提示词模板成功: {template_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新提示词模板失败: {e}")
            return False
    
    def delete_template(self, template_id: str) -> bool:
        """
        删除提示词模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            if template_id not in self.templates:
                raise ValueError(f"模板ID '{template_id}' 不存在")
            
            del self.templates[template_id]
            self.save_templates()
            
            logger.info(f"删除提示词模板成功: {template_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除提示词模板失败: {e}")
            return False
    
    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """
        获取指定提示词模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            PromptTemplate: 模板对象，如果不存在返回None
        """
        return self.templates.get(template_id)
    
    def get_all_templates(self) -> Dict[str, PromptTemplate]:
        """获取所有提示词模板"""
        return self.templates.copy()
    
    def get_templates_by_category(self, category: str) -> Dict[str, PromptTemplate]:
        """
        根据分类获取提示词模板
        
        Args:
            category: 分类名称
            
        Returns:
            Dict: 该分类下的所有模板
        """
        return {
            template_id: template 
            for template_id, template in self.templates.items() 
            if template.category == category
        }
    
    def get_enabled_templates(self) -> Dict[str, PromptTemplate]:
        """获取所有启用的提示词模板"""
        return {
            template_id: template 
            for template_id, template in self.templates.items() 
            if template.enabled
        }
    
    def render_template(self, template_id: str, variables: Dict[str, Any]) -> Optional[str]:
        """
        渲染提示词模板
        
        Args:
            template_id: 模板ID
            variables: 模板变量字典
            
        Returns:
            str: 渲染后的提示词，如果失败返回None
        """
        try:
            template = self.get_template(template_id)
            if not template:
                raise ValueError(f"模板不存在: {template_id}")
            
            if not template.enabled:
                raise ValueError(f"模板未启用: {template_id}")
            
            # 使用Python的Template类进行渲染
            template_obj = Template(template.template)
            rendered = template_obj.safe_substitute(variables)
            
            return rendered
            
        except Exception as e:
            logger.error(f"渲染提示词模板失败: {e}")
            return None
    
    def get_template_variables(self, template_id: str) -> List[str]:
        """
        获取模板所需的变量列表
        
        Args:
            template_id: 模板ID
            
        Returns:
            List[str]: 变量列表
        """
        template = self.get_template(template_id)
        if template:
            return template.variables
        return []
    
    def search_templates(self, keyword: str) -> Dict[str, PromptTemplate]:
        """
        搜索提示词模板
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            Dict: 匹配的模板
        """
        keyword = keyword.lower()
        results = {}
        
        for template_id, template in self.templates.items():
            # 在名称、描述、标签中搜索
            if (keyword in template.name.lower() or 
                (template.description and keyword in template.description.lower()) or
                any(keyword in tag.lower() for tag in template.tags)):
                results[template_id] = template
        
        return results
    
    def get_categories(self) -> List[str]:
        """获取所有分类列表"""
        categories = set()
        for template in self.templates.values():
            categories.add(template.category)
        return sorted(list(categories))


# 全局提示词管理器实例
prompt_manager = PromptManager()