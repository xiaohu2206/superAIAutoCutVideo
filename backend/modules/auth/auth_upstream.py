#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证上游：对账号服务 HTTP 原样透传响应（状态码与 JSON/正文），不在此解析业务码。

- 开发：http://127.0.0.1:3000
- 打包（frozen）：http://47.92.113.170

直连上游时关闭 trust_env，避免 VPN/系统设置的 HTTP(S)_PROXY 把 localhost 或固定 IP 走代理导致 ConnectError→502。
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import getproxies

import httpx
from fastapi.responses import JSONResponse, Response

from modules.httpx_trust_env import trust_env_for_http_url

try:
    import psutil
except ImportError:  # Source-only development environments may omit runtime deps.
    psutil = None  # type: ignore[assignment]

_AUTH_UPSTREAM_DEV = "http://47.92.113.170:8176" # "http://127.0.0.1:3000"
_AUTH_UPSTREAM_PROD = "http://47.92.113.170:8176"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=8.0, read=45.0, write=20.0, pool=8.0)
# 刷新页时常见串行请求 /me，上游慢会拖住首屏；单独收紧读超时（仍足够拉用户信息）
AUTH_ME_HTTP_TIMEOUT = httpx.Timeout(connect=4.0, read=10.0, write=8.0, pool=4.0)

_UPSTREAM_UNREACHABLE_MSG = "认证服务暂时不可用，请稍后重试"


def _use_production_upstream() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_auth_upstream_base() -> str:
    base = _AUTH_UPSTREAM_PROD if _use_production_upstream() else _AUTH_UPSTREAM_DEV
    return base.rstrip("/")


def _passthrough_response(resp: httpx.Response) -> Response:
    if resp.status_code >= 500 and not resp.content:
        return JSONResponse(
            status_code=resp.status_code,
            content={"detail": _UPSTREAM_UNREACHABLE_MSG},
        )
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


def _should_retry_with_proxy_env(url: str) -> bool:
    """Retry public upstreams through the system proxy when one is configured."""
    if not trust_env_for_http_url(url):
        return False
    scheme = (urlparse(url).scheme or "").lower()
    proxies = getproxies()
    return bool(proxies.get(scheme) or proxies.get("all"))


def _is_empty_server_error(resp: httpx.Response) -> bool:
    """VPN proxies sometimes surface routing failures as an empty 5xx response."""
    return resp.status_code >= 500 and not resp.content


def _local_lan_ipv4_candidates() -> list[str]:
    """
    Return local LAN addresses that can bypass VPN TUN default routes.

    Some VPN clients route direct sockets through a TUN adapter while still
    exposing the physical LAN address on the host. Binding that address lets
    the OS use the physical interface for the auth upstream request.
    """
    addresses: list[str] = []
    if psutil is not None:
        try:
            stats = psutil.net_if_stats()
            for name, interface_addresses in psutil.net_if_addrs().items():
                stat = stats.get(name)
                if stat is not None and not stat.isup:
                    continue
                addresses.extend(
                    addr.address
                    for addr in interface_addresses
                    if addr.family == socket.AF_INET
                )
        except Exception:
            pass
    try:
        addresses.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    candidates: list[str] = []
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not isinstance(ip, ipaddress.IPv4Address):
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            continue
        # RFC 2544 benchmarking range, commonly used by VPN TUN adapters.
        if ip in ipaddress.ip_network("198.18.0.0/15"):
            continue
        candidates.append(str(ip))
    return list(dict.fromkeys(candidates))


async def request_auth_upstream(
    method: str,
    url: str,
    *,
    timeout: httpx.Timeout,
    **kwargs: Any,
) -> httpx.Response:
    """Prefer direct auth requests, then bypass VPN TUN routes when possible."""
    direct_error: Optional[httpx.RequestError] = None
    fallback_response: Optional[httpx.Response] = None
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.request(method, url, **kwargs)
            if not _is_empty_server_error(response):
                return response
            fallback_response = response
    except httpx.RequestError as exc:
        direct_error = exc
        if not trust_env_for_http_url(url):
            raise
    if not trust_env_for_http_url(url):
        assert fallback_response is not None
        return fallback_response
    for local_address in _local_lan_ipv4_candidates():
        transport = httpx.AsyncHTTPTransport(local_address=local_address)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
                transport=transport,
            ) as client:
                response = await client.request(method, url, **kwargs)
                if not _is_empty_server_error(response):
                    return response
                fallback_response = response
        except httpx.RequestError:
            pass
    if not _should_retry_with_proxy_env(url):
        if fallback_response is not None:
            return fallback_response
        assert direct_error is not None
        raise direct_error
    async with httpx.AsyncClient(timeout=timeout, trust_env=True) as client:
        return await client.request(method, url, **kwargs)


def _upstream_request_error_response(exc: httpx.RequestError) -> JSONResponse:
    if isinstance(exc, httpx.TimeoutException):
        return JSONResponse(
            status_code=504,
            content={"detail": "认证服务响应超时，请稍后重试"},
        )
    return JSONResponse(
        status_code=502,
        content={"detail": _UPSTREAM_UNREACHABLE_MSG},
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
        r = await request_auth_upstream(
            "POST",
            url,
            timeout=_DEFAULT_TIMEOUT,
            json=body,
            headers=headers,
        )
    except httpx.RequestError as exc:
        return _upstream_request_error_response(exc)
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
        r = await request_auth_upstream(
            "POST",
            url,
            timeout=_DEFAULT_TIMEOUT,
            content=content,
            headers=headers,
        )
    except httpx.RequestError as exc:
        return _upstream_request_error_response(exc)
    return _passthrough_response(r)


async def fetch_upstream_json(path: str, authorization: Optional[str] = None) -> Optional[dict]:
    """从上游获取 JSON 数据，成功返回 dict，失败返回 None（不抛异常）。"""
    url = f"{get_auth_upstream_base()}{path}"
    headers = {"Accept": "application/json, text/plain, */*"}
    if authorization:
        headers["Authorization"] = authorization
    try:
        r = await request_auth_upstream(
            "GET",
            url,
            timeout=_DEFAULT_TIMEOUT,
            headers=headers,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def forward_upstream_get(
    path: str,
    authorization: Optional[str],
    *,
    timeout: Optional[httpx.Timeout] = None,
) -> Response:
    url = f"{get_auth_upstream_base()}{path}"
    headers = {"Accept": "application/json, text/plain, */*"}
    if authorization:
        headers["Authorization"] = authorization
    eff_timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
    try:
        r = await request_auth_upstream(
            "GET",
            url,
            timeout=eff_timeout,
            headers=headers,
        )
    except httpx.RequestError as exc:
        return _upstream_request_error_response(exc)
    return _passthrough_response(r)
