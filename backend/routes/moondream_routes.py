import logging
import platform
import subprocess
import asyncio
import multiprocessing
import os
import threading
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from modules.moondream_model_manager import MoondreamPathManager, validate_model_dir, download_model_snapshot
from services.vision_frame_analysis_service import vision_frame_analyzer
from modules.app_paths import user_data_dir
from modules.ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vision/moondream", tags=["Moondream"])

class ValidateRequest(BaseModel):
    key: str = "moondream2_gguf"

class TestRequest(BaseModel):
    prompt: str = "Describe this image."

class DownloadRequest(BaseModel):
    provider: str = "modelscope"

class StopDownloadRequest(BaseModel):
    key: str = "moondream2_gguf"

_download_tasks: Dict[str, asyncio.Task] = {}
_download_states: Dict[str, Dict[str, Any]] = {}
_download_lock = asyncio.Lock()
_download_processes: Dict[str, multiprocessing.Process] = {}
_download_result_queues: Dict[str, multiprocessing.Queue] = {}

# Background task logic (similar to FunASR)
def _download_worker(target_dir: str, provider: str, result_queue: multiprocessing.Queue) -> None:
    stop_event = threading.Event()
    target_path = Path(target_dir)
    
    # Estimate total size (~3.8GB)
    total_bytes = 3.8 * 1024 * 1024 * 1024

    def calc_dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except Exception:
                    continue
        return total

    def report_progress() -> None:
        last_reported = -1
        while not stop_event.is_set():
            current = calc_dir_size(target_path)
            if current != last_reported:
                result_queue.put({
                    "type": "progress",
                    "downloaded_bytes": current,
                    "total_bytes": total_bytes
                })
                last_reported = current
            time.sleep(1.0)

    progress_thread = threading.Thread(target=report_progress, daemon=True)
    progress_thread.start()

    try:
        download_model_snapshot(target_path, provider)
        stop_event.set()
        progress_thread.join(timeout=2)
        result_queue.put({"type": "completed"})
    except Exception as e:
        stop_event.set()
        result_queue.put({"type": "error", "error": str(e)})

async def _run_download_monitor(key: str, provider: str, target_dir: str):
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_download_worker, args=(target_dir, provider, q))
    p.start()
    
    async with _download_lock:
        _download_processes[key] = p
        _download_result_queues[key] = q

    loop = asyncio.get_running_loop()
    
    try:
        while True:
            # Non-blocking check
            try:
                msg = await loop.run_in_executor(None, lambda: q.get(timeout=1.0))
            except Exception: # Empty
                if not p.is_alive():
                    # Process died unexpectedly?
                    if p.exitcode != 0:
                        raise RuntimeError(f"Download process exited with code {p.exitcode}")
                    break
                continue

            msg_type = msg.get("type")
            if msg_type == "progress":
                async with _download_lock:
                    st = _download_states.get(key)
                    if st:
                        st["downloaded_bytes"] = msg.get("downloaded_bytes")
                        st["total_bytes"] = msg.get("total_bytes")
                        # Calculate percentage
                        if st["total_bytes"]:
                            st["progress"] = (st["downloaded_bytes"] / st["total_bytes"]) * 100
                # Broadcast
                await manager.broadcast(json.dumps({
                    "type": "progress",
                    "scope": "moondream_download",
                    "key": key,
                    "progress": _download_states[key]["progress"],
                    "downloaded_bytes": _download_states[key]["downloaded_bytes"],
                    "total_bytes": _download_states[key]["total_bytes"],
                    "message": "正在下载..."
                }))
            elif msg_type == "completed":
                async with _download_lock:
                    st = _download_states.get(key)
                    if st:
                        st["status"] = "completed"
                        st["progress"] = 100
                        st["message"] = "下载完成"
                await manager.broadcast(json.dumps({
                    "type": "completed",
                    "scope": "moondream_download",
                    "key": key,
                    "message": "下载完成"
                }))
                break
            elif msg_type == "error":
                raise RuntimeError(msg.get("error"))
    except asyncio.CancelledError:
        p.terminate()
        p.join()
        async with _download_lock:
            st = _download_states.get(key)
            if st:
                st["status"] = "cancelled"
                st["message"] = "已取消"
        await manager.broadcast(json.dumps({
            "type": "cancelled",
            "scope": "moondream_download",
            "key": key,
            "message": "下载已取消"
        }))
    except Exception as e:
        logger.error(f"Download failed: {e}")
        async with _download_lock:
            st = _download_states.get(key)
            if st:
                st["status"] = "failed"
                st["message"] = str(e)
        await manager.broadcast(json.dumps({
            "type": "error",
            "scope": "moondream_download",
            "key": key,
            "message": str(e)
        }))
    finally:
        async with _download_lock:
            if key in _download_processes:
                del _download_processes[key]
            if key in _download_result_queues:
                del _download_result_queues[key]
            if key in _download_tasks:
                del _download_tasks[key]

