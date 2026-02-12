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


def _is_replication_pad_half_not_implemented(err: Exception) -> bool:
    try:
        msg = str(err)
    except Exception:
        return False
    return ("replication_pad" in msg) and ("not implemented for 'Half'" in msg or 'not implemented for "Half"' in msg)


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

    try:
        c_nn = getattr(getattr(torch, "_C", None), "_nn", None)
        if c_nn is not None:
            def _should_fallback_pad_cast(err: Exception) -> bool:
                msg = str(err)
                return (
                    "not implemented for 'Half'" in msg
                    or "not implemented for 'BFloat16'" in msg
                    or "replication_pad" in msg
                )

            for _name in ("replication_pad1d", "replication_pad2d", "replication_pad3d"):
                _orig = getattr(c_nn, _name, None)
                if not callable(_orig) or getattr(_orig, "__sacv_cpu_half_replication_pad_patch__", False):
                    continue

                def _make_replication_pad_patched(orig_fn):
                    def _replication_pad_patched(*args, **kwargs):
                        try:
                            return orig_fn(*args, **kwargs)
                        except Exception as e:
                            try:
                                input = args[0] if len(args) >= 1 else kwargs.get("input")
                                if (
                                    isinstance(input, torch.Tensor)
                                    and input.dtype in (torch.float16, torch.bfloat16)
                                    and _should_fallback_pad_cast(e)
                                ):
                                    args2 = list(args)
                                    kwargs2 = dict(kwargs)
                                    if len(args2) >= 1:
                                        args2[0] = input.float()
                                    else:
                                        kwargs2["input"] = input.float()
                                    out = orig_fn(*args2, **kwargs2)
                                    if isinstance(out, torch.Tensor):
                                        return out.to(dtype=input.dtype)
                                    return out
                            except Exception:
                                pass
                            raise

                    setattr(_replication_pad_patched, "__sacv_cpu_half_replication_pad_patch__", True)
                    return _replication_pad_patched

                try:
                    setattr(c_nn, _name, _make_replication_pad_patched(_orig))
                except Exception:
                    pass
    except Exception:
        pass

    try:
        import torch.nn.modules.padding as _padding_mod
    except Exception:
        _padding_mod = None

    def _patch_replication_pad_forward(cls) -> None:
        try:
            if cls is None:
                return
            orig_forward = getattr(cls, "forward", None)
            if not callable(orig_forward) or getattr(orig_forward, "__sacv_cpu_half_replication_pad_patch__", False):
                return

            def _make_forward_patched(ofn):
                def _forward_patched(self, input):
                    try:
                        if (
                            isinstance(input, torch.Tensor)
                            and input.device.type == "cpu"
                            and input.dtype in (torch.float16, torch.bfloat16)
                        ):
                            out = ofn(self, input.float())
                            if isinstance(out, torch.Tensor):
                                return out.to(dtype=input.dtype)
                            return out
                    except Exception:
                        pass
                    return ofn(self, input)

                setattr(_forward_patched, "__sacv_cpu_half_replication_pad_patch__", True)
                return _forward_patched

            try:
                setattr(cls, "forward", _make_forward_patched(orig_forward))
            except Exception:
                pass
        except Exception:
            return

    try:
        if _padding_mod is not None:
            _patch_replication_pad_forward(getattr(_padding_mod, "_ReplicationPadNd", None))
            _patch_replication_pad_forward(getattr(_padding_mod, "ReplicationPad1d", None))
            _patch_replication_pad_forward(getattr(_padding_mod, "ReplicationPad2d", None))
            _patch_replication_pad_forward(getattr(_padding_mod, "ReplicationPad3d", None))
    except Exception:
        pass

    try:
        aten = getattr(getattr(torch, "ops", None), "aten", None)
        if aten is not None:
            def _patch_aten_replication_pad(name: str) -> None:
                try:
                    pkt = getattr(aten, name, None)
                    if pkt is None:
                        return
                    fn = getattr(pkt, "default", None)
                    if not callable(fn) or getattr(fn, "__sacv_cpu_half_replication_pad_patch__", False):
                        return

                    def _aten_replication_pad_patched(*args, **kwargs):
                        try:
                            return fn(*args, **kwargs)
                        except Exception as e:
                            try:
                                input = args[0] if len(args) >= 1 else kwargs.get("input")
                                if (
                                    isinstance(input, torch.Tensor)
                                    and input.device.type == "cpu"
                                    and input.dtype in (torch.float16, torch.bfloat16)
                                    and _should_fallback_pad_cast(e)
                                ):
                                    args2 = list(args)
                                    kwargs2 = dict(kwargs)
                                    if len(args2) >= 1:
                                        args2[0] = input.float()
                                    else:
                                        kwargs2["input"] = input.float()
                                    out = fn(*args2, **kwargs2)
                                    if isinstance(out, torch.Tensor):
                                        return out.to(dtype=input.dtype)
                                    return out
                            except Exception:
                                pass
                            raise

                    setattr(_aten_replication_pad_patched, "__sacv_cpu_half_replication_pad_patch__", True)
                    try:
                        setattr(pkt, "default", _aten_replication_pad_patched)
                    except Exception:
                        pass
                except Exception:
                    return

            for _name in ("replication_pad1d", "replication_pad2d", "replication_pad3d"):
                _patch_aten_replication_pad(_name)
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

    candidates = []

    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            candidates.append(Path(meipass))
    except Exception:
        meipass = None

    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir)
        candidates.append(exe_dir / "_internal")
    except Exception:
        exe_dir = None

    try:
        here = Path(__file__).resolve()
        for p in [here.parent, *here.parents]:
            if len(candidates) >= 12:
                break
            try:
                if (p / "torch" / "lib").exists() or (p / "_internal" / "torch" / "lib").exists():
                    candidates.append(p)
            except Exception:
                continue
    except Exception:
        pass

    expanded = []
    for root in candidates:
        try:
            if not isinstance(root, Path):
                continue
            expanded.append(root)
            expanded.append(root / "torch" / "lib")
            expanded.append(root / "_internal" / "torch" / "lib")
            expanded.append(root / "Library" / "bin")
            expanded.append(root / "_internal" / "Library" / "bin")
            try:
                for p in root.glob("nvidia/**/bin"):
                    expanded.append(p)
            except Exception:
                pass
            try:
                for p in (root / "_internal").glob("nvidia/**/bin"):
                    expanded.append(p)
            except Exception:
                pass
        except Exception:
            continue

    seen = set()
    candidates2 = []
    for p in expanded:
        try:
            sp = str(p)
            if not sp or sp in seen:
                continue
            seen.add(sp)
            candidates2.append(p)
        except Exception:
            continue

    for p in candidates2:
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
        self._runtime_precision: str = "fp32"
        self._last_device_error: Optional[str] = None

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "loaded": self._model is not None,
            "model_key": self._model_key,
            "model_path": self._model_path,
            "device": self._runtime_device,
            "precision": self._runtime_precision,
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

    async def _load_model(self, model_key: str, device: Optional[str] = None, precision: Optional[str] = None) -> None:
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

            p_in = (precision or "").strip().lower()
            if p_in in {"fp16", "float16", "half"}:
                requested_precision = "fp16"
            elif p_in in {"bf16", "bfloat16"}:
                requested_precision = "bf16"
            elif p_in in {"fp32", "float32"}:
                requested_precision = "fp32"
            else:
                requested_precision = "fp16" if requested_device.startswith("cuda") else "fp32"

            try:
                logging.getLogger("modules.qwen3_tts_service").info(
                    f"准备加载Qwen3-TTS模型: key={model_key} 设备={requested_device or 'cpu'} 精度={requested_precision} 路径={model_path}"
                )
            except Exception:
                pass

            if (
                self._model is not None
                and self._model_key == model_key
                and self._model_path == model_path
                and self._runtime_device == requested_device
                and self._runtime_precision == requested_precision
            ):
                return

            ready, err = self._ensure_ready(model_key)
            if not ready:
                raise RuntimeError(err)

            try:
                _prepare_windows_dll_search_paths()
            except Exception:
                pass

            try:
                import torch
                _ensure_torch_cpu_half_replication_pad_patch()
                _ensure_torch_cuda_device_mix_patch()
                _ensure_torch_cuda_multinomial_stability_patch()
            except Exception:
                pass

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
                if q.startswith("cuda") and torch.cuda.is_available():
                    if requested_precision == "fp32":
                        def _load_sdpa_fp32():
                            return Qwen3TTSModel.from_pretrained(
                                model_path,
                                dtype=torch.float32,
                                attn_implementation="sdpa",
                            )
                        inst = await asyncio.get_running_loop().run_in_executor(None, _load_sdpa_fp32)
                        chosen_dtype = torch.float32
                        chosen_attn = "sdpa"
                    else:
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
                            if requested_precision == "bf16":
                                def _load_sdpa_bf16():
                                    return Qwen3TTSModel.from_pretrained(
                                        model_path,
                                        dtype=torch.bfloat16,
                                        attn_implementation="sdpa",
                                    )
                                inst = await asyncio.get_running_loop().run_in_executor(None, _load_sdpa_bf16)
                                chosen_dtype = torch.bfloat16
                                chosen_attn = "sdpa"
                            elif getattr(getattr(torch, "cuda", None), "is_bf16_supported", None) and torch.cuda.is_bf16_supported():
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

            try:
                logging.getLogger("modules.qwen3_tts_service").info(
                    f"已创建Qwen3-TTS实例: 目标设备={q} 选择dtype={str(chosen_dtype)} 注意力={str(chosen_attn or '')}"
                )
            except Exception:
                pass

            actual_device = "cpu"
            self._last_device_error = None
            if q and q != "cpu":
                try:
                    import torch

                    inst.model.to(torch.device(q))
                    actual_device = q
                    try:
                        logging.getLogger("modules.qwen3_tts_service").info(
                            f"模型已迁移到设备: {actual_device}"
                        )
                    except Exception:
                        pass
                except Exception as e:
                    self._last_device_error = f"model_to_device_failed:{e}"
                    try:
                        logging.getLogger("modules.qwen3_tts_service").error(
                            f"模型迁移到设备失败: 目标={q} 错误={e}"
                        )
                    except Exception:
                        pass
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
                try:
                    logging.getLogger("modules.qwen3_tts_service").info(
                        "当前在CPU上运行（精度将设为FP32）"
                    )
                except Exception:
                    pass

            self._model_key = model_key
            self._model_path = model_path
            self._model = inst
            self._runtime_device = actual_device
            self._runtime_precision = ("fp32" if actual_device == "cpu" else requested_precision)
            try:
                logging.getLogger("modules.qwen3_tts_service").info(
                    f"Qwen3-TTS loaded: key={model_key} path={model_path} device={actual_device} dtype={str(chosen_dtype)} attn={str(chosen_attn or '')} precision={self._runtime_precision}"
                )
            except Exception:
                pass
            try:
                logging.getLogger("modules.qwen3_tts_service").info(
                    f"Qwen3-TTS 已就绪: 模型={model_key} 设备={actual_device} 精度={self._runtime_precision} dtype={str(chosen_dtype)} 注意力={str(chosen_attn or '')}"
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

        def _run() -> Tuple[np.ndarray, int]:
            m = cast(Any, self._model)
            if m is None:
                raise RuntimeError("qwen3_tts_model_not_loaded")
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

        try:
            return await self._write_wav(out_path, _run)
        except Exception as e:
            if self._runtime_device.startswith("cuda") and self._runtime_precision != "fp32" and _is_replication_pad_half_not_implemented(e):
                await self._load_model(model_key=model_key, device=self._runtime_device, precision="fp32")
                return await self._write_wav(out_path, _run)
            raise

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

        def _run() -> Tuple[np.ndarray, int]:
            m = cast(Any, self._model)
            if m is None:
                raise RuntimeError("qwen3_tts_model_not_loaded")
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

        try:
            return await self._write_wav(out_path, _run)
        except Exception as e:
            if self._runtime_device.startswith("cuda") and self._runtime_precision != "fp32" and _is_replication_pad_half_not_implemented(e):
                await self._load_model(model_key=model_key, device=self._runtime_device, precision="fp32")
                return await self._write_wav(out_path, _run)
            raise

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

        def _run() -> Tuple[np.ndarray, int]:
            m = cast(Any, self._model)
            if m is None:
                raise RuntimeError("qwen3_tts_model_not_loaded")
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

        try:
            return await self._write_wav(out_path, _run)
        except Exception as e:
            if self._runtime_device.startswith("cuda") and self._runtime_precision != "fp32" and _is_replication_pad_half_not_implemented(e):
                await self._load_model(model_key=model_key, device=self._runtime_device, precision="fp32")
                return await self._write_wav(out_path, _run)
            raise

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
            device_s = (str(device or "").strip() or "auto")
            actual_text = (v.get("ref_text") if kind == "design_clone" else text) or ""
            preview = actual_text.replace("\r", " ").replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            logging.getLogger("modules.qwen3_tts_service").info(
                f"Qwen3-TTS 开始合成: kind={kind} key={model_key} language={language} device={device_s} out={Path(out_path).name} "
                f"文本长度={len(actual_text)} 预览=\"{preview}\" 进度=0%"
            )
        except Exception:
            pass

        if kind == "custom_role":
            res = await self.synthesize_custom_voice_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language=language,
                speaker=str(v.get("speaker") or "Vivian"),
                instruct=v.get("instruct"),
                device=device,
            )
        elif kind == "design_clone":
            res = await self.synthesize_voice_clone_to_wav(
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
            res = await self.synthesize_voice_clone_to_wav(
                text=text,
                out_path=out_path,
                model_key=model_key,
                language="auto",
                ref_audio=str(v.get("ref_audio_path") or ""),
                ref_text=v.get("ref_text"),
                x_vector_only_mode=bool(v.get("x_vector_only_mode", True)),
                device=device,
            )

        try:
            logging.getLogger("modules.qwen3_tts_service").info(
                f"Qwen3-TTS 完成合成: kind={kind} key={model_key} out={Path(out_path).name} "
                f"时长={res.get('duration') if isinstance(res, dict) else None} 进度=100%"
            )
        except Exception:
            pass
        return res

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

try:
    _prepare_windows_dll_search_paths()
    _ensure_torch_cpu_half_replication_pad_patch()
    _ensure_torch_cuda_device_mix_patch()
    _ensure_torch_cuda_multinomial_stability_patch()
except Exception:
    pass
