import asyncio
import json
import logging
import os
import re
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
from services.vision_scene_status import scene_vision_success_ok

logger = logging.getLogger(__name__)
WIN_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# 在线视觉大模型调用：失败后重试间隔（秒），共 3 次重试即最多 4 次请求
_ONLINE_VISION_INFER_RETRY_DELAYS_SEC: Tuple[float, float, float] = (1.0, 2.0, 3.0)
# 并发调用大模型：相邻两次发起请求的最小间隔（秒），减轻瞬时打满上游
_ONLINE_VISION_INFER_CONCURRENT_INTERVAL_SEC = 0.1


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

    async def infer_multi(
        self,
        images: List[Image.Image],
        prompt: str,
        max_tokens: int = 1024,
    ) -> Tuple[str, Dict[str, Any]]:
        if not images:
            raise ValueError("infer_multi 需要至少一张图片")
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{img_base64}"
            content.append({"type": "image_url", "image_url": {"url": data_uri}})
            

        t0 = time.time()
        resp = await self._provider_impl.chat_completion(
            [
                ChatMessage(
                    role="user",
                    content=content,
                )
            ],
            extra_params={"max_tokens": int(max_tokens)},
        )
        t1 = time.time()
        usage = (resp.usage or {}) if hasattr(resp, "usage") else {}

        stats = {
            "backend": "online",
            "provider": self._provider,
            "model": self._model_name,
            "infer_s": t1 - t0,
            "n_images": len(images),
            "prompt_tokens": int((usage or {}).get("prompt_tokens", 0) or 0),
            "completion_tokens": int((usage or {}).get("completion_tokens", 0) or 0),
            "total_tokens": int((usage or {}).get("total_tokens", 0) or 0),
        }

        return (resp.content or ""), stats


def _segment_key_frame_seek_times(t_start: float, t_end: float, count: int) -> List[float]:
    ts = float(t_start)
    te = float(t_end)
    if te < ts:
        ts, te = te, ts
    span = te - ts
    if count <= 1 or span <= 1e-6:
        return [(ts + te) / 2.0]
    if count >= 3:
        eps = min(0.05, span / 6.0)
        return [ts + eps, (ts + te) / 2.0, te - eps]
    return [(ts + te) / 2.0]


def _log_skip_existing_vision_analysis(
    project_id: str,
    scene_idx: int,
    scene: Dict[str, Any],
    mode: str,
    backend_label: str,
) -> None:
    """历史已合并视觉结果时跳过重复推理，便于排查与统计。"""
    try:
        tr = f"{float(scene.get('start_time')):.3f}-{float(scene.get('end_time')):.3f}"
    except (TypeError, ValueError):
        tr = "?"
    logger.info(
        "跳过重复视觉推理 (already analyzed): project_id=%s scene_idx=%s time_range=%s mode=%s vision_status=%s backend=%s",
        project_id,
        scene_idx,
        tr,
        mode,
        scene.get("vision_status"),
        backend_label,
    )


def _normalize_subtitle_for_vision(sub: Any) -> str:
    s = (str(sub).strip() if sub is not None else "") or ""
    if not s or s == "无":
        return "（本镜头无对白或未识别字幕）"
    return s


def _build_online_scene_analysis_prompt(subtitle_text: str, num_frames: int) -> str:
    sub = _normalize_subtitle_for_vision(subtitle_text)
    return f"""200字以内，描述这个影视画面，主体人物与动作、环境与背景、字幕与剧情暗示等信息（自然语言）。
    字幕：
    {sub}
    """


def _try_parse_vision_json(raw: str) -> Optional[Dict[str, Any]]:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    try:
        out = json.loads(s)
        return out if isinstance(out, dict) else None
    except Exception:
        pass
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        try:
            out = json.loads(s[i : j + 1])
            return out if isinstance(out, dict) else None
        except Exception:
            pass
    return None


