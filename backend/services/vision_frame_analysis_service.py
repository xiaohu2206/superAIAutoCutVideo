import asyncio
import json
import logging
import os
import time
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import base64
from io import BytesIO

import cv2
from PIL import Image

from modules.ai import AIModelConfig, ChatMessage, get_provider_class
from modules.moondream_model_manager import MoondreamPathManager
from modules.moondream_inference_settings import resolve_moondream_runtime_config
from modules.task_progress_store import task_progress_store
from modules.task_cancel_store import task_cancel_store

logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class _OnlineVisionRunner:
    def __init__(self, provider: str, api_key: str, base_url: str, model_name: str, timeout: int = 120):
        self._provider = provider
        self._model_name = model_name
        self._signature = (str(provider or ""), str(api_key or ""), str(base_url or ""), str(model_name or ""), int(timeout or 0))

        provider_cls = get_provider_class(provider)
        if not provider_cls:
            raise ValueError(f"不支持的AI提供商: {provider}")

        ai_cfg = AIModelConfig(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            timeout=timeout,
            extra_params={"max_tokens": 512},
        )
        self._provider_impl = provider_cls(ai_cfg)

    @property
    def signature(self) -> Tuple[str, str, str, str, int]:
        return self._signature

    async def close(self):
        await self._provider_impl.close()

    async def infer(self, img: Image.Image, prompt: str = "Describe this image briefly.") -> Tuple[str, Dict[str, Any]]:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{img_base64}"

        t0 = time.time()
        resp = await self._provider_impl.chat_completion(
            [
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                )
            ]
        )
        t1 = time.time()
        usage = (resp.usage or {}) if hasattr(resp, "usage") else {}

        stats = {
            "backend": "online",
            "provider": self._provider,
            "model": self._model_name,
            "infer_s": t1 - t0,
            "prompt_tokens": int((usage or {}).get("prompt_tokens", 0) or 0),
            "completion_tokens": int((usage or {}).get("completion_tokens", 0) or 0),
            "total_tokens": int((usage or {}).get("total_tokens", 0) or 0),
        }

        return (resp.content or ""), stats


