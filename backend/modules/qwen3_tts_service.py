import asyncio
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple, cast

import numpy as np
import logging

from modules.qwen3_tts_model_manager import Qwen3TTSPathManager, validate_model_dir


_TORCH_PAD_PATCHED = False
_TORCH_DEVICE_MIX_PATCHED = False
_TORCH_MULTINOMIAL_PATCHED = False


def _ensure_torch_cpu_half_replication_pad_patch() -> None:
    global _TORCH_PAD_PATCHED
    if _TORCH_PAD_PATCHED:
        return
    try:
        import torch
        import torch.nn.functional as F
    except Exception:
        return

    orig_pad = getattr(F, "pad", None)
    if not callable(orig_pad):
        return
    if getattr(orig_pad, "__sacv_cpu_half_replication_pad_patch__", False):
        _TORCH_PAD_PATCHED = True
        return

    def _pad_patched(input, pad, mode="constant", value=None):
        try:
            if (
                isinstance(input, torch.Tensor)
                and input.device.type == "cpu"
                and input.dtype in (torch.float16, torch.bfloat16)
                and mode in ("replicate", "replication")
            ):
                out = orig_pad(input.float(), pad, mode, value)
                return out.to(dtype=input.dtype)
        except Exception:
            pass
        return orig_pad(input, pad, mode, value)

    setattr(_pad_patched, "__sacv_cpu_half_replication_pad_patch__", True)
    F.pad = _pad_patched

    try:
        orig_c_pad = getattr(getattr(torch, "_C", None), "_nn", None)
        orig_c_pad = getattr(orig_c_pad, "pad", None)
    except Exception:
        orig_c_pad = None

    if callable(orig_c_pad) and not getattr(orig_c_pad, "__sacv_cpu_half_replication_pad_patch__", False):
        def _c_pad_patched(*args, **kwargs):
            try:
                input = args[0] if len(args) >= 1 else kwargs.get("input")
                pad = args[1] if len(args) >= 2 else kwargs.get("pad")
                mode = args[2] if len(args) >= 3 else kwargs.get("mode", "constant")
                value = args[3] if len(args) >= 4 else kwargs.get("value", None)
                if (
                    isinstance(input, torch.Tensor)
                    and input.device.type == "cpu"
                    and input.dtype in (torch.float16, torch.bfloat16)
                    and mode in ("replicate", "replication")
                ):
                    out = orig_c_pad(input.float(), pad, mode, value)
                    return out.to(dtype=input.dtype)
            except Exception:
                pass
            return orig_c_pad(*args, **kwargs)

        setattr(_c_pad_patched, "__sacv_cpu_half_replication_pad_patch__", True)
        try:
            torch._C._nn.pad = _c_pad_patched
        except Exception:
            pass

    _TORCH_PAD_PATCHED = True


