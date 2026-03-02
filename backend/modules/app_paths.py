import os
import sys
import json
import shutil
from pathlib import Path

def data_base_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "SuperAutoCutVideo"

def user_config_dir() -> Path:
    d = data_base_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d

def user_data_dir() -> Path:
    d = data_base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d

def app_settings_file() -> Path:
    return user_config_dir() / "app_settings.json"

def uploads_dir() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    candidates = []
    if env:
        candidates.append(Path(env))
    try:
        settings_path = app_settings_file()
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            root = str(data.get("uploads_root") or "").strip()
            if root:
                candidates.append(Path(root).expanduser())
    except Exception:
        pass
    candidates.append(data_base_dir() / "uploads")
    candidates.append(user_data_dir() / "uploads")
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    return candidates[0]

def ensure_defaults_migrated() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    repo_cfg = backend_dir / "config"
    repo_data = backend_dir / "data"
    cfg_dst = user_config_dir()
    data_dst = user_data_dir()
    for name in [
        "content_model_config.json",
        "video_model_config.json",
        "tts_config.json",
        "jianying_config.json",
        "prompts.json",
    ]:
        src = repo_cfg / name
        dst = cfg_dst / name
        try:
            if src.exists() and not dst.exists():
                shutil.copy2(str(src), str(dst))
        except Exception:
            pass
    for name in [
        "projects.json",
        "user_prompts.json",
    ]:
        src = repo_data / name
        dst = data_dst / name
        try:
            if src.exists() and not dst.exists():
                shutil.copy2(str(src), str(dst))
        except Exception:
            pass
