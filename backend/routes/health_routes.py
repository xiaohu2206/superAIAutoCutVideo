#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康检查和系统状态路由
提供系统健康状态、AI服务状态、配置状态等监控接口
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/health", tags=["Health"])


# 响应模型
class HealthStatus(BaseModel):
    """健康状态模型"""
    status: str = Field(..., description="状态: healthy, degraded, unhealthy")
    timestamp: str = Field(..., description="检查时间")
    uptime: float = Field(..., description="运行时间(秒)")
    version: str = Field("1.0.0", description="版本号")


class ServiceStatus(BaseModel):
    """服务状态模型"""
    name: str = Field(..., description="服务名称")
    status: str = Field(..., description="状态")
    message: str = Field(..., description="状态消息")
    response_time: Optional[float] = Field(None, description="响应时间(毫秒)")
    last_check: str = Field(..., description="最后检查时间")


class SystemInfo(BaseModel):
    """系统信息模型"""
    python_version: str = Field(..., description="Python版本")
    platform: str = Field(..., description="平台信息")
    memory_usage: Dict[str, Any] = Field(..., description="内存使用情况")
    disk_usage: Dict[str, Any] = Field(..., description="磁盘使用情况")


class DetailedHealthResponse(BaseModel):
    """详细健康检查响应"""
    overall_status: str = Field(..., description="总体状态")
    timestamp: str = Field(..., description="检查时间")
    uptime: float = Field(..., description="运行时间")
    system_info: Optional[SystemInfo] = Field(None, description="系统信息")


# 全局变量记录启动时间
_start_time = time.time()


def get_uptime() -> float:
    """获取运行时间"""
    return time.time() - _start_time


async def check_ai_service_health() -> ServiceStatus:
    """检查AI服务健康状态"""
    start_time = time.time()
    
    try:
        # 获取AI服务信息
        provider_info = ai_service.get_provider_info()
        response_time = (time.time() - start_time) * 1000
        
        if provider_info.get("active_provider"):
            return ServiceStatus(
                name="AI Service",
                status="healthy",
                message=f"Active provider: {provider_info['active_provider']}",
                response_time=response_time,
                last_check=datetime.now().isoformat()
            )
        else:
            return ServiceStatus(
                name="AI Service",
                status="degraded",
                message="No active AI provider configured",
                response_time=response_time,
                last_check=datetime.now().isoformat()
            )
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceStatus(
            name="AI Service",
            status="unhealthy",
            message=f"AI service error: {str(e)}",
            response_time=response_time,
            last_check=datetime.now().isoformat()
        )


async def check_config_service_health() -> ServiceStatus:
    """检查配置服务健康状态"""
    start_time = time.time()
    
    try:
        # 检查配置管理器
        configs = ai_config_manager.get_all_configs()
        active_config = ai_config_manager.get_active_config_id()
        response_time = (time.time() - start_time) * 1000
        
        return ServiceStatus(
            name="Config Service",
            status="healthy",
            message=f"Loaded {len(configs)} configs, active: {active_config or 'none'}",
            response_time=response_time,
            last_check=datetime.now().isoformat()
        )
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceStatus(
            name="Config Service",
            status="unhealthy",
            message=f"Config service error: {str(e)}",
            response_time=response_time,
            last_check=datetime.now().isoformat()
        )


def get_system_info() -> SystemInfo:
    """获取系统信息"""
    import sys
    import platform
    import psutil
    
    # 内存使用情况
    memory = psutil.virtual_memory()
    memory_usage = {
        "total": memory.total,
        "available": memory.available,
        "percent": memory.percent,
        "used": memory.used,
        "free": memory.free
    }
    
    # 磁盘使用情况
    disk = psutil.disk_usage('/')
    disk_usage = {
        "total": disk.total,
        "used": disk.used,
        "free": disk.free,
        "percent": (disk.used / disk.total) * 100
    }
    
    return SystemInfo(
        python_version=sys.version,
        platform=platform.platform(),
        memory_usage=memory_usage,
        disk_usage=disk_usage
    )


