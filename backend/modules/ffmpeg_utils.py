# -*- coding: utf-8 -*-
"""统一的 ffmpeg/ffprobe 路径解析与常用操作封装。

所有需要使用 ffmpeg 的模块应统一从此处获取可执行文件路径和工具函数，
避免各处重复实现 _find_ffmpeg / _resolve_ffmpeg 等逻辑。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from modules.subprocess_no_console import run_no_console

logger = logging.getLogger(__name__)

WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_HWACCEL_MODE_VALUES = {"auto", "cpu", "cuda"}
_ffmpeg_cuda_hwaccel_cache: Optional[bool] = None
_ffmpeg_cuda_hwaccel_logged = False


def _bin_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


def resolve_ffmpeg_bin() -> Optional[str]:
    """搜索 ffmpeg 可执行文件的完整路径。

    搜索顺序：
      1. FFMPEG_PATH 环境变量
      2. FFMPEG_DIR / FFMPEG_HOME 环境变量
      3. shutil.which("ffmpeg") — 系统 PATH
      4. imageio_ffmpeg.get_ffmpeg_exe()
      5. src-tauri/resources/ (开发 & 打包)
      6. PyInstaller exe 同目录 resources/
      7. SACV_INSTALL_DIR/resources/
      8. 当前模块父目录 resources/
      9. cwd/resources/
      10. Windows 常见安装位置
    """
    return _resolve_bin("ffmpeg")


def resolve_ffprobe_bin() -> Optional[str]:
    """搜索 ffprobe 可执行文件的完整路径，搜索顺序同 resolve_ffmpeg_bin。"""
    return _resolve_bin("ffprobe")


def _resolve_bin(base: str) -> Optional[str]:
    name = _bin_name(base)

    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        try:
            p = Path(env_path)
            if p.exists():
                # ffprobe 不能与 ffmpeg 混用：FFMPEG_PATH 常指向 ffmpeg.exe，不能原样当作 ffprobe。
                if base == "ffprobe":
                    pl = p.name.lower()
                    if "ffprobe" in pl:
                        return str(p)
                    sibling = p.parent / name
                    if sibling.exists():
                        return str(sibling)
                else:
                    return str(p)
        except Exception:
            pass

    env_dir = os.environ.get("FFMPEG_DIR") or os.environ.get("FFMPEG_HOME")
    if env_dir:
        try:
            p = Path(env_dir) / name
            if p.exists():
                return str(p)
        except Exception:
            pass

    hit = shutil.which(base)
    if hit:
        return hit

    try:
        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        if ff:
            pp = Path(ff)
            if pp.exists():
                # imageio 仅捆绑 ffmpeg：取同目录下的 ffprobe，不能把 ffmpeg 当作 ffprobe。
                if base == "ffprobe":
                    probe = pp.parent / name
                    if probe.exists():
                        return str(probe)
                else:
                    return str(pp)
    except Exception:
        pass

    candidates: List[Path] = []

    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "resources" / name)
        candidates.append(exe_dir / name)
    except Exception:
        pass

    try:
        root = Path(__file__).resolve().parents[2]
        candidates.append(root / "src-tauri" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "debug" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "release" / "resources" / name)
    except Exception:
        pass

    install_dir = os.environ.get("SACV_INSTALL_DIR")
    if install_dir:
        try:
            candidates.append(Path(install_dir) / "resources" / name)
        except Exception:
            pass

    try:
        here = Path(__file__).resolve()
        candidates.append(here.parent.parent / "resources" / name)
    except Exception:
        pass

    try:
        candidates.append(Path.cwd() / "resources" / name)
    except Exception:
        pass

    if os.name == "nt":
        try:
            candidates.append(Path("C:/Program Files/ffmpeg/bin") / name)
            candidates.append(Path("C:/ffmpeg/bin") / name)
            candidates.append(Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / name)
            candidates.append(Path("C:/ProgramData/chocolatey/bin") / name)
        except Exception:
            pass

    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            continue

    return None



def get_ffmpeg_hwaccel_mode() -> str:
    raw = str(os.environ.get("OMNI_FFMPEG_HWACCEL") or "auto").strip().lower()
    if raw in _HWACCEL_MODE_VALUES:
        return raw
    return "auto"


def ffmpeg_supports_cuda_hwaccel() -> bool:
    global _ffmpeg_cuda_hwaccel_cache, _ffmpeg_cuda_hwaccel_logged
    if _ffmpeg_cuda_hwaccel_cache is not None:
        return bool(_ffmpeg_cuda_hwaccel_cache)

    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        _ffmpeg_cuda_hwaccel_cache = False
        return False

    try:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if os.name == "nt":
            kwargs["creationflags"] = WIN_NO_WINDOW
        proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-hwaccels"],
            check=False,
            **kwargs,
        )
        if proc.returncode == 0:
            text = (proc.stdout or b"").decode(errors="ignore").lower()
            _ffmpeg_cuda_hwaccel_cache = ("cuda" in text) or ("nvdec" in text) or ("cuvid" in text)
        else:
            _ffmpeg_cuda_hwaccel_cache = False
    except Exception:
        _ffmpeg_cuda_hwaccel_cache = False

    if not _ffmpeg_cuda_hwaccel_logged:
        if _ffmpeg_cuda_hwaccel_cache:
            logger.info("ffmpeg 检测到 CUDA hwaccel，Omni 解码将优先尝试 GPU")
        else:
            logger.info("ffmpeg 未检测到 CUDA hwaccel，Omni 解码将使用 CPU")
        _ffmpeg_cuda_hwaccel_logged = True

    return bool(_ffmpeg_cuda_hwaccel_cache)


def get_ffmpeg_cuda_prefix() -> Tuple[str, ...]:
    mode = get_ffmpeg_hwaccel_mode()
    if mode == "cpu":
        return ()
    if mode == "cuda":
        return ("-hwaccel", "cuda")
    if ffmpeg_supports_cuda_hwaccel():
        return ("-hwaccel", "cuda")
    return ()


async def wav_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """使用 ffmpeg 将 wav 转为 mp3（libmp3lame, -q:a 3）。"""
    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        logger.warning("wav_to_mp3: 未找到 ffmpeg")
        return False

    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "3",
        str(mp3_path),
    ]

    async def _run_ffmpeg_async() -> tuple[int, bytes]:
        kwargs = {"creationflags": WIN_NO_WINDOW} if os.name == "nt" else {}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        _stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stderr or b""

    def _run_ffmpeg_sync() -> tuple[int, bytes]:
        proc = run_no_console(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc.returncode or 0, (proc.stderr or b"")

    try:
        try:
            rc, stderr = await _run_ffmpeg_async()
        except NotImplementedError:
            # Windows 上 SelectorEventLoop 不支持 asyncio 子进程，与是否安装 ffmpeg 无关
            logger.info(
                "wav_to_mp3: 当前事件循环不支持异步子进程，已改用同步 ffmpeg 调用"
            )
            rc, stderr = await asyncio.to_thread(_run_ffmpeg_sync)
    except FileNotFoundError:
        logger.warning("wav_to_mp3: ffmpeg 命令未找到 (%s)", ffmpeg_bin)
        return False
    except Exception as e:
        logger.warning("wav_to_mp3 异常 (%s): %s", type(e).__name__, e)
        return False

    if rc == 0 and mp3_path.exists():
        return True
    err_text = (stderr or b"").decode("utf-8", errors="replace").strip()
    if err_text:
        logger.warning("wav_to_mp3 失败 (rc=%s): %s", rc, err_text[:500])
    else:
        logger.warning("wav_to_mp3 失败 (rc=%s)", rc)
    return False


async def ffprobe_get_duration(path: str) -> Optional[float]:
    """使用 ffprobe 获取音视频时长（先尝试音频流时长，再尝试格式时长）。"""
    ffprobe_bin = resolve_ffprobe_bin()
    if not ffprobe_bin:
        logger.warning("ffprobe_get_duration: 未找到 ffprobe")
        return None

    try:
        kwargs = {"creationflags": WIN_NO_WINDOW} if os.name == "nt" else {}

        cmd_a = [
            ffprobe_bin, "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=duration",
            "-of", "default=nk=1:nw=1",
            path,
        ]
        proc_a = await asyncio.create_subprocess_exec(
            *cmd_a,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        out_a, _ = await proc_a.communicate()
        if proc_a.returncode == 0:
            try:
                return float(out_a.decode(errors="ignore").strip())
            except Exception:
                pass

        cmd_f = [
            ffprobe_bin, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nk=1:nw=1",
            path,
        ]
        proc_f = await asyncio.create_subprocess_exec(
            *cmd_f,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        out_f, _ = await proc_f.communicate()
        if proc_f.returncode == 0:
            try:
                return float(out_f.decode(errors="ignore").strip())
            except Exception:
                return None

        return None
    except Exception:
        return None
