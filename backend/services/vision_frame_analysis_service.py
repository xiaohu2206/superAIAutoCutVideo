import asyncio
import logging
import os
import threading
import multiprocessing
import queue
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import base64
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from modules.moondream_model_manager import MoondreamPathManager, validate_model_dir
from modules.task_progress_store import task_progress_store
from modules.task_cancel_store import task_cancel_store

logger = logging.getLogger(__name__)


def _resolve_moondream_n_gpu_layers() -> int:
    raw = str(os.environ.get("MOONDREAM_N_GPU_LAYERS") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except Exception:
        return 0


def _moondream_worker_main(model_dir: str, req_q: multiprocessing.Queue, resp_q: multiprocessing.Queue) -> None:
    try:
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MoondreamChatHandler
    except Exception as e:
        resp_q.put({"type": "fatal", "error": f"missing_dependency: {e}"})
        return

    md = Path(model_dir)
    clip_path = md / "moondream2-mmproj-f16.gguf"
    text_path = md / "moondream2-text-model-f16.gguf"
    if not clip_path.exists() or not text_path.exists():
        resp_q.put({"type": "fatal", "error": "Moondream 模型文件不完整，请重新下载并校验"})
        return

    n_gpu_layers = _resolve_moondream_n_gpu_layers()

    try:
        chat_handler = MoondreamChatHandler(clip_model_path=str(clip_path), verbose=False)
        model = Llama(
            model_path=str(text_path),
            chat_handler=chat_handler,
            n_ctx=2048,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
    except Exception as e:
        resp_q.put({"type": "fatal", "error": str(e)})
        return

    while True:
        try:
            msg = req_q.get()
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "shutdown":
            return
        req_id = msg.get("request_id")
        prompt = str(msg.get("prompt") or "Describe this image briefly.")
        img_b64 = str(msg.get("image_base64") or "")
        if not img_b64:
            resp_q.put({"type": "error", "request_id": req_id, "error": "image_base64 为空"})
            continue
        try:
            resp = model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ]
            )
            text = resp["choices"][0]["message"]["content"]
            resp_q.put({"type": "ok", "request_id": req_id, "text": text})
        except Exception as e:
            resp_q.put({"type": "error", "request_id": req_id, "error": str(e)})


class _MoondreamInferWorker:
    def __init__(self) -> None:
        self._ctx = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._process: Optional[multiprocessing.Process] = None
        self._req_q: Optional[multiprocessing.Queue] = None
        self._resp_q: Optional[multiprocessing.Queue] = None
        self._next_id = 1
        self._model_dir: Optional[str] = None

    def _ensure_started(self, model_dir: str) -> None:
        if self._process and self._process.is_alive() and self._model_dir == model_dir:
            return
        self._stop_locked()
        self._model_dir = model_dir
        self._req_q = self._ctx.Queue()
        self._resp_q = self._ctx.Queue()
        p = self._ctx.Process(target=_moondream_worker_main, args=(model_dir, self._req_q, self._resp_q), daemon=True)
        p.start()
        self._process = p

        try:
            first = self._resp_q.get(timeout=0.2)
            if isinstance(first, dict) and first.get("type") == "fatal":
                raise RuntimeError(str(first.get("error") or "Moondream 推理进程启动失败"))
            if first is not None:
                self._resp_q.put(first)
        except queue.Empty:
            pass

    def _stop_locked(self) -> None:
        p = self._process
        q = self._req_q
        if q is not None:
            try:
                q.put({"type": "shutdown"})
            except Exception:
                pass
        if p is not None:
            try:
                if p.is_alive():
                    p.terminate()
                p.join(timeout=0.5)
            except Exception:
                pass
        self._process = None
        self._req_q = None
        self._resp_q = None

    def infer(self, model_dir: str, image_base64: str, prompt: str, timeout_s: float = 60.0) -> str:
        with self._lock:
            self._ensure_started(model_dir)
            req_q = self._req_q
            resp_q = self._resp_q
            p = self._process
            if req_q is None or resp_q is None or p is None:
                raise RuntimeError("Moondream 推理进程未就绪")
            req_id = self._next_id
            self._next_id += 1
            req_q.put({"type": "infer", "request_id": req_id, "prompt": prompt, "image_base64": image_base64})
            try:
                resp = resp_q.get(timeout=timeout_s)
            except queue.Empty:
                alive = p.is_alive()
                self._stop_locked()
                raise RuntimeError("Moondream 推理超时" + ("" if alive else "（推理进程已退出，可能发生 native 崩溃）"))
            if not isinstance(resp, dict):
                raise RuntimeError("Moondream 推理返回异常")
            if resp.get("request_id") != req_id:
                raise RuntimeError("Moondream 推理返回不匹配")
            if resp.get("type") == "ok":
                return str(resp.get("text") or "")
            raise RuntimeError(str(resp.get("error") or "Moondream 推理失败"))


