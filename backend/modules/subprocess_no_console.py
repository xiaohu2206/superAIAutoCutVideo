# -*- coding: utf-8 -*-
"""
Windows 下避免 ffmpeg/ffprobe 等控制台子进程弹出 CMD 黑框（Tauri / 无控制台宿主场景）。

**新代码请优先使用本模块的封装**，不要直接调用 asyncio.create_subprocess_exec / subprocess.run
等（除非刻意需要可见控制台）。

- 异步：`acreate_subprocess_exec`
- 同步：`check_output_no_console`、`run_no_console`、`popen_no_console`

若需与现有 creationflags 按位或，请使用 `creationflags_for_windows()` 的返回值。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any, Dict

_WIN = int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def creationflags_for_windows() -> int:
    """当前平台用于隐藏子进程窗口的 creationflags（非 Windows 为 0）。"""
    return _WIN


def _merge_creationflags(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(kwargs)
    if os.name != "nt":
        return out
    if "creationflags" in out:
        return out
    if _WIN:
        out["creationflags"] = _WIN
    return out


async def acreate_subprocess_exec(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
    """
    等价 asyncio.create_subprocess_exec；在 Windows 上若未传 creationflags，则自动加上 CREATE_NO_WINDOW。

    若需要保留控制台窗口（调试），传入 ``visible_console=True``（本函数会消费该参数，不会传给 asyncio）。
    """
    visible = bool(kwargs.pop("visible_console", False))
    if visible:
        return await asyncio.create_subprocess_exec(*args, **kwargs)
    return await asyncio.create_subprocess_exec(*args, **_merge_creationflags(kwargs))


def check_output_no_console(*args: Any, **kwargs: Any) -> bytes:
    return subprocess.check_output(*args, **_merge_creationflags(kwargs))


def run_no_console(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **_merge_creationflags(kwargs))


def popen_no_console(*args: Any, **kwargs: Any) -> subprocess.Popen:
    return subprocess.Popen(*args, **_merge_creationflags(kwargs))
