#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的 WebSocket 连接管理器，供后端各路由广播实时进度使用，避免 main.py 的循环依赖。
"""

import logging
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