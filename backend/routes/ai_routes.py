#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI相关API路由
提供AI配置管理、模型调用、提示词管理等接口
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import logging
import json

from modules.ai import ChatMessage, get_available_providers
from modules.config import AIConfigModel, ai_config_manager
from modules.prompts import PromptTemplate, prompt_manager
from services import ai_service, get_ai_service

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/ai", tags=["AI"])


# 请求/响应模型
class ChatRequest(BaseModel):
    """聊天请求"""
    messages: List[Dict[str, str]] = Field(..., description="聊天消息列表")
    config_id: Optional[str] = Field(None, description="使用的配置ID")
    stream: bool = Field(False, description="是否使用流式响应")


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str = Field(..., description="响应内容")
    usage: Optional[Dict[str, int]] = Field(None, description="Token使用情况")
    model: Optional[str] = Field(None, description="使用的模型")
    config_id: Optional[str] = Field(None, description="使用的配置ID")


class ConfigCreateRequest(BaseModel):
    """配置创建请求"""
    config_id: str = Field(..., description="配置ID")
    config: AIConfigModel = Field(..., description="配置数据")


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    config: AIConfigModel = Field(..., description="配置数据")


class PromptRenderRequest(BaseModel):
    """提示词渲染请求"""
    template_id: str = Field(..., description="模板ID")
    variables: Dict[str, Any] = Field(..., description="模板变量")


# AI配置管理接口
@router.get("/providers", summary="获取可用的AI提供商列表")
async def get_providers():
    """获取所有可用的AI提供商"""
    try:
        providers = get_available_providers()
        return {
            "success": True,
            "data": providers,
            "message": f"获取到 {len(providers)} 个可用提供商"
        }
    except Exception as e:
        logger.error(f"获取AI提供商列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs", summary="获取所有AI配置")
async def get_configs():
    """获取所有AI配置"""
    try:
        configs = ai_config_manager.get_all_configs()
        active_config_id = ai_config_manager.get_active_config_id()
        
        # 转换为字典格式，隐藏API密钥
        config_data = {}
        for config_id, config in configs.items():
            config_dict = config.dict()
            # 隐藏API密钥的敏感部分
            if config_dict.get("api_key"):
                api_key = config_dict["api_key"]
                if len(api_key) > 8:
                    config_dict["api_key"] = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
            config_data[config_id] = config_dict
        
        return {
            "success": True,
            "data": {
                "configs": config_data,
                "active_config_id": active_config_id
            },
            "message": f"获取到 {len(configs)} 个配置"
        }
    except Exception as e:
        logger.error(f"获取AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs", summary="创建AI配置")
async def create_config(request: ConfigCreateRequest):
    """创建新的AI配置"""
    try:
        success = ai_config_manager.add_config(request.config_id, request.config)
        if success:
            return {
                "success": True,
                "message": f"配置 '{request.config_id}' 创建成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置创建失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/configs/{config_id}", summary="更新AI配置")
async def update_config(config_id: str, request: ConfigUpdateRequest):
    """更新AI配置"""
    try:
        success = ai_config_manager.update_config(config_id, request.config)
        if success:
            return {
                "success": True,
                "message": f"配置 '{config_id}' 更新成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置更新失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/configs/{config_id}", summary="删除AI配置")
async def delete_config(config_id: str):
    """删除AI配置"""
    try:
        success = ai_config_manager.delete_config(config_id)
        if success:
            return {
                "success": True,
                "message": f"配置 '{config_id}' 删除成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置删除失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configs/{config_id}/activate", summary="激活AI配置")
