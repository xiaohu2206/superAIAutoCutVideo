# -*- coding: utf-8 -*-
"""
本机 License 用设备 ID：在运行本后端的电脑上用系统信息生成，不依赖浏览器。

- macOS：IOPlatformUUID（ioreg）
- Windows：MachineGuid（注册表，无需 WMIC 黑框；与 Win32 常见做法一致）
- 其他环境：回退为机器特征哈希（仅用于开发/非生产）
"""

from __future__ import annotations

import hashlib
import re
import socket
import subprocess
import sys
import uuid
from functools import lru_cache
from typing import Optional

from modules.subprocess_no_console import check_output_no_console


def _fingerprint_from_parts(prefix: str, *parts: str) -> str:
    raw = "|".join(parts)
    h = hashlib.sha256(f"{prefix}:{raw}".encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}{h[:48]}"


def _node_host_parts() -> tuple[str, str]:
    return f"{uuid.getnode():x}", socket.gethostname() or "unknown"


def _macos_io_platform_uuid() -> Optional[str]:
    try:
        out = check_output_no_console(
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    text = out.decode("utf-8", errors="replace")
    m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', text)
    if not m:
        return None
    s = m.group(1).strip()
    if not s:
        return None
    return s.lower()


def _windows_machine_guid() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    key_path = r"SOFTWARE\Microsoft\Cryptography"
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as k:
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
    except OSError:
        return None
    if not val or not isinstance(val, str):
        return None
    s = val.strip().lower()
    return s or None


@lru_cache(maxsize=1)
def get_host_device_fingerprint() -> str:
    """
    返回稳定、可复现的字符串（同机多次调用在进程内缓存一致；跨平台格式不同，便于识别来源）。
    """
    node, host = _node_host_parts()
    if sys.platform == "darwin":
        u = _macos_io_platform_uuid()
        if u:
            return f"mac:{u}"
        return _fingerprint_from_parts("mac:", "no-ioreg", node, host)
    if sys.platform == "win32":
        g = _windows_machine_guid()
        if g:
            return f"win:{g}"
        return _fingerprint_from_parts("win:", "no-machineguid", node, host)
    return _fingerprint_from_parts("other:", sys.platform, node, host)