def _ensure_torch_cuda_device_mix_patch() -> None:
    global _TORCH_DEVICE_MIX_PATCHED
    if _TORCH_DEVICE_MIX_PATCHED:
        return
    try:
        import torch
        import torch.nn.functional as F
    except Exception:
        return

    try:
        orig_embedding = getattr(F, "embedding", None)
        if callable(orig_embedding) and not getattr(orig_embedding, "__sacv_cuda_device_mix_patch__", False):
            def _embedding_patched(input, weight, *args, **kwargs):
                try:
                    if isinstance(input, torch.Tensor) and isinstance(weight, torch.Tensor):
                        if weight.device.type == "cuda" and input.device.type == "cpu":
                            input = input.to(weight.device)
                except Exception:
                    pass
                return orig_embedding(input, weight, *args, **kwargs)

            setattr(_embedding_patched, "__sacv_cuda_device_mix_patch__", True)
            F.embedding = _embedding_patched
    except Exception:
        pass

    try:
        orig_index_select = getattr(torch, "index_select", None)
        if callable(orig_index_select) and not getattr(orig_index_select, "__sacv_cuda_device_mix_patch__", False):
            def _index_select_patched(input, dim, index, *args, **kwargs):
                try:
                    if isinstance(input, torch.Tensor) and input.device.type == "cuda":
                        if isinstance(index, torch.Tensor) and index.device.type == "cpu":
                            index = index.to(input.device)
                except Exception:
                    pass
                return orig_index_select(input, dim, index, *args, **kwargs)

            setattr(_index_select_patched, "__sacv_cuda_device_mix_patch__", True)
            torch.index_select = _index_select_patched
    except Exception:
        pass

    try:
        orig_tensor_index_select = getattr(torch.Tensor, "index_select", None)
        if callable(orig_tensor_index_select) and not getattr(orig_tensor_index_select, "__sacv_cuda_device_mix_patch__", False):
            def _tensor_index_select_patched(self, dim, index):
                try:
                    if isinstance(self, torch.Tensor) and self.device.type == "cuda":
                        if isinstance(index, torch.Tensor) and index.device.type == "cpu":
                            index = index.to(self.device)
                except Exception:
                    pass
                return orig_tensor_index_select(self, dim, index)

            setattr(_tensor_index_select_patched, "__sacv_cuda_device_mix_patch__", True)
            try:
                torch.Tensor.index_select = _tensor_index_select_patched
            except Exception:
                pass
    except Exception:
        pass

    _TORCH_DEVICE_MIX_PATCHED = True


def _ensure_torch_cuda_multinomial_stability_patch() -> None:
    global _TORCH_MULTINOMIAL_PATCHED
    if _TORCH_MULTINOMIAL_PATCHED:
        return
    try:
        import torch
    except Exception:
        return

    orig_multinomial = getattr(torch, "multinomial", None)
    if not callable(orig_multinomial):
        return
    if getattr(orig_multinomial, "__sacv_cuda_multinomial_patch__", False):
        _TORCH_MULTINOMIAL_PATCHED = True
        return

    def _multinomial_patched(input, num_samples, replacement=False, generator=None, out=None):
        try:
            if not isinstance(input, torch.Tensor) or input.device.type != "cuda":
                return orig_multinomial(input, num_samples, replacement=replacement, generator=generator, out=out)

            probs = input
            if probs.dtype in (torch.float16, torch.bfloat16):
                probs = probs.float()
            else:
                probs = probs.clone() if probs.requires_grad else probs

            probs = torch.nan_to_num(probs, nan=0.0, posinf=0.0, neginf=0.0)
            probs = torch.clamp(probs, min=0.0)

            if probs.dim() == 1:
                s = probs.sum()
                if not torch.isfinite(s) or float(s.item()) <= 0.0:
                    idx = int(torch.argmax(probs).item()) if probs.numel() > 0 else 0
                    r = torch.tensor([idx] * int(num_samples), device=probs.device, dtype=torch.int64)
                    return r
                probs = probs / s
            elif probs.dim() == 2:
                s = probs.sum(dim=1, keepdim=True)
                bad = (~torch.isfinite(s)) | (s <= 0)
                if bool(bad.any().item()):
                    best = torch.argmax(probs, dim=1, keepdim=True).to(dtype=torch.int64)
                    if int(num_samples) == 1:
                        return best
                    return best.repeat(1, int(num_samples))
                probs = probs / s
            return orig_multinomial(probs, num_samples, replacement=replacement, generator=generator, out=out)
        except Exception:
            try:
                if isinstance(input, torch.Tensor) and input.device.type == "cuda":
                    if input.dim() == 1:
                        idx = int(torch.argmax(torch.nan_to_num(input.float(), nan=0.0, posinf=0.0, neginf=0.0)).item()) if input.numel() > 0 else 0
                        return torch.tensor([idx] * int(num_samples), device=input.device, dtype=torch.int64)
                    if input.dim() == 2:
                        best = torch.argmax(torch.nan_to_num(input.float(), nan=0.0, posinf=0.0, neginf=0.0), dim=1, keepdim=True).to(dtype=torch.int64)
                        if int(num_samples) == 1:
                            return best
                        return best.repeat(1, int(num_samples))
            except Exception:
                pass
            return orig_multinomial(input, num_samples, replacement=replacement, generator=generator, out=out)

    setattr(_multinomial_patched, "__sacv_cuda_multinomial_patch__", True)
    torch.multinomial = _multinomial_patched
    _TORCH_MULTINOMIAL_PATCHED = True


