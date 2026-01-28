import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from modules.app_paths import uploads_dir


QWEN3_TTS_MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "tokenizer_12hz": {
        "hf": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
        "ms": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
        "local": "Qwen3-TTS-Tokenizer-12Hz",
    },
    "base_0_6b": {
        "hf": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "ms": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        "local": "Qwen3-TTS-12Hz-0.6B-Base",
    },
    "custom_0_6b": {
        "hf": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "ms": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "local": "Qwen3-TTS-12Hz-0.6B-CustomVoice",
    },
    "base_1_7b": {
        "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "ms": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "local": "Qwen3-TTS-12Hz-1.7B-Base",
    },
    "custom_1_7b": {
        "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "ms": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "local": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    },
    "voice_design_1_7b": {
        "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "ms": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        "local": "Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    },
}


@dataclass(frozen=True)
class Qwen3TTSModelStatus:
    key: str
    path: str
    exists: bool


class Qwen3TTSPathManager:
    def __init__(self) -> None:
        base = os.environ.get("QWEN_TTS_MODELS_DIR")
        if base and base.strip():
            self.base_dir = Path(base.strip())
        else:
            self.base_dir = uploads_dir() / "models" / "Qwen"

    def model_path(self, key: str) -> Path:
        if key not in QWEN3_TTS_MODEL_REGISTRY:
            raise KeyError(f"unknown_model_key: {key}")
        return self.base_dir / QWEN3_TTS_MODEL_REGISTRY[key]["local"]

    def list_status(self) -> List[Qwen3TTSModelStatus]:
        out: List[Qwen3TTSModelStatus] = []
        for key in QWEN3_TTS_MODEL_REGISTRY.keys():
            p = self.model_path(key)
            out.append(Qwen3TTSModelStatus(key=key, path=str(p), exists=p.exists()))
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

    if key == "tokenizer_12hz":
        if "preprocessor_config.json" not in files and "feature_extractor_config.json" not in files:
            missing.append("preprocessor_config.json|feature_extractor_config.json")
        has_weights = any(
            name.endswith(".safetensors") or name in {"pytorch_model.bin", "model.safetensors"}
            for name in files
        )
        if not has_weights:
            missing.append("weights(.safetensors|pytorch_model.bin)")
    else:
        has_weights = any(
            name.endswith(".safetensors") or name in {"pytorch_model.bin", "model.safetensors"}
            for name in files
        )
        if not has_weights:
            missing.append("weights(.safetensors|pytorch_model.bin)")
        if "processor_config.json" not in files and "preprocessor_config.json" not in files:
            missing.append("processor_config.json|preprocessor_config.json")

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
    if key not in QWEN3_TTS_MODEL_REGISTRY:
        raise ValueError(f"unknown_model_key: {key}")
    provider = (provider or "").strip().lower()
    if provider not in {"hf", "modelscope"}:
        raise ValueError("provider_must_be_hf_or_modelscope")

    target_dir.mkdir(parents=True, exist_ok=True)

    if provider == "hf":
        try:
            from huggingface_hub import snapshot_download
        except Exception as e:
            raise RuntimeError(f"missing_dependency:huggingface_hub:{e}")
        repo_id = QWEN3_TTS_MODEL_REGISTRY[key]["hf"]
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        return {"provider": "hf", "repo_id": repo_id, "path": str(target_dir)}

    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
    except Exception as e:
        raise RuntimeError(f"missing_dependency:modelscope:{e}")

    model_id = QWEN3_TTS_MODEL_REGISTRY[key]["ms"]
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
