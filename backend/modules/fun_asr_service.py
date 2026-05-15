import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import wave
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from modules.app_paths import uploads_dir
from modules.ffmpeg_utils import resolve_ffmpeg_bin, resolve_ffprobe_bin
from modules.fun_asr_acceleration import get_fun_asr_preferred_device, prepare_windows_dll_search_paths
from modules.fun_asr_model_manager import FUN_ASR_MODEL_REGISTRY, FunASRPathManager, validate_model_dir


logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_FUNASR_DIAG_LOGGED = False
_TIKTOKEN_SPECIAL_CHECK_PATCHED = False


def _patch_tiktoken_special_check_for_funasr() -> None:
    """Let FunASR encode ASR text that happens to look like special tokens."""
    global _TIKTOKEN_SPECIAL_CHECK_PATCHED
    if _TIKTOKEN_SPECIAL_CHECK_PATCHED:
        return
    try:
        from tiktoken.core import Encoding  # type: ignore

        orig_encode = Encoding.encode
        if getattr(orig_encode, "_sacv_funasr_special_patch", False):
            _TIKTOKEN_SPECIAL_CHECK_PATCHED = True
            return

        def _sacv_encode(self, text, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "allowed_special" not in kwargs and "disallowed_special" not in kwargs:
                kwargs["disallowed_special"] = ()
            return orig_encode(self, text, *args, **kwargs)

        setattr(_sacv_encode, "_sacv_funasr_special_patch", True)
        Encoding.encode = _sacv_encode  # type: ignore[assignment]
        _TIKTOKEN_SPECIAL_CHECK_PATCHED = True
    except Exception:
        return


def _env_int(name: str) -> Optional[int]:
    try:
        v = int(str(os.environ.get(name) or "").strip())
        if v >= 1:
            return v
    except Exception:
        pass
    return None


def _resolve_funasr_max_concurrency(requested: Optional[int], runtime_device: str) -> int:
    """
    Controls how many VAD segments are processed concurrently.
    - CPU: higher concurrency helps throughput.
    - CUDA: default low to reduce OOM risk unless user overrides.
    """
    env = _env_int("SACV_FUNASR_MAX_CONCURRENCY")
    if isinstance(requested, int) and requested >= 1:
        n = requested
    elif isinstance(env, int) and env >= 1:
        n = env
    else:
        cores = max(1, int(os.cpu_count() or 1))
        if str(runtime_device or "").startswith("cuda"):
            n = 1
        else:
            n = min(4, cores)
    return max(1, min(int(n), 32))


def _env_flag(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    return bool(default)


def _env_int_range(name: str, default: int, minimum: int, maximum: int) -> int:
    value = _env_int(name)
    if value is None:
        return int(default)
    return max(int(minimum), min(int(value), int(maximum)))


def _resolve_funasr_batch_size(runtime_device: str) -> int:
    default = 8 if str(runtime_device or "").startswith("cuda") else 4
    return _env_int_range("SACV_FUNASR_BATCH_SIZE", default, 1, 64)


def _json_dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        try:
            return json.dumps(str(obj), ensure_ascii=False)
        except Exception:
            return "<json_dump_failed>"


def _truncate_str(s: str, limit: int = 4000) -> str:
    if not isinstance(s, str):
        s = str(s)
    if limit <= 0:
        return ""
    if len(s) <= limit:
        return s
    return s[:limit] + "...(truncated)"


def _collect_funasr_diag(expected_adaptor: str = "Transformer") -> Dict[str, Any]:
    diag: Dict[str, Any] = {
        "expected_adaptor": expected_adaptor,
        "frozen": bool(getattr(sys, "frozen", False)),
        "meipass": getattr(sys, "_MEIPASS", None),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cwd": os.getcwd(),
    }

    try:
        diag["sys_path_head"] = sys.path[:12]
    except Exception:
        pass

    try:
        import importlib.util

        for mod in ["funasr", "modelscope", "torch", "torchaudio", "transformers", "whisper", "tiktoken"]:
            try:
                diag[f"find_spec:{mod}"] = bool(importlib.util.find_spec(mod) is not None)
            except Exception as e:
                diag[f"find_spec:{mod}"] = f"error:{type(e).__name__}:{e}"
    except Exception:
        pass

    try:
        import funasr  # type: ignore

        diag["funasr_file"] = getattr(funasr, "__file__", None)
        diag["funasr_version"] = getattr(funasr, "__version__", None)
    except Exception as e:
        diag["funasr_import_error"] = f"{type(e).__name__}:{e}"
        return diag

    try:
        from funasr.register import tables  # type: ignore

        adaptor_classes = getattr(tables, "adaptor_classes", {}) or {}
        encoder_classes = getattr(tables, "encoder_classes", {}) or {}
        model_classes = getattr(tables, "model_classes", {}) or {}
        tokenizer_classes = getattr(tables, "tokenizer_classes", {}) or {}
        diag["tables_sizes"] = {
            "adaptor_classes": len(adaptor_classes),
            "encoder_classes": len(encoder_classes),
            "model_classes": len(model_classes),
            "tokenizer_classes": len(tokenizer_classes),
        }
        diag["adaptor_present"] = bool(expected_adaptor in adaptor_classes)
        try:
            diag["adaptor_sample"] = sorted(list(adaptor_classes.keys()))[:80]
        except Exception:
            pass
        try:
            diag["model_classes_has_FunASRNano"] = bool("FunASRNano" in model_classes)
        except Exception:
            pass

        try:
            import importlib
            import pkgutil

            imported = 0
            failed: List[str] = []
            pkg_path = getattr(funasr, "__path__", None)
            if pkg_path:
                for modinfo in pkgutil.walk_packages(pkg_path, "funasr."):
                    if expected_adaptor in getattr(tables, "adaptor_classes", {}):
                        break
                    name = modinfo.name
                    low = name.lower()
                    if "adaptor" not in low and "transformer" not in low:
                        continue
                    try:
                        importlib.import_module(name)
                        imported += 1
                    except Exception as e:
                        if len(failed) < 25:
                            failed.append(f"{name}:{type(e).__name__}:{e}")
                    if imported >= 300:
                        break
            diag["registry_import_probe"] = {
                "imported": imported,
                "failed_sample": failed,
                "adaptor_present_after": bool(expected_adaptor in getattr(tables, "adaptor_classes", {})),
            }
        except Exception as e:
            diag["registry_import_probe_error"] = f"{type(e).__name__}:{e}"
    except Exception as e:
        diag["tables_import_error"] = f"{type(e).__name__}:{e}"

    return diag


def _patch_inspect_getsource_for_frozen() -> bool:
    if not bool(getattr(sys, "frozen", False)):
        return False
    try:
        import inspect

        if getattr(inspect.getsource, "__name__", "") == "_sacv_safe_getsource":
            return True

        _orig_getsource = inspect.getsource
        _orig_getsourcelines = inspect.getsourcelines

        def _sacv_safe_getsourcelines(obj):  # type: ignore[no-untyped-def]
            try:
                return _orig_getsourcelines(obj)
            except OSError as e:
                if "could not get source code" in str(e):
                    return ([], 0)
                raise

        def _sacv_safe_getsource(obj):  # type: ignore[no-untyped-def]
            try:
                return _orig_getsource(obj)
            except OSError as e:
                if "could not get source code" in str(e):
                    return ""
                raise

        inspect.getsourcelines = _sacv_safe_getsourcelines  # type: ignore[assignment]
        inspect.getsource = _sacv_safe_getsource  # type: ignore[assignment]
        return True
    except Exception:
        return False


def _ensure_dependency_ready() -> Tuple[bool, str]:
    global _FUNASR_DIAG_LOGGED
    _patch_tiktoken_special_check_for_funasr()
    try:
        patched = _patch_inspect_getsource_for_frozen()
        if patched and (bool(os.environ.get("SACV_FORCE_FUNASR_DIAG")) or not _FUNASR_DIAG_LOGGED):
            logger.warning("FUNASR_INSPECT_PATCHED_FOR_FROZEN:1")
    except Exception:
        pass
    try:
        prepare_windows_dll_search_paths()
    except Exception:
        pass
    try:
        import funasr  # type: ignore
        from funasr.register import tables  # type: ignore
    except Exception as e:
        hint = "请在后端 Python 环境安装 FunASR 依赖（例如：python -m pip install -r backend/requirements.runtime.txt）"
        return False, f"missing_dependency:funasr:{e}。{hint}"

    def _try_populate_registry(expected_adaptor: str) -> None:
        if expected_adaptor in getattr(tables, "adaptor_classes", {}):
            return
        try:
            import importlib
            import pkgutil

            def _walk_and_import(pkg_name: str, keywords: List[str], limit: int) -> None:
                try:
                    pkg = importlib.import_module(pkg_name)
                except Exception:
                    return
                pkg_path = getattr(pkg, "__path__", None)
                if not pkg_path:
                    return
                imported = 0
                failed: List[str] = []
                for modinfo in pkgutil.walk_packages(pkg_path, pkg_name + "."):
                    if expected_adaptor in getattr(tables, "adaptor_classes", {}):
                        if failed and (bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SACV_FORCE_FUNASR_DIAG"))):
                            logger.warning(f"FUNASR_REGISTRY_WALK_FAIL_SAMPLE:{_json_dumps_safe(failed[:10])}")
                        return
                    name = modinfo.name
                    low = name.lower()
                    if keywords and not any(k in low for k in keywords):
                        continue
                    try:
                        importlib.import_module(name)
                    except Exception:
                        if len(failed) < 20:
                            try:
                                import traceback as _tb

                                failed.append(f"{name}:err:{_tb.format_exc(limit=1).strip()}")
                            except Exception:
                                failed.append(f"{name}:err")
                    imported += 1
                    if imported >= limit:
                        if failed and (bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SACV_FORCE_FUNASR_DIAG"))):
                            logger.warning(f"FUNASR_REGISTRY_WALK_FAIL_SAMPLE:{_json_dumps_safe(failed[:10])}")
                        return

            _walk_and_import("funasr.models", ["adaptor", "transformer", "nano"], limit=600)
            _walk_and_import("funasr.modules", ["adaptor", "transformer"], limit=400)
            _walk_and_import("funasr.tokenizer", ["token", "spm", "bpe"], limit=200)
            if expected_adaptor in getattr(tables, "adaptor_classes", {}):
                return
            _walk_and_import("funasr.models", [], limit=1200)
        except Exception:
            return

    try:
        import importlib
        import pkgutil

        missing: List[str] = []
        for mod in ["whisper", "tiktoken"]:
            try:
                importlib.import_module(mod)
            except Exception as e:
                missing.append(f"{mod}:{type(e).__name__}:{e}")
        if missing:
            hint = "请安装 openai-whisper 与 tiktoken，并确保打包时被正确收集（PyInstaller 需包含 whisper/tiktoken 与 funasr.tokenizer 子模块）。"
            return False, f"missing_dependency:whisper_tiktoken:{'|'.join(missing)}。{hint}"

        _manual_imports = [
            "funasr.models.transformer",
            "funasr.models.conformer",
            "funasr.models.paraformer",
            "funasr.models.campplus",
            "funasr.models.fsmn",
            "funasr.models.sense_voice",
            "funasr.models.bicif_paraformer",
        ]
        manual_fail: List[str] = []
        for m in _manual_imports:
            try:
                importlib.import_module(m)
            except Exception as e:
                if len(manual_fail) < 20:
                    manual_fail.append(f"{m}:{type(e).__name__}:{e}")

        for pkg_name in ["funasr.tokenizer", "funasr.modules", "funasr.models"]:
            try:
                pkg = importlib.import_module(pkg_name)
            except Exception:
                continue
            try:
                pkg_path = getattr(pkg, "__path__", None)
                if not pkg_path:
                    continue
                for modinfo in pkgutil.iter_modules(pkg_path, pkg_name + "."):
                    try:
                        importlib.import_module(modinfo.name)
                    except Exception:
                        continue
            except Exception:
                continue

        if manual_fail and (bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SACV_FORCE_FUNASR_DIAG"))):
            logger.warning(f"FUNASR_MANUAL_IMPORT_FAIL_SAMPLE:{_json_dumps_safe(manual_fail[:10])}")
    except Exception:
        pass

    try:
        if "Transformer" not in getattr(tables, "adaptor_classes", {}):
            if bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SACV_FORCE_FUNASR_REGISTRY_PRELOAD")):
                _try_populate_registry("Transformer")
    except Exception:
        pass

    # Patch for FunASRNano if missing (often missing in funasr < 1.4)
    # We load our patched version which fixes broken imports in the site-packages version
    if "FunASRNano" not in tables.model_classes:
        try:
            # Import patched version to register it
            from .patched_fun_asr_nano import FunASRNano  # type: ignore
            logger.info("Registered patched FunASRNano class")
        except Exception as e:
            logger.warning(f"Failed to register patched FunASRNano: {type(e).__name__}:{e}", exc_info=True)
            # Fallback to SenseVoiceSmall if patch fails (though likely incompatible config)
            if "SenseVoiceSmall" in tables.model_classes:
                try:
                    tables.model_classes["FunASRNano"] = tables.model_classes["SenseVoiceSmall"]
                    logger.info("Fallback: Patched FunASRNano -> SenseVoiceSmall")
                except Exception:
                    pass

    try:
        if (bool(getattr(sys, "frozen", False)) or bool(os.environ.get("SACV_FORCE_FUNASR_DIAG"))) and not _FUNASR_DIAG_LOGGED:
            _FUNASR_DIAG_LOGGED = True
            logger.warning(f"FUNASR_PACK_DIAG_BOOT:{_json_dumps_safe(_collect_funasr_diag())}")
    except Exception:
        pass

    return True, ""


def _tmp_dir() -> Path:
    root = uploads_dir()
    d = root / "tmp" / "fun_asr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ffprobe_duration_ms(path: Path) -> Optional[int]:
    ffprobe = resolve_ffprobe_bin()
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        kwargs: Dict[str, Any] = {"stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = WIN_NO_WINDOW
        out = subprocess.check_output(cmd, **kwargs)
        s = out.decode("utf-8", errors="ignore").strip()
        if not s:
            return None
        return int(float(s) * 1000)
    except Exception:
        return None

def _ffprobe_sample_rate(path: Path) -> Optional[int]:
    ffprobe = resolve_ffprobe_bin()
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        kwargs: Dict[str, Any] = {"stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = WIN_NO_WINDOW
        out = subprocess.check_output(cmd, **kwargs)
        s = out.decode("utf-8", errors="ignore").strip()
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None


def _extract_segment_to_wav(src_audio: Path, start_ms: int, end_ms: int, out_wav: Path) -> None:
    ffmpeg = resolve_ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("missing_dependency:ffmpeg")
    start_s = max(0.0, float(start_ms) / 1000.0)
    end_s = max(start_s, float(end_ms) / 1000.0)
    dur_s = max(0.05, end_s - start_s)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_s:.3f}",
        "-t",
        f"{dur_s:.3f}",
        "-i",
        str(src_audio),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    kwargs2: Dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        kwargs2["creationflags"] = WIN_NO_WINDOW
    proc = subprocess.run(cmd, **kwargs2)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg_extract_failed")


def _is_target_funasr_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == 16000
    except Exception:
        return False


def _convert_audio_to_target_wav(src_audio: Path, out_wav: Path) -> None:
    ffmpeg = resolve_ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("missing_dependency:ffmpeg")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src_audio),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    kwargs: Dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = WIN_NO_WINDOW
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg_convert_failed")


def _ensure_target_funasr_wav(src_audio: Path, tmp_dir: Path) -> Path:
    if _is_target_funasr_wav(src_audio):
        return src_audio
    out_wav = tmp_dir / "input_16k_mono.wav"
    _convert_audio_to_target_wav(src_audio, out_wav)
    return out_wav


def _write_wav_segment_from_pcm(src_wav: Path, start_ms: int, end_ms: int, out_wav: Path) -> None:
    start_ms = max(0, int(start_ms))
    end_ms = max(start_ms, int(end_ms))
    if end_ms <= start_ms:
        raise RuntimeError("empty_wav_segment")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(src_wav), "rb") as src:
        channels = src.getnchannels()
        sample_width = src.getsampwidth()
        sample_rate = src.getframerate()
        if channels != 1 or sample_width != 2 or sample_rate != 16000:
            raise RuntimeError("source_wav_not_16k_mono_pcm16")
        total_frames = src.getnframes()
        start_frame = max(0, min(total_frames, int(start_ms * sample_rate / 1000)))
        end_frame = max(start_frame, min(total_frames, int(end_ms * sample_rate / 1000)))
        if end_frame <= start_frame:
            raise RuntimeError("empty_wav_segment")
        src.setpos(start_frame)
        frames = src.readframes(end_frame - start_frame)
        with wave.open(str(out_wav), "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(sample_width)
            dst.setframerate(sample_rate)
            dst.writeframes(frames)


def _extract_segment_to_wav_fast(src_audio: Path, start_ms: int, end_ms: int, out_wav: Path) -> None:
    try:
        _write_wav_segment_from_pcm(src_audio, start_ms, end_ms, out_wav)
    except Exception:
        _extract_segment_to_wav(src_audio, start_ms, end_ms, out_wav)


def _normalize_vad_intervals(
    intervals: List[Tuple[int, int]],
    total_ms: Optional[int],
    *,
    min_segment_ms: Optional[int] = None,
    merge_gap_ms: Optional[int] = None,
    max_segment_ms: Optional[int] = None,
) -> List[Tuple[int, int]]:
    total = int(total_ms or 0)
    min_ms = int(min_segment_ms if min_segment_ms is not None else _env_int_range("SACV_FUNASR_MIN_SEGMENT_MS", 300, 0, 30_000))
    gap_ms = int(merge_gap_ms if merge_gap_ms is not None else _env_int_range("SACV_FUNASR_MERGE_GAP_MS", 300, 0, 30_000))
    max_ms = int(max_segment_ms if max_segment_ms is not None else _env_int_range("SACV_FUNASR_MAX_SEGMENT_MS", 30_000, 1_000, 10 * 60_000))

    cleaned: List[Tuple[int, int]] = []
    for st, et in intervals:
        try:
            s = max(0, int(st))
            e = max(s, int(et))
            if total > 0:
                s = min(s, total)
                e = min(e, total)
            if e <= s:
                continue
            if (e - s) < min_ms:
                continue
            cleaned.append((s, e))
        except Exception:
            continue
    cleaned.sort(key=lambda x: (x[0], x[1]))
    if not cleaned:
        return []

    merged: List[Tuple[int, int]] = []
    cur_s, cur_e = cleaned[0]
    for s, e in cleaned[1:]:
        if s <= cur_e + gap_ms and (e - cur_s) <= max_ms:
            cur_e = max(cur_e, e)
            continue
        merged.append((cur_s, cur_e))
        cur_s, cur_e = s, e
    merged.append((cur_s, cur_e))

    out: List[Tuple[int, int]] = []
    for s, e in merged:
        if (e - s) <= max_ms:
            out.append((s, e))
            continue
        part_s = s
        while part_s < e:
            part_e = min(e, part_s + max_ms)
            if part_e - part_s >= max(1, min_ms):
                out.append((part_s, part_e))
            part_s = part_e
    return out


def _chunked(items: List[Tuple[int, int, int]], size: int) -> List[List[Tuple[int, int, int]]]:
    n = max(1, int(size))
    return [items[i : i + n] for i in range(0, len(items), n)]


def _make_default_test_wav(out_path: Path) -> Dict[str, Any]:
    import math
    import wave

    sr = 16000
    dur = 1.2
    freq = 440.0
    amp = 0.15
    n = int(sr * dur)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            s = amp * math.sin(2.0 * math.pi * freq * (i / sr))
            v = int(max(-1.0, min(1.0, s)) * 32767)
            frames.extend(int(v).to_bytes(2, "little", signed=True))
        wf.writeframes(bytes(frames))
    return {"sample_rate": sr, "duration": dur}


def _normalize_test_language(language: Optional[str]) -> str:
    l = (language or "").strip().lower()
    if not l:
        return "zh"
    l2 = l.replace("_", "-")
    if any(x in l2 for x in ["粤语", "yue", "cantonese", "zh-hk", "zh-hant-hk"]):
        return "yue"
    if any(x in l2 for x in ["中文", "汉语", "普通话", "zh", "chinese", "zh-cn", "zh-hans"]):
        return "zh"
    if any(x in l2 for x in ["英文", "英语", "en", "english"]):
        return "en"
    if any(x in l2 for x in ["日文", "日语", "ja", "japanese"]):
        return "ja"
    if any(x in l2 for x in ["韩文", "韩语", "ko", "korean"]):
        return "ko"
    if any(x in l2 for x in ["法文", "法语", "fr", "french"]):
        return "fr"
    if any(x in l2 for x in ["德文", "德语", "de", "german"]):
        return "de"
    if any(x in l2 for x in ["西班牙", "西语", "es", "spanish"]):
        return "es"
    return l2


def _default_test_text(lang_key: str) -> str:
    texts = {
        "zh": "你好，这是一段中文测试语音。",
        "yue": "你好，呢段係粤语测试语音。",
        "en": "Hello, this is an English test speech.",
        "ja": "こんにちは、これは日本語のテスト音声です。",
        "ko": "안녕하세요, 이것은 한국어 테스트 음성입니다.",
        "fr": "Bonjour, ceci est un message de test en français.",
        "de": "Hallo, dies ist eine deutsche Testaufnahme.",
        "es": "Hola, este es un mensaje de prueba en español.",
    }
    return texts.get(lang_key, texts["zh"])


def _default_test_voice(lang_key: str) -> str:
    voices = {
        "zh": "zh-CN-XiaoxiaoNeural",
        "yue": "zh-HK-HiuGaaiNeural",
        "en": "en-US-JennyNeural",
        "ja": "ja-JP-NanamiNeural",
        "ko": "ko-KR-SunHiNeural",
        "fr": "fr-FR-DeniseNeural",
        "de": "de-DE-KatjaNeural",
        "es": "es-ES-ElviraNeural",
    }
    return voices.get(lang_key, voices["zh"])


async def _ensure_default_test_audio(language: str) -> Tuple[Path, Dict[str, Any]]:
    lang_key = _normalize_test_language(language)
    out_dir = _tmp_dir() / "default_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = out_dir / f"asr_test_{lang_key}.mp3"
    try:
        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            return mp3_path, {"format": "MP3"}
    except Exception:
        pass
    try:
        from modules.edge_tts_service import edge_tts_service

        text = _default_test_text(lang_key)
        voice_id = _default_test_voice(lang_key)
        res = await edge_tts_service.synthesize(
            text=text,
            voice_id=voice_id,
            speed_ratio=None,
            out_path=mp3_path,
        )
        if res.get("success"):
            meta: Dict[str, Any] = {"format": "MP3"}
            if res.get("duration") is not None:
                meta["duration"] = res.get("duration")
            return mp3_path, meta
    except Exception as e:
        try:
            logger.warning(f"default_test_audio_edge_tts_failed: {e}")
        except Exception:
            pass
    wav_path = out_dir / f"asr_test_{lang_key}.wav"
    meta2 = _make_default_test_wav(wav_path)
    meta2["format"] = "WAV"
    return wav_path, meta2


def _parse_vad_intervals(res: Any) -> List[Tuple[int, int]]:
    if isinstance(res, list) and res:
        first = res[0]
        if isinstance(first, dict):
            val = first.get("value")
            if isinstance(val, list) and val and all(isinstance(x, (list, tuple)) and len(x) >= 2 for x in val):
                out: List[Tuple[int, int]] = []
                for x in val:
                    try:
                        st = int(float(x[0]))
                        et = int(float(x[1]))
                        if et > st:
                            out.append((st, et))
                    except Exception:
                        continue
                return out
            segs = first.get("segments")
            if isinstance(segs, list):
                out2: List[Tuple[int, int]] = []
                for it in segs:
                    if not isinstance(it, dict):
                        continue
                    st = it.get("start") or it.get("start_ms") or it.get("start_time")
                    et = it.get("end") or it.get("end_ms") or it.get("end_time")
                    try:
                        st_i = int(float(st))
                        et_i = int(float(et))
                        if et_i > st_i:
                            out2.append((st_i, et_i))
                    except Exception:
                        continue
                return out2
    return []


class FunASRService:
    def __init__(self) -> None:
        self._asr_key: Optional[str] = None
        self._asr_model_path: Optional[str] = None
        self._asr_model: Any = None
        self._vad_model_path: Optional[str] = None
        self._vad_model: Any = None
        self._load_lock = asyncio.Lock()
        self._runtime_device: str = "cpu"
        self._last_device_error: Optional[str] = None
        self._warmup_signature: Optional[str] = None

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "loaded": self._asr_model is not None,
            "asr_key": self._asr_key,
            "asr_path": self._asr_model_path,
            "vad_path": self._vad_model_path,
            "device": self._runtime_device,
            "last_device_error": self._last_device_error,
            "batch_size": _resolve_funasr_batch_size(self._runtime_device),
            "max_concurrency": _resolve_funasr_max_concurrency(None, self._runtime_device),
            "warmup_done": bool(self._warmup_signature),
        }

    def _normalize_device(self, device: Optional[str]) -> str:
        d = (device or "").strip()
        if not d:
            return ""
        if d == "cuda":
            return "cuda:0"
        return d

    def _safe_extract_zip(self, zip_path: Path, dest_dir: Path) -> None:
        base = dest_dir.resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for info in zf.infolist():
                name = str(info.filename or "")
                if not name or name.endswith("/"):
                    continue
                name = name.replace("\\", "/")
                if name.startswith("/") or name.startswith("../") or "/../" in name:
                    raise RuntimeError(f"unsafe_zip_entry:{name}")
                target = (dest_dir / name).resolve()
                try:
                    target.relative_to(base)
                except Exception:
                    raise RuntimeError(f"unsafe_zip_entry:{name}")
                zf.extract(info, str(dest_dir))

    def _maybe_extract_local_zip(self, key: str, model_dir: Path) -> bool:
        if model_dir.exists():
            return False
        zip_path = model_dir.parent / f"{model_dir.name}.zip"
        if not zip_path.exists() or not zip_path.is_file():
            return False
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                roots = set()
                for name in zf.namelist():
                    n = str(name or "").replace("\\", "/")
                    if not n or n.endswith("/"):
                        continue
                    parts = [p for p in n.split("/") if p]
                    if parts:
                        roots.add(parts[0])
                if len(roots) == 1 and next(iter(roots)) == model_dir.name:
                    self._safe_extract_zip(zip_path, model_dir.parent)
                else:
                    self._safe_extract_zip(zip_path, model_dir)
            return model_dir.exists()
        except Exception as e:
            try:
                logger.warning(f"funasr_zip_extract_failed: key={key} zip={zip_path} err={e}")
            except Exception:
                pass
            return False

    def _resolve_model_dir(self, key: str) -> Path:
        pm = FunASRPathManager()
        p = pm.model_path(key)
        ok, missing = validate_model_dir(key, p)
        if ok:
            return p
        if "dir_missing" in missing:
            extracted = self._maybe_extract_local_zip(key, p)
            if extracted:
                ok2, missing2 = validate_model_dir(key, p)
                if ok2:
                    return p
                missing = missing2
        missing_s = ",".join(missing) if missing else ""
        raise RuntimeError(f"model_invalid_or_missing:{key}|path={p}|missing={missing_s}")

    async def _load_models(self, asr_key: str, device: Optional[str] = None) -> None:
        async with self._load_lock:
            try:
                prepare_windows_dll_search_paths()
            except Exception:
                pass

            ok_dep, err = _ensure_dependency_ready()
            if not ok_dep:
                raise RuntimeError(err)

            explicit_device = bool((device or "").strip())
            requested_device = self._normalize_device(device)
            if not requested_device:
                requested_device = self._normalize_device(get_fun_asr_preferred_device())
            if not explicit_device and requested_device.startswith("cuda") and self._runtime_device == "cpu" and self._last_device_error:
                requested_device = "cpu"

            asr_dir = self._resolve_model_dir(asr_key)
            asr_path = str(asr_dir)
            try:
                asr_has_remote = (asr_dir / "model.py").exists()
            except Exception:
                asr_has_remote = False

            vad_dir = None
            try:
                vad_dir = self._resolve_model_dir("fsmn_vad")
            except Exception:
                vad_dir = None
            vad_path = str(vad_dir) if vad_dir is not None else "fsmn-vad"

            if (
                self._asr_model is not None
                and self._asr_key == asr_key
                and self._asr_model_path == asr_path
                and self._vad_model is not None
                and self._vad_model_path == vad_path
                and self._runtime_device == requested_device
            ):
                return

            try:
                from funasr import AutoModel  # type: ignore
            except Exception as e:
                raise RuntimeError(f"missing_dependency:funasr_import_failed:{e}")

            def _load_asr(target_device: str):
                if asr_has_remote:
                    return AutoModel(
                        model=asr_path,
                        trust_remote_code=True,
                        remote_code="./model.py",
                        device=target_device,
                        hub="modelscope",
                    )
                return AutoModel(
                    model=asr_path,
                    device=target_device,
                    hub="modelscope",
                )

            def _load_vad(target_device: str):
                return AutoModel(
                    model=vad_path,
                    device=target_device,
                    hub="modelscope",
                )

            loop = asyncio.get_running_loop()
            cuda_error: Optional[str] = None
            try:
                asr_model = await loop.run_in_executor(None, _load_asr, requested_device)
                vad_model = await loop.run_in_executor(None, _load_vad, requested_device)
                actual_device = requested_device
            except Exception as e:
                err_load = f"funasr_model_load_failed:{type(e).__name__}:{e}"
                try:
                    msg_e = str(e)
                    if "missing_dependency:funasr_registry:" in msg_e or "could not get source code" in msg_e:
                        diag = _collect_funasr_diag(expected_adaptor="Transformer")
                        diag_s = _truncate_str(_json_dumps_safe(diag), 6000)
                        logging.getLogger("modules.fun_asr_service").warning(f"FUNASR_PACK_DIAG_ON_FAIL:{diag_s}")
                        err_load = f"{err_load}|diag={diag_s}"
                except Exception:
                    pass
                if requested_device.startswith("cuda") and not explicit_device:
                    cuda_error = err_load
                    try:
                        logging.getLogger("modules.fun_asr_service").warning(
                            f"FunASR 加载到 {requested_device} 失败，将回退 CPU：{type(e).__name__}:{e}",
                            exc_info=True,
                        )
                    except Exception:
                        pass
                    try:
                        asr_model = await loop.run_in_executor(None, _load_asr, "cpu")
                        vad_model = await loop.run_in_executor(None, _load_vad, "cpu")
                        actual_device = "cpu"
                    except Exception as e2:
                        err2 = f"funasr_model_load_failed:{type(e2).__name__}:{e2}"
                        try:
                            msg_e2 = str(e2)
                            if "missing_dependency:funasr_registry:" in msg_e2 or "could not get source code" in msg_e2:
                                diag2 = _collect_funasr_diag(expected_adaptor="Transformer")
                                diag2_s = _truncate_str(_json_dumps_safe(diag2), 6000)
                                logging.getLogger("modules.fun_asr_service").warning(f"FUNASR_PACK_DIAG_ON_FAIL_CPU:{diag2_s}")
                                err2 = f"{err2}|diag={diag2_s}"
                        except Exception:
                            pass
                        raise RuntimeError(err2)
                else:
                    raise RuntimeError(err_load)

            self._asr_key = asr_key
            self._asr_model_path = asr_path
            self._asr_model = asr_model
            self._vad_model_path = vad_path
            self._vad_model = vad_model
            self._runtime_device = actual_device
            self._last_device_error = cuda_error
            self._warmup_signature = None
            try:
                logging.getLogger("modules.fun_asr_service").info(
                    f"FunASR loaded: key={asr_key} path={asr_path} device={actual_device} vad={vad_path}"
                )
            except Exception:
                pass
            await self._warmup_asr_model(asr_key, actual_device)

    async def _warmup_asr_model(self, asr_key: str, device: str) -> None:
        if not _env_flag("SACV_FUNASR_WARMUP", True):
            return
        signature = f"{asr_key}|{device}|{self._asr_model_path}"
        if self._warmup_signature == signature:
            return
        m_asr = self._asr_model
        if m_asr is None:
            return
        warmup_path = _tmp_dir() / "warmup_16k_mono.wav"
        try:
            if not warmup_path.exists() or warmup_path.stat().st_size <= 44:
                _make_default_test_wav(warmup_path)

            def _run_warmup() -> Any:
                return m_asr.generate(input=[str(warmup_path)], cache={}, batch_size=1, itn=True)

            await asyncio.get_running_loop().run_in_executor(None, _run_warmup)
            self._warmup_signature = signature
            logger.info("FunASR warmup done: key=%s device=%s", asr_key, device)
        except Exception as e:
            logger.warning("FunASR warmup skipped: key=%s device=%s err=%s", asr_key, device, e)

    async def transcribe_to_utterances(
        self,
        audio_path: Path,
        model_key: str,
        language: str = "中文",
        itn: bool = True,
        hotwords: Optional[List[str]] = None,
        device: Optional[str] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        max_concurrency: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        await self._load_models(asr_key=model_key, device=device)
        m_asr = cast(Any, self._asr_model)
        m_vad = cast(Any, self._vad_model)
        if m_asr is None or m_vad is None:
            raise RuntimeError("funasr_model_not_loaded")

        def report(p: int, msg: str) -> None:
            if on_progress:
                try:
                    on_progress(int(p), str(msg))
                except Exception:
                    pass

        tmp_fast = _tmp_dir() / f"job_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        tmp_fast.mkdir(parents=True, exist_ok=True)
        utterances_fast: List[Dict[str, Any]] = []
        try:
            loop = asyncio.get_running_loop()
            report(1, "FunASR: preparing 16k mono audio")
            normalized_audio = await loop.run_in_executor(None, _ensure_target_funasr_wav, audio_path, tmp_fast)

            report(4, "FunASR: VAD segmenting")

            def _run_vad_fast() -> Any:
                return m_vad.generate(input=[str(normalized_audio)], cache={}, batch_size=1)

            res_vad_fast = await loop.run_in_executor(None, _run_vad_fast)
            raw_intervals = _parse_vad_intervals(res_vad_fast)
            dur_ms = _ffprobe_duration_ms(normalized_audio) or _ffprobe_duration_ms(audio_path) or 0
            if not raw_intervals:
                raw_intervals = [(0, dur_ms if dur_ms > 0 else 30_000)]

            intervals_fast = _normalize_vad_intervals(raw_intervals, dur_ms)
            if not intervals_fast:
                intervals_fast = [(0, dur_ms if dur_ms > 0 else 30_000)]
            if len(intervals_fast) > 2000:
                intervals_fast = intervals_fast[:2000]

            eff_batch_size = _resolve_funasr_batch_size(str(self._runtime_device or "cpu"))
            eff_concurrency = _resolve_funasr_max_concurrency(max_concurrency, str(self._runtime_device or "cpu"))
            indexed_intervals = [(i, int(st), int(et)) for i, (st, et) in enumerate(intervals_fast, start=1)]
            batches = _chunked(indexed_intervals, eff_batch_size)
            sem = asyncio.Semaphore(eff_concurrency)
            total = len(indexed_intervals)
            completed = 0
            completed_lock = asyncio.Lock()

            report(
                8,
                f"FunASR: VAD got {len(raw_intervals)} raw / {len(intervals_fast)} normalized segments, batch={eff_batch_size}, concurrency={eff_concurrency}",
            )

            async def _process_batch(batch_no: int, batch: List[Tuple[int, int, int]]) -> List[Dict[str, Any]]:
                nonlocal completed
                async with sem:
                    def _prepare_batch_segments() -> List[Tuple[int, int, int, Path]]:
                        out: List[Tuple[int, int, int, Path]] = []
                        batch_dir = tmp_fast / f"batch_{batch_no:04d}"
                        batch_dir.mkdir(parents=True, exist_ok=True)
                        for idx, st, et in batch:
                            seg_path = batch_dir / f"seg_{idx:05d}.wav"
                            _extract_segment_to_wav_fast(normalized_audio, int(st), int(et), seg_path)
                            out.append((idx, st, et, seg_path))
                        return out

                    seg_items = await loop.run_in_executor(None, _prepare_batch_segments)
                    inputs = [str(item[3]) for item in seg_items]

                    def _run_asr_batch(paths: List[str]) -> Any:
                        return m_asr.generate(
                            input=paths,
                            cache={},
                            batch_size=max(1, min(eff_batch_size, len(paths))),
                            hotwords=hotwords or [],
                            language=language,
                            itn=bool(itn),
                        )

                    try:
                        res_asr = await loop.run_in_executor(None, _run_asr_batch, inputs)
                    except Exception:
                        if len(inputs) <= 1:
                            raise
                        res_asr = []
                        for one in inputs:
                            single_res = await loop.run_in_executor(None, _run_asr_batch, [one])
                            if isinstance(single_res, list):
                                res_asr.extend(single_res)
                            else:
                                res_asr.append(single_res)

                    results = res_asr if isinstance(res_asr, list) else [res_asr]
                    parsed: List[Dict[str, Any]] = []
                    for pos, item in enumerate(seg_items):
                        _idx, st, et, _path = item
                        text = ""
                        try:
                            if pos < len(results) and isinstance(results[pos], dict):
                                text = str(results[pos].get("text") or "").strip()
                        except Exception:
                            text = ""
                        if text:
                            parsed.append({"start_time": int(st), "end_time": int(et), "text": text})

                    async with completed_lock:
                        completed += len(batch)
                        pct = min(90, 10 + int(completed / max(1, total) * 78))
                    report(pct, f"FunASR: batch recognizing {completed}/{total} segments")
                    return parsed

            tasks = [asyncio.create_task(_process_batch(batch_no, batch)) for batch_no, batch in enumerate(batches, start=1)]
            for fut in asyncio.as_completed(tasks):
                utterances_fast.extend(await fut or [])
        finally:
            try:
                if tmp_fast.exists():
                    shutil.rmtree(tmp_fast)
            except Exception:
                pass

        report(95, "FunASR: recognition done")
        utterances_fast.sort(key=lambda x: (int(x.get("start_time") or 0), int(x.get("end_time") or 0)))
        return utterances_fast

        report(1, "开始 VAD 切分")

        def _run_vad() -> Any:
            return m_vad.generate(input=[str(audio_path)], cache={}, batch_size=1)

        res_vad = await asyncio.get_running_loop().run_in_executor(None, _run_vad)
        intervals = _parse_vad_intervals(res_vad)
        if not intervals:
            dur_ms = _ffprobe_duration_ms(audio_path) or 0
            if dur_ms <= 0:
                dur_ms = 30_000
            intervals = [(0, dur_ms)]

        if len(intervals) > 2000:
            intervals = intervals[:2000]

        report(8, f"切分得到 {len(intervals)} 段")

        tmp = _tmp_dir() / f"job_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        tmp.mkdir(parents=True, exist_ok=True)

        utterances: List[Dict[str, Any]] = []
        eff_concurrency = _resolve_funasr_max_concurrency(max_concurrency, str(self._runtime_device or "cpu"))
        sem = asyncio.Semaphore(eff_concurrency)
        try:
            total = len(intervals)
            completed = 0
            completed_lock = asyncio.Lock()
            loop = asyncio.get_running_loop()

            async def _process_one(idx: int, st: int, et: int) -> Optional[Dict[str, Any]]:
                nonlocal completed
                async with sem:
                    seg_name = f"seg_{idx:04d}.wav"
                    seg_path = tmp / seg_name
                    await loop.run_in_executor(None, _extract_segment_to_wav, audio_path, int(st), int(et), seg_path)

                    def _run_asr() -> Any:
                        return m_asr.generate(
                            input=[str(seg_path)],
                            cache={},
                            batch_size=1,
                            hotwords=hotwords or [],
                            language=language,
                            itn=bool(itn),
                        )

                    res_asr = await loop.run_in_executor(None, _run_asr)
                    text = ""
                    try:
                        if isinstance(res_asr, list) and res_asr and isinstance(res_asr[0], dict):
                            text = str(res_asr[0].get("text") or "").strip()
                    except Exception:
                        text = ""

                    async with completed_lock:
                        completed += 1
                        pct = min(90, 10 + int(completed / max(1, total) * 70))
                    report(pct, f"识别中 {completed}/{total}（并发={eff_concurrency}）")

                    if not text:
                        return None
                    return {"start_time": int(st), "end_time": int(et), "text": text}

            tasks = [asyncio.create_task(_process_one(i, int(st), int(et))) for i, (st, et) in enumerate(intervals, start=1)]
            for fut in asyncio.as_completed(tasks):
                item = await fut
                if item:
                    utterances.append(item)
        finally:
            try:
                if tmp.exists():
                    for it in tmp.iterdir():
                        try:
                            if it.is_file() or it.is_symlink():
                                it.unlink()
                        except Exception:
                            pass
                    try:
                        tmp.rmdir()
                    except Exception:
                        pass
            except Exception:
                pass

        report(95, "识别完成")
        utterances.sort(key=lambda x: (int(x.get("start_time") or 0), int(x.get("end_time") or 0)))
        return utterances

    async def run_default_test(
        self,
        model_key: str,
        device: Optional[str] = None,
        language: str = "中文",
        itn: bool = True,
    ) -> Dict[str, Any]:
        if model_key not in FUN_ASR_MODEL_REGISTRY:
            raise ValueError("unknown_model_key")
        audio_path, meta_seed = await _ensure_default_test_audio(language)
        sr = meta_seed.get("sample_rate") or _ffprobe_sample_rate(audio_path)
        duration = meta_seed.get("duration")
        if duration is None:
            dur_ms = _ffprobe_duration_ms(audio_path)
            duration = (float(dur_ms) / 1000.0) if dur_ms is not None else None
        fmt = str(meta_seed.get("format") or audio_path.suffix.lstrip(".").upper() or "AUDIO")
        meta: Dict[str, Any] = {"sample_rate": sr, "duration": duration, "format": fmt}
        utterances = await self.transcribe_to_utterances(
            audio_path=audio_path,
            model_key=model_key,
            device=device,
            language=language,
            itn=itn,
            hotwords=[],
        )
        text = " ".join((u.get("text") or "").strip() for u in utterances if (u.get("text") or "").strip()).strip()
        return {"success": True, "text": text, "utterances": utterances, "audio_path": str(audio_path), "audio_meta": meta}


fun_asr_service = FunASRService()
