import importlib
import sys
from pathlib import Path


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
