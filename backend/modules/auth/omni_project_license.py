# -*- coding: utf-8 -*-
"""
全感知（omni）项目创建前：在服务端用用户 JWT 拉取已绑定 License，并对本机 deviceId
调用上游 POST /api/license/verify，与公开 License 校验接口语义一致。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from modules.auth.auth_upstream import get_auth_upstream_base
from modules.auth.device_id_crypto import encrypt_device_id
from modules.auth.license_device_id import get_host_device_fingerprint

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=8.0, read=15.0, write=10.0, pool=8.0)


def _unwrap_licenses_json(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []
    if isinstance(body.get("data"), list):
        return [x for x in body["data"] if isinstance(x, dict)]
    return []


def _error_detail_from_any(body: Any) -> str:
    if isinstance(body, dict):
        m = body.get("message")
        if isinstance(m, str) and m.strip():
            return m.strip()
        d = body.get("detail")
        if isinstance(d, str) and d.strip():
            return d.strip()
        if isinstance(d, list) and d and isinstance(d[0], dict):
            msg = d[0].get("msg")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    return "License 校验未通过"


def _verify_response_ok(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    if body.get("code") == 0 and isinstance(body.get("data"), dict):
        return body["data"].get("valid") is True
    return body.get("valid") is True


def _parse_expire_at(lic: dict[str, Any]) -> Optional[datetime]:
    raw = lic.get("expireAt")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("omni license: invalid expireAt format: %s", raw)
        return None


def _is_license_expired(lic: dict[str, Any]) -> bool:
    expire_dt = _parse_expire_at(lic)
    if expire_dt is None:
        return False
    return expire_dt <= datetime.now(timezone.utc)


async def require_valid_license_for_omni(authorization: Optional[str]) -> None:
    if not (authorization and authorization.strip()):
        raise HTTPException(
            status_code=401,
            detail="创建全感知项目需要先登录，并在账号中绑定 License。",
        )
    auth = authorization.strip()
    base = get_auth_upstream_base()
    list_url = f"{base}/api/licenses"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            list_url,
            headers={"Accept": "application/json", "Authorization": auth},
        )
    if r.status_code == 401:
        raise HTTPException(
            status_code=400,
            detail="登录已过期或无效，请重新登录后再创建全感知项目。",
        )
    if r.status_code != 200:
        logger.warning("omni license gate: GET /api/licenses -> %s", r.status_code)
        raise HTTPException(
            status_code=403,
            detail="无法获取 License 信息，请稍后重试。",
        )
    try:
        list_body: Any = r.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="License 服务返回异常，请稍后重试。",
        )
    items = _unwrap_licenses_json(list_body)
    candidates: list[dict[str, Any]] = []
    for it in items:
        if it.get("status") != "active":
            continue
        if _is_license_expired(it):
            continue
        k = it.get("licenseKey")
        if not isinstance(k, str) or not k.strip():
            continue
        candidates.append(it)
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="创建全感知项目需要有效的 License：请先在个人中心绑定并处于生效中的 License。",
        )
    # 与列表 API 一致：id 大的优先
    def _key_id(lic: dict[str, Any]) -> int:
        n = lic.get("id")
        if isinstance(n, (int, float)) and n == int(n):
            return int(n)
        return 0

    candidates.sort(key=_key_id, reverse=True)

    device_id = await asyncio.to_thread(get_host_device_fingerprint)
    encrypted_device_id = encrypt_device_id(device_id)
    device_name = "SuperAI 自动剪辑 本机"
    verify_url = f"{base}/api/license/verify"
    last_error = "当前账号下无可用 License 通过校验（设备绑定、过期等），请检查个人中心或联系支持。"

    for lic in candidates:
        key = (lic.get("licenseKey") or "").strip() if isinstance(lic.get("licenseKey"), str) else ""
        if not key:
            continue
        payload = {
            "licenseKey": key,
            "deviceId": encrypted_device_id,
            "deviceName": device_name,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            vr = await client.post(
                verify_url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        vbody: Any
        try:
            vbody = vr.json() if vr.content else {}
        except Exception:
            vbody = {}
        if 200 <= vr.status_code < 300 and _verify_response_ok(vbody):
            return
        err = _error_detail_from_any(vbody) if vbody else f"License 校验失败 (HTTP {vr.status_code})"
        if err:
            last_error = err
    raise HTTPException(status_code=400, detail=last_error)