def _vision_structured_to_display_text(d: Dict[str, Any]) -> str:
    desc = str(d.get("desc") or "").strip()
    objs = d.get("objects")
    if isinstance(objs, list):
        obj_str = "、".join(str(x).strip() for x in objs if str(x).strip())
    else:
        obj_str = str(objs or "").strip()
    action = str(d.get("action") or "").strip()
    scene = str(d.get("scene") or "").strip()
    emotion = str(d.get("emotion") or "").strip()
    lines: List[str] = []
    if desc:
        lines.append(f"画面：{desc}")
    if obj_str:
        lines.append(f"物体：{obj_str}")
    if action:
        lines.append(f"动作：{action}")
    if scene:
        lines.append(f"场景：{scene}")
    if emotion:
        lines.append(f"情绪：{emotion}")
    return "\n".join(lines)


def _parse_online_vision_model_output(raw: str) -> Tuple[Optional[Dict[str, Any]], str]:
    return None, (raw or "").strip()


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

    def _read_frame_from_capture(
        self,
        cap: cv2.VideoCapture,
        seek_t: float,
        mode: str,
        fps: float,
        frame_count: float,
    ) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
        fps_ok = fps > 0.0
        frame_count_ok = frame_count > 0.0
        fps_safe = float(fps) if fps_ok else 25.0

        try:
            if mode == "msec":
                ok_seek = cap.set(cv2.CAP_PROP_POS_MSEC, float(seek_t) * 1000.0)
                ret, frame = cap.read()
            else:
                target_frame = int(round(float(seek_t) * float(fps_safe)))
                if frame_count_ok:
                    target_frame = max(0, min(int(frame_count) - 1, target_frame))
                ok_seek = cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = cap.read()

            if (not ret) or frame is None:
                return None, {
                    "code": "read_failed",
                    "message": "读取帧失败",
                    "seek_mode": mode,
                    "seek_time": float(seek_t),
                    "fps": float(fps),
                    "frame_count": float(frame_count),
                    "seek_ok": bool(ok_seek),
                }

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame), None
        except Exception as e:
            return None, {
                "code": "cv2_exception",
                "message": str(e),
                "seek_mode": mode,
                "seek_time": float(seek_t),
            }

    def _extract_frames_with_cv2_with_reason(
        self, video_path: str, seek_times: List[float]
    ) -> Tuple[Optional[List[Image.Image]], Optional[Dict[str, Any]]]:
        if not seek_times:
            return [], None

        seek_times_normalized = [max(0.0, float(t)) for t in seek_times]
        last_err: Optional[Dict[str, Any]] = None

        for mode in ("msec", "frame"):
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                try:
                    cap.release()
                except Exception:
                    pass
                last_err = {"code": "open_failed", "message": "无法打开视频文件", "seek_mode": mode}
                continue

            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            images: List[Image.Image] = []

            try:
                for seek_t in seek_times_normalized:
                    img, err = self._read_frame_from_capture(cap, seek_t, mode, fps, frame_count)
                    if img is None:
                        last_err = err
                        images = []
                        break
                    images.append(img)
                if images:
                    return images, None
            finally:
                try:
                    cap.release()
                except Exception:
                    pass

        return None, last_err

    def _extract_frame_with_ffmpeg_with_reason(
        self, video_path: str, seek_t: float
    ) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
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

        ts = f"{float(seek_t):.3f}"
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

    def _extract_frames_ffmpeg_concurrent_with_reason(
        self, video_path: str, seek_times: List[float], max_workers: int
    ) -> Tuple[Optional[List[Image.Image]], Optional[Dict[str, Any]]]:
        if not seek_times:
            return [], None
        if not video_path:
            return None, {"code": "invalid_path", "message": "video_path 为空", "seek_times": seek_times}
        if not Path(video_path).exists():
            return None, {"code": "path_not_found", "message": "视频文件不存在", "video_path": video_path, "seek_times": seek_times}

        seek_times_normalized = [max(0.0, float(t)) for t in seek_times]
        workers = max(1, min(int(max_workers or 1), len(seek_times_normalized)))
        results: List[Optional[Image.Image]] = [None] * len(seek_times_normalized)
        first_error: Optional[Dict[str, Any]] = None
        lock = threading.Lock()

        def _extract_one(index: int, seek_t: float) -> None:
            nonlocal first_error
            img, err = self._extract_frame_with_ffmpeg_with_reason(video_path, seek_t)
            with lock:
                if img is not None:
                    results[index] = img
                    return
                if first_error is None:
                    merged = dict(err or {})
                    merged["code"] = merged.get("code") or "extract_frame_failed"
                    merged["seek_times"] = seek_times_normalized
                    merged["failed_seek_time"] = float(seek_t)
                    first_error = merged

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ffmpeg_frame_extract") as executor:
            futures = [
                executor.submit(_extract_one, index, seek_t)
                for index, seek_t in enumerate(seek_times_normalized)
            ]
            for future in futures:
                future.result()

        if first_error is not None:
            return None, first_error
        if any(img is None for img in results):
            return None, {
                "code": "extract_frame_failed",
                "message": "并发 ffmpeg 抽帧结果不完整",
                "seek_times": seek_times_normalized,
            }
        return [img for img in results if img is not None], None

    def extract_frame_at_time_with_reason(self, video_path: str, seek_time: float) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
        try:
            if not video_path:
                return None, {"code": "invalid_path", "message": "video_path 为空"}
            if not Path(video_path).exists():
                return None, {"code": "path_not_found", "message": "视频文件不存在", "video_path": video_path}

            seek_t = max(0.0, float(seek_time))
            images, cv_err = self._extract_frames_with_cv2_with_reason(video_path, [seek_t])
            if images:
                return images[0], None

            ff_img, ff_err = self._extract_frame_with_ffmpeg_with_reason(video_path, seek_t)
            if ff_img is not None:
                return ff_img, None

            return None, {
                "code": "extract_frame_failed",
                "message": "抽帧失败（cv2 与 ffmpeg 均失败）",
                "cv2": cv_err,
                "ffmpeg": ff_err,
            }
        except Exception as e:
            logger.error(f"Error extracting frame: {e}")
            return None, {"code": "exception", "message": str(e)}

    def extract_center_frame_with_reason(self, video_path: str, t_start: float, t_end: float) -> Tuple[Optional[Image.Image], Optional[Dict[str, Any]]]:
        seek_t = (float(t_start) + float(t_end)) / 2.0
        if seek_t < 0:
            seek_t = 0.0
        return self.extract_frame_at_time_with_reason(video_path, seek_t)

    def extract_center_frame(self, video_path: str, t_start: float, t_end: float) -> Optional[Image.Image]:
        img, _ = self.extract_center_frame_with_reason(video_path, t_start, t_end)
        return img

    def extract_segment_key_frames_with_reason(
        self, video_path: str, t_start: float, t_end: float, key_frame_count: int
    ) -> Tuple[Optional[List[Image.Image]], Optional[Dict[str, Any]]]:
        times = _segment_key_frame_seek_times(t_start, t_end, int(key_frame_count))
        ffmpeg_images, ffmpeg_err = self._extract_frames_ffmpeg_concurrent_with_reason(
            video_path,
            times,
            max_workers=max(1, len(times)),
        )
        if ffmpeg_images:
            return ffmpeg_images, None

        if not video_path:
            return None, {"code": "invalid_path", "message": "video_path 为空", "seek_times": times}
        if not Path(video_path).exists():
            return None, {"code": "path_not_found", "message": "视频文件不存在", "video_path": video_path, "seek_times": times}

        images, cv_err = self._extract_frames_with_cv2_with_reason(video_path, times)
        if images:
            return images, None

        merged = dict(ffmpeg_err or {})
        merged["code"] = merged.get("code") or "extract_frame_failed"
        merged["seek_times"] = times
        merged["t_start"] = float(t_start)
        merged["t_end"] = float(t_end)
        if cv_err is not None:
            merged["cv2"] = cv_err
        return None, merged

    def infer_with_moondream(self, img: Image.Image, prompt: str = "Describe this image briefly.", return_stats: bool = False):
        optimized_img = self._optimize_image(img)
        if return_stats:
            return self._moondream.infer_with_stats(optimized_img, prompt=prompt)
        return self._moondream.infer(optimized_img, prompt=prompt)

    def get_moondream_runtime_status(self) -> Dict[str, Any]:
        return self._moondream.get_runtime_status()

    async def _extract_scenes_online_frames(
        self,
        project_id: str,
        video_path: str,
        scenes: List[Dict[str, Any]],
        to_analyze_indices: List[int],
        task_id: Optional[str],
        extract_concurrency: int,
        vision_key_frames: int,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """先并发完成所有镜头的在线视觉抽帧。"""
        kf = int(vision_key_frames) if int(vision_key_frames) in (1, 3) else 1
        loop = asyncio.get_running_loop()
        total_to_analyze = len(to_analyze_indices)
        extract_done_count = 0

        def _update_extract_progress_state() -> None:
            if not task_id or total_to_analyze <= 0:
                return
            progress = 90 + (extract_done_count / total_to_analyze) * 5
            task_progress_store.set_state(
                scope=self.SCOPE,
                project_id=project_id,
                task_id=task_id,
                status="processing",
                progress=progress,
                message=f"在线视觉抽帧中: {extract_done_count}/{total_to_analyze}",
                phase="analyze_vision_online_extract",
            )

        extract_executor = ThreadPoolExecutor(max_workers=extract_concurrency, thread_name_prefix="online_vision_extract")

        def _extract_segment_sync(
            v_path: str, t_s: float, t_e: float, scene_idx: int, scheduled_at: float
        ):
            thread_start = time.time()
            queue_wait_sec = max(0.0, thread_start - float(scheduled_at))
            t_work0 = time.time()
            try:
                imgs, frame_err = self.extract_segment_key_frames_with_reason(v_path, t_s, t_e, kf)
                extract_work_sec = time.time() - t_work0
                base = {"queue_wait_sec": queue_wait_sec, "extract_work_sec": extract_work_sec}
                if not imgs:
                    return {
                        **base,
                        "ok": False,
                        "imgs": None,
                        "error": "extract_frame_failed",
                        "frame_error": frame_err,
                    }
                return {**base, "ok": True, "imgs": imgs, "error": None, "frame_error": None}
            except Exception as e:
                extract_work_sec = time.time() - t_work0
                logger.error("在线视觉抽帧失败：镜头%s，时间段%.3f-%.3f，错误=%s", scene_idx, float(t_s), float(t_e), e)
                return {
                    "queue_wait_sec": queue_wait_sec,
                    "extract_work_sec": extract_work_sec,
                    "ok": False,
                    "imgs": None,
                    "error": str(e),
                    "frame_error": None,
                }

        async def extract_single_scene_online(idx: int) -> Dict[str, Any]:
            nonlocal extract_done_count
            if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")

            scene = scenes[idx]
            merged_from = scene.get("merged_from", [])
            segments = merged_from if merged_from else [{"start_time": scene["start_time"], "end_time": scene["end_time"]}]
            extracted_segments: List[Dict[str, Any]] = []

            for seg_idx, seg in enumerate(segments, start=1):
                if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError("任务已取消")

                t_start = seg["start_time"]
                t_end = seg["end_time"]
                t0 = time.time()
                logger.info(
                    "在线视觉抽帧开始：镜头%s，分段%s/%s，时间段%.3f-%.3f",
                    idx,
                    seg_idx,
                    len(segments),
                    float(t_start),
                    float(t_end),
                )
                extract_res = await loop.run_in_executor(
                    extract_executor,
                    _extract_segment_sync,
                    video_path,
                    t_start,
                    t_end,
                    idx,
                    t0,
                )
                t1 = time.time()
                extract_elapsed = t1 - t0
                imgs = extract_res.get("imgs") if isinstance(extract_res, dict) else None
                q_wait = float(extract_res.get("queue_wait_sec") or 0) if isinstance(extract_res, dict) else 0.0
                ex_work = float(extract_res.get("extract_work_sec") or 0) if isinstance(extract_res, dict) else 0.0

                if isinstance(extract_res, dict) and extract_res.get("ok") and isinstance(imgs, list) and len(imgs) > 0:
                    logger.info(
                        "在线视觉抽帧完成：镜头%s，分段%s/%s，时间段%.3f-%.3f，排队%.3fs，抽帧执行%.3fs，合计%.3fs，帧数=%s",
                        idx,
                        seg_idx,
                        len(segments),
                        float(t_start),
                        float(t_end),
                        q_wait,
                        ex_work,
                        extract_elapsed,
                        len(imgs),
                    )
                    extracted_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "extract_status": "ok",
                            "imgs": imgs,
                            "queue_wait_sec": q_wait,
                            "extract_work_sec": ex_work,
                            "extract_elapsed_sec": extract_elapsed,
                            "frame_error": None,
                            "error": None,
                        }
                    )
                else:
                    err = extract_res.get("error") if isinstance(extract_res, dict) else "invalid_result"
                    logger.warning(
                        "在线视觉抽帧结果异常：镜头%s，分段%s/%s，时间段%.3f-%.3f，排队%.3fs，抽帧执行%.3fs，合计%.3fs，错误=%s",
                        idx,
                        seg_idx,
                        len(segments),
                        float(t_start),
                        float(t_end),
                        q_wait,
                        ex_work,
                        extract_elapsed,
                        err,
                    )
                    extracted_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "extract_status": "no_frame" if err == "extract_frame_failed" else "error",
                            "imgs": None,
                            "queue_wait_sec": q_wait,
                            "extract_work_sec": ex_work,
                            "extract_elapsed_sec": extract_elapsed,
                            "frame_error": extract_res.get("frame_error") if isinstance(extract_res, dict) else None,
                            "error": None if err == "extract_frame_failed" else str(err or "unknown_error"),
                        }
                    )

            extract_done_count += 1
            logger.info(
                "在线视觉抽帧进度：已完成%s/%s个镜头",
                extract_done_count,
                total_to_analyze,
            )
            _update_extract_progress_state()
            return {"idx": idx, "segments": extracted_segments}

        try:
            logger.info("在线视觉分析阶段一开始：并发抽帧。")
            _update_extract_progress_state()
            extract_results = await asyncio.gather(
                *(extract_single_scene_online(idx) for idx in to_analyze_indices),
                return_exceptions=True,
            )

            extracted_by_scene: Dict[int, List[Dict[str, Any]]] = {}
            for r in extract_results:
                if isinstance(r, asyncio.CancelledError):
                    raise r
                if isinstance(r, Exception):
                    logger.error("在线视觉抽帧任务失败：%s", r)
                    continue
                extracted_by_scene[r["idx"]] = r["segments"]

            logger.info(
                "在线视觉分析阶段一结束：抽帧完成，成功收集%s/%s个镜头的抽帧结果。",
                len(extracted_by_scene),
                total_to_analyze,
            )
            return extracted_by_scene
        finally:
            try:
                extract_executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                try:
                    extract_executor.shutdown(wait=True)
                except Exception:
                    pass

    async def _infer_scenes_online_from_frames(
        self,
        project_id: str,
        scenes: List[Dict[str, Any]],
        to_analyze_indices: List[int],
        extracted_by_scene: Dict[int, List[Dict[str, Any]]],
        online_runner: Any,
        provider: str,
        model_name: str,
        infer_wall_sec: float,
        api_concurrency: int,
        task_id: Optional[str],
    ) -> bool:
        """使用已抽取好的帧并发调用在线视觉模型。"""
        total_to_analyze = len(to_analyze_indices)
        processed_count = 0
        stop_infer_all = asyncio.Event()
        infer_semaphore = asyncio.Semaphore(api_concurrency)
        infer_start_lock = asyncio.Lock()
        infer_last_start_mono = 0.0

        async def _pace_online_infer_start() -> None:
            nonlocal infer_last_start_mono
            async with infer_start_lock:
                now = time.monotonic()
                gap = _ONLINE_VISION_INFER_CONCURRENT_INTERVAL_SEC - (now - infer_last_start_mono)
                if gap > 0:
                    await asyncio.sleep(gap)
                infer_last_start_mono = time.monotonic()

        def _finalize_scene_vision(scene: Dict[str, Any], vision_segments: List[Dict[str, Any]], bump_progress: bool) -> None:
            nonlocal processed_count
            scene["vision"] = vision_segments
            has_ok = any(s.get("status") == "ok" and (s.get("text") or "").strip() for s in vision_segments)
            has_timeout = any(s.get("status") == "infer_timeout" for s in vision_segments)
            has_error = any(s.get("status") == "error" for s in vision_segments)
            has_no_frame = any(s.get("status") == "no_frame" for s in vision_segments)
            if has_ok:
                scene["vision_status"] = "ok"
            elif has_timeout:
                scene["vision_status"] = "infer_timeout"
                last_te = next(
                    (s.get("error") for s in reversed(vision_segments) if s.get("status") == "infer_timeout"),
                    None,
                )
                if last_te:
                    scene["vision_error"] = last_te
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
            if not bump_progress:
                return
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
                    phase="analyze_vision_online",
                )

        async def infer_single_scene_online(idx: int, extracted_segments: List[Dict[str, Any]]):
            if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                raise asyncio.CancelledError("任务已取消")
            if stop_infer_all.is_set():
                return

            scene = scenes[idx]
            subtitle_for_scene = scene.get("subtitle")
            vision_segments: List[Dict[str, Any]] = []

            try:
                for seg_idx, seg in enumerate(extracted_segments, start=1):
                    if stop_infer_all.is_set():
                        break
                    if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError("任务已取消")

                    t_start = seg["start_time"]
                    t_end = seg["end_time"]
                    imgs = seg.get("imgs")
                    q_wait = float(seg.get("queue_wait_sec") or 0)
                    ex_work = float(seg.get("extract_work_sec") or 0)
                    extract_elapsed = float(seg.get("extract_elapsed_sec") or 0)
                    extract_status = seg.get("extract_status")

                    if extract_status != "ok" or not isinstance(imgs, list) or len(imgs) == 0:
                        if extract_status == "no_frame":
                            vision_segments.append(
                                {
                                    "start_time": float(t_start),
                                    "end_time": float(t_end),
                                    "status": "no_frame",
                                    "text": None,
                                    "frame_error": seg.get("frame_error"),
                                }
                            )
                        else:
                            vision_segments.append(
                                {
                                    "start_time": float(t_start),
                                    "end_time": float(t_end),
                                    "status": "error",
                                    "text": None,
                                    "error": str(seg.get("error") or "unknown_error"),
                                }
                            )
                        continue

                    try:
                        optimized_imgs = [self._optimize_image(im, max_edge=1024) for im in imgs]
                        prompt = _build_online_scene_analysis_prompt(subtitle_for_scene, len(optimized_imgs))

                        retry_delays = _ONLINE_VISION_INFER_RETRY_DELAYS_SEC
                        max_attempts = 1 + len(retry_delays)
                        out: Optional[str] = None
                        online_stats: Dict[str, Any] = {}
                        t2 = 0.0
                        t3 = 0.0
                        last_fail: Optional[BaseException] = None
                        last_was_timeout = False

                        for attempt in range(max_attempts):
                            if stop_infer_all.is_set():
                                break
                            if task_id and task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError("任务已取消")
                            try:
                                await _pace_online_infer_start()
                                async with infer_semaphore:
                                    if stop_infer_all.is_set():
                                        break
                                    logger.info(
                                        "在线视觉分析发起调用：镜头%s，分段%s/%s，时间段%.3f-%.3f，当前大模型并发上限=%s，第%s/%s次",
                                        idx,
                                        seg_idx,
                                        len(extracted_segments),
                                        float(t_start),
                                        float(t_end),
                                        api_concurrency,
                                        attempt + 1,
                                        max_attempts,
                                    )
                                    t2 = time.time()
                                    out, online_stats = await asyncio.wait_for(
                                        online_runner.infer_multi(optimized_imgs, prompt=prompt),
                                        timeout=infer_wall_sec,
                                    )
                                    t3 = time.time()
                                last_fail = None
                                break
                            except asyncio.TimeoutError as te:
                                last_fail = te
                                last_was_timeout = True
                                if attempt < max_attempts - 1:
                                    logger.warning(
                                        "在线视觉分析超时：镜头%s，分段%s/%s，时间段%.3f-%.3f，%.1fs 后重试 (%s/%s)，超时阈值%s秒",
                                        idx,
                                        seg_idx,
                                        len(extracted_segments),
                                        float(t_start),
                                        float(t_end),
                                        retry_delays[attempt],
                                        attempt + 1,
                                        max_attempts - 1,
                                        infer_wall_sec,
                                    )
                                    await asyncio.sleep(retry_delays[attempt])
                            except Exception as e:
                                last_fail = e
                                last_was_timeout = False
                                if attempt < max_attempts - 1:
                                    logger.warning(
                                        "在线视觉分析失败：镜头%s，分段%s/%s，时间段%.3f-%.3f，%.1fs 后重试 (%s/%s)，错误=%s",
                                        idx,
                                        seg_idx,
                                        len(extracted_segments),
                                        float(t_start),
                                        float(t_end),
                                        retry_delays[attempt],
                                        attempt + 1,
                                        max_attempts - 1,
                                        e,
                                    )
                                    await asyncio.sleep(retry_delays[attempt])

                        if out is None:
                            if last_fail is not None:
                                if last_was_timeout:
                                    msg = f"单次模型调用超过{int(infer_wall_sec)}秒未返回，已中止其余视觉分析"
                                    logger.warning(
                                        "在线视觉分析超时：镜头%s，分段%s/%s，时间段%.3f-%.3f，超时阈值%s秒（已重试%s次），已停止后续批次调用",
                                        idx,
                                        seg_idx,
                                        len(extracted_segments),
                                        float(t_start),
                                        float(t_end),
                                        infer_wall_sec,
                                        len(retry_delays),
                                    )
                                    vision_segments.append(
                                        {
                                            "start_time": float(t_start),
                                            "end_time": float(t_end),
                                            "status": "infer_timeout",
                                            "text": None,
                                            "error": msg,
                                        }
                                    )
                                    stop_infer_all.set()
                                    scene["vision_stopped_early_infer_timeout"] = True
                                    _finalize_scene_vision(scene, vision_segments, bump_progress=True)
                                    return
                                logger.error(
                                    "在线视觉分析失败：镜头%s，分段%s/%s，时间段%.3f-%.3f，错误=%s",
                                    idx,
                                    seg_idx,
                                    len(extracted_segments),
                                    float(t_start),
                                    float(t_end),
                                    last_fail,
                                )
                                vision_segments.append(
                                    {
                                        "start_time": float(t_start),
                                        "end_time": float(t_end),
                                        "status": "error",
                                        "text": None,
                                        "error": str(last_fail),
                                    }
                                )
                                continue
                            break

                        logger.info(
                            "在线视觉分析完成：镜头%s，分段%s/%s，时间段%.3f-%.3f，抽帧(排队%.3fs+执行%.3fs=%.3fs)，推理%.3fs，总耗时%.3fs，provider=%s，model=%s，图片数=%s",
                            idx,
                            seg_idx,
                            len(extracted_segments),
                            float(t_start),
                            float(t_end),
                            q_wait,
                            ex_work,
                            extract_elapsed,
                            t3 - t2,
                            extract_elapsed + (t3 - t2),
                            provider,
                            model_name,
                            online_stats.get("n_images"),
                        )

                        _, display_text = _parse_online_vision_model_output(str(out or ""))
                        txt = (display_text or "").strip()
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "ok" if txt else "empty",
                                "text": txt if txt else None,
                            }
                        )
                    except Exception as e:
                        logger.error("在线视觉分析失败：镜头%s，分段%s/%s，时间段%.3f-%.3f，错误=%s", idx, seg_idx, len(extracted_segments), float(t_start), float(t_end), e)
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

                if vision_segments:
                    _finalize_scene_vision(scene, vision_segments, bump_progress=True)
            except asyncio.CancelledError:
                if vision_segments:
                    _finalize_scene_vision(scene, vision_segments, bump_progress=True)
                raise

        logger.info("在线视觉分析阶段二开始：并发调用大模型。")
        results = await asyncio.gather(
            *(infer_single_scene_online(idx, extracted_by_scene.get(idx, [])) for idx in to_analyze_indices),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, asyncio.CancelledError):
                if stop_infer_all.is_set():
                    continue
                raise r
            if isinstance(r, Exception):
                logger.error("在线视觉分析任务失败：%s", r)

        return stop_infer_all.is_set()

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
        max_concurrency: int = 128,
        vision_key_frames: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Analyze scenes using online vision models (302ai, yunwu, etc.).
        mode: "no_subtitles" or "all"
        vision_key_frames: 1 或 3，每个镜头时间段抽取的关键帧数量，多帧按时间顺序一并送入模型。
        max_concurrency: 兼容旧参数；抽帧默认 8 并发，API 调用默认 32 并发，都会受该参数上限约束。
        """
        try:
            infer_wall_sec = float(str(os.environ.get("VISION_ONLINE_INFER_TIMEOUT_SEC") or "").strip() or "300")
        except Exception:
            infer_wall_sec = 300.0
        if infer_wall_sec < 1.0:
            infer_wall_sec = 300.0

        effective_http_timeout = max(int(timeout or 0), int(infer_wall_sec + 0.999))
        online_runner = await self._get_online_runner(
            provider, api_key, base_url, model_name, effective_http_timeout
        )

        concurrency_cap = max(1, int(max_concurrency or 1))
        extract_concurrency = min(8, concurrency_cap)
        api_concurrency = min(64, concurrency_cap)

        to_analyze_indices = []
        for idx, scene in enumerate(scenes):
            should_analyze = False
            if mode == "all":
                should_analyze = True
            elif mode == "no_subtitles":
                sub = scene.get("subtitle")
                if not sub or sub == "无":
                    should_analyze = True
            if not should_analyze:
                continue
            if scene_vision_success_ok(scene):
                _log_skip_existing_vision_analysis(project_id, idx, scene, mode, str(provider or "online"))
                continue
            to_analyze_indices.append(idx)

        total_to_analyze = len(to_analyze_indices)
        if total_to_analyze == 0:
            return scenes

        waiting_count = max(0, total_to_analyze - api_concurrency)
        logger.info(
            "在线视觉分析准备开始：待分析%s个镜头，抽帧并发=%s，大模型并发=%s，预计首批调用%s个，剩余%s个等待下一批",
            total_to_analyze,
            extract_concurrency,
            api_concurrency,
            min(total_to_analyze, api_concurrency),
            waiting_count,
        )
        logger.info(
            "在线视觉分析已切换为两阶段执行：先并发抽帧，再并发调用大模型。"
        )

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="processing",
            progress=90,
            message="开始在线视觉分析...",
            phase="analyze_vision_online_start"
        )

        logger.info(
            "在线视觉分析开始：待处理镜头=%s，抽帧并发=%s，大模型并发=%s",
            total_to_analyze,
            extract_concurrency,
            api_concurrency,
        )

        extracted_by_scene = await self._extract_scenes_online_frames(
            project_id=project_id,
            video_path=video_path,
            scenes=scenes,
            to_analyze_indices=to_analyze_indices,
            task_id=task_id,
            extract_concurrency=extract_concurrency,
            vision_key_frames=vision_key_frames,
        )

        stopped_early = await self._infer_scenes_online_from_frames(
            project_id=project_id,
            scenes=scenes,
            to_analyze_indices=to_analyze_indices,
            extracted_by_scene=extracted_by_scene,
            online_runner=online_runner,
            provider=provider,
            model_name=model_name,
            infer_wall_sec=infer_wall_sec,
            api_concurrency=api_concurrency,
            task_id=task_id,
        )

        if stopped_early:
            if task_id:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=95,
                    message=f"单次模型调用超过{int(infer_wall_sec)}秒未返回，已保存已完成的视觉分析，跳过剩余镜头",
                    phase="analyze_vision_online_timeout_partial",
                )

        return scenes

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

            if not should_analyze:
                continue
            if scene_vision_success_ok(scene):
                _log_skip_existing_vision_analysis(project_id, idx, scene, mode, "moondream")
                continue
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

            remaining = [i for i in to_analyze_indices if not scene_vision_success_ok(scenes[i])]
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
