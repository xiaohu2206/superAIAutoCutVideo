import numpy as np
import os
import sys
from typing import Optional, Tuple


class VoxCPMTTSModel:
    def __init__(self, model_path: str, dtype=None):
        self.model_path = model_path
        self.dtype = dtype
        self._model = None

    @classmethod
    def from_pretrained(cls, model_path: str, dtype=None, **kwargs):
        instance = cls(model_path, dtype)
        instance._load_model(**kwargs)
        return instance

    def _load_model(self, **kwargs):
        enable_denoiser = kwargs.get('enable_denoiser', False)
        optimize = kwargs.get('optimize', None)
        if optimize is None:
            optimize = False if bool(getattr(sys, "frozen", False)) else True

        if bool(getattr(sys, "frozen", False)):
            os.environ.setdefault("PYTORCH_JIT", "0")
            os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
            try:
                import torch
                import torch.jit._state as _jit_state
                _jit_state.disable()
                if hasattr(torch, "_C") and hasattr(torch._C, "_jit_set_enabled"):
                    torch._C._jit_set_enabled(False)
            except Exception:
                pass

        from voxcpm import VoxCPM

        self._model = VoxCPM(
            voxcpm_model_path=self.model_path,
            enable_denoiser=enable_denoiser,
            optimize=optimize,
        )

    def generate_voice_clone(
        self,
        text: str,
        language: str,
        ref_audio: str,
        ref_text: Optional[str] = None,
    ) -> Tuple[np.ndarray, int]:
        prompt_wav_path = str(ref_audio or "").strip()
        if not prompt_wav_path:
            raise ValueError("missing_prompt_wav_path")

        prompt_text = (ref_text or "").strip()
        if not prompt_text:
            raise ValueError("ref_text_required_for_voice_clone")
        wav = self._model.generate(
            text=text,
            prompt_wav_path=prompt_wav_path,
            prompt_text=prompt_text,
        )
        sr = self._model.tts_model.sample_rate
        return [wav], sr
