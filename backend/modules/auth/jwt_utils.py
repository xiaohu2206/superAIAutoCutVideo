#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JWT Token 工具模块
- 生成 JWT Token
- 解析 / 验证 JWT Token
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import JWTError, jwt

import logging

logger = logging.getLogger(__name__)

# 从环境变量读取密钥，默认使用固定值（开发用）
SECRET_KEY = os.environ.get("SACV_JWT_SECRET", "super-auto-cut-video-jwt-secret-key-2026")
ALGORITHM = "HS256"
# Token 有效期（小时）
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7天


def create_token(user_id: int, email: str, extra: Optional[Dict[str, Any]] = None) -> str:
    """生成 JWT Token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码并验证 JWT Token。
    成功返回 payload 字典，失败返回 None。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode failed: {e}")
        return None


def get_user_id_from_token(token: str) -> Optional[int]:
    """从 Token 中提取用户 ID，失败返回 None"""
    payload = decode_token(token)
    if not payload:
        return None
    try:
        return int(payload.get("sub", 0))
    except (ValueError, TypeError):
        return None