def _prepare_windows_dll_search_paths() -> None:
    if sys.platform != "win32":
        return

    try:
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    except Exception:
        pass
    try:
        os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
    except Exception:
        pass

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass or not isinstance(meipass, str):
        return

    candidates = [
        Path(meipass),
        Path(meipass) / "torch" / "lib",
        Path(meipass) / "Library" / "bin",
    ]
    try:
        for p in Path(meipass).glob("nvidia/**/bin"):
            candidates.append(p)
    except Exception:
        pass

    for p in candidates:
        try:
            if not p.exists():
                continue
        except Exception:
            continue

        try:
            os.add_dll_directory(str(p))
        except Exception:
            pass

        try:
            old = os.environ.get("PATH", "")
            if str(p) not in old:
                os.environ["PATH"] = str(p) + os.pathsep + old
        except Exception:
            pass


class Qwen3TTSService:
    def __init__(self) -> None:
        self._model_key: Optional[str] = None
        self._model_path: Optional[str] = None
        self._model: Any = None
        self._load_lock = asyncio.Lock()
        self._runtime_device: str = "cpu"
        self._last_device_error: Optional[str] = None

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "loaded": self._model is not None,
            "model_key": self._model_key,
            "model_path": self._model_path,
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

    def _normalize_model_path(self, p: str) -> str:
        s = (p or "").strip()
        if s.startswith("\\\\?\\UNC\\"):
            return "\\\\" + s[8:]
        if s.startswith("\\\\?\\"):
            return s[4:]
        return s

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
            _prepare_windows_dll_search_paths()
            pm = Qwen3TTSPathManager()
            try:
                model_dir = pm.model_path(model_key)
            except KeyError:
                raise RuntimeError(f"unknown_model_key:{model_key}")

            model_path = self._normalize_model_path(str(model_dir))
            requested_device = self._normalize_device(device)
            if not requested_device:
                try:
                    from modules.qwen3_tts_acceleration import get_qwen3_tts_preferred_device

                    requested_device = self._normalize_device(get_qwen3_tts_preferred_device())
                except Exception:
                    requested_device = "cpu"

            if (
                self._model is not None
                and self._model_key == model_key
                and self._model_path == model_path
                and self._runtime_device == requested_device
            ):
                return

            ready, err = self._ensure_ready(model_key)
            if not ready:
                raise RuntimeError(err)

            try:
                from modules.vendor.qwen_tts import Qwen3TTSModel
            except Exception as e:
                raise RuntimeError(f"qwen_tts_import_failed:{e}")

            q = requested_device or "cpu"
            inst = None
            chosen_dtype = None
            chosen_attn = None
            try:
                import torch
                _ensure_torch_cpu_half_replication_pad_patch()
                _ensure_torch_cuda_device_mix_patch()
                _ensure_torch_cuda_multinomial_stability_patch()
                if q.startswith("cuda") and torch.cuda.is_available():
                    def _load_flash():
                        return Qwen3TTSModel.from_pretrained(
                            model_path,
                            dtype=torch.bfloat16,
                            attn_implementation="flash_attention_2",
                        )
                    try:
                        inst = await asyncio.get_running_loop().run_in_executor(None, _load_flash)
                        chosen_dtype = torch.bfloat16
                        chosen_attn = "flash_attention_2"
                    except Exception:
                        if getattr(getattr(torch, "cuda", None), "is_bf16_supported", None) and torch.cuda.is_bf16_supported():
                            def _load_sdpa_bf16():
                                return Qwen3TTSModel.from_pretrained(
                                    model_path,
                                    dtype=torch.bfloat16,
                                    attn_implementation="sdpa",
                                )
                            try:
                                inst = await asyncio.get_running_loop().run_in_executor(None, _load_sdpa_bf16)
                                chosen_dtype = torch.bfloat16
                                chosen_attn = "sdpa"
                            except Exception:
                                def _load_sdpa_fp16():
                                    return Qwen3TTSModel.from_pretrained(
                                        model_path,
                                        dtype=torch.float16,
                                        attn_implementation="sdpa",
                                    )
                                inst = await asyncio.get_running_loop().run_in_executor(None, _load_sdpa_fp16)
                                chosen_dtype = torch.float16
                                chosen_attn = "sdpa"
                        else:
                            def _load_sdpa_fp16():
                                return Qwen3TTSModel.from_pretrained(
                                    model_path,
                                    dtype=torch.float16,
                                    attn_implementation="sdpa",
                                )
                            inst = await asyncio.get_running_loop().run_in_executor(None, _load_sdpa_fp16)
                            chosen_dtype = torch.float16
                            chosen_attn = "sdpa"
                else:
                    def _load_cpu():
                        return Qwen3TTSModel.from_pretrained(
                            model_path,
                            dtype=torch.float32,
                        )
                    inst = await asyncio.get_running_loop().run_in_executor(None, _load_cpu)
                    chosen_dtype = getattr(__import__("torch"), "float32")
                    chosen_attn = None
            except Exception as e:
                raise RuntimeError(f"qwen_tts_model_load_failed:{e}")

            actual_device = "cpu"
            self._last_device_error = None
            if q and q != "cpu":
                try:
                    import torch

                    inst.model.to(torch.device(q))
                    actual_device = q
                except Exception as e:
                    self._last_device_error = f"model_to_device_failed:{e}"
                    if q.startswith("cuda"):
                        raise RuntimeError(self._last_device_error)
                    actual_device = "cpu"
            if actual_device == "cpu":
                try:
                    import torch
                    inst.model.to(dtype=torch.float32)
                except Exception:
                    try:
                        inst.model.float()
                    except Exception:
                        pass

            self._model_key = model_key
            self._model_path = model_path
            self._model = inst
            self._runtime_device = actual_device
            try:
                logging.getLogger("modules.qwen3_tts_service").info(
                    f"Qwen3-TTS loaded: key={model_key} path={model_path} device={actual_device} dtype={str(chosen_dtype)} attn={str(chosen_attn or '')}"
                )
            except Exception:
                pass

    async def _write_wav(self, out_path: Path, run_fn) -> Dict[str, Any]:
        runtime_device = self._runtime_device

        def _run_with_torch_defaults() -> Tuple[np.ndarray, int]:
            try:
                import torch
                _ensure_torch_cpu_half_replication_pad_patch()
                _ensure_torch_cuda_device_mix_patch()
                _ensure_torch_cuda_multinomial_stability_patch()
            except Exception:
                return run_fn()

            prev_device = None
            try:
                if hasattr(torch, "get_default_device"):
                    prev_device = torch.get_default_device()
                if runtime_device and runtime_device.startswith("cuda") and torch.cuda.is_available():
                    try:
                        torch.set_default_device(runtime_device)
                    except Exception:
                        pass
                return run_fn()
            finally:
                if prev_device is not None:
                    try:
                        torch.set_default_device(prev_device)
                    except Exception:
                        pass

        wav, sr = await asyncio.get_running_loop().run_in_executor(None, _run_with_torch_defaults)
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
        try:
            logging.getLogger("modules.qwen3_tts_service").info(
                f"Qwen3-TTS synthesize request: kind={kind} key={model_key} language={language} device={str(device or '').strip() or 'auto'}"
            )
        except Exception:
            pass

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
                text=v.get("ref_text"),
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
                language="auto",
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
