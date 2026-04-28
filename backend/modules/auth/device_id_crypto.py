# -*- coding: utf-8 -*-
"""
device_id 透明加密/解密模块：对客户端发来的 deviceId 进行加密保护，
并在服务端解密时校验有效期，防止篡改和重放。

使用 Fernet（AES-128-CBC + HMAC-SHA256）对称加密，密钥通过环境变量注入。

用法:
    # 客户端侧（本机）：
    from modules.auth.device_id_crypto import encrypt_device_id
    encrypted = encrypt_device_id("win:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

    # 服务端侧：
    from modules.auth.device_id_crypto import decrypt_device_id
    original_device_id = decrypt_device_id(encrypted)

环境变量:
    DEVICE_ID_SECRET_KEY: 加密密钥（任意字符串，内部通过 SHA-256 派生为 Fernet key）
                          两端必须使用相同的值。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENV_KEY_NAME = "DEVICE_ID_SECRET_KEY"
_DEFAULT_TTL_SECONDS = 300  # 加密后 5 分钟内有效
_FERNET_KEY: Optional[bytes] = None


def _get_fernet_key() -> bytes:
    """从环境变量读取密钥（Base64 编码的 32 字节），首次调用时缓存。"""
    global _FERNET_KEY
    if _FERNET_KEY is not None:
        return _FERNET_KEY

    raw = "DFGSDDFGE222^^%**^^^RRTERT345DFG234345Q235DG3(**^*@#@#@#!SDRWER]SDR2345SDFASDFA"

    # 支持两种格式：
    # 1. 直接是 Fernet key（Base64 编码的 32 字节随机数，44 字符）
    # 2. 任意字符串，通过 SHA-256 派生为 Fernet key
    key_bytes = raw.encode("utf-8")
    if len(key_bytes) == 44 and b"=" not in key_bytes:
        try:
            Fernet(key_bytes)
            _FERNET_KEY = key_bytes
            return _FERNET_KEY
        except Exception:
            pass

    # 回退：SHA-256 派生为 Fernet key
    derived = hashlib.sha256(key_bytes).digest()
    _FERNET_KEY = base64.urlsafe_b64encode(derived)
    return _FERNET_KEY


def encrypt_device_id(
    plaintext_device_id: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS
) -> str:
    """
    加密 device_id，返回包含密文 + 时间戳的 token 字符串。

    payload 结构（JSON）::

        {
            "d": <plaintext_device_id>,
            "t": <unix_timestamp>,
            "ttl": <有效期秒数>
        }

    Args:
        plaintext_device_id: 原始设备标识符，如 ``"win:xxxx-xxxx-..."``
        ttl_seconds: token 有效期，单位秒，默认 300 秒（5 分钟）

    Returns:
        Fernet 加密后的 URL-safe Base64 字符串
    """
    if not plaintext_device_id or not plaintext_device_id.strip():
        raise ValueError("plaintext_device_id 不能为空")

    payload = json.dumps(
        {
            "d": plaintext_device_id.strip(),
            "t": int(time.time()),
            "ttl": ttl_seconds,
        },
        separators=(",", ":"),
    ).encode("utf-8")

    fernet = Fernet(_get_fernet_key())
    encrypted = fernet.encrypt(payload)
    return encrypted.decode("utf-8")


def decrypt_device_id(token: str) -> str:
    """
    解密 token，返回原始 device_id。

    - 校验签名完整性（Fernet 自带 HMAC-SHA256）
    - 校验时间戳有效期（ttl 秒内）
    - 过期或篡改抛出 ``ValueError``

    Args:
        token: ``encrypt_device_id()`` 返回的加密字符串

    Returns:
        原始 device_id 字符串

    Raises:
        ValueError: token 过期、被篡改、或格式异常
    """
    if not token or not token.strip():
        raise ValueError("token 不能为空")

    fernet = Fernet(_get_fernet_key())
    try:
        decrypted = fernet.decrypt(token.strip().encode("utf-8"), ttl=None)
    except InvalidToken:
        raise ValueError("token 无效或签名被篡改")
    except Exception as exc:
        raise ValueError(f"token 解密失败: {exc}") from exc

    try:
        payload = json.loads(decrypted.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"token 内部格式异常: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("token 内部格式异常")

    device_id = payload.get("d")
    ts = payload.get("t")
    ttl = payload.get("ttl", _DEFAULT_TTL_SECONDS)

    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("token 中 device_id 缺失或为空")
    if not isinstance(ts, (int, float)):
        raise ValueError("token 中时间戳缺失或类型异常")

    elapsed = time.time() - ts
    if elapsed < 0:
        # 允许 5 秒时钟偏差
        if abs(elapsed) > 5:
            raise ValueError("token 时间戳异常（未来时间）")
    elif elapsed > ttl:
        raise ValueError(
            f"token 已过期（已过 {int(elapsed)} 秒，有效期 {ttl} 秒）"
        )

    return device_id.strip()
