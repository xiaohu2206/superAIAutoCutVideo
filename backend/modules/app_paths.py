"""
应用数据与 uploads 根路径解析。

设计以 Windows（含 Tauri / PyInstaller 打包）为主路径：
- 默认持久化目录：%LOCALAPPDATA%\\SuperAutoCutVideo\\uploads
- 支持盘符路径、UNC、以及从设置/环境变量传入的 %VAR% 展开
非 Windows 仍可用，但优先级与测试以 Windows 为准。
"""
import os
import sys
import json
import shutil
from pathlib import Path
from typing import Optional, List

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
    # 用户可能在设置里填写 %LOCALAPPDATA%\\... 等形式
    if "%" in s:
        try:
            s = os.path.expandvars(s)
        except Exception:
            pass
    return s


def _is_windows_abs_path_str(s: str) -> bool:
    """判断是否为 Windows 绝对路径（盘符+根 或 UNC）。不含 C:relative 这类相对盘符路径。"""
    if os.name != "nt" or not s:
        return False
    t = s.strip()
    if t.startswith("\\\\"):
        return True
    # C:\ 或 C:/ 为绝对；单独 C:foo 为相对当前目录，不按绝对路径短路
    if len(t) >= 3 and t[1] == ":" and t[2] in "/\\":
        return True
    return False


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

def _looks_like_unix_only_abs_path(s: str) -> bool:
    """Windows 上排除从 macOS/Linux 同步来的 POSIX 绝对路径，避免误解析为当前盘符根下路径。"""
    t = str(s or "").strip().replace("\\", "/")
    if not t.startswith("/") or t.startswith("//"):
        return False
    return t.startswith(("/Users/", "/home/", "/Volumes/", "/private/", "/var/", "/tmp/", "/opt/", "/usr/"))


def uploads_dir(include_legacy_repo_uploads: bool = True) -> Path:
    candidates = uploads_roots_for_resolve(include_legacy_repo_uploads=include_legacy_repo_uploads)
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    return candidates[0]


def uploads_roots_for_resolve(include_legacy_repo_uploads: bool = True) -> List[Path]:
    roots: List[Path] = []
    seen: set[str] = set()

    def add(p: Optional[Path]) -> None:
        if p is None:
            return
        try:
            pp = Path(p).expanduser()
            key = str(pp)
            if key not in seen:
                seen.add(key)
                roots.append(pp)
        except Exception:
            return

    env = normalize_path_str(os.environ.get("SACV_UPLOADS_DIR") or "")
    if env:
        add(Path(env))
    try:
        settings_path = app_settings_file()
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            root = normalize_path_str(str(data.get("uploads_root") or ""))
            if root:
                if os.name == "nt" and _looks_like_unix_only_abs_path(root):
                    pass
                else:
                    add(Path(root))
    except Exception:
        pass
    # 默认：…/SuperAutoCutVideo/uploads，其次 …/SuperAutoCutVideo/data/uploads（Windows 下顺序同上）
    add(data_base_dir() / "uploads")
    add(user_data_dir() / "uploads")
    if include_legacy_repo_uploads:
        backend_dir = Path(__file__).resolve().parents[1]
        add(backend_dir.parent / "uploads")
    return roots


def to_uploads_web_path(p: Path) -> str:
    path = Path(p)
    for root in uploads_roots_for_resolve():
        try:
            r = root.resolve()
            try:
                rp = path.resolve(strict=False)
            except TypeError:
                rp = path.resolve()
            rel = rp.relative_to(r)
            return "/uploads/" + str(rel).replace("\\", "/")
        except Exception:
            continue
    raise ValueError(f"Path is outside uploads roots: {path}")


def resolve_uploads_path(path_str: str) -> Path:
    s = normalize_path_str(str(path_str or "").strip())
    if not s:
        return Path("")

    # Windows：已是绝对路径（含 UNC）时直接返回，避免被当作「以 / 开头的相对路径」处理
    if _is_windows_abs_path_str(s):
        try:
            return Path(s)
        except Exception:
            return Path("")

    s_norm = s.replace("\\", "/")
    if s_norm.lower().startswith("file:"):
        s_norm = s_norm.split("://", 1)[-1].lstrip("/")
        if len(s_norm) > 1 and s_norm[1] == ":":
            s_norm = s_norm[:2] + "/" + s_norm[2:]

    roots = uploads_roots_for_resolve()

    def first_existing_or_default(rel: str) -> Path:
        rel_clean = rel.lstrip("/")
        candidates = [base / rel_clean for base in roots]
        for c in candidates:
            try:
                if c.exists():
                    return c
            except Exception:
                pass
        return candidates[0] if candidates else Path(rel_clean)

    if s_norm.startswith("/uploads/") or s_norm == "/uploads":
        rel = s_norm[len("/uploads/"):] if s_norm.startswith("/uploads/") else ""
        return first_existing_or_default(rel)

    if s_norm.lower().startswith("uploads/"):
        rel = s_norm[len("uploads/"):]
        return first_existing_or_default(rel)

    if any(s_norm.startswith(prefix) for prefix in ("videos/", "subtitles/", "audios/", "analyses/", "jianying_drafts/", "tmp/", "models/")):
        return first_existing_or_default(s_norm)

    try:
        p = Path(s)
        if p.is_absolute():
            return p
    except Exception:
        pass

    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    if s_norm.startswith("/"):
        return project_root / s_norm[1:]
    return Path(s)


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
