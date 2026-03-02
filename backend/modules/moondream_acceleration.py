import platform
from typing import Any, Dict, Optional, Tuple


_MIN_CUDA_COMPUTE_CAPABILITY: Tuple[int, int] = (6, 0)


def _safe_import_torch() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from modules.fun_asr_acceleration import prepare_windows_dll_search_paths

        prepare_windows_dll_search_paths()
    except Exception:
        pass
    try:
        import torch  # type: ignore

        return torch, None
    except Exception as e:
        return None, f"torch_import_failed:{e}"


def _safe_import_llama_cpp() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from modules.fun_asr_acceleration import prepare_windows_dll_search_paths

        prepare_windows_dll_search_paths()
    except Exception:
        pass
    try:
        import llama_cpp  # type: ignore

        return llama_cpp, None
    except Exception as e:
        return None, f"llama_cpp_import_failed:{e}"


def get_moondream_preferred_device() -> str:
    st = get_moondream_acceleration_status()
    if st.get("supported"):
        return str(st.get("preferred_device") or "cuda:0")
    return "cpu"


def get_moondream_acceleration_status() -> Dict[str, Any]:
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
        "llama_cpp": {},
        "min_cuda_compute_capability": {"major": _MIN_CUDA_COMPUTE_CAPABILITY[0], "minor": _MIN_CUDA_COMPUTE_CAPABILITY[1]},
    }

    llama_cpp, llama_err = _safe_import_llama_cpp()
    if llama_cpp is None:
        result["reasons"].append(llama_err or "llama_cpp_not_available")
    else:
        try:
            result["llama_cpp"] = {"version": getattr(llama_cpp, "__version__", None)}
        except Exception:
            result["llama_cpp"] = {}
        try:
            ll = getattr(llama_cpp, "llama_cpp", None)
            fn = getattr(ll, "llama_supports_gpu_offload", None)
            if callable(fn):
                result["llama_cpp"]["supports_gpu_offload"] = bool(fn())
        except Exception:
            pass

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

    supports_offload = bool(result.get("llama_cpp", {}).get("supports_gpu_offload")) if isinstance(result.get("llama_cpp"), dict) else False
    if not supports_offload:
        result["reasons"].append("llama_cpp_gpu_offload_not_supported")
        return result

    result["supported"] = True
    result["preferred_device"] = "cuda:0"
    result["backend"] = "llama-cpp-cuda" if llama_cpp is not None else "cuda"
    return result
