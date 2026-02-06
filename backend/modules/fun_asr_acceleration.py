import platform
from typing import Any, Dict, Optional, Tuple


_MIN_CUDA_COMPUTE_CAPABILITY: Tuple[int, int] = (6, 0)


def _safe_import_torch() -> Tuple[Optional[Any], Optional[str]]:
    try:
        import torch  # type: ignore

        return torch, None
    except Exception as e:
        return None, f"torch_import_failed:{e}"


def get_fun_asr_preferred_device() -> str:
    status = get_fun_asr_acceleration_status()
    if status.get("supported"):
        return str(status.get("preferred_device") or "cuda:0")
    return "cpu"


def get_fun_asr_acceleration_status() -> Dict[str, Any]:
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

