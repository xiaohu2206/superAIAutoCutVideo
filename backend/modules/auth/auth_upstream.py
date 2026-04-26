#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证上游：对账号服务 HTTP 原样透传响应（状态码与 JSON/正文），不在此解析业务码。

- 开发：http://127.0.0.1:3000
- 打包（frozen）：http://47.92.113.170

httpx 使用 trust_env=False，避免本机 HTTP(S)_PROXY 把对明确上游地址的请求走代理导致 502 等，与 curl 直连 127.0.0.1 行为一致。
"""

from __future__ import annotations

import sys
from typing import Any, Optional

import httpx
from fastapi.responses import JSONResponse, Response

_AUTH_UPSTREAM_DEV = "http://127.0.0.1:3000"
_AUTH_UPSTREAM_PROD = "http://47.92.113.170"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=8.0, read=45.0, write=20.0, pool=8.0)


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
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT, trust_env=False
    ) as client:
        r = await client.post(url, json=body, headers=headers)
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
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT, trust_env=False
    ) as client:
        r = await client.post(url, content=content, headers=headers)
    return _passthrough_response(r)


async def forward_upstream_get(path: str, authorization: Optional[str]) -> Response:
    url = f"{get_auth_upstream_base()}{path}"
    headers = {"Accept": "application/json, text/plain, */*"}
    if authorization:
        headers["Authorization"] = authorization
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT, trust_env=False
    ) as client:
        r = await client.get(url, headers=headers)
    return _passthrough_response(r)