@router.get("/", response_model=HealthStatus, summary="基础健康检查")
async def health_check():
    """基础健康检查接口"""
    try:
        # 简单的健康检查
        uptime = get_uptime()
        
        # 检查基本服务
        ai_status = await check_ai_service_health()
        config_status = await check_config_service_health()
        
        # 判断总体状态
        if ai_status.status == "healthy" and config_status.status == "healthy":
            overall_status = "healthy"
        elif ai_status.status == "unhealthy" or config_status.status == "unhealthy":
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now().isoformat(),
            uptime=uptime
        )
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detailed", response_model=DetailedHealthResponse, summary="详细健康检查")
async def detailed_health_check():
    """详细健康检查接口"""
    try:
        uptime = get_uptime()
        
        # 检查各个服务
        services = []
        
        # AI服务检查
        ai_status = await check_ai_service_health()
        services.append(ai_status)
        
        # 配置服务检查
        config_status = await check_config_service_health()
        services.append(config_status)
        
        # 判断总体状态
        unhealthy_count = sum(1 for s in services if s.status == "unhealthy")
        degraded_count = sum(1 for s in services if s.status == "degraded")
        
        if unhealthy_count > 0:
            overall_status = "unhealthy"
        elif degraded_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        # 获取AI配置状态
        try:
            configs = ai_config_manager.get_all_configs()
            active_config_id = ai_config_manager.get_active_config_id()
            ai_configs = {
                "total_configs": len(configs),
                "active_config": active_config_id,
                "config_names": list(configs.keys())
            }
        except Exception as e:
            ai_configs = {"error": str(e)}
        
        # 获取系统信息
        try:
            system_info = get_system_info()
        except Exception as e:
            logger.warning(f"获取系统信息失败: {e}")
            system_info = None
        
        return DetailedHealthResponse(
            overall_status=overall_status,
            timestamp=datetime.now().isoformat(),
            uptime=uptime,
            services=services,
            system_info=system_info,
            ai_configs=ai_configs
        )
    except Exception as e:
        logger.error(f"详细健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai", summary="AI服务健康检查")
async def ai_health_check():
    """AI服务专项健康检查"""
    try:
        ai_status = await check_ai_service_health()
        
        # 获取更详细的AI服务信息
        try:
            provider_info = ai_service.get_provider_info()
            configs = ai_config_manager.get_all_configs()
            
            detailed_info = {
                "service_status": ai_status.dict(),
                "provider_info": provider_info,
                "total_configs": len(configs),
                "config_details": {}
            }
            
            # 获取每个配置的基本信息（不包含敏感信息）
            for config_id, config in configs.items():
                detailed_info["config_details"][config_id] = {
                    "provider": config.provider,
                    "model": config.model,
                    "enabled": config.enabled,
                    "base_url": config.base_url
                }
            
            return {
                "success": True,
                "data": detailed_info
            }
        except Exception as e:
            return {
                "success": False,
                "data": ai_status.dict(),
                "error": str(e)
            }
    except Exception as e:
        logger.error(f"AI服务健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", summary="配置服务健康检查")
async def config_health_check():
    """配置服务专项健康检查"""
    try:
        config_status = await check_config_service_health()
        
        # 获取更详细的配置信息
        try:
            configs = ai_config_manager.get_all_configs()
            active_config_id = ai_config_manager.get_active_config_id()
            
            config_summary = {}
            for config_id, config in configs.items():
                config_summary[config_id] = {
                    "provider": config.provider,
                    "model": config.model,
                    "enabled": config.enabled,
                    "is_active": config_id == active_config_id
                }
            
            detailed_info = {
                "service_status": config_status.dict(),
                "total_configs": len(configs),
                "active_config": active_config_id,
                "configs": config_summary
            }
            
            return {
                "success": True,
                "data": detailed_info
            }
        except Exception as e:
            return {
                "success": False,
                "data": config_status.dict(),
                "error": str(e)
            }
    except Exception as e:
        logger.error(f"配置服务健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system", summary="系统信息检查")
async def system_health_check():
    """系统信息检查"""
    try:
        system_info = get_system_info()
        uptime = get_uptime()
        
        # 判断系统状态
        memory_percent = system_info.memory_usage["percent"]
        disk_percent = system_info.disk_usage["percent"]
        
        if memory_percent > 90 or disk_percent > 90:
            status = "unhealthy"
            message = "High resource usage detected"
        elif memory_percent > 80 or disk_percent > 80:
            status = "degraded"
            message = "Moderate resource usage"
        else:
            status = "healthy"
            message = "System resources normal"
        
        return {
            "success": True,
            "data": {
                "status": status,
                "message": message,
                "uptime": uptime,
                "timestamp": datetime.now().isoformat(),
                "system_info": system_info.dict()
            }
        }
    except Exception as e:
        logger.error(f"系统信息检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-all-connections", summary="测试所有AI连接")
async def test_all_ai_connections():
    """测试所有AI配置的连接状态"""
    try:
        # 使用AI服务的连接测试功能
        results = await ai_service.test_all_connections()
        
        # 统计结果
        total = len(results)
        successful = sum(1 for r in results.values() if r.get("success", False))
        failed = total - successful
        
        overall_status = "healthy" if failed == 0 else ("degraded" if successful > 0 else "unhealthy")
        
        return {
            "success": True,
            "data": {
                "overall_status": overall_status,
                "summary": {
                    "total": total,
                    "successful": successful,
                    "failed": failed
                },
                "results": results,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"测试所有AI连接失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))