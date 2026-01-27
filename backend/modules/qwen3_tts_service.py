import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

import numpy as np

from modules.qwen3_tts_model_manager import Qwen3TTSPathManager, validate_model_dir


class Qwen3TTSService:
    def __init__(self) -> None:
        self.pm = Qwen3TTSPathManager()
        self._model_key: Optional[str] = None
        self._model: Any = None
        self._load_lock = asyncio.Lock()

    def _ensure_ready(self, model_key: str) -> Tuple[bool, str]:
        model_dir = self.pm.model_path(model_key)
        ok, missing = validate_model_dir(model_key, model_dir)
        if not ok:
            return False, f"model_invalid:{model_key}:{','.join(missing)}"
        return True, ""

    async def _load_model(self, model_key: str, device: Optional[str] = None) -> None:
        async with self._load_lock:
            if self._model is not None and self._model_key == model_key:
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
                None, lambda: Qwen3TTSModel.from_pretrained(str(self.pm.model_path(model_key)), **kwargs)
            )

            if q and q != "cpu":
                try:
                    import torch

                    inst.model.to(torch.device(q))
                except Exception:
                    pass

            self._model_key = model_key
            self._model = inst

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
        model_key = (model_key or "").strip() or "custom_0_6b"
        language = (language or "").strip() or "Auto"
        await self._load_model(model_key=model_key, device=device)

        m = cast(Any, self._model)
        if m is None:
            raise RuntimeError("qwen3_tts_model_not_loaded")

        if model_key == "custom_0_6b":
            spk_in = (speaker or "").strip()
            if not spk_in:
                supported = await self.list_supported_speakers(model_key=model_key, device=device)
                first = next((str(x).strip() for x in supported if x is not None and str(x).strip()), "")
                if not first:
                    raise ValueError("speaker_required_for_custom_voice")
                speaker = first

        def _run() -> Tuple[np.ndarray, int]:
            if model_key == "custom_0_6b":
                spk = (speaker or "").strip()
                if not spk:
                    raise ValueError("speaker_required_for_custom_voice")
                wavs, sr = m.generate_custom_voice(
                    text=text,
                    speaker=spk,
                    language=language,
                    instruct=instruct,
                    non_streaming_mode=True,
                    do_sample=True,
                    top_k=50,
                    top_p=1.0,
                    temperature=0.9,
                    max_new_tokens=2048,
                )
            else:
                ra = (ref_audio or "").strip()
                if not ra:
                    raise ValueError("ref_audio_required_for_voice_clone")
                wavs, sr = m.generate_voice_clone(
                    text=text,
                    language=language,
                    ref_audio=ra,
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

        wav, sr = await asyncio.get_running_loop().run_in_executor(None, _run)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import soundfile as sf

            sf.write(str(out_path), wav, sr, format="WAV")
        except Exception as e:
            raise RuntimeError(f"soundfile_write_failed:{e}")

        duration = float(len(wav) / sr) if sr > 0 else None
        return {"success": True, "path": str(out_path), "duration": duration, "sample_rate": sr}

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


qwen3_tts_service = Qwen3TTSService()
