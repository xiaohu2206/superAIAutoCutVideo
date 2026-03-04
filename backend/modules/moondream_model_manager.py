import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.app_paths import uploads_dir


MOONDREAM_MODEL_FILES = {
    "required": [
        "configuration.json",
        "moondream2-mmproj-f16.gguf",
        "moondream2-text-model-f16.gguf",
        "moondream2.preset.json",
    ],
    "optional": [
        "README.md",
        ".gitattributes",
    ]
}

@dataclass(frozen=True)
class MoondreamModelStatus:
    key: str
    path: str
    exists: bool
    valid: bool
    missing: List[str]
    display_name: str
    description: str


class MoondreamPathManager:
    def __init__(self) -> None:
        base = os.environ.get("MOONDREAM_MODELS_DIR")
        if base and base.strip():
            self.base_dir = Path(base.strip())
        else:
            self.base_dir = uploads_dir() / "models" / "Moondream"

    def model_path(self) -> Path:
        return self.base_dir / "Moondream2-GGUF"

    def get_status(self) -> MoondreamModelStatus:
        p = self.model_path()
        valid, missing = validate_model_dir(p)
        return MoondreamModelStatus(
            key="moondream2_gguf",
            path=str(p),
            exists=p.exists(),
            valid=valid,
            missing=missing,
            display_name="Moondream2-GGUF",
            description="Moondream2 视觉语言模型 (GGUF版)",
        )


def validate_model_dir(model_dir: Path) -> Tuple[bool, List[str]]:
    if not model_dir.exists() or not model_dir.is_dir():
        return False, ["dir_missing"]

    files = set()
    try:
        for item in model_dir.iterdir():
            if item.is_file():
                files.add(item.name)
    except Exception:
        pass
    
    missing: List[str] = []
    for name in MOONDREAM_MODEL_FILES["required"]:
        if name not in files:
            missing.append(name)

    return len(missing) == 0, missing


def download_model_snapshot(target_dir: Path, provider: str = "modelscope") -> Dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    provider = provider.lower()
    
    if provider == "hf":
        repo_id = "vikhyatk/moondream2"
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise RuntimeError("missing_dependency:huggingface_hub")
            
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
            allow_patterns=["*.json", "*.gguf", "*.md", ".gitattributes"],
        )
        return {"provider": "hf", "repo_id": repo_id, "path": str(target_dir)}
        
    else: # modelscope (default)
        model_id = "moondream/moondream2-gguf"
        try:
            from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
        except Exception as e:
            raise RuntimeError(f"missing_dependency:modelscope:{type(e).__name__}:{e}")
            
        ms_cache_dir = target_dir / ".modelscope_cache"
        ms_cache_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = ms_snapshot_download(
            model_id=model_id, 
            cache_dir=str(ms_cache_dir),
        )
        downloaded_dir = Path(str(downloaded))
        
        # Move files to target_dir
        if downloaded_dir.exists() and downloaded_dir.is_dir() and downloaded_dir.resolve() != target_dir.resolve():
            for item in downloaded_dir.iterdir():
                _merge_move(item, target_dir / item.name)
            try:
                shutil.rmtree(ms_cache_dir)
            except Exception:
                pass
                
        return {"provider": "modelscope", "model_id": model_id, "path": str(target_dir)}

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

