import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.app_paths import uploads_dir


FUN_ASR_MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "fun_asr_nano_2512": {
        "ms": "FunAudioLLM/Fun-ASR-Nano-2512",
        "hf": "FunAudioLLM/Fun-ASR-Nano-2512",
        "local": "Fun-ASR-Nano-2512",
        "display_name": "Fun-ASR-Nano-2512",
        "languages": ["中文", "英文", "日文"],
        "description": "支持中文（含7种方言、26种口音）、英文、日文；支持歌词识别与说唱识别。",
    },
    "fun_asr_mlt_nano_2512": {
        "ms": "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
        "hf": "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
        "local": "Fun-ASR-MLT-Nano-2512",
        "display_name": "Fun-ASR-MLT-Nano-2512",
        "languages": [
            "中文",
            "英文",
            "粤语",
            "日文",
            "韩文",
            "越南语",
            "印尼语",
            "泰语",
            "马来语",
            "菲律宾语",
            "阿拉伯语",
            "印地语",
            "保加利亚语",
            "克罗地亚语",
            "捷克语",
            "丹麦语",
            "荷兰语",
            "爱沙尼亚语",
            "芬兰语",
            "希腊语",
            "匈牙利语",
            "爱尔兰语",
            "拉脱维亚语",
            "立陶宛语",
            "马耳他语",
            "波兰语",
            "葡萄牙语",
            "罗马尼亚语",
            "斯洛伐克语",
            "斯洛文尼亚语",
            "瑞典语",
        ],
        "description": "支持31种语言的多语种识别模型。",
    },
    "fsmn_vad": {
        "ms": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        "hf": None,
        "local": "fsmn-vad",
        "display_name": "fsmn-vad",
        "languages": [],
        "description": "VAD（语音活动检测）模型，用于长音频切分。",
    },
}

FUN_ASR_MODEL_TOTAL_BYTES_BY_KEY: Dict[str, int] = {
    "fun_asr_nano_2512": int(2.0 * 1024 * 1024 * 1024),
    "fun_asr_mlt_nano_2512": int(2.0 * 1024 * 1024 * 1024),
    "fsmn_vad": int(60 * 1024 * 1024),
}


@dataclass(frozen=True)
class FunASRModelStatus:
    key: str
    path: str
    exists: bool
    display_name: str
    languages: List[str]
    sources: Dict[str, str]
    description: str


class FunASRPathManager:
    def __init__(self) -> None:
        base = os.environ.get("FUN_ASR_MODELS_DIR") or os.environ.get("FUNASR_MODELS_DIR")
        if base and base.strip():
            self.base_dir = Path(base.strip())
        else:
            self.base_dir = uploads_dir() / "models" / "FunASR"

    def model_path(self, key: str) -> Path:
        if key not in FUN_ASR_MODEL_REGISTRY:
            raise KeyError(f"unknown_model_key:{key}")
        return self.base_dir / FUN_ASR_MODEL_REGISTRY[key]["local"]

    def list_status(self) -> List[FunASRModelStatus]:
        out: List[FunASRModelStatus] = []
        for key, info in FUN_ASR_MODEL_REGISTRY.items():
            p = self.model_path(key)
            out.append(
                FunASRModelStatus(
                    key=key,
                    path=str(p),
                    exists=p.exists(),
                    display_name=str(info.get("display_name") or key),
                    languages=list(info.get("languages") or []),
                    sources={
                        "hf": str(info.get("hf") or ""),
                        "ms": str(info.get("ms") or ""),
                        "local": str(info.get("local") or ""),
                    },
                    description=str(info.get("description") or ""),
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

    has_weights = any(
        name.endswith(".safetensors")
        or name.endswith(".bin")
        or name.endswith(".pt")
        or name.endswith(".pth")
        for name in files
    )
    if not has_weights:
        missing.append("weights(*.safetensors|*.bin|*.pt|*.pth)")

    if key in {"fun_asr_nano_2512", "fun_asr_mlt_nano_2512"}:
        has_cfg = any(name in {"config.json", "configuration.json", "config.yaml", "configuration.yaml"} for name in files)
        if not has_cfg:
            missing.append("config.(json|yaml)")
        # model.py 不是强制要求，有些快照不包含该文件；加载时按需处理

    if key == "fsmn_vad":
        has_cfg = any(name in {"config.yaml", "configuration.yaml", "config.json"} for name in files)
        if not has_cfg:
            missing.append("config.(yaml|json)")

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
    if key not in FUN_ASR_MODEL_REGISTRY:
        raise ValueError(f"unknown_model_key:{key}")
    provider = (provider or "").strip().lower()
    if provider not in {"hf", "modelscope"}:
        raise ValueError("provider_must_be_hf_or_modelscope")

    target_dir.mkdir(parents=True, exist_ok=True)

    if provider == "hf":
        repo_id = str(FUN_ASR_MODEL_REGISTRY[key].get("hf") or "").strip()
        if not repo_id:
            raise ValueError("hf_not_supported_for_this_model")
        try:
            from huggingface_hub import snapshot_download
        except Exception as e:
            raise RuntimeError(f"missing_dependency:huggingface_hub:{e}")
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        return {"provider": "hf", "repo_id": repo_id, "path": str(target_dir)}

    model_id = str(FUN_ASR_MODEL_REGISTRY[key].get("ms") or "").strip()
    if not model_id:
        raise ValueError("modelscope_model_id_missing")
    try:
        from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
    except Exception as e:
        raise RuntimeError(f"missing_dependency:modelscope:{e}")

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
    return {"provider": "modelscope", "model_id": model_id, "path": str(target_dir), "snapshot_path": str(downloaded_dir)}


def get_model_total_bytes(key: str, provider: str) -> Optional[int]:
    _ = provider
    if key in FUN_ASR_MODEL_TOTAL_BYTES_BY_KEY:
        return int(FUN_ASR_MODEL_TOTAL_BYTES_BY_KEY[key])
    return None
