import platform
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple


_MIN_CUDA_COMPUTE_CAPABILITY: Tuple[int, int] = (6, 0)


def _prepare_windows_dll_search_paths() -> None:
    if platform.system().lower() != "windows":
        return

    try:
        os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    except Exception:
        pass

    candidates = []
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            candidates.append(Path(meipass))
    except Exception:
        pass

    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir)
        candidates.append(exe_dir / "_internal")
    except Exception:
        pass

    try:
        here = Path(__file__).resolve()
        for p in [here.parent, *here.parents]:
            try:
                if (p / "torch" / "lib").exists() or (p / "_internal" / "torch" / "lib").exists():
                    candidates.append(p)
                    break
            except Exception:
                continue
    except Exception:
        pass

    expanded = []
    for root in candidates:
        try:
            expanded.append(root)
            expanded.append(root / "torch" / "lib")
            expanded.append(root / "_internal" / "torch" / "lib")
            expanded.append(root / "Library" / "bin")
            expanded.append(root / "_internal" / "Library" / "bin")
            try:
                for p in root.glob("nvidia/**/bin"):
                    expanded.append(p)
            except Exception:
                pass
            try:
                for p in (root / "_internal").glob("nvidia/**/bin"):
                    expanded.append(p)
            except Exception:
                pass
        except Exception:
            continue

    seen = set()
    for p in expanded:
        try:
            if not p.exists():
                continue
        except Exception:
            continue
        try:
            sp = str(p)
            if sp in seen:
                continue
            seen.add(sp)
        except Exception:
            continue
        try:
            os.add_dll_directory(str(p))
        except Exception:
            pass
        try:
            old = os.environ.get("PATH", "")
            if str(p) not in old:
                os.environ["PATH"] = str(p) + os.pathsep + old
        except Exception:
            pass


def _safe_import_torch() -> Tuple[Optional[Any], Optional[str]]:
    try:
        _prepare_windows_dll_search_paths()
        import torch  # type: ignore

        return torch, None
    except Exception as e:
        return None, f"torch_import_failed:{e}"


def get_qwen3_tts_preferred_device() -> str:
    status = get_qwen3_tts_acceleration_status()
    if status.get("supported"):
        return str(status.get("preferred_device") or "cuda:0")
    return "cpu"


def get_qwen3_tts_acceleration_status() -> Dict[str, Any]:
    sys = platform.system()
    result: Dict[str, Any] = {
        "supported": False,
        "preferred_device": "cpu",
        "backend": "cpu",
        "reasons": [],
        "os": {
            "system": sys,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "torch": {},
        "cuda": {},
        "gpu": None,
        "min_cuda_compute_capability": {"major": _MIN_CUDA_COMPUTE_CAPABILITY[0], "minor": _MIN_CUDA_COMPUTE_CAPABILITY[1]},
    }

    torch, err = _safe_import_torch()
    if torch is None:
        result["reasons"].append(err or "torch_not_available")
        return result

    try:
        result["torch"] = {
            "version": getattr(torch, "__version__", None),
            "cuda_version": getattr(getattr(torch, "version", None), "cuda", None),
        }
    except Exception:
        result["torch"] = {}

    cuda_available = False
    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as e:
        result["reasons"].append(f"cuda_check_failed:{e}")
        return result

    try:
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
    except Exception:
        device_count = 0

    result["cuda"] = {
        "available": cuda_available,
        "device_count": device_count,
    }

    if not cuda_available:
        result["reasons"].append("cuda_not_available")
        return result

    if device_count <= 0:
        result["reasons"].append("cuda_device_not_found")
        return result

    try:
        idx = 0
        cap = torch.cuda.get_device_capability(idx)
        props = torch.cuda.get_device_properties(idx)
        gpu_name = getattr(props, "name", None)
        total_mem = getattr(props, "total_memory", None)
        result["gpu"] = {
            "index": idx,
            "name": gpu_name,
            "total_memory_bytes": int(total_mem) if isinstance(total_mem, int) else total_mem,
            "compute_capability": {"major": int(cap[0]), "minor": int(cap[1])},
        }
    except Exception as e:
        result["reasons"].append(f"cuda_device_query_failed:{e}")
        return result

    cap_major = int(result["gpu"]["compute_capability"]["major"])
    cap_minor = int(result["gpu"]["compute_capability"]["minor"])
    if (cap_major, cap_minor) < _MIN_CUDA_COMPUTE_CAPABILITY:
        result["reasons"].append("cuda_compute_capability_too_low")
        return result

    result["supported"] = True
    result["preferred_device"] = "cuda:0"
    result["backend"] = "pytorch-cuda"
    return result

