#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证码服务模块
- 生成6位随机验证码
- 基于内存存储验证码及过期时间（5分钟有效）
- 支持注册验证码与重置密码验证码两类，互不干扰
"""

import random
import string
import time
from typing import Dict, Optional, Tuple
from threading import RLock

import logging

logger = logging.getLogger(__name__)

# 验证码有效期（秒）
CODE_TTL = 5 * 60

# 同一邮箱同一类型发送间隔（秒），防止频繁发送
SEND_INTERVAL = 60


class CodeService:
    """验证码生成与校验服务"""

    def __init__(self):
        self._lock = RLock()
        # key: (email_lower, code_type) -> (code, created_at, last_sent_at)
        self._store: Dict[Tuple[str, str], Tuple[str, float, float]] = {}

    @staticmethod
    def _generate_code(length: int = 6) -> str:
        return "".join(random.choices(string.digits, k=length))

    def send_code(self, email: str, code_type: str = "register") -> str:
        """
        生成验证码并存储。返回验证码明文，由调用方负责发送邮件。

        如果距离上次发送不足 SEND_INTERVAL 秒，抛出 ValueError。
        """
        email_lower = email.strip().lower()
        key = (email_lower, code_type)
        now = time.time()

        with self._lock:
            existing = self._store.get(key)
            if existing:
                _, _, last_sent = existing
                if now - last_sent < SEND_INTERVAL:
                    raise ValueError("发送验证码过于频繁，请稍后再试")

            code = self._generate_code()
            self._store[key] = (code, now, now)
            logger.info(f"验证码已生成: email={email_lower} type={code_type}")
            return code

    def verify_code(self, email: str, code: str, code_type: str = "register") -> bool:
        """校验验证码是否正确且未过期"""
        email_lower = email.strip().lower()
        key = (email_lower, code_type)
        now = time.time()

        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return False
            stored_code, created_at, _ = entry
            if now - created_at > CODE_TTL:
                # 过期，清除
                del self._store[key]
                return False
            if stored_code != code:
                return False
            # 验证成功后清除，防止重复使用
            del self._store[key]
            return True


# 单例
code_service = CodeService()
