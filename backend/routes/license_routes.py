#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
License 路由：请求体与 Authorization 原样转发至上游账号服务，响应原样返回。
与 auth_routes 使用同一上游基址与 forward 实现。

说明：POST /api/licenses/bind 的 devices[].deviceId 由本机后端根据系统信息生成并注入，不信任浏览器。
POST /api/licenses/{id}/self-unbind 将空 JSON 体与 Authorization 原样转发上游。
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.auth.auth_upstream import (
    forward_upstream_get,
    forward_upstream_post_raw,
)
from modules.auth.device_id_crypto import encrypt_device_id
from modules.auth.license_device_id import get_host_device_fingerprint

licenses_router = APIRouter(prefix="/api/licenses", tags=["Licenses"])

license_public_router = APIRouter(prefix="/api/license", tags=["License"])


@licenses_router.get("", summary="查询当前用户已绑定的 License 列表")
async def list_licenses(request: Request):
    return await forward_upstream_get(
        "/api/licenses",
        request.headers.get("Authorization"),
    )


@licenses_router.get(
    "/client-device",
    summary="本机 License 设备 ID（由后端按 macOS / Windows 等系统信息生成，供展示或调试）",
)
async def get_license_client_device() -> dict[str, str]:
    did = await asyncio.to_thread(get_host_device_fingerprint)
    return {"deviceId": did}


@licenses_router.post("/bind", summary="将 License 绑定到当前用户")
async def bind_license(request: Request):
    auth = request.headers.get("Authorization")
    content_type = request.headers.get("content-type")
    raw = await request.body()
    if not raw:
        return JSONResponse(
            status_code=400, content={"detail": "请求体为空，缺少 licenseKey"}
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"detail": "请求体不是合法 JSON"})

    data: dict
    if isinstance(parsed, dict):
        data = parsed
    else:
        data = {}

    key = data.get("licenseKey")
    if not isinstance(key, str) or not key.strip():
        return JSONResponse(
            status_code=400, content={"detail": "缺少 licenseKey 或类型错误"}
        )

    device_id = await asyncio.to_thread(get_host_device_fingerprint)
    encrypted_device_id = encrypt_device_id(device_id)
    payload = {
        "licenseKey": key.strip(),
        "devices": [{"deviceId": encrypted_device_id}],
    }
    out = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return await forward_upstream_post_raw(
        "/api/licenses/bind",
        out,
        auth,
        "application/json",
    )


@licenses_router.post(
    "/{license_id}/self-unbind",
    summary="自助解绑 License（上游累计 3 次，第 3 次将吊销）",
)
async def self_unbind_license(license_id: int, request: Request):
    return await forward_upstream_post_raw(
        f"/api/licenses/{license_id}/self-unbind",
        b"{}",
        request.headers.get("Authorization"),
        "application/json",
    )


@licenses_router.get("/{license_id}", summary="查询单条 License 详情（须属于当前用户）")
async def get_license_detail(license_id: int, request: Request):
    return await forward_upstream_get(
        f"/api/licenses/{license_id}",
        request.headers.get("Authorization"),
    )


@license_public_router.post("/verify", summary="License 校验 / 换取 licenseToken")
async def verify_license(request: Request):
    raw = await request.body()
    return await forward_upstream_post_raw(
        "/api/license/verify",
        raw,
        None,
        request.headers.get("content-type"),
    )


@license_public_router.post("/refresh-token", summary="刷新 licenseToken")
async def refresh_license_token(request: Request):
    raw = await request.body()
    return await forward_upstream_post_raw(
        "/api/license/refresh-token",
        raw,
        None,
        request.headers.get("content-type"),
    )