def _resolve_moondream_env_n_gpu_layers() -> int:
    raw = str(os.environ.get("MOONDREAM_N_GPU_LAYERS") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except Exception:
        return 0


class _MoondreamRunner:
    def __init__(self) -> None:
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._mode: Optional[str] = None
        self._runtime_key: Optional[str] = None
        self._model_dir: Optional[str] = None
        self._model_id: Optional[str] = None
        self._device: Optional[str] = None
        self._dtype: Optional[str] = None
        self._llm = None
        self._hf_model = None

    def _runtime_snapshot(self) -> Tuple[Dict[str, Any], str]:
        runtime, _ = resolve_moondream_runtime_config(env_n_gpu_layers=_resolve_moondream_env_n_gpu_layers())
        try:
            key = json.dumps(runtime or {}, ensure_ascii=False, sort_keys=True)
        except Exception:
            key = str(runtime)
        return runtime or {}, key

    def _resolve_gguf_dir(self) -> Path:
        env_dir = str(os.environ.get("MOONDREAM_GGUF_DIR") or "").strip()
        if env_dir:
            return Path(env_dir)
        return MoondreamPathManager().model_path()

    def _load_gguf(self, runtime: Dict[str, Any]) -> None:
        try:
            import llama_cpp
            from llama_cpp import Llama
            from llama_cpp.llama_chat_format import MoondreamChatHandler
        except ModuleNotFoundError:
            raise RuntimeError(
                "缺少依赖 llama-cpp-python（Moondream 推理需要）。请在后端 Python 环境安装："
                "python -m pip install \"llama-cpp-python==0.2.90\""
            )

        md = self._resolve_gguf_dir()
        clip_path = md / "moondream2-mmproj-f16.gguf"
        text_path = md / "moondream2-text-model-f16.gguf"
        if not clip_path.exists() or not text_path.exists():
            raise RuntimeError("Moondream GGUF 模型文件不完整，请重新下载并校验")

        n_gpu_layers = int(runtime.get("n_gpu_layers") or 0)
        supports_offload = False
        try:
            ll = getattr(llama_cpp, "llama_cpp", None)
            fn = getattr(ll, "llama_supports_gpu_offload", None)
            if callable(fn):
                supports_offload = bool(fn())
        except Exception:
            supports_offload = False

        dev = str(runtime.get("device") or "").strip().lower()
        wants_gpu = dev.startswith("cuda") or (n_gpu_layers != 0)
        if wants_gpu and (not supports_offload):
            raise RuntimeError(
                "Moondream 需要 llama-cpp-python 的 CUDA 构建（GGML_CUDA=on）才能进行 GPU offload，但当前环境检测为 CPU 构建。"
                "请安装/打包 GPU 版后端，或将 Moondream 推理设备切换为 CPU。"
            )

        if n_gpu_layers >= 99:
            n_gpu_layers = -1
        main_gpu = runtime.get("main_gpu")
        if isinstance(main_gpu, bool):
            main_gpu = None
        if isinstance(main_gpu, (int, float)):
            main_gpu = int(main_gpu)
        else:
            main_gpu = None


        chat_handler = MoondreamChatHandler(clip_model_path=str(clip_path), verbose=False)
        kwargs: Dict[str, Any] = {}
        if n_gpu_layers > 0 and main_gpu is not None:
            kwargs["main_gpu"] = int(main_gpu)

        logger.info(f"Loading Moondream GGUF model from {md} (llama_cpp={getattr(llama_cpp, '__version__', None)} gpu_offload={supports_offload})")
        self._llm = Llama(
            model_path=str(text_path),
            chat_handler=chat_handler,
            n_ctx=2048,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
            **kwargs,
        )

        self._mode = "gguf"
        self._model_dir = str(md)
        self._model_id = None

    def _load_hf(self, runtime: Dict[str, Any]) -> None:
        try:
            import torch
            from modules.vendor.moondream.hf import LATEST_REVISION, Moondream
        except ModuleNotFoundError as e:
            raise RuntimeError(f"缺少依赖（Moondream HF 推理需要）：{e}")

        dev = str(runtime.get("device") or "").strip().lower()
        if dev == "cpu":
            device = torch.device("cpu")
            dtype = torch.float32
        elif dev.startswith("cuda"):
            device = torch.device(dev)
            dtype = torch.bfloat16
        else:
            if torch.cuda.is_available():
                device = torch.device("cuda")
                dtype = torch.bfloat16
            else:
                device = torch.device("cpu")
                dtype = torch.float32

        model_id = os.environ.get("MOONDREAM_MODEL_ID", "moondream/moondream-2b-2025-04-14-4bit")
        revision = os.environ.get("MOONDREAM_REVISION", None)
        if revision is None and "moondream-2b-2025-04-14-4bit" not in model_id:
            revision = LATEST_REVISION

        default_cache_dir = Path(__file__).resolve().parents[1] / "serviceData" / "models" / "moondream2"
        cache_dir = os.environ.get("MOONDREAM_CACHE_DIR", str(default_cache_dir))
        local_only = os.environ.get("HF_HUB_OFFLINE", "0") == "1" or os.environ.get("MOONDREAM_LOCAL_ONLY", "0") == "1"

        logger.info(f"Loading Moondream HF model: {model_id} (device={device})")
        model = Moondream.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=dtype,
            cache_dir=cache_dir,
            local_files_only=local_only,
        ).to(device=device)
        model.eval()

        self._hf_model = model
        self._mode = "hf"
        self._model_id = str(model_id)
        self._model_dir = str(cache_dir)
        self._device = str(device)
        self._dtype = str(dtype)
        self._llm = None

    def _ensure_loaded(self, runtime: Dict[str, Any], runtime_key: str) -> None:
        if self._mode and self._runtime_key == runtime_key:
            return
        with self._load_lock:
            if self._mode and self._runtime_key == runtime_key:
                return

            self._mode = None
            self._runtime_key = runtime_key
            self._model_dir = None
            self._model_id = None
            self._device = None
            self._dtype = None
            self._llm = None
            self._hf_model = None

            gguf_dir = self._resolve_gguf_dir()
            gguf_text = gguf_dir / "moondream2-text-model-f16.gguf"
            gguf_mmproj = gguf_dir / "moondream2-mmproj-f16.gguf"
            use_gguf = gguf_text.exists() and gguf_mmproj.exists()

            if use_gguf:
                self._load_gguf(runtime)
                return
            self._load_hf(runtime)

    def infer_with_stats(self, img: Image.Image, prompt: str) -> Tuple[str, Dict[str, Any]]:
        runtime, key = self._runtime_snapshot()
        t_load0 = time.time()
        self._ensure_loaded(runtime, key)
        load_s = time.time() - t_load0

        wait0 = time.time()
        self._infer_lock.acquire()
        wait_s = time.time() - wait0
        compute_s = 0.0
        backend = self._mode

        try:
            if self._mode == "gguf":
                buf = BytesIO()
                img.save(buf, format="PNG")
                data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(prompt or "Describe this image briefly.")},
                            {"type": "image_url", "image_url": {"url": data_uri}},
                        ],
                    }
                ]
                t0 = time.time()
                resp = self._llm.create_chat_completion(messages=messages)
                compute_s = time.time() - t0
                choice = (resp or {}).get("choices", [{}])[0] if isinstance(resp, dict) else {}
                msg = choice.get("message") if isinstance(choice, dict) else None
                if isinstance(msg, dict) and (msg.get("content") is not None):
                    text = str(msg.get("content") or "")
                elif isinstance(choice, dict) and (choice.get("text") is not None):
                    text = str(choice.get("text") or "")
                else:
                    text = ""
                stats = {
                    "backend": backend,
                    "device": runtime.get("device"),
                    "n_gpu_layers": runtime.get("n_gpu_layers"),
                    "main_gpu": runtime.get("main_gpu"),
                    "load_s": float(load_s),
                    "wait_s": float(wait_s),
                    "compute_s": float(compute_s),
                    "infer_total_s": float(wait_s + compute_s),
                }
                return text, stats

            t0 = time.time()
            result = self._hf_model.caption(img, length="normal")
            compute_s = time.time() - t0
            if isinstance(result, dict) and ("caption" in result):
                text = str(result.get("caption") or "")
                stats = {
                    "backend": backend,
                    "device": runtime.get("device"),
                    "n_gpu_layers": runtime.get("n_gpu_layers"),
                    "main_gpu": runtime.get("main_gpu"),
                    "load_s": float(load_s),
                    "wait_s": float(wait_s),
                    "compute_s": float(compute_s),
                    "infer_total_s": float(wait_s + compute_s),
                }
                return text, stats
            raise RuntimeError("Moondream HF 推理返回格式异常")
        finally:
            try:
                self._infer_lock.release()
            except Exception:
                pass

    def infer(self, img: Image.Image, prompt: str) -> str:
        text, _ = self.infer_with_stats(img, prompt=prompt)
        return text

    def get_runtime_status(self) -> Dict[str, Any]:
        runtime, _ = self._runtime_snapshot()
        return {
            "mode": "inprocess",
            "backend": self._mode,
            "loaded": bool(self._mode),
            "model_dir": self._model_dir,
            "model_id": self._model_id,
            "device": runtime.get("device"),
            "n_gpu_layers": runtime.get("n_gpu_layers"),
            "main_gpu": runtime.get("main_gpu"),
            "hf_device": self._device,
            "hf_dtype": self._dtype,
        }


