import importlib
import sys
from pathlib import Path


import logging
import importlib.util
import os


def _diag_info() -> dict:
    try:
        return {
            "frozen": bool(getattr(sys, "frozen", False)),
            "meipass": getattr(sys, "_MEIPASS", None),
            "executable": getattr(sys, "executable", None),
            "cwd": str(Path.cwd()),
            "this_file": str(Path(__file__).resolve()),
            "sys_path_0_5": list(sys.path[:5]),
            "spec_voxcpm": bool(importlib.util.find_spec("voxcpm")),
            "spec_voxcpm_tts": bool(importlib.util.find_spec("voxcpm_tts")),
        }
    except Exception:
        return {}


def _try_import_local() -> tuple[object | None, Exception | None]:
    try:
        from .voxcpm_tts import VoxCPMTTSModel as _M  # type: ignore
        return _M, None
    except Exception as e:
        return None, e


if bool(getattr(sys, "frozen", False)):
    os.environ.setdefault("PYTORCH_JIT", "0")
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

VoxCPMTTSModel, _local_err = _try_import_local()
if VoxCPMTTSModel is not None:
    try:
        logging.getLogger("modules.vendor.voxcpm_tts").info(
            f"VoxCPM vendor ready: impl=modules.vendor.voxcpm_tts.voxcpm_tts diag={_diag_info()}"
        )
    except Exception:
        pass


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve()
    backend_dir = here.parents[3]
    repo_root = backend_dir.parent

    roots: list[Path] = []
    roots.append(repo_root)

    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        roots.insert(0, Path(meipass))

    return roots


def _ensure_voxcpm_tts_importable() -> None:
    try:
        importlib.import_module("voxcpm_tts")
        return
    except Exception:
        pass

    for root in _candidate_roots():
        p = root / ".trae" / "cache" / "VoxCPM"
        if p.exists() and p.is_dir():
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)
            try:
                importlib.import_module("voxcpm_tts")
                return
            except Exception:
                continue

    try:
        importlib.import_module("voxcpm")
        here = Path(__file__).resolve()
        vendor_dir = here.parent
        sys.path.insert(0, str(vendor_dir))
        importlib.import_module("voxcpm_tts")
        return
    except Exception:
        pass


if VoxCPMTTSModel is None:
    try:
        logging.getLogger("modules.vendor.voxcpm_tts").error(
            f"VoxCPM vendor local import failed: err={_local_err} diag={_diag_info()}"
        )
    except Exception:
        pass

    if bool(getattr(sys, "frozen", False)):
        msg = str(_local_err)
        if "TorchScript requires source access" in msg or "Can't get source" in msg:
            raise RuntimeError(
                f"torchscript_source_unavailable_in_frozen:{msg}|"
                f"hint=已在打包版默认设置 PYTORCH_JIT=0 且 optimize=False；如仍失败，请提供本日志"
            ) from _local_err
        raise RuntimeError(f"voxcpm_vendor_import_failed:{msg}") from _local_err

    if isinstance(_local_err, ModuleNotFoundError) and ("voxcpm" in str(_local_err)):
        raise ModuleNotFoundError(f"missing_dependency:voxcpm:{_local_err}") from _local_err

    _ensure_voxcpm_tts_importable()
    try:
        _m = importlib.import_module("voxcpm_tts")
    except Exception as e:
        msg = str(e)
        if "No module named 'voxcpm_tts'" in msg or 'No module named "voxcpm_tts"' in msg:
            raise ModuleNotFoundError(
                "voxcpm_tts_not_installed: 请安装 VoxCPM 依赖（模块名为 voxcpm_tts），并重新安装后端依赖"
            ) from e
        raise
    VoxCPMTTSModel = getattr(_m, "VoxCPMTTSModel", None)

if VoxCPMTTSModel is None:
    raise ModuleNotFoundError(
        "voxcpm_tts_model_not_found: VoxCPMTTSModel 类未找到，请检查 voxcpm_tts 模块是否正确安装"
    )

__all__ = ["VoxCPMTTSModel"]