@router.get("/models")
async def list_models() -> Dict[str, Any]:
    pm = MoondreamPathManager()
    status = pm.get_status()
    # Return a list for extensibility
    data = [
        {
            "key": status.key,
            "path": status.path,
            "exists": status.exists,
            "valid": status.valid,
            "missing": status.missing,
            "display_name": status.display_name,
            "description": status.description,
        }
    ]
    return {"success": True, "data": data, "message": "ok"}

@router.post("/models/validate")
async def validate_model(req: ValidateRequest) -> Dict[str, Any]:
    pm = MoondreamPathManager()
    status = pm.get_status()
    return {"success": True, "data": {"key": status.key, "path": status.path, "valid": status.valid, "missing": status.missing}}

@router.post("/models/download")
async def download_model(req: DownloadRequest) -> Dict[str, Any]:
    pm = MoondreamPathManager()
    target_dir = pm.model_path()
    key = "moondream2_gguf"
    
    async with _download_lock:
        if key in _download_tasks and not _download_tasks[key].done():
             return {"success": True, "data": _download_states.get(key), "message": "下载任务已在运行"}
        
        _download_states[key] = {
            "key": key,
            "provider": req.provider,
            "status": "running",
            "progress": 0,
            "downloaded_bytes": 0,
            "total_bytes": 3.8 * 1024 * 1024 * 1024, # Est
            "message": "开始下载..."
        }
        
        task = asyncio.create_task(_run_download_monitor(key, req.provider, str(target_dir)))
        _download_tasks[key] = task
        
    return {"success": True, "data": _download_states[key], "message": "下载任务已启动"}

@router.get("/models/downloads")
async def list_downloads() -> Dict[str, Any]:
    async with _download_lock:
        # Only running tasks
        tasks = [v for k, v in _download_states.items() if _download_tasks.get(k) and not _download_tasks[k].done()]
    return {"success": True, "data": tasks, "message": "ok"}

@router.post("/models/downloads/stop")
async def stop_download(req: StopDownloadRequest) -> Dict[str, Any]:
    async with _download_lock:
        task = _download_tasks.get(req.key)
        if task:
            task.cancel()
            return {"success": True, "message": "已请求停止"}
    return {"success": False, "message": "任务未运行"}

@router.get("/models/open-path")
async def open_model_path() -> Dict[str, Any]:
    try:
        pm = MoondreamPathManager()
        model_path = pm.model_path()
        target_dir = model_path if model_path.exists() else model_path.parent
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            
        sysname = platform.system().lower()
        if "windows" in sysname:
            subprocess.Popen(["explorer", str(target_dir)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif "darwin" in sysname:
            subprocess.Popen(["open", str(target_dir)])
        else:
            subprocess.Popen(["xdg-open", str(target_dir)])
        return {"success": True, "data": {"path": str(target_dir)}, "message": "已打开文件管理器"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_model(req: TestRequest) -> Dict[str, Any]:
    try:
        # Create a dummy image
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (256, 256), color = (100, 150, 200))
        d = ImageDraw.Draw(img)
        d.rectangle([50, 50, 200, 200], fill=(255, 200, 0))
        
        result = vision_frame_analyzer.infer_with_moondream(img, req.prompt)
        return {"success": True, "data": {"text": result}, "message": "测试成功"}
    except Exception as e:
        logger.error(f"Moondream test failed: {e}")
        msg = str(e)
        if "llama-cpp-python" in msg or "llama_cpp" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=500, detail=str(e))