async def activate_config(config_id: str):
    """激活指定的AI配置"""
    try:
        success = ai_config_manager.set_active_config(config_id)
        if success:
            # 重新初始化AI服务
            await ai_service.initialize()
            return {
                "success": True,
                "message": f"配置 '{config_id}' 激活成功"
            }
        else:
            raise HTTPException(status_code=400, detail="配置激活失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"激活AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# AI模型调用接口
@router.post("/chat", summary="AI聊天接口")
async def chat_completion(request: ChatRequest):
    """AI聊天完成接口"""
    try:
        # 转换消息格式
        messages = [
            ChatMessage(role=msg["role"], content=msg["content"]) 
            for msg in request.messages
        ]
        
        if request.stream:
            # 流式响应
            async def generate_stream():
                try:
                    async for chunk in ai_service.stream_chat_completion(messages, request.config_id):
                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/plain",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
        else:
            # 普通响应
            response = await ai_service.chat_completion(messages, request.config_id)
            
            return {
                "success": True,
                "data": {
                    "content": response.content,
                    "usage": response.usage,
                    "model": response.model,
                    "config_id": request.config_id
                }
            }
            
    except Exception as e:
        logger.error(f"AI聊天请求失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", summary="获取AI服务状态")
async def get_ai_status():
    """获取AI服务状态"""
    try:
        provider_info = ai_service.get_provider_info()
        return {
            "success": True,
            "data": provider_info
        }
    except Exception as e:
        logger.error(f"获取AI服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 连接测试接口
@router.post("/test/{config_id}", summary="测试AI配置连接")
async def test_config_connection(config_id: str):
    """测试指定配置的连接"""
    try:
        result = await ai_service.test_connection(config_id)
        return {
            "success": result["success"],
            "data": result
        }
    except Exception as e:
        logger.error(f"测试AI配置连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-all", summary="测试所有AI配置连接")
async def test_all_connections():
    """测试所有启用配置的连接"""
    try:
        results = await ai_service.test_all_connections()
        return {
            "success": True,
            "data": results,
            "message": f"测试了 {len(results)} 个配置"
        }
    except Exception as e:
        logger.error(f"测试所有AI配置连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 提示词管理接口
@router.get("/prompts", summary="获取所有提示词模板")
async def get_prompts():
    """获取所有提示词模板"""
    try:
        templates = prompt_manager.get_all_templates()
        template_data = {
            template_id: template.dict() 
            for template_id, template in templates.items()
        }
        
        return {
            "success": True,
            "data": template_data,
            "message": f"获取到 {len(templates)} 个提示词模板"
        }
    except Exception as e:
        logger.error(f"获取提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/categories", summary="获取提示词分类")
async def get_prompt_categories():
    """获取所有提示词分类"""
    try:
        categories = prompt_manager.get_categories()
        return {
            "success": True,
            "data": categories,
            "message": f"获取到 {len(categories)} 个分类"
        }
    except Exception as e:
        logger.error(f"获取提示词分类失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/category/{category}", summary="根据分类获取提示词")
async def get_prompts_by_category(category: str):
    """根据分类获取提示词模板"""
    try:
        templates = prompt_manager.get_templates_by_category(category)
        template_data = {
            template_id: template.dict() 
            for template_id, template in templates.items()
        }
        
        return {
            "success": True,
            "data": template_data,
            "message": f"分类 '{category}' 下有 {len(templates)} 个模板"
        }
    except Exception as e:
        logger.error(f"根据分类获取提示词失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompts", summary="创建提示词模板")
async def create_prompt_template(template: PromptTemplate):
    """创建新的提示词模板"""
    try:
        success = prompt_manager.add_template(template)
        if success:
            return {
                "success": True,
                "message": f"提示词模板 '{template.id}' 创建成功"
            }
        else:
            raise HTTPException(status_code=400, detail="提示词模板创建失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/prompts/{template_id}", summary="更新提示词模板")
async def update_prompt_template(template_id: str, template: PromptTemplate):
    """更新提示词模板"""
    try:
        success = prompt_manager.update_template(template_id, template)
        if success:
            return {
                "success": True,
                "message": f"提示词模板 '{template_id}' 更新成功"
            }
        else:
            raise HTTPException(status_code=400, detail="提示词模板更新失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"更新提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/prompts/{template_id}", summary="删除提示词模板")
async def delete_prompt_template(template_id: str):
    """删除提示词模板"""
    try:
        success = prompt_manager.delete_template(template_id)
        if success:
            return {
                "success": True,
                "message": f"提示词模板 '{template_id}' 删除成功"
            }
        else:
            raise HTTPException(status_code=400, detail="提示词模板删除失败")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompts/{template_id}/render", summary="渲染提示词模板")
async def render_prompt_template(template_id: str, request: PromptRenderRequest):
    """渲染提示词模板"""
    try:
        rendered = prompt_manager.render_template(template_id, request.variables)
        if rendered is not None:
            return {
                "success": True,
                "data": {
                    "template_id": template_id,
                    "rendered_content": rendered,
                    "variables": request.variables
                }
            }
        else:
            raise HTTPException(status_code=400, detail="提示词模板渲染失败")
    except Exception as e:
        logger.error(f"渲染提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/search/{keyword}", summary="搜索提示词模板")
async def search_prompt_templates(keyword: str):
    """搜索提示词模板"""
    try:
        templates = prompt_manager.search_templates(keyword)
        template_data = {
            template_id: template.dict() 
            for template_id, template in templates.items()
        }
        
        return {
            "success": True,
            "data": template_data,
            "message": f"找到 {len(templates)} 个匹配的模板"
        }
    except Exception as e:
        logger.error(f"搜索提示词模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))