#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证上游：对账号服务 HTTP 原样透传响应（状态码与 JSON/正文），不在此解析业务码。

- 开发：http://127.0.0.1:3000
- 打包（frozen）：http://47.92.113.170

直连上游时关闭 trust_env，避免 VPN/系统设置的 HTTP(S)_PROXY 把 localhost 或固定 IP 走代理导致 ConnectError→502。
"""

from __future__ import annotations

import sys
from typing import Any, Optional

import httpx
from fastapi.responses import JSONResponse, Response

_AUTH_UPSTREAM_DEV = "http://47.92.113.170:8176" # "http://127.0.0.1:3000"
_AUTH_UPSTREAM_PROD = "http://47.92.113.170:8176"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=8.0, read=45.0, write=20.0, pool=8.0)

_UPSTREAM_UNREACHABLE_MSG = "认证服务暂时不可用，请稍后重试"


def _use_production_upstream() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_auth_upstream_base() -> str:
    base = _AUTH_UPSTREAM_PROD if _use_production_upstream() else _AUTH_UPSTREAM_DEV
    return base.rstrip("/")


def _passthrough_response(resp: httpx.Response) -> Response:
    ct = (resp.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception:
            pass
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


async def forward_upstream_post(
    path: str,
    body: Any,
    authorization: Optional[str],
) -> Response:
    url = f"{get_auth_upstream_base()}{path}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            trust_env=False,
        ) as client:
            r = await client.post(url, json=body, headers=headers)
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"detail": _UPSTREAM_UNREACHABLE_MSG},
        )
    return _passthrough_response(r)


async def forward_upstream_post_raw(
    path: str,
    content: bytes,
    authorization: Optional[str],
    content_type: Optional[str],
) -> Response:
    """POST 原样转发请求体字节与 Content-Type，避免 JSON 解析后再 dumps 与上游校验不一致。"""
    url = f"{get_auth_upstream_base()}{path}"
    headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
    }
    ct = (content_type or "").strip()
    headers["Content-Type"] = ct if ct else "application/json"
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            trust_env=False,
        ) as client:
            r = await client.post(url, content=content, headers=headers)
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"detail": _UPSTREAM_UNREACHABLE_MSG},
        )
    return _passthrough_response(r)


async def fetch_upstream_json(path: str, authorization: Optional[str] = None) -> Optional[dict]:
    """从上游获取 JSON 数据，成功返回 dict，失败返回 None（不抛异常）。"""
    url = f"{get_auth_upstream_base()}{path}"
    headers = {"Accept": "application/json, text/plain, */*"}
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            trust_env=False,
        ) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


async def forward_upstream_get(path: str, authorization: Optional[str]) -> Response:
    url = f"{get_auth_upstream_base()}{path}"
    headers = {"Accept": "application/json, text/plain, */*"}
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            trust_env=False,
        ) as client:
            r = await client.get(url, headers=headers)
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"detail": _UPSTREAM_UNREACHABLE_MSG},
        )
    return _passthrough_response(r)
