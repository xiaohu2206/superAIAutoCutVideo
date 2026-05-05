"""
HTTPS 校验（企业 HTTPS 解密代理 / MITM）：

- 浏览器信「系统证书库」；Python 的 requests/urllib3 默认信 certifi，不含公司根证书 → SSLError。
- 优先：REQUESTS_CA_BUNDLE / SSL_CERT_FILE / CURL_CA_BUNDLE 指向有效 PEM（含企业根证书）。
- 否则：truststore.inject_into_ssl() 一次，全局让标准库 ssl 使用操作系统证书库（与 Edge/系统信任一致）。
  必须在发出任何 HTTPS 请求前尽早调用 ensure_os_trust_injected()（见 main.py）。
- 调试：SUPERAUTO_SKIP_SYSTEM_TLS=1 跳过注入。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_injected = False


class _SSLContextAdapter(HTTPAdapter):
    """走代理时 urllib3 会走 proxy_manager_for，仅改写 init_poolmanager 不够。"""

    def __init__(self, ssl_context, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs.setdefault("ssl_context", self._ssl_context)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def _env_ca_bundle_path() -> Optional[str]:
    raw = (
        os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("CURL_CA_BUNDLE")
    )
    if not raw:
        return None
    path = os.path.expanduser(raw.strip().strip('"'))
    return path if os.path.isfile(path) else None


def ensure_os_trust_injected() -> None:
    """进程内幂等：在无自定义 CA 文件时注入 truststore。"""
    global _injected
    if os.environ.get("SUPERAUTO_SKIP_SYSTEM_TLS", "").strip().lower() in {"1", "true", "yes"}:
        return
    if _env_ca_bundle_path() is not None:
        return
    with _lock:
        if _injected:
            return
        try:
            import truststore

            truststore.inject_into_ssl()
            _log.info("HTTPS: 已注入 truststore（ssl 使用操作系统证书库）")
        except ImportError:
            _log.warning(
                "HTTPS: 未安装 truststore；企业代理环境请执行 pip install truststore，"
                "或设置 REQUESTS_CA_BUNDLE 指向含企业根证书的 PEM"
            )
        except Exception as e:
            _log.warning("HTTPS: truststore 注入失败: %s", e)
        _injected = True


def _merged_ssl_context():
    """系统信任 + certifi 公共 CA，减少仅一边缺链的情况。"""
    import truststore

    ctx = truststore.ssl_context()
    try:
        import certifi

        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ctx


def requests_session_with_os_trust() -> requests.Session:
    bundle = _env_ca_bundle_path()
    session = requests.Session()
    if bundle is not None:
        session.verify = bundle
        return session

    ensure_os_trust_injected()

    try:
        ctx = _merged_ssl_context()
        session.mount("https://", _SSLContextAdapter(ctx))
    except ImportError:
        session.verify = True
    except Exception as e:
        _log.warning("HTTPS: 合并 SSL 上下文失败，仅依赖全局 truststore 注入: %s", e)
        session.verify = True

    return session
