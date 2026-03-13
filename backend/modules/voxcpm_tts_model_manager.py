import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from modules.app_paths import uploads_dir


VOXCPM_TTS_MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "voxcpm_0_5b": {
        "ms": "OpenBMB/VoxCPM-0.5B",
        "local": "VoxCPM-0.5B",
        "model_type": "voice_clone",
        "size": "0.5B",
        "display_names": ["VoxCPM-0.5B", "OpenBMB/VoxCPM-0.5B"],
    },
    "voxcpm_1_5b": {
        "ms": "OpenBMB/VoxCPM1.5",
        "local": "VoxCPM1.5",
        "model_type": "voice_clone",
        "size": "1.5B",
        "display_names": ["VoxCPM1.5", "OpenBMB/VoxCPM1.5"],
    },
}


VOXCPM_TTS_MODEL_TOTAL_BYTES_BY_KEY: Dict[str, int] = {
    "voxcpm_0_5b": int(1.6 * 1024 * 1024 * 1024),
    "voxcpm_1_5b": int(1.95 * 1024 * 1024 * 1024),
}


@dataclass(frozen=True)
class VoxCPMTTSModelStatus:
    key: str
    path: str
    exists: bool
    model_type: str
    size: str
    display_names: List[str]
    sources: Dict[str, str]


class VoxCPMTTSPathManager:
    def __init__(self) -> None:
        base = os.environ.get("VOXCPM_TTS_MODELS_DIR")
        if base and base.strip():
            self.base_dir = Path(base.strip())
        else:
            self.base_dir = uploads_dir() / "models" / "OpenBMB" / "VoxCPM"

    def model_path(self, key: str) -> Path:
        if key not in VOXCPM_TTS_MODEL_REGISTRY:
            raise KeyError(f"unknown_model_key: {key}")
        return self.base_dir / VOXCPM_TTS_MODEL_REGISTRY[key]["local"]

    def list_status(self) -> List[VoxCPMTTSModelStatus]:
        out: List[VoxCPMTTSModelStatus] = []
        for key, info in VOXCPM_TTS_MODEL_REGISTRY.items():
            p = self.model_path(key)
            out.append(
                VoxCPMTTSModelStatus(
                    key=key,
                    path=str(p),
                    exists=p.exists(),
                    model_type=str(info.get("model_type", "voice_clone")),
                    size=str(info.get("size", "")),
                    display_names=info.get("display_names", []),
                    sources={
                        "ms": str(info.get("ms", "")),
                        "local": str(info.get("local", "")),
                    },
                )
            )
        return out


def _list_files_flat(p: Path) -> List[str]:
    if not p.exists() or not p.is_dir():
        return []
    out: List[str] = []
    try:
        for item in p.iterdir():
            if item.is_file():
                out.append(item.name)
    except Exception:
        return []
    return out


def validate_model_dir(key: str, model_dir: Path) -> Tuple[bool, List[str]]:
    if not model_dir.exists() or not model_dir.is_dir():
        return False, ["dir_missing"]

    files = set(_list_files_flat(model_dir))
    missing: List[str] = []

    if "config.json" not in files:
        missing.append("config.json")

    has_weights = any(
        name.endswith(".safetensors") or name.endswith(".bin") for name in files
    )
    if not has_weights:
        missing.append("weights(.safetensors|.bin)")

    if "audiovae.pth" not in files:
        missing.append("audiovae.pth")

    if "tokenizer.json" not in files:
        missing.append("tokenizer.json")

    return len(missing) == 0, missing


def _merge_move(src: Path, dst: Path) -> None:
    if not src.exists():
        return

    if src.is_dir():
        if dst.exists() and not dst.is_dir():
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                shutil.rmtree(dst)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            _merge_move(child, dst / child.name)
        try:
            src.rmdir()
        except Exception:
            pass
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    shutil.move(str(src), str(dst))


def download_model_snapshot(key: str, provider: str, target_dir: Path) -> Dict[str, Any]:
    if key not in VOXCPM_TTS_MODEL_REGISTRY:
        raise ValueError(f"unknown_model_key: {key}")
    provider = (provider or "").strip().lower()
    if provider != "modelscope":
        raise ValueError("provider_must_be_modelscope")

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
    except Exception as e:
        raise RuntimeError(f"missing_dependency:modelscope:{e}")

    model_id = VOXCPM_TTS_MODEL_REGISTRY[key]["ms"]
    ms_cache_dir = target_dir / ".modelscope_cache"
    ms_cache_dir.mkdir(parents=True, exist_ok=True)
    downloaded = ms_snapshot_download(model_id=model_id, cache_dir=str(ms_cache_dir))
    downloaded_dir = Path(str(downloaded))
    if downloaded_dir.exists() and downloaded_dir.is_dir() and downloaded_dir.resolve() != target_dir.resolve():
        for item in downloaded_dir.iterdir():
            _merge_move(item, target_dir / item.name)
        try:
            shutil.rmtree(ms_cache_dir)
        except Exception:
            pass

    legacy_owner_dir = target_dir / (model_id.split("/", 1)[0] if "/" in model_id else model_id)
    if legacy_owner_dir.exists() and legacy_owner_dir.is_dir() and (target_dir / "config.json").exists():
        try:
            shutil.rmtree(legacy_owner_dir)
        except Exception:
            pass
    return {
        "provider": "modelscope",
        "model_id": model_id,
        "path": str(target_dir),
        "snapshot_path": str(downloaded_dir),
    }


def _sum_modelscope_repo_size(model_id: str) -> Optional[int]:
    try:
        from modelscope.hub.api import HubApi
    except Exception:
        return None
    try:
        api = HubApi()
        files = None
        if hasattr(api, "list_model_files"):
            try:
                files = api.list_model_files(model_id, recursive=True)
            except Exception:
                files = None
        if not files:
            try:
                model = api.get_model(model_id)
            except Exception:
                model = None
            if isinstance(model, dict):
                files = model.get("model_files")
            else:
                files = getattr(model, "model_files", None)
        total = 0
        for item in files or []:
            size = getattr(item, "size", None)
            if size is None and isinstance(item, dict):
                size = item.get("size") or item.get("file_size") or item.get("file_size_bytes")
            if size:
                total += int(size)
        return total or None
    except Exception:
        return None


def get_model_total_bytes(key: str, provider: str) -> Optional[int]:
    if key not in VOXCPM_TTS_MODEL_REGISTRY:
        return None
    const_bytes = VOXCPM_TTS_MODEL_TOTAL_BYTES_BY_KEY.get(key)
    if const_bytes is not None:
        return const_bytes
    provider = (provider or "").strip().lower()
    if provider == "modelscope":
        model_id = VOXCPM_TTS_MODEL_REGISTRY[key]["ms"]
        return _sum_modelscope_repo_size(model_id)
    return None
