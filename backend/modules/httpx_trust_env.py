# -*- coding: utf-8 -*-
"""httpx 与系统/VPN 代理：按目标主机决定是否读取 HTTP(S)_PROXY（trust_env）。"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

import httpx


def trust_env_for_http_url(url: str) -> bool:
    """
    对本机 / 私网 / 链路本地地址返回 False，避免全局代理把局域网请求发到 VPN 侧导致失败。
    公网或其它主机名保持 True，便于用户通过系统代理访问 OpenAI 等。
    """
    try:
        host = urlparse(url).hostname
    except Exception:
        return True
    if not host:
        return True
    h = host.strip().lower()
    if h == "localhost":
        return False
    if h.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return False
    except ValueError:
        pass
    return True


def async_client_no_proxy_env(**kwargs: Any) -> httpx.AsyncClient:
    """不读取 HTTP_PROXY/HTTPS_PROXY；用于局域网服务等必须直连的场景。"""
    merged = dict(kwargs)
    merged["trust_env"] = False
    return httpx.AsyncClient(**merged)
