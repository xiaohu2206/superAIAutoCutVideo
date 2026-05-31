import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from modules.auth import auth_upstream
from modules.auth import omni_project_license


class _FakeAsyncClient:
    calls: list[tuple[bool, object, str, str]] = []
    outcomes: list[object] = []

    def __init__(self, *, timeout: httpx.Timeout, trust_env: bool, transport=None):
        self.trust_env = trust_env
        self.transport = transport

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def request(self, method: str, url: str, **kwargs):
        self.calls.append((self.trust_env, self.transport, method, url))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"code": 0, "data": True},
        request=httpx.Request("POST", "http://example.com/api/auth/login"),
    )


def test_local_lan_candidates_are_discovered_from_active_interfaces(monkeypatch):
    fake_psutil = SimpleNamespace(
        net_if_stats=lambda: {
            "wlan": SimpleNamespace(isup=True),
            "tun": SimpleNamespace(isup=True),
            "offline": SimpleNamespace(isup=False),
        },
        net_if_addrs=lambda: {
            "wlan": [SimpleNamespace(family=socket.AF_INET, address="10.1.2.3")],
            "tun": [SimpleNamespace(family=socket.AF_INET, address="198.18.0.1")],
            "offline": [SimpleNamespace(family=socket.AF_INET, address="192.168.50.8")],
        },
    )
    monkeypatch.setattr(auth_upstream, "psutil", fake_psutil)
    monkeypatch.setattr(
        auth_upstream.socket,
        "gethostbyname_ex",
        lambda hostname: (hostname, [], ["10.1.2.3"]),
    )

    assert auth_upstream._local_lan_ipv4_candidates() == ["10.1.2.3"]


@pytest.mark.asyncio
async def test_request_upstream_prefers_direct_connection(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.outcomes = [_response()]
    monkeypatch.setattr(auth_upstream.httpx, "AsyncClient", _FakeAsyncClient)

    response = await auth_upstream.request_auth_upstream(
        "POST",
        "http://47.92.113.170:8176/api/auth/login",
        timeout=auth_upstream._DEFAULT_TIMEOUT,
    )

    assert response.status_code == 200
    assert [call[0] for call in _FakeAsyncClient.calls] == [False]


@pytest.mark.asyncio
async def test_request_upstream_retries_via_lan_address_before_proxy(monkeypatch):
    request = httpx.Request("POST", "http://47.92.113.170:8176/api/auth/login")
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.outcomes = [
        httpx.RemoteProtocolError("disconnected", request=request),
        _response(),
    ]
    monkeypatch.setattr(auth_upstream.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(auth_upstream, "_local_lan_ipv4_candidates", lambda: ["192.168.1.103"])

    response = await auth_upstream.request_auth_upstream(
        "POST",
        str(request.url),
        timeout=auth_upstream._DEFAULT_TIMEOUT,
    )

    assert response.status_code == 200
    assert [call[0] for call in _FakeAsyncClient.calls] == [False, False]
    assert _FakeAsyncClient.calls[1][1] is not None


@pytest.mark.asyncio
async def test_request_upstream_retries_empty_502_via_lan_address(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.outcomes = [
        httpx.Response(502, request=httpx.Request("GET", "http://example.com")),
        _response(),
    ]
    monkeypatch.setattr(auth_upstream.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(auth_upstream, "_local_lan_ipv4_candidates", lambda: ["10.1.2.3"])

    response = await auth_upstream.request_auth_upstream(
        "GET",
        "http://47.92.113.170:8176/api/licenses",
        timeout=auth_upstream._DEFAULT_TIMEOUT,
    )

    assert response.status_code == 200
    assert [call[0] for call in _FakeAsyncClient.calls] == [False, False]


@pytest.mark.asyncio
async def test_request_upstream_retries_public_url_via_system_proxy(monkeypatch):
    request = httpx.Request("POST", "http://47.92.113.170:8176/api/auth/login")
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.outcomes = [
        httpx.RemoteProtocolError("disconnected", request=request),
        _response(),
    ]
    monkeypatch.setattr(auth_upstream.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(auth_upstream, "_local_lan_ipv4_candidates", lambda: [])
    monkeypatch.setattr(auth_upstream, "getproxies", lambda: {"http": "http://127.0.0.1:7990"})

    response = await auth_upstream.request_auth_upstream(
        "POST",
        str(request.url),
        timeout=auth_upstream._DEFAULT_TIMEOUT,
    )

    assert response.status_code == 200
    assert [call[0] for call in _FakeAsyncClient.calls] == [False, True]


@pytest.mark.asyncio
async def test_forward_post_turns_timeout_into_json_response(monkeypatch):
    request = httpx.Request("POST", "http://47.92.113.170:8176/api/auth/login")

    async def _timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out", request=request)

    monkeypatch.setattr(auth_upstream, "request_auth_upstream", _timeout)

    response = await auth_upstream.forward_upstream_post("/api/auth/login", {}, None)

    assert response.status_code == 504
    assert json.loads(response.body)["detail"] == "认证服务响应超时，请稍后重试"


@pytest.mark.asyncio
async def test_omni_license_gate_turns_network_error_into_503(monkeypatch):
    request = httpx.Request("GET", "http://47.92.113.170:8176/api/licenses")

    async def _network_error(*args, **kwargs):
        raise httpx.ConnectError("unreachable", request=request)

    monkeypatch.setattr(omni_project_license, "request_auth_upstream", _network_error)

    with pytest.raises(HTTPException) as exc:
        await omni_project_license.require_valid_license_for_omni("Bearer probe-token")

    assert exc.value.status_code == 503
    assert exc.value.detail == "无法连接 License 服务，请稍后重试。"
