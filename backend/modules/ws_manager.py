#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的 WebSocket 连接管理器，供后端各路由广播实时进度使用，避免 main.py 的循环依赖。
"""

import logging
import json
from typing import List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket连接已建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket连接已断开，当前连接数: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"发送个人消息失败: {e}")

    async def broadcast(self, message: str):
        try:
            from modules.runtime_log_store import runtime_log_store

            try:
                obj = json.loads(message)
                if isinstance(obj, dict) and (obj.get("_stored") or (obj.get("id") is not None and obj.get("channel"))):
                    message = json.dumps(obj, ensure_ascii=False)
                elif isinstance(obj, dict) and not obj.get("_stored"):
                    stored = runtime_log_store.append({**obj, "_stored": True}, project_id=obj.get("project_id"))
                    message = json.dumps(stored, ensure_ascii=False)
                elif isinstance(obj, dict):
                    pass
                else:
                    runtime_log_store.append(
                        {"type": "ws_text", "scope": "broadcast", "message": str(message)},
                        project_id=None,
                    )
            except Exception:
                runtime_log_store.append(
                    {"type": "ws_text", "scope": "broadcast", "message": str(message)},
                    project_id=None,
                )
        except Exception:
            pass

        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"广播消息失败: {e}")
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


# 全局单例
manager = ConnectionManager()
