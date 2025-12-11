#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI智能视频剪辑桌面应用 - FastAPI后端服务
支持HTTP API和WebSocket实时通信
"""

import asyncio
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 解决 PyInstaller 打包后 uvicorn 日志报错 "AttributeError: 'NoneType' object has no attribute 'isatty'"
# 当 console=False 时，sys.stdout 和 sys.stderr 为 None
class NullWriter:
    def write(self, text):
        pass
    def flush(self):
        pass
    def isatty(self):
        return False

if getattr(sys, 'frozen', False):
    if sys.stdout is None:
        sys.stdout = NullWriter()
    if sys.stderr is None:
        sys.stderr = NullWriter()

print("Backend initializing...")  # Debug marker

# 导入AI路由
from routes import health_router
from routes.video_model_routes import router as video_model_router
from routes.content_model_routes import router as content_model_router
from routes.project_routes import router as project_router
from routes.tts_routes import router as tts_router
from routes.prompts_routes import router as prompts_router
from modules.ws_manager import manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="AI智能视频剪辑后端",
    description="提供视频处理、AI剪辑和实时进度推送服务",
    version="1.0.0"
)
logger.info(f"Python 解释器: {sys.executable}")

# 配置CORS - 允许Tauri前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router)
app.include_router(video_model_router)
app.include_router(content_model_router)
app.include_router(project_router)
app.include_router(tts_router)
app.include_router(prompts_router)

def get_app_paths():
    """
    获取应用路径配置，兼容开发环境和打包环境（PyInstaller）
    """
    if getattr(sys, 'frozen', False):
        # 打包环境 (PyInstaller)
        # sys._MEIPASS 是解压后的临时目录，包含代码和 bundled 资源
        base_path = Path(sys._MEIPASS)
        
        # sys.executable 是可执行文件所在目录
        # 我们希望 uploads 和 config 等持久化数据位于可执行文件同级目录，或者用户数据目录
        # 这里为了便携性，暂定为可执行文件同级目录
        exe_dir = Path(sys.executable).parent
        
        # serviceData 如果是只读配置或临时缓存，可以使用 bundled 中的路径
        # 如果需要持久化修改，应该在启动时复制到 exe_dir
        # 目前 edge_voices_cache.json 会写入，所以使用临时目录没问题（重启丢失缓存）
        # 或者也可以指向 exe_dir / "serviceData" 并要求用户手动复制（或者代码自动复制）
        # 为了简单起见，先使用 bundled 路径（意味着缓存不持久化）
        # 修正：如果 main.py 尝试 mount 一个不存在的目录会报错，必须确保目录存在
        service_data_dir = base_path / "backend" / "serviceData"
        if not service_data_dir.exists():
             # 尝试备用路径（spec文件中可能配置为直接在根目录）
             service_data_dir = base_path / "serviceData"
        
        uploads_dir = exe_dir / "uploads"
        
    else:
        # 开发环境
        base_path = Path(__file__).resolve().parent # backend/
        project_root = base_path.parent # superAIAutoCutVideo/
        
        service_data_dir = base_path / "serviceData"
        uploads_dir = project_root / "uploads"
        
    return service_data_dir, uploads_dir

service_data_dir, uploads_dir = get_app_paths()

# 确保目录存在
if not service_data_dir.exists():
    # 如果 bundled 中没有 serviceData（例如首次打包遗漏），尝试创建以免 crash
    # 但如果是只读 mount，内容为空可能导致功能缺失
    logger.warning(f"ServiceData directory not found at {service_data_dir}, creating empty directory")
    service_data_dir.mkdir(parents=True, exist_ok=True)

uploads_dir.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
# 注意：挂载路径 url 保持不变
app.mount("/backend/serviceData", StaticFiles(directory=str(service_data_dir)), name="serviceData")

# WebSocket连接管理器在 modules/ws_manager.py 中定义并提供单例 manager

# 数据模型
class VideoProcessRequest(BaseModel):
    video_path: str
    output_path: str
    settings: Dict = {}

class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: float  # 0-100
    message: str

# 全局任务状态存储
tasks_status: Dict[str, TaskStatus] = {}

# 全局变量存储当前服务器配置
current_server_config = {
    "host": "127.0.0.1",
    "port": 8000,
    "started_at": None
}


def is_port_available(host: str, port: int) -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            # 尝试绑定端口，如果成功则端口可用
            sock.bind((host, port))
            return True
    except OSError:
        # 端口被占用或其他错误
        return False


def find_available_port(host: str, start_port: int, max_attempts: int = 10) -> int:
    """查找可用端口，从start_port开始累加重试"""
    for i in range(max_attempts):
        port = start_port + i
        if is_port_available(host, port):
            return port
    raise RuntimeError(f"无法找到可用端口，已尝试从 {start_port} 到 {start_port + max_attempts - 1}")


# API路由
@app.get("/")
async def root():
    """根路径健康检查"""
    return {"message": "AI智能视频剪辑后端服务运行中", "timestamp": datetime.now().isoformat()}

@app.get("/api/hello")
async def hello():
    """测试API接口"""
    logger.info("收到Hello API请求")
    return {"message": "Hello from FastAPI!", "timestamp": datetime.now().isoformat()}

@app.get("/api/status")
async def get_status():
    """获取服务状态"""
    return {
        "status": "running",
        "version": "1.0.0",
        "active_connections": len(manager.active_connections),
        "tasks_count": len(tasks_status),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/server/info")
async def get_server_info():
    """获取服务器信息，包括当前使用的端口"""
    return {
        "message": "服务器信息",
        "data": {
            "host": current_server_config["host"],
            "port": current_server_config["port"],
            "started_at": current_server_config["started_at"],
            "status": "running"
        },
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/video/process")
async def process_video(request: VideoProcessRequest):
    """处理视频剪辑请求"""
    try:
        task_id = f"task_{int(time.time() * 1000)}"
        
        # 创建任务状态
        task_status = TaskStatus(
            task_id=task_id,
            status="pending",
            progress=0.0,
            message="任务已创建，等待处理"
        )
        tasks_status[task_id] = task_status
        
        logger.info(f"创建视频处理任务: {task_id}")
        
        # 异步处理视频（模拟）
        asyncio.create_task(simulate_video_processing(task_id, request))
        
        return {
            "task_id": task_id,
            "message": "视频处理任务已创建",
            "status": "pending"
        }
    
    except Exception as e:
        logger.error(f"创建视频处理任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return tasks_status[task_id].dict()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接端点"""
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            logger.info(f"收到WebSocket消息: {data}")
            
            # 解析消息
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message(
                        json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}),
                        websocket
                    )
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({"type": "error", "message": "无效的JSON格式"}),
                    websocket
                )
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket客户端断开连接")

