import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

import numpy as np

from modules.voxcpm_tts_model_manager import VoxCPMTTSPathManager, validate_model_dir


class VoxCPMTTSService:
    def __init__(self) -> None:
        self._model_key: Optional[str] = None
        self._model_path: Optional[str] = None
        self._model: Any = None
        self._load_lock = asyncio.Lock()
        self._runtime_device: str = "cpu"
        self._runtime_precision: str = "fp32"
        self._last_device_error: Optional[str] = None

    def _compact_spaces(self, s: str) -> str:
        x = (s or "").replace("\r", " ").replace("\n", " ")
        return re.sub(r"\s+", " ", x).strip()

    def _to_funasr_language(self, voxcpm_language: str) -> str:
        s = (voxcpm_language or "").strip().lower()
        if not s or s in {"auto", "default"}:
            return "中文"
        if s in {"zh", "zh-cn", "zh-hans", "chinese", "cn"}:
            return "中文"
        if s in {"yue", "cantonese", "zh-hk", "hk"}:
            return "粤语"
        if s in {"en", "en-us", "en-gb", "english"}:
            return "英文"
        if s in {"ja", "jp", "japanese"}:
            return "日文"
        if s in {"ko", "kr", "korean"}:
            return "韩文"
        if s in {"fr", "french"}:
            return "法文"
        if s in {"de", "german"}:
            return "德文"
        if s in {"es", "spanish"}:
            return "西班牙语"
        return "中文"

    def _pick_funasr_model_key(self, funasr_language: str) -> Optional[str]:
        try:
            from modules.fun_asr_model_manager import FunASRPathManager, validate_model_dir as validate_funasr_model_dir
        except Exception:
            return None

        candidates = ["fun_asr_nano_2512", "fun_asr_mlt_nano_2512"]
        if funasr_language not in {"中文", "英文", "日文"}:
            candidates = ["fun_asr_mlt_nano_2512", "fun_asr_nano_2512"]

        pm = FunASRPathManager()
        for key in candidates:
            try:
                p = pm.model_path(key)
            except Exception:
                continue
            try:
                ok, _missing = validate_funasr_model_dir(key, p)
            except Exception:
                ok = False
            if ok:
                return key
        return None

    async def _auto_infer_ref_text(self, ref_audio: str, language: str, device: Optional[str]) -> str:
        p = Path(str(ref_audio or "").strip())
        if not p.exists():
            return ""

        asr_lang = self._to_funasr_language(language)
        asr_key = self._pick_funasr_model_key(asr_lang)
        if not asr_key:
            return ""

        try:
            from modules.fun_asr_service import fun_asr_service
        except Exception:
            return ""

        try:
            utterances = await fun_asr_service.transcribe_to_utterances(
                audio_path=p,
                model_key=asr_key,
                language=asr_lang,
                itn=True,
                hotwords=[],
                device=device,
                on_progress=None,
            )
        except Exception:
            return ""

        text = " ".join(
            self._compact_spaces(str(u.get("text") or "")) for u in (utterances or []) if isinstance(u, dict)
        ).strip()
        return self._compact_spaces(text)

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
        if d.lower() in {"auto", "default"}:
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
        pm = VoxCPMTTSPathManager()
        try:
            model_dir = pm.model_path(model_key)
        except KeyError:
            return False, f"unknown_model_key:{model_key}"
        ok, missing = validate_model_dir(model_key, model_dir)
        if not ok:
            return False, f"model_invalid:{model_key}:{','.join(missing)}|path={model_dir}"
        return True, ""

    async def _load_model(self, model_key: str, device: Optional[str] = None, precision: Optional[str] = None) -> None:
        pm = VoxCPMTTSPathManager()
        try:
            model_dir = pm.model_path(model_key)
        except KeyError:
            raise RuntimeError(f"unknown_model_key:{model_key}")

        model_path = self._normalize_model_path(str(model_dir))
        requested_device = self._normalize_device(device)
        requested_precision: Optional[str] = None
        if precision is not None:
            p_in = (precision or "").strip().lower()
            if p_in in {"fp16", "float16", "half"}:
                requested_precision = "fp16"
            elif p_in in {"bf16", "bfloat16"}:
                requested_precision = "bf16"
            elif p_in in {"fp32", "float32"}:
                requested_precision = "fp32"

        if (
            self._model is not None
            and self._model_key == model_key
            and self._model_path == model_path
            and (not requested_device or self._runtime_device == requested_device)
            and (requested_precision is None or self._runtime_precision == requested_precision)
        ):
            return

        async with self._load_lock:
            pm = VoxCPMTTSPathManager()
            try:
                model_dir = pm.model_path(model_key)
            except KeyError:
                raise RuntimeError(f"unknown_model_key:{model_key}")

            model_path = self._normalize_model_path(str(model_dir))
            requested_device = self._normalize_device(device)
            requested_precision = None
            if precision is not None:
                p_in = (precision or "").strip().lower()
                if p_in in {"fp16", "float16", "half"}:
                    requested_precision = "fp16"
                elif p_in in {"bf16", "bfloat16"}:
                    requested_precision = "bf16"
                elif p_in in {"fp32", "float32"}:
                    requested_precision = "fp32"

            if (
                self._model is not None
                and self._model_key == model_key
                and self._model_path == model_path
                and (not requested_device or self._runtime_device == requested_device)
                and (requested_precision is None or self._runtime_precision == requested_precision)
            ):
                return

            if not requested_device:
                try:
                    import torch
                    if torch.cuda.is_available():
                        requested_device = "cuda:0"
                    else:
                        requested_device = "cpu"
                except Exception:
                    requested_device = "cpu"
            if requested_precision is None:
                requested_precision = "fp16" if requested_device.startswith("cuda") else "fp32"

            try:
                logging.getLogger("modules.voxcpm_tts_service").info(
                    f"准备加载VoxCPM模型: key={model_key} 设备={requested_device or 'cpu'} 精度={requested_precision} 路径={model_path}"
                )
            except Exception:
                pass

            ready, err = self._ensure_ready(model_key)
            if not ready:
                raise RuntimeError(err)

            try:
                import torch
            except Exception as e:
                raise RuntimeError(f"missing_dependency:torch:{e}")

            try:
                from modules.vendor.voxcpm_tts import VoxCPMTTSModel
            except Exception as e:
                hint = ""
                try:
                    import sys
                    if sys.platform == "win32" and (getattr(e, "winerror", None) == 206 or "WinError 206" in str(e) or "文件名或扩展名太长" in str(e)):
                        hint = " | windows_path_too_long: 建议将后端安装/运行目录移到更短路径，或在系统中启用 Windows 长路径支持"
                except Exception:
                    hint = ""
                raise RuntimeError(f"voxcpm_tts_import_failed:{e}{hint}")

            q = requested_device or "cpu"
            inst = None
            chosen_dtype = None
            try:
                import torch
                if q.startswith("cuda") and torch.cuda.is_available():
                    if requested_precision == "fp32":
                        def _load_fp32():
                            return VoxCPMTTSModel.from_pretrained(
                                model_path,
                                dtype=torch.float32,
                            )
                        inst = await asyncio.get_running_loop().run_in_executor(None, _load_fp32)
                        chosen_dtype = torch.float32
                    else:
                        def _load_fp16():
                            return VoxCPMTTSModel.from_pretrained(
                                model_path,
                                dtype=torch.float16,
                            )
                        try:
                            inst = await asyncio.get_running_loop().run_in_executor(None, _load_fp16)
                            chosen_dtype = torch.float16
                        except Exception:
                            def _load_fp32():
                                return VoxCPMTTSModel.from_pretrained(
                                    model_path,
                                    dtype=torch.float32,
                                )
                            inst = await asyncio.get_running_loop().run_in_executor(None, _load_fp32)
                            chosen_dtype = torch.float32
                else:
                    def _load_cpu():
                        return VoxCPMTTSModel.from_pretrained(
                            model_path,
                            dtype=torch.float32,
                        )
                    inst = await asyncio.get_running_loop().run_in_executor(None, _load_cpu)
                    chosen_dtype = getattr(__import__("torch"), "float32")
            except Exception as e:
                raise RuntimeError(f"voxcpm_model_load_failed:{e}")

            try:
                logging.getLogger("modules.voxcpm_tts_service").info(
                    f"已创建VoxCPM实例: 目标设备={q} 选择dtype={str(chosen_dtype)}"
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
                        logging.getLogger("modules.voxcpm_tts_service").info(
                            f"模型已迁移到设备: {actual_device}"
                        )
                    except Exception:
                        pass
                except Exception as e:
                    self._last_device_error = f"model_to_device_failed:{e}"
                    try:
                        logging.getLogger("modules.voxcpm_tts_service").error(
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
                    logging.getLogger("modules.voxcpm_tts_service").info(
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
                logging.getLogger("modules.voxcpm_tts_service").info(
                    f"VoxCPM loaded: key={model_key} path={model_path} device={actual_device} dtype={str(chosen_dtype)} precision={self._runtime_precision}"
                )
            except Exception:
                pass
            try:
                logging.getLogger("modules.voxcpm_tts_service").info(
                    f"VoxCPM 已就绪: 模型={model_key} 设备={actual_device} 精度={self._runtime_precision} dtype={str(chosen_dtype)}"
                )
            except Exception:
                pass

    async def _write_wav(self, out_path: Path, run_fn) -> Dict[str, Any]:
        runtime_device = self._runtime_device

        def _run_with_torch_defaults() -> Tuple[np.ndarray, int]:
            try:
                import torch
            except Exception:
                return run_fn()

            prev_device = None
            try:
                if hasattr(torch, "get_default_device"):
                    prev_device = torch.get_default_device()
                if runtime_device and runtime_device.startswith("cuda"):
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.set_default_device(runtime_device)
                    except Exception:
                        pass
                return run_fn()
            finally:
                if prev_device is not None:
                    try:
                        import torch
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

    async def synthesize_voice_clone_to_wav(
        self,
        text: str,
        out_path: Path,
        model_key: str,
        language: str,
        ref_audio: str,
        ref_text: Optional[str] = None,
        device: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._load_model(model_key=model_key, device=device)

        clean_text = self._compact_spaces(str(text or ""))
        clean_ref_text = self._compact_spaces(str(ref_text or ""))
        if not clean_text:
            raise RuntimeError("empty_text")
        if not clean_ref_text:
            inferred = await self._auto_infer_ref_text(ref_audio=ref_audio, language=language, device=device)
            clean_ref_text = self._compact_spaces(inferred)
        if not clean_ref_text:
            clean_ref_text = clean_text[:120].strip()

        def _run() -> Tuple[np.ndarray, int]:
            m = cast(Any, self._model)
            if m is None:
                raise RuntimeError("voxcpm_model_not_loaded")
            wavs, sr = m.generate_voice_clone(
                text=clean_text,
                language=language,
                ref_audio=ref_audio,
                ref_text=clean_ref_text,
            )
            if not wavs:
                raise RuntimeError("empty_audio")
            return wavs[0].astype(np.float32), int(sr)

        return await self._write_wav(out_path, _run)

    async def synthesize_by_voice_asset(
        self,
        text: str,
        out_path: Path,
        voice_asset: Any,
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
        model_key = v.get("model_key", "voxcpm_0_5b")
        language = v.get("language", "Auto")

        if not self._compact_spaces(str(v.get("ref_text") or "")):
            inferred = await self._auto_infer_ref_text(
                ref_audio=str(v.get("ref_audio_path") or ""),
                language=str(language or "Auto"),
                device=device,
            )
            inferred = self._compact_spaces(inferred)
            if inferred:
                v["ref_text"] = inferred
                try:
                    from modules.voxcpm_tts_voice_store import voxcpm_tts_voice_store

                    vid = str(v.get("id") or "").strip()
                    if vid:
                        base_meta = v.get("meta")
                        meta = dict(base_meta) if isinstance(base_meta, dict) else {}
                        meta["auto_ref_text"] = inferred
                        meta["auto_ref_text_source"] = "funasr"
                        voxcpm_tts_voice_store.update(vid, {"ref_text": inferred, "meta": meta})
                except Exception:
                    pass
        try:
            device_s = (str(device or "").strip() or "auto")
            actual_text = text
            preview = actual_text.replace("\r", " ").replace("\n", " ")
            if len(preview) > 500:
                preview = preview[:500] + "..."
            logging.getLogger("modules.voxcpm_tts_service").info(
                f"VoxCPM 开始合成: kind={kind} key={model_key} language={language} device={device_s} out={Path(out_path).name} "
                f"文本长度={len(actual_text)} 预览=\"{preview}\" 进度=0%"
            )
        except Exception:
            pass

        res = await self.synthesize_voice_clone_to_wav(
            text=text,
            out_path=out_path,
            model_key=model_key,
            language=language,
            ref_audio=str(v.get("ref_audio_path") or ""),
            ref_text=v.get("ref_text"),
            device=device,
        )

        try:
            logging.getLogger("modules.voxcpm_tts_service").info(
                f"VoxCPM 完成合成: kind={kind} key={model_key} out={Path(out_path).name} "
                f"时长={res.get('duration') if isinstance(res, dict) else None} 进度=100%"
            )
        except Exception:
            pass
        return res


voxcpm_tts_service = VoxCPMTTSService()
