import importlib
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve()
    backend_dir = here.parents[3]
    repo_root = backend_dir.parent

    roots: list[Path] = []
    roots.append(repo_root)

    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        roots.insert(0, Path(meipass))

    return roots


def _ensure_qwen_tts_importable() -> None:
    try:
        importlib.import_module("qwen_tts")
        return
    except Exception:
        pass

    for root in _candidate_roots():
        p = root / ".trae" / "cache" / "Qwen3-TTS"
        if p.exists() and p.is_dir():
            sp = str(p)
            if sp not in sys.path:
                sys.path.insert(0, sp)
            try:
                importlib.import_module("qwen_tts")
                return
            except Exception:
                continue


_ensure_qwen_tts_importable()
try:
    _m = importlib.import_module("qwen_tts")
except Exception as e:
    msg = str(e)
    if "No module named 'qwen_tts'" in msg or 'No module named "qwen_tts"' in msg:
        raise ModuleNotFoundError(
            "qwen_tts_not_installed: 请安装官方依赖 `qwen-tts`（模块名为 qwen_tts），并重新安装后端依赖"
        ) from e
    if "No module named 'qwen'" in msg or 'No module named "qwen"' in msg:
        raise ModuleNotFoundError(
            "qwen_tts_bad_install: 检测到 qwen_tts 导入时缺少模块 qwen。通常是安装了非官方/不完整的 qwen_tts 包；请卸载后改装官方 `qwen-tts`"
        ) from e
    raise

Qwen3TTSModel = getattr(_m, "Qwen3TTSModel")
Qwen3TTSTokenizer = getattr(_m, "Qwen3TTSTokenizer")
VoiceClonePromptItem = getattr(_m, "VoiceClonePromptItem", None)

__all__ = ["Qwen3TTSModel", "Qwen3TTSTokenizer", "VoiceClonePromptItem"]
