import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from modules.app_paths import uploads_dir
from modules.fun_asr_acceleration import get_fun_asr_preferred_device
from modules.fun_asr_model_manager import FUN_ASR_MODEL_REGISTRY, FunASRPathManager, validate_model_dir


logger = logging.getLogger(__name__)


def _find_ffmpeg_bin(name: str) -> Optional[str]:
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        try:
            p = Path(env_path)
            if p.exists():
                return str(p)
        except Exception:
            pass
    env_dir = os.environ.get("FFMPEG_DIR") or os.environ.get("FFMPEG_HOME")
    if env_dir:
        try:
            p = Path(env_dir) / name
            if p.exists():
                return str(p)
        except Exception:
            pass
    hit = shutil.which(name)
    if hit:
        return hit
    candidates: List[Path] = []
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "resources" / name)
        candidates.append(exe_dir / name)
    except Exception:
        pass
    try:
        root = Path(__file__).resolve().parents[2]
        candidates.append(root / "src-tauri" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "debug" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "release" / "resources" / name)
    except Exception:
        pass
    install_dir = os.environ.get("SACV_INSTALL_DIR")
    if install_dir:
        try:
            candidates.append(Path(install_dir) / "resources" / name)
        except Exception:
            pass
    try:
        here = Path(__file__).resolve()
        candidates.append(here.parent.parent / "resources" / name)
    except Exception:
        pass
    try:
        candidates.append(Path.cwd() / "resources" / name)
    except Exception:
        pass
    try:
        if os.name == "nt":
            candidates.append(Path("C:/Program Files/ffmpeg/bin") / name)
            candidates.append(Path("C:/ffmpeg/bin") / name)
            candidates.append(Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / name)
            candidates.append(Path("C:/ProgramData/chocolatey/bin") / name)
    except Exception:
        pass
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            continue
    return None


def _find_ffmpeg() -> Optional[str]:
    return _find_ffmpeg_bin("ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def _find_ffprobe() -> Optional[str]:
    return _find_ffmpeg_bin("ffprobe.exe" if os.name == "nt" else "ffprobe")


def _ensure_dependency_ready() -> Tuple[bool, str]:
    try:
        import funasr  # type: ignore
        from funasr.register import tables  # type: ignore
    except Exception as e:
        return False, f"missing_dependency:funasr:{e}"

    # Patch for FunASRNano if missing (often missing in funasr < 1.4)
    # We load our patched version which fixes broken imports in the site-packages version
    if "FunASRNano" not in tables.model_classes:
        try:
            # Import patched version to register it
            from .patched_fun_asr_nano import FunASRNano  # type: ignore
            logger.info("Registered patched FunASRNano class")
        except Exception as e:
            logger.warning(f"Failed to register patched FunASRNano: {e}")
            # Fallback to SenseVoiceSmall if patch fails (though likely incompatible config)
            if "SenseVoiceSmall" in tables.model_classes:
                try:
                    tables.model_classes["FunASRNano"] = tables.model_classes["SenseVoiceSmall"]
                    logger.info("Fallback: Patched FunASRNano -> SenseVoiceSmall")
                except Exception:
                    pass

    return True, ""


def _tmp_dir() -> Path:
    root = uploads_dir()
    d = root / "tmp" / "fun_asr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ffprobe_duration_ms(path: Path) -> Optional[int]:
    ffprobe = _find_ffprobe()
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
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        s = out.decode("utf-8", errors="ignore").strip()
        if not s:
            return None
        return int(float(s) * 1000)
    except Exception:
        return None

def _ffprobe_sample_rate(path: Path) -> Optional[int]:
    ffprobe = _find_ffprobe()
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
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        s = out.decode("utf-8", errors="ignore").strip()
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None


def _extract_segment_to_wav(src_audio: Path, start_ms: int, end_ms: int, out_wav: Path) -> None:
    ffmpeg = _find_ffmpeg()
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
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg_extract_failed")


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

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "loaded": self._asr_model is not None,
            "asr_key": self._asr_key,
            "asr_path": self._asr_model_path,
            "vad_path": self._vad_model_path,
            "device": self._runtime_device,
            "last_device_error": self._last_device_error,
        }

    def _normalize_device(self, device: Optional[str]) -> str:
        d = (device or "").strip()
        if not d:
            return ""
        if d == "cuda":
            return "cuda:0"
        return d

    def _resolve_model_dir(self, key: str) -> Path:
        pm = FunASRPathManager()
        p = pm.model_path(key)
        ok, _ = validate_model_dir(key, p)
        if ok:
            return p
        raise RuntimeError(f"model_invalid_or_missing:{key}|path={p}")

    async def _load_models(self, asr_key: str, device: Optional[str] = None) -> None:
        async with self._load_lock:
            ok_dep, err = _ensure_dependency_ready()
            if not ok_dep:
                raise RuntimeError(err)

            requested_device = self._normalize_device(device)
            if not requested_device:
                requested_device = self._normalize_device(get_fun_asr_preferred_device())

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

            def _load_asr():
                if asr_has_remote:
                    return AutoModel(
                        model=asr_path,
                        trust_remote_code=True,
                        remote_code="./model.py",
                        device=requested_device,
                        hub="modelscope",
                    )
                return AutoModel(
                    model=asr_path,
                    device=requested_device,
                    hub="modelscope",
                )

            def _load_vad():
                return AutoModel(
                    model=vad_path,
                    device=requested_device,
                    hub="modelscope",
                )

            try:
                loop = asyncio.get_running_loop()
                asr_model = await loop.run_in_executor(None, _load_asr)
                vad_model = await loop.run_in_executor(None, _load_vad)
            except Exception as e:
                raise RuntimeError(f"funasr_model_load_failed:{e}")

            self._asr_key = asr_key
            self._asr_model_path = asr_path
            self._asr_model = asr_model
            self._vad_model_path = vad_path
            self._vad_model = vad_model
            self._runtime_device = requested_device
            self._last_device_error = None
            try:
                logging.getLogger("modules.fun_asr_service").info(
                    f"FunASR loaded: key={asr_key} path={asr_path} device={requested_device} vad={vad_path}"
                )
            except Exception:
                pass

    async def transcribe_to_utterances(
        self,
        audio_path: Path,
        model_key: str,
        language: str = "中文",
        itn: bool = True,
        hotwords: Optional[List[str]] = None,
        device: Optional[str] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
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
        try:
            for i, (st, et) in enumerate(intervals, start=1):
                seg_name = f"seg_{i:04d}.wav"
                seg_path = tmp / seg_name
                await asyncio.get_running_loop().run_in_executor(None, _extract_segment_to_wav, audio_path, int(st), int(et), seg_path)

                report(min(90, 10 + int(i / max(1, len(intervals)) * 70)), f"识别中 {i}/{len(intervals)}")

                def _run_asr() -> Any:
                    return m_asr.generate(
                        input=[str(seg_path)],
                        cache={},
                        batch_size=1,
                        hotwords=hotwords or [],
                        language=language,
                        itn=bool(itn),
                    )

                res_asr = await asyncio.get_running_loop().run_in_executor(None, _run_asr)
                text = ""
                try:
                    if isinstance(res_asr, list) and res_asr and isinstance(res_asr[0], dict):
                        text = str(res_asr[0].get("text") or "").strip()
                except Exception:
                    text = ""
                if not text:
                    continue
                utterances.append({"start_time": int(st), "end_time": int(et), "text": text})
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