class VisionFrameAnalyzer:
    SCOPE = "extract_scene"

    def __init__(self):
        self._moondream = _MoondreamRunner()
        self._online_runner: Optional[_OnlineVisionRunner] = None
        self._online_runner_lock = threading.Lock()

    async def _get_online_runner(self, provider: str, api_key: str, base_url: str, model_name: str, timeout: int = 120) -> _OnlineVisionRunner:
        sig = (str(provider or ""), str(api_key or ""), str(base_url or ""), str(model_name or ""), int(timeout or 0))
        old: Optional[_OnlineVisionRunner] = None
        with self._online_runner_lock:
            if self._online_runner is None:
                self._online_runner = _OnlineVisionRunner(provider, api_key, base_url, model_name, timeout)
            elif self._online_runner.signature != sig:
                old = self._online_runner
                self._online_runner = _OnlineVisionRunner(provider, api_key, base_url, model_name, timeout)
            runner = self._online_runner

        if old is not None:
            try:
                await old.close()
            except Exception:
                pass
        return runner

    async def close_online_runner(self):
        if self._online_runner is not None:
            await self._online_runner.close()
            self._online_runner = None

    def _optimize_image(self, image_input: Union[str, Image.Image], max_edge: int = 1024) -> Image.Image:
        """
        Optimizes an image for Moondream model inference by resizing it.
        """
        if isinstance(image_input, str):
            try:
                img = Image.open(image_input)
            except IOError as e:
                raise ValueError(f"Unable to load image from {image_input}: {e}")
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            raise ValueError("Input must be a file path string or a PIL Image object")

        if img.mode != 'RGB':
            img = img.convert('RGB')

        width, height = img.size
        
        if max(width, height) > max_edge:
            ratio = max_edge / max(width, height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
        return img

    def extract_center_frame(self, video_path: str, t_start: float, t_end: float) -> Optional[Image.Image]:
        img, _ = self.extract_center_frame_with_reason(video_path, t_start, t_end)
        return img

    def extract_center_frame_with_reason(self, video_path: str, t_start: float, t_end: float) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
        try:
            if not video_path:
                return None, {"code": "invalid_path", "message": "video_path 为空"}
            if not Path(video_path).exists():
                return None, {"code": "path_not_found", "message": "视频文件不存在", "video_path": video_path}

            center_time = (float(t_start) + float(t_end)) / 2.0
            if center_time < 0:
                center_time = 0.0

            def _try_cv2(mode: str) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    try:
                        cap.release()
                    except Exception:
                        pass
                    return None, {"code": "open_failed", "message": "无法打开视频文件", "seek_mode": mode}

                fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
                fps_ok = fps > 0.0
                frame_count_ok = frame_count > 0.0
                fps_safe = float(fps) if fps_ok else 25.0

                try:
                    if mode == "msec":
                        ok_seek = cap.set(cv2.CAP_PROP_POS_MSEC, float(center_time) * 1000.0)
                        ret, frame = cap.read()
                        if (not ret) or frame is None:
                            back = max(0.0, float(center_time) - 2.0)
                            cap.set(cv2.CAP_PROP_POS_MSEC, back * 1000.0)
                            frame = None
                            for _ in range(int(round(2.0 * fps_safe)) + 5):
                                ret_i, fr_i = cap.read()
                                if not ret_i or fr_i is None:
                                    continue
                                frame = fr_i
                            ret = frame is not None
                    else:
                        target_frame = int(round(float(center_time) * float(fps_safe)))
                        if frame_count_ok:
                            target_frame = max(0, min(int(frame_count) - 1, target_frame))
                        ok_seek = cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        ret, frame = cap.read()
                        if (not ret) or frame is None:
                            back_frames = max(0, target_frame - int(round(2.0 * fps_safe)))
                            cap.set(cv2.CAP_PROP_POS_FRAMES, back_frames)
                            frame = None
                            steps = max(1, target_frame - back_frames) + 5
                            for _ in range(steps):
                                ret_i, fr_i = cap.read()
                                if not ret_i or fr_i is None:
                                    continue
                                frame = fr_i
                            ret = frame is not None

                    if (not ret) or frame is None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        return None, {
                            "code": "read_failed",
                            "message": "读取帧失败",
                            "seek_mode": mode,
                            "t_start": float(t_start),
                            "t_end": float(t_end),
                            "center_time": float(center_time),
                            "fps": float(fps),
                            "frame_count": float(frame_count),
                            "seek_ok": bool(ok_seek),
                        }

                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    try:
                        cap.release()
                    except Exception:
                        pass
                    return Image.fromarray(frame), None
                except Exception as e:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    return None, {
                        "code": "cv2_exception",
                        "message": str(e),
                        "seek_mode": mode,
                        "t_start": float(t_start),
                        "t_end": float(t_end),
                        "center_time": float(center_time),
                    }

            def _try_ffmpeg() -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
                def run_one(args: List[str]) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
                    try:
                        kwargs: Dict[str, Any] = {
                            "stdout": subprocess.PIPE,
                            "stderr": subprocess.PIPE,
                            "timeout": 12,
                            "check": False,
                        }
                        if os.name == "nt":
                            kwargs["creationflags"] = WIN_NO_WINDOW
                        p = subprocess.run(args, **kwargs)
                        if p.returncode != 0 or not p.stdout:
                            return None, {
                                "code": "ffmpeg_failed",
                                "message": "ffmpeg 抽帧失败",
                                "returncode": int(p.returncode),
                                "stderr": (p.stderr or b"")[:2000].decode("utf-8", errors="ignore"),
                            }
                        return p.stdout, None
                    except FileNotFoundError:
                        return None, {"code": "ffmpeg_not_found", "message": "未找到 ffmpeg 可执行文件"}
                    except subprocess.TimeoutExpired:
                        return None, {"code": "ffmpeg_timeout", "message": "ffmpeg 抽帧超时"}
                    except Exception as e:
                        return None, {"code": "ffmpeg_exception", "message": str(e)}

                ts = f"{float(center_time):.3f}"
                cmd_fast = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-ss",
                    ts,
                    "-i",
                    video_path,
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "pipe:1",
                ]
                out, err = run_one(cmd_fast)
                if out is None:
                    cmd_acc = [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-nostdin",
                        "-i",
                        video_path,
                        "-ss",
                        ts,
                        "-frames:v",
                        "1",
                        "-f",
                        "image2pipe",
                        "-vcodec",
                        "mjpeg",
                        "pipe:1",
                    ]
                    out, err2 = run_one(cmd_acc)
                    err = err2 if err2 else err
                if out is None:
                    return None, err
                try:
                    img = Image.open(BytesIO(out)).convert("RGB")
                    return img, None
                except Exception as e:
                    return None, {"code": "ffmpeg_decode_failed", "message": str(e)}

            cv_img, cv_err = _try_cv2("msec")
            if cv_img is not None:
                return cv_img, None
            cv_img2, cv_err2 = _try_cv2("frame")
            if cv_img2 is not None:
                return cv_img2, None

            ff_img, ff_err = _try_ffmpeg()
            if ff_img is not None:
                return ff_img, None

            return None, {
                "code": "extract_frame_failed",
                "message": "抽帧失败（cv2 与 ffmpeg 均失败）",
                "cv2_msec": cv_err,
                "cv2_frame": cv_err2,
                "ffmpeg": ff_err,
            }
        except Exception as e:
            logger.error(f"Error extracting frame: {e}")
            return None, {"code": "exception", "message": str(e)}

    def infer_with_moondream(self, img: Image.Image, prompt: str = "Describe this image briefly.", return_stats: bool = False):
        optimized_img = self._optimize_image(img)
        if return_stats:
            return self._moondream.infer_with_stats(optimized_img, prompt=prompt)
        return self._moondream.infer(optimized_img, prompt=prompt)

    def get_moondream_runtime_status(self) -> Dict[str, Any]:
        return self._moondream.get_runtime_status()

    async def analyze_scenes_online(
        self,
        project_id: str,
        video_path: str,
        scenes: List[Dict[str, Any]],
        provider: str,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout: int = 120,
        mode: str = "all",
        task_id: Optional[str] = None,
        max_concurrency: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Analyze scenes using online vision models (302ai, yunwu, etc.).
        mode: "no_subtitles" (default) or "all"
        """
        online_runner = await self._get_online_runner(provider, api_key, base_url, model_name, timeout)
        prompt = "Describe this image briefly."

        extract_concurrency = max(1, min(max_concurrency, 8))
        api_concurrency = max(1, min(max_concurrency, 4))
        extract_semaphore = asyncio.Semaphore(extract_concurrency)
        api_semaphore = asyncio.Semaphore(api_concurrency)

        to_analyze_indices = []
        for idx, scene in enumerate(scenes):
            should_analyze = False
            if mode == "all":
                should_analyze = True
            elif mode == "no_subtitles":
                sub = scene.get("subtitle")
                if not sub or sub == "无":
                    should_analyze = True
            if should_analyze:
                to_analyze_indices.append(idx)

        total_to_analyze = len(to_analyze_indices)
        if total_to_analyze == 0:
            return scenes

        processed_count = 0
        loop = asyncio.get_running_loop()

        extract_executor = ThreadPoolExecutor(max_workers=extract_concurrency, thread_name_prefix="online_vision_extract")

        def _extract_segment_sync(v_path: str, t_s: float, t_e: float, scene_idx: int):
            try:
                img, frame_err = self.extract_center_frame_with_reason(v_path, t_s, t_e)
                if not img:
                    return {"ok": False, "img": None, "error": "extract_frame_failed", "frame_error": frame_err}
                return {"ok": True, "img": img, "error": None, "frame_error": None}
            except Exception as e:
                logger.error(f"Frame extract failed for {t_s}-{t_e}: {e}")
                return {"ok": False, "img": None, "error": str(e), "frame_error": None}

        async def analyze_single_scene(idx: int):
            nonlocal processed_count
            if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")

            scene = scenes[idx]
            merged_from = scene.get("merged_from", [])

            segments = merged_from if merged_from else [{"start_time": scene["start_time"], "end_time": scene["end_time"]}]

            vision_segments: List[Dict[str, Any]] = []
            for seg in segments:
                t_start = seg["start_time"]
                t_end = seg["end_time"]

                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")

                t0 = time.time()
                async with extract_semaphore:
                    extract_res = await loop.run_in_executor(extract_executor, _extract_segment_sync, video_path, t_start, t_end, idx)
                t1 = time.time()

                if not (isinstance(extract_res, dict) and extract_res.get("ok") and extract_res.get("img") is not None):
                    err = extract_res.get("error") if isinstance(extract_res, dict) else "invalid_result"
                    if err == "extract_frame_failed":
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "no_frame",
                                "text": None,
                                "frame_error": extract_res.get("frame_error") if isinstance(extract_res, dict) else None,
                            }
                        )
                    else:
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "error",
                                "text": None,
                                "error": str(err or "unknown_error"),
                            }
                        )
                    continue

                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")

                try:
                    logger.info(f"Online vision analyze: scene_idx={idx} segment={float(t_start):.3f}-{float(t_end):.3f} provider={provider}")
                    img = extract_res.get("img")
                    optimized_img = self._optimize_image(img, max_edge=1024)

                    async with api_semaphore:
                        t2 = time.time()
                        out, online_stats = await online_runner.infer(optimized_img, prompt=prompt)
                        t3 = time.time()

                    logger.info(
                        f"Online vision timing: scene_idx={idx} segment={float(t_start):.3f}-{float(t_end):.3f} extract_s={t1 - t0:.3f} infer_s={t3 - t2:.3f} total_s={t3 - t0:.3f} provider={provider} model={model_name}"
                    )

                    txt = str(out or "").strip()
                    vision_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "status": "ok" if txt else "empty",
                            "text": txt if txt else None,
                        }
                    )
                except Exception as e:
                    logger.error(f"Online vision analysis failed for {t_start}-{t_end}: {e}")
                    vision_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "status": "error",
                            "text": None,
                            "error": str(e),
                        }
                    )
                    continue

            scene["vision"] = vision_segments

            has_ok = any(s.get("status") == "ok" and (s.get("text") or "").strip() for s in vision_segments)
            has_error = any(s.get("status") == "error" for s in vision_segments)
            has_no_frame = any(s.get("status") == "no_frame" for s in vision_segments)
            if has_ok:
                scene["vision_status"] = "ok"
            elif has_error:
                scene["vision_status"] = "error"
                last_err = next((s.get("error") for s in reversed(vision_segments) if s.get("status") == "error"), None)
                if last_err:
                    scene["vision_error"] = last_err
            elif has_no_frame:
                scene["vision_status"] = "no_frame"
                last_fe = next((s.get("frame_error") for s in reversed(vision_segments) if s.get("status") == "no_frame"), None)
                if last_fe:
                    scene["vision_frame_error"] = last_fe
            else:
                scene["vision_status"] = "empty"
            scene["vision_analyzed"] = True

            processed_count += 1

            if task_id:
                progress = 90 + (processed_count / total_to_analyze) * 10
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=progress,
                    message=f"在线视觉分析中: {processed_count}/{total_to_analyze}",
                    phase="analyze_vision_online"
                )

        tasks = []
        for idx in to_analyze_indices:
            tasks.append(asyncio.create_task(analyze_single_scene(idx)))

        try:
            if tasks:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=90,
                    message="开始在线视觉分析...",
                    phase="analyze_vision_online_start"
                )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, asyncio.CancelledError):
                        raise r

            remaining = [i for i in to_analyze_indices if not bool(scenes[i].get("vision_analyzed"))]
            if remaining:
                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")
                processed_count = total_to_analyze - len(remaining)
                for i in remaining:
                    await analyze_single_scene(i)

            return scenes
        finally:
            try:
                extract_executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                try:
                    extract_executor.shutdown(wait=True)
                except Exception:
                    pass

    async def analyze_scenes(
        self, 
        project_id: str,
        video_path: str, 
        scenes: List[Dict[str, Any]], 
        mode: str = "all",
        task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze scenes using Moondream.
        mode: "no_subtitles" (default) or "all"
        """
        
        # Determine concurrency limit
        max_concurrency = os.environ.get("VISION_ANALYSIS_MAX_CONCURRENCY")
        val = 32
        if max_concurrency is not None:
            try:
                if isinstance(max_concurrency, (int, float)):
                    parsed = int(max_concurrency)
                else:
                    s = str(max_concurrency).strip()
                    parsed = int(s) if s else 0
                if parsed > 0:
                    val = parsed
            except Exception:
                val = 32
        extract_concurrency = max(1, int(val))
        extract_semaphore = asyncio.Semaphore(extract_concurrency)
        pipeline_semaphore = asyncio.Semaphore(max(2, extract_concurrency * 2))
        prompt = "Describe this image briefly."

        # Identify scenes to analyze
        to_analyze_indices = []
        for idx, scene in enumerate(scenes):
            should_analyze = False
            if mode == "all":
                should_analyze = True
            elif mode == "no_subtitles":
                # Check for "无" or empty/None subtitle
                sub = scene.get("subtitle")
                if not sub or sub == "无":
                    should_analyze = True
            
            if should_analyze:
                to_analyze_indices.append(idx)

        total_to_analyze = len(to_analyze_indices)
        if total_to_analyze == 0:
            return scenes

        processed_count = 0
        loop = asyncio.get_running_loop()

        extract_executor = ThreadPoolExecutor(max_workers=extract_concurrency, thread_name_prefix="vision_extract")
        infer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moondream_infer")

        def _extract_segment_sync(v_path: str, t_s: float, t_e: float, scene_idx: int):
            try:
                img, frame_err = self.extract_center_frame_with_reason(v_path, t_s, t_e)
                if not img:
                    return {"ok": False, "img": None, "error": "extract_frame_failed", "frame_error": frame_err}
                return {"ok": True, "img": img, "error": None, "frame_error": None}
            except Exception as e:
                logger.error(f"Frame extract failed for {t_s}-{t_e}: {e}")
                return {"ok": False, "img": None, "error": str(e), "frame_error": None}

        def _infer_segment_sync(img: Image.Image, pr: str, scene_idx: int, t_s: float, t_e: float):
            out, md_stats = self.infer_with_moondream(img, prompt=pr, return_stats=True)
            return out, md_stats

        async def analyze_single_scene(idx: int):
            nonlocal processed_count
            if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")
            
            scene = scenes[idx]
            merged_from = scene.get("merged_from", [])
            
            segments = merged_from if merged_from else [{"start_time": scene["start_time"], "end_time": scene["end_time"]}]
            
            vision_segments: List[Dict[str, Any]] = []
            for seg in segments:
                t_start = seg["start_time"]
                t_end = seg["end_time"]
                
                # Check cancellation before each segment
                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")

                async with pipeline_semaphore:
                    t0 = time.time()
                    async with extract_semaphore:
                        extract_res = await loop.run_in_executor(extract_executor, _extract_segment_sync, video_path, t_start, t_end, idx)
                    t1 = time.time()

                    if not (isinstance(extract_res, dict) and extract_res.get("ok") and extract_res.get("img") is not None):
                        err = extract_res.get("error") if isinstance(extract_res, dict) else "invalid_result"
                        if err == "extract_frame_failed":
                            vision_segments.append(
                                {
                                    "start_time": float(t_start),
                                    "end_time": float(t_end),
                                    "status": "no_frame",
                                    "text": None,
                                    "frame_error": extract_res.get("frame_error") if isinstance(extract_res, dict) else None,
                                }
                            )
                        else:
                            vision_segments.append(
                                {
                                    "start_time": float(t_start),
                                    "end_time": float(t_end),
                                    "status": "error",
                                    "text": None,
                                    "error": str(err or "unknown_error"),
                                }
                            )
                        continue

                    if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError("任务已取消")

                    try:
                        logger.info(f"Moondream analyze: scene_idx={idx} segment={float(t_start):.3f}-{float(t_end):.3f}")
                        img = extract_res.get("img")
                        t2 = time.time()
                        out, md_stats = await loop.run_in_executor(infer_executor, _infer_segment_sync, img, prompt, idx, t_start, t_end)
                        t3 = time.time()
                        logger.info(
                            f"Moondream timing: scene_idx={idx} segment={float(t_start):.3f}-{float(t_end):.3f} extract_s={t1 - t0:.3f} infer_s={t3 - t2:.3f} total_s={t3 - t0:.3f} backend={md_stats.get('backend')} device={md_stats.get('device')} n_gpu_layers={md_stats.get('n_gpu_layers')} main_gpu={md_stats.get('main_gpu')} wait_s={float(md_stats.get('wait_s') or 0.0):.3f} compute_s={float(md_stats.get('compute_s') or 0.0):.3f} load_s={float(md_stats.get('load_s') or 0.0):.3f}"
                        )

                        txt = str(out or "").strip()
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "ok" if txt else "empty",
                                "text": txt if txt else None,
                            }
                        )
                    except Exception as e:
                        logger.error(f"Vision analysis failed for {t_start}-{t_end}: {e}")
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "error",
                                "text": None,
                                "error": str(e),
                            }
                        )
                        continue

            scene["vision"] = vision_segments

            has_ok = any(s.get("status") == "ok" and (s.get("text") or "").strip() for s in vision_segments)
            has_error = any(s.get("status") == "error" for s in vision_segments)
            has_no_frame = any(s.get("status") == "no_frame" for s in vision_segments)
            if has_ok:
                scene["vision_status"] = "ok"
            elif has_error:
                scene["vision_status"] = "error"
                last_err = next((s.get("error") for s in reversed(vision_segments) if s.get("status") == "error"), None)
                if last_err:
                    scene["vision_error"] = last_err
            elif has_no_frame:
                scene["vision_status"] = "no_frame"
                last_fe = next((s.get("frame_error") for s in reversed(vision_segments) if s.get("status") == "no_frame"), None)
                if last_fe:
                    scene["vision_frame_error"] = last_fe
            else:
                scene["vision_status"] = "empty"
            scene["vision_analyzed"] = True
            
            processed_count += 1
            
            if task_id:
                # Map 0 -> total_to_analyze to 90 -> 100
                progress = 90 + (processed_count / total_to_analyze) * 10
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=progress,
                    message=f"视觉分析中: {processed_count}/{total_to_analyze}",
                    phase="analyze_vision_infer"
                )

        tasks = []
        for idx in to_analyze_indices:
            tasks.append(asyncio.create_task(analyze_single_scene(idx)))

        try:
            if tasks:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=90,
                    message="开始视觉分析...",
                    phase="analyze_vision_start"
                )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, asyncio.CancelledError):
                        raise r

            remaining = [i for i in to_analyze_indices if not bool(scenes[i].get("vision_analyzed"))]
            if remaining:
                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")
                processed_count = total_to_analyze - len(remaining)
                for i in remaining:
                    await analyze_single_scene(i)

            return scenes
        finally:
            try:
                extract_executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                try:
                    extract_executor.shutdown(wait=True)
                except Exception:
                    pass
            try:
                infer_executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                try:
                    infer_executor.shutdown(wait=True)
                except Exception:
                    pass

vision_frame_analyzer = VisionFrameAnalyzer()
