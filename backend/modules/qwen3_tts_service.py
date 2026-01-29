import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

import numpy as np

from modules.qwen3_tts_model_manager import Qwen3TTSPathManager, validate_model_dir


class Qwen3TTSService:
    def __init__(self) -> None:
        self._model_key: Optional[str] = None
        self._model_path: Optional[str] = None
        self._model: Any = None
        self._load_lock = asyncio.Lock()

    def _ensure_ready(self, model_key: str) -> Tuple[bool, str]:
        pm = Qwen3TTSPathManager()
        try:
            model_dir = pm.model_path(model_key)
        except KeyError:
            return False, f"unknown_model_key:{model_key}"
        ok, missing = validate_model_dir(model_key, model_dir)
        if not ok:
            return False, f"model_invalid:{model_key}:{','.join(missing)}|path={model_dir}"
        return True, ""

    async def _load_model(self, model_key: str, device: Optional[str] = None) -> None:
        async with self._load_lock:
            pm = Qwen3TTSPathManager()
            try:
                model_dir = pm.model_path(model_key)
            except KeyError:
                raise RuntimeError(f"unknown_model_key:{model_key}")

            model_path = str(model_dir)
            if self._model is not None and self._model_key == model_key and self._model_path == model_path:
                return

            ready, err = self._ensure_ready(model_key)
            if not ready:
                raise RuntimeError(err)

            try:
                from modules.vendor.qwen_tts import Qwen3TTSModel
            except Exception as e:
                raise RuntimeError(f"qwen_tts_import_failed:{e}")

            kwargs: Dict[str, Any] = {}
            q = device or "cpu"
            try:
                import torch

                if q.startswith("cuda") and torch.cuda.is_available():
                    kwargs["torch_dtype"] = torch.float16
            except Exception:
                pass

            inst = await asyncio.get_running_loop().run_in_executor(
                None, lambda: Qwen3TTSModel.from_pretrained(model_path, **kwargs)
            )

            if q and q != "cpu":
                try:
                    import torch

                    inst.model.to(torch.device(q))
                except Exception:
                    pass

            self._model_key = model_key
            self._model_path = model_path
            self._model = inst

    async def _write_wav(self, out_path: Path, run_fn) -> Dict[str, Any]:
        wav, sr = await asyncio.get_running_loop().run_in_executor(None, run_fn)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import soundfile as sf

            sf.write(str(out_path), wav, sr, format="WAV")
        except Exception as e:
            raise RuntimeError(f"soundfile_write_failed:{e}")

        duration = float(len(wav) / sr) if sr > 0 else None
        return {"success": True, "path": str(out_path), "duration": duration, "sample_rate": sr}

    async def synthesize_custom_voice_to_wav(
        self,
        text: str,
        out_path: Path,
        model_key: str,
        language: str,
        speaker: str,
        instruct: Optional[str] = None,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._load_model(model_key=model_key, device=device)
        m = cast(Any, self._model)
        if m is None:
            raise RuntimeError("qwen3_tts_model_not_loaded")

        def _run() -> Tuple[np.ndarray, int]:
            wavs, sr = m.generate_custom_voice(
                text=text,
                speaker=speaker,
                language=language,
                instruct=instruct,
                non_streaming_mode=True,
                do_sample=True,
                top_k=50,
                top_p=1.0,
                temperature=0.9,
                max_new_tokens=2048,
            )
            if not wavs:
                raise RuntimeError("empty_audio")
            return wavs[0].astype(np.float32), int(sr)

        return await self._write_wav(out_path, _run)

    async def synthesize_voice_clone_to_wav(
        self,
        text: str,
        out_path: Path,
        model_key: str,
        language: str,
        ref_audio: str,
        ref_text: Optional[str] = None,
        x_vector_only_mode: bool = True,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._load_model(model_key=model_key, device=device)
        m = cast(Any, self._model)
        if m is None:
            raise RuntimeError("qwen3_tts_model_not_loaded")

        def _run() -> Tuple[np.ndarray, int]:
            wavs, sr = m.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=x_vector_only_mode,
                non_streaming_mode=True,
                do_sample=True,
                top_k=50,
                top_p=1.0,
                temperature=0.9,
                max_new_tokens=2048,
            )
            if not wavs:
                raise RuntimeError("empty_audio")
            return wavs[0].astype(np.float32), int(sr)

        return await self._write_wav(out_path, _run)

    async def synthesize_voice_design_to_wav(
        self,
        text: str,
        out_path: Path,
        model_key: str,
        language: str,
        instruct: str,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._load_model(model_key=model_key, device=device)
        m = cast(Any, self._model)
        if m is None:
            raise RuntimeError("qwen3_tts_model_not_loaded")

        def _run() -> Tuple[np.ndarray, int]:
            wavs, sr = m.generate_voice_design(
                text=text,
                language=language,
                instruct=instruct,
                non_streaming_mode=True,
                do_sample=True,
                top_k=50,
                top_p=1.0,
                temperature=0.9,
                max_new_tokens=2048,
            )
            if not wavs:
                raise RuntimeError("empty_audio")
            return wavs[0].astype(np.float32), int(sr)

        return await self._write_wav(out_path, _run)

    async def synthesize_by_voice_asset(
        self,
        text: str,
        out_path: Path,
        voice_asset: Any,  # Qwen3TTSVoice or dict
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        v = voice_asset
        if not isinstance(v, dict):
            try:
                v = v.model_dump()
            except Exception:
                pass

        if not isinstance(v, dict):
            raise ValueError("invalid_voice_asset")

        kind = v.get("kind", "clone")
        model_key = v.get("model_key", "base_0_6b")
        language = v.get("language", "Auto")

        if kind == "custom_role":
            return await self.synthesize_custom_voice_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                speaker=str(v.get("speaker") or "Vivian"),
                instruct=v.get("instruct"),
                device=device,
            )
        elif kind == "design_clone":
            return await self.synthesize_voice_clone_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                ref_audio=str(v.get("ref_audio_path") or ""),
                ref_text=v.get("ref_text"),
                x_vector_only_mode=False,
                device=device,
            )
        else:  # clone
            return await self.synthesize_voice_clone_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                ref_audio=str(v.get("ref_audio_path") or ""),
                ref_text=v.get("ref_text"),
                x_vector_only_mode=bool(v.get("x_vector_only_mode", True)),
                device=device,
            )

    async def synthesize_to_wav(
        self,
        text: str,
        out_path: Path,
        model_key: str,
        language: str,
        speaker: Optional[str] = None,
        instruct: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        x_vector_only_mode: bool = True,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Legacy adapter
        if model_key.startswith("custom_"):
            spk_in = (speaker or "").strip()
            if not spk_in:
                supported = await self.list_supported_speakers(model_key=model_key, device=device)
                first = next((str(x).strip() for x in supported if x is not None and str(x).strip()), "")
                if not first:
                    raise ValueError("speaker_required_for_custom_voice")
                spk_in = first
            return await self.synthesize_custom_voice_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                speaker=spk_in,
                instruct=instruct,
                device=device,
            )
        else:
            return await self.synthesize_voice_clone_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                ref_audio=str(ref_audio or ""),
                ref_text=ref_text,
                x_vector_only_mode=x_vector_only_mode,
                device=device,
            )

    async def list_supported_speakers(self, model_key: str, device: Optional[str] = None) -> list[str]:
        model_key = (model_key or "").strip() or "custom_0_6b"
        await self._load_model(model_key=model_key, device=device)
        m = cast(Any, self._model)
        if m is None:
            return []
        for fn in [
            getattr(getattr(m, "model", None), "get_supported_speakers", None),
            getattr(m, "get_supported_speakers", None),
        ]:
            if callable(fn):
                try:
                    v = fn()
                    if isinstance(v, list):
                        return [str(x) for x in v if x is not None]
                except Exception:
                    continue
        return []

    async def list_supported_languages(self, model_key: str, device: Optional[str] = None) -> list[str]:
        model_key = (model_key or "").strip() or "custom_0_6b"
        await self._load_model(model_key=model_key, device=device)
        m = cast(Any, self._model)
        if m is None:
            return []
        for fn in [
            getattr(getattr(m, "model", None), "get_supported_languages", None),
            getattr(m, "get_supported_languages", None),
        ]:
            if callable(fn):
                try:
                    v = fn()
                    if isinstance(v, list):
                        return [str(x) for x in v if x is not None]
                except Exception:
                    continue
        return []


qwen3_tts_service = Qwen3TTSService()
