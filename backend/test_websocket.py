#!/usr/bin/env python3
"""
WebSocket测试客户端
用于测试WebSocket连接和消息传输功能
"""

import asyncio
import json
import websockets
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketTestClient:
    def __init__(self, uri="ws://127.0.0.1:8000/ws"):
        self.uri = uri
        self.websocket = None
        
    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            self.websocket = await websockets.connect(self.uri)
            logger.info(f"✅ 成功连接到WebSocket服务器: {self.uri}")
            return True
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            return False
    
    async def send_message(self, message):
        """发送消息到服务器"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(message))
                logger.info(f"📤 发送消息: {message}")
            except Exception as e:
                logger.error(f"❌ 发送消息失败: {e}")
    
    async def receive_message(self):
        """接收服务器消息"""
        if self.websocket:
            try:
                message = await self.websocket.recv()
                logger.info(f"📥 收到消息: {message}")
                return json.loads(message)
            except Exception as e:
                logger.error(f"❌ 接收消息失败: {e}")
                return None
    
    async def ping_test(self):
        """测试ping-pong功能"""
        ping_message = {
            "type": "ping",
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(ping_message)
        
        # 等待pong响应
        response = await self.receive_message()
        if response and response.get("type") == "pong":
            logger.info("✅ Ping-Pong测试成功")
            return True
        else:
            logger.error("❌ Ping-Pong测试失败")
            return False
    
    async def heartbeat_test(self):
        """测试心跳消息"""
        heartbeat_message = {
            "type": "heartbeat",
            "timestamp": datetime.now().isoformat()
        }
        await self.send_message(heartbeat_message)
        logger.info("✅ 心跳消息发送成功")
    
    async def invalid_json_test(self):
        """测试无效JSON处理"""
        try:
            await self.websocket.send("invalid json message")
            logger.info("📤 发送无效JSON消息")
            
            response = await self.receive_message()
            if response and response.get("type") == "error":
                logger.info("✅ 无效JSON错误处理测试成功")
                return True
            else:
                logger.error("❌ 无效JSON错误处理测试失败")
                return False
        except Exception as e:
            logger.error(f"❌ 无效JSON测试失败: {e}")
            return False
    
    async def close(self):
        """关闭连接"""
        if self.websocket:
            await self.websocket.close()
            logger.info("🔌 WebSocket连接已关闭")

async def run_tests():
    """运行所有WebSocket测试"""
    logger.info("🚀 开始WebSocket功能测试")
    logger.info("=" * 50)
    
    client = WebSocketTestClient()
    
    # 测试连接
    if not await client.connect():
        logger.error("❌ 无法连接到WebSocket服务器，测试终止")
        return
    
    try:
        # 测试1: Ping-Pong
        logger.info("\n📋 测试1: Ping-Pong功能")
        await client.ping_test()
        await asyncio.sleep(1)
        
        # 测试2: 心跳消息
        logger.info("\n📋 测试2: 心跳消息")
        await client.heartbeat_test()
        await asyncio.sleep(1)
        
        # 测试3: 无效JSON处理
        logger.info("\n📋 测试3: 无效JSON处理")
        await client.invalid_json_test()
        await asyncio.sleep(1)
        
        # 测试4: 连续消息发送
        logger.info("\n📋 测试4: 连续消息发送")
        for i in range(3):
            test_message = {
                "type": "test",
                "sequence": i + 1,
                "message": f"测试消息 {i + 1}",
                "timestamp": datetime.now().isoformat()
            }
            await client.send_message(test_message)
            await asyncio.sleep(0.5)
        
        logger.info("\n✅ 所有测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
    
    finally:
        await client.close()
        logger.info("=" * 50)
        logger.info("🏁 WebSocket测试结束")

if __name__ == "__main__":
    asyncio.run(run_tests())