_moondream_infer_worker = _MoondreamInferWorker()


class VisionFrameAnalyzer:
    SCOPE = "extract_scene"

    def __init__(self):
        self._model = None
        self._model_lock = asyncio.Lock()
        self._path_manager = MoondreamPathManager()

    def _get_model(self):
        if self._model:
            return self._model

        model_dir = self._path_manager.model_path()
        ok, missing = validate_model_dir(model_dir)
        if not ok:
            raise RuntimeError(f"Moondream model missing files: {missing}")

        try:
            from llama_cpp import Llama, LlamaRAMCache
            from llama_cpp.llama_chat_format import MoondreamChatHandler
        except ModuleNotFoundError:
            raise RuntimeError(
                "缺少依赖 llama-cpp-python（Moondream 推理需要）。请在后端 Python 环境安装："
                "python -m pip install \"llama-cpp-python==0.2.90\""
            )

        logger.info(f"Loading Moondream model from {model_dir}")
        
        n_gpu_layers = _resolve_moondream_n_gpu_layers()

        clip_path = model_dir / "moondream2-mmproj-f16.gguf"
        text_path = model_dir / "moondream2-text-model-f16.gguf"
        if not clip_path.exists() or not text_path.exists():
            raise RuntimeError("Moondream 模型文件不完整，请重新下载并校验")

        chat_handler = MoondreamChatHandler(clip_model_path=str(clip_path), verbose=False)

        self._model = Llama(
            model_path=str(text_path),
            chat_handler=chat_handler,
            n_ctx=2048,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        return self._model

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
                        p = subprocess.run(
                            args,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=12,
                            check=False,
                        )
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

    def _image_to_base64(self, img: Image.Image) -> str:
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def infer_with_moondream(self, img: Image.Image, prompt: str = "Describe this image briefly.") -> str:
        optimized_img = self._optimize_image(img)
        
        base64_image = self._image_to_base64(optimized_img)

        model_dir = str(self._path_manager.model_path())
        return _moondream_infer_worker.infer(model_dir=model_dir, image_base64=base64_image, prompt=prompt)

    async def analyze_scenes(
        self, 
        project_id: str,
        video_path: str, 
        scenes: List[Dict[str, Any]], 
        mode: str = "no_subtitles",
        task_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze scenes using Moondream.
        mode: "no_subtitles" (default) or "all"
        """
        
        # Determine concurrency limit
        max_concurrency = os.environ.get("VISION_ANALYSIS_MAX_CONCURRENCY")
        semaphore = None
        if max_concurrency and max_concurrency.strip():
            try:
                val = int(max_concurrency)
                if val > 0:
                    semaphore = asyncio.Semaphore(val)
            except ValueError:
                pass

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
        
        # Define the synchronous processing function
        def _process_segment_sync(v_path, t_s, t_e):
            try:
                # Extract frame
                img, frame_err = self.extract_center_frame_with_reason(v_path, t_s, t_e)
                if not img:
                    return {"ok": False, "text": "", "error": "extract_frame_failed", "frame_error": frame_err}
                # Inference
                out = self.infer_with_moondream(img)
                return {"ok": True, "text": out or "", "error": None}
            except Exception as e:
                logger.error(f"Vision analysis failed for {t_s}-{t_e}: {e}")
                return {"ok": False, "text": "", "error": str(e)}

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

                res = await loop.run_in_executor(None, _process_segment_sync, video_path, t_start, t_end)
                if isinstance(res, dict) and res.get("ok"):
                    txt = str(res.get("text") or "").strip()
                    vision_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "status": "ok" if txt else "empty",
                            "text": txt if txt else None,
                        }
                    )
                elif isinstance(res, dict):
                    err = res.get("error")
                    if err == "extract_frame_failed":
                        vision_segments.append(
                            {
                                "start_time": float(t_start),
                                "end_time": float(t_end),
                                "status": "no_frame",
                                "text": None,
                                "frame_error": res.get("frame_error"),
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
                else:
                    vision_segments.append(
                        {
                            "start_time": float(t_start),
                            "end_time": float(t_end),
                            "status": "error",
                            "text": None,
                            "error": "invalid_result",
                        }
                    )

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
            if semaphore:
                async def sem_task(i=idx):
                    async with semaphore:
                        await analyze_single_scene(i)
                tasks.append(asyncio.create_task(sem_task()))
            else:
                tasks.append(asyncio.create_task(analyze_single_scene(idx)))

        # Execute
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

vision_frame_analyzer = VisionFrameAnalyzer()
