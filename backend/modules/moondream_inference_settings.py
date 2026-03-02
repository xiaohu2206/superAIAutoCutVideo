import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modules.app_paths import app_settings_file


def _read_app_settings() -> Dict[str, Any]:
    p = app_settings_file()
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _write_app_settings(data: Dict[str, Any]) -> None:
    p = app_settings_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _normalize_device(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return "auto"
    if s in {"auto", "cpu"}:
        return s
    if s.startswith("cuda:"):
        tail = s.split(":", 1)[1].strip()
        idx = _to_int(tail)
        if idx is None or idx < 0:
            return "auto"
        return f"cuda:{idx}"
    return "auto"


def get_moondream_settings() -> Dict[str, Any]:
    data = _read_app_settings()
    md = data.get("moondream") if isinstance(data, dict) else None
    md = md if isinstance(md, dict) else {}
    device = _normalize_device(md.get("inference_device"))
    n_gpu_layers = _to_int(md.get("n_gpu_layers"))
    if n_gpu_layers is not None and n_gpu_layers < 0:
        n_gpu_layers = None
    return {"inference_device": device, "n_gpu_layers": n_gpu_layers}


def update_moondream_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    current = get_moondream_settings()
    if isinstance(patch, dict):
        if "inference_device" in patch:
            current["inference_device"] = _normalize_device(patch.get("inference_device"))
        if "n_gpu_layers" in patch:
            v = _to_int(patch.get("n_gpu_layers"))
            if v is not None and v < 0:
                v = None
            current["n_gpu_layers"] = v
    all_settings = _read_app_settings()
    if not isinstance(all_settings, dict):
        all_settings = {}
    all_settings["moondream"] = dict(current)
    _write_app_settings(all_settings)
    return dict(current)


def resolve_moondream_runtime_config(
    settings: Optional[Dict[str, Any]] = None,
    env_n_gpu_layers: Optional[int] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    st = dict(settings or get_moondream_settings())
    device = _normalize_device(st.get("inference_device"))

    resolved_device = device
    resolved_by = "settings"
    if device == "auto":
        try:
            from modules.moondream_acceleration import get_moondream_preferred_device

            resolved_device = _normalize_device(get_moondream_preferred_device())
            resolved_by = "auto"
        except Exception:
            resolved_device = "cpu"
            resolved_by = "auto"

    main_gpu = None
    if resolved_device.startswith("cuda:"):
        main_gpu = _to_int(resolved_device.split(":", 1)[1])
        if main_gpu is None or main_gpu < 0:
            main_gpu = 0

    n_gpu_layers = _to_int(st.get("n_gpu_layers"))
    n_gpu_layers_by = "settings"
    if n_gpu_layers is None:
        if env_n_gpu_layers is not None:
            n_gpu_layers = int(env_n_gpu_layers)
            n_gpu_layers_by = "env"
        else:
            n_gpu_layers = 0
            n_gpu_layers_by = "default"

    if resolved_device == "cpu":
        n_gpu_layers = 0
        n_gpu_layers_by = "cpu_forced"
    else:
        if n_gpu_layers <= 0:
            n_gpu_layers = 99
            n_gpu_layers_by = "gpu_default"

    runtime = {
        "device": resolved_device,
        "main_gpu": main_gpu,
        "n_gpu_layers": int(n_gpu_layers),
    }
    meta = {
        "resolved_device_by": resolved_by,
        "resolved_n_gpu_layers_by": n_gpu_layers_by,
        "settings": st,
    }
    return runtime, meta

