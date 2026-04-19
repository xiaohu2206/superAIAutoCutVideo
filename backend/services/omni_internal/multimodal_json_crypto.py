#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 多模态结果 JSON（shots_multimodal.json）磁盘加密：保存时加密、读取时解密。

- 磁盘格式：魔数 OMMJ1 + 换行 + Fernet 密文（ASCII）。
- 兼容：仍以 `{` / `[` 开头的旧明文文件按 JSON 解析。
- 密钥：优先环境变量 OMNI_MULTIMODAL_JSON_FERNET_KEY（Fernet.generate_key() 产出的 44 字符）；
  否则用 OMNI_MULTIMODAL_JSON_SECRET 经 PBKDF2 派生；若均未设置则用本机指纹材料派生（本地混淆，非强安全）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import uuid
from pathlib import Path
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_MAGIC = b"OMMJ1\n"
_PBKDF2_SALT = b"superAIAutoCutVideoPro-omni-multimodal-json-v1"
_PBKDF2_ITER = 390_000


def _machine_material() -> str:
    try:
        return f"{platform.node()}-{uuid.getnode()}"
    except Exception:
        return "omni-multimodal-json-fallback-material"


def _fernet_from_password(secret: str) -> Fernet:
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        _PBKDF2_SALT,
        _PBKDF2_ITER,
        dklen=32,
    )
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def get_multimodal_json_fernet() -> Fernet:
    env_key = (os.getenv("OMNI_MULTIMODAL_JSON_FERNET_KEY") or "").strip()
    if env_key:
        return Fernet(env_key.encode("ascii"))
    secret = (os.getenv("OMNI_MULTIMODAL_JSON_SECRET") or "").strip()
    if secret:
        return _fernet_from_password(secret)
    material = _machine_material()
    logger.warning(
        "未设置 OMNI_MULTIMODAL_JSON_FERNET_KEY / OMNI_MULTIMODAL_JSON_SECRET，"
        "Omni 多模态 JSON 使用本机指纹派生密钥（换机后无法解密旧文件）"
    )
    return _fernet_from_password(material)


def encrypt_json_text(plain_utf8: str) -> bytes:
    f = get_multimodal_json_fernet()
    token = f.encrypt(plain_utf8.encode("utf-8"))
    return _MAGIC + token


def decrypt_json_text(blob: bytes) -> str:
    if blob.startswith(_MAGIC):
        body = blob[len(_MAGIC) :].strip()
        f = get_multimodal_json_fernet()
        return f.decrypt(body).decode("utf-8")
    raise ValueError("不是 OMMJ1 加密格式")


def write_encrypted_multimodal_json(path: Path, payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_json_text(text))


def read_multimodal_json(path: Path) -> Dict[str, Any]:
    raw = path.read_bytes()
    stripped = raw.lstrip(b"\xef\xbb\xbf")  # BOM
    if stripped[:1] in (b"{", b"["):
        return json.loads(stripped.decode("utf-8"))
    if stripped.startswith(_MAGIC):
        try:
            text = decrypt_json_text(stripped)
        except InvalidToken as e:
            raise ValueError("Omni 多模态 JSON 解密失败（密钥不匹配或文件损坏）") from e
        return json.loads(text)
    try:
        return json.loads(stripped.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError("无法解析 Omni 多模态 JSON（非明文且非 OMMJ1 格式）") from e