async def simulate_video_processing(task_id: str, request: VideoProcessRequest):
    """模拟视频处理过程"""
    try:
        task = tasks_status[task_id]
        task.status = "processing"
        task.message = "开始处理视频"
        
        # 模拟处理进度
        for progress in range(0, 101, 10):
            task.progress = float(progress)
            task.message = f"处理进度: {progress}%"
            
            # 通过WebSocket广播进度
            progress_message = {
                "type": "progress",
                "task_id": task_id,
                "progress": progress,
                "message": task.message,
                "timestamp": datetime.now().isoformat()
            }
            await manager.broadcast(json.dumps(progress_message))
            
            # 模拟处理时间
            await asyncio.sleep(1)
        
        # 完成处理
        task.status = "completed"
        task.progress = 100.0
        task.message = "视频处理完成"
        
        completion_message = {
            "type": "completed",
            "task_id": task_id,
            "message": "视频处理完成",
            "output_path": request.output_path,
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast(json.dumps(completion_message))
        
        logger.info(f"任务 {task_id} 处理完成")
    
    except Exception as e:
        logger.error(f"任务 {task_id} 处理失败: {e}")
        task = tasks_status.get(task_id)
        if task:
            task.status = "failed"
            task.message = f"处理失败: {str(e)}"
            
            error_message = {
                "type": "error",
                "task_id": task_id,
                "message": task.message,
                "timestamp": datetime.now().isoformat()
            }
            await manager.broadcast(json.dumps(error_message))

async def send_periodic_heartbeat():
    """定期发送心跳消息"""
    while True:
        try:
            heartbeat_message = {
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "server_time": time.time()
            }
            await manager.broadcast(json.dumps(heartbeat_message))
            await asyncio.sleep(5)  # 每5秒发送一次心跳
        except Exception as e:
            logger.error(f"发送心跳失败: {e}")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("AI智能视频剪辑后端服务启动")
    # 启动心跳任务
    asyncio.create_task(send_periodic_heartbeat())

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("AI智能视频剪辑后端服务关闭")

if __name__ == "__main__":
    # 获取端口配置
    initial_port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    logger.info(f"启动使用的 Python 解释器: {sys.executable}")

    try:
        # 查找可用端口
        port = find_available_port(host, initial_port)
        
        # 更新全局配置
        current_server_config["host"] = host
        current_server_config["port"] = port
        current_server_config["started_at"] = datetime.now().isoformat()
        
        if port != initial_port:
            logger.info(f"端口 {initial_port} 被占用，自动切换到端口 {port}")
        
        logger.info(f"启动FastAPI服务器: {host}:{port}")
        
        # 启动服务器：直接传递 app 对象，避免 PyInstaller 环境下字符串导入失败（ModuleNotFoundError: 'main'）
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,  # 生产环境不使用reload
            log_level="info"
        )
    except RuntimeError as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


# 删除重复的全局变量和接口定义
