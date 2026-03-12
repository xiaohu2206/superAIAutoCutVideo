import os
import sys
import json
import shutil
from pathlib import Path

def _strip_invisible_chars(s: str) -> str:
    s = s.replace("\ufeff", "")
    s = s.replace("\u200b", "")
    s = s.replace("\u00ad", "")
    return s


def normalize_path_str(path_str: str) -> str:
    s = _strip_invisible_chars(str(path_str or "")).strip()
    if not s:
        return ""
    if os.name != "nt":
        return s
    s = s.replace("%5C", "\\").replace("%5c", "\\")
    s = s.replace("%2F", "/").replace("%2f", "/")
    if "%%" in s and ("\\" not in s and "/" not in s):
        s = s.replace("%%", "\\")
    if len(s) >= 2 and s[1] == ":" and "%" in s and ("Users" in s or "AppData" in s or "SuperAutoCutVideo" in s):
        s = s.replace("%", "\\")
    if "%" in s and ("\\" not in s and "/" not in s) and len(s) >= 2 and s[1] == ":":
        s = s.replace("%", "\\")
    if len(s) >= 3 and s[1] == ":" and s[2] not in ("\\", "/"):
        s = s[:2] + "\\" + s[2:]
    return s


def windows_local_appdata_dir() -> Path:
    raw = normalize_path_str(os.environ.get("LOCALAPPDATA") or "")
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def data_base_dir() -> Path:
    if os.name == "nt":
        base = windows_local_appdata_dir()
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
    env = normalize_path_str(os.environ.get("SACV_UPLOADS_DIR") or "")
    candidates = []
    if env:
        candidates.append(Path(env).expanduser())
    try:
        settings_path = app_settings_file()
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            root = normalize_path_str(str(data.get("uploads_root") or ""))
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
