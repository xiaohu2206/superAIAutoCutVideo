import asyncio
import json
import multiprocessing
import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from modules.fun_asr_acceleration import get_fun_asr_acceleration_status
from modules.fun_asr_model_manager import (
    FUN_ASR_MODEL_REGISTRY,
    FunASRPathManager,
    download_model_snapshot,
    validate_model_dir,
    get_model_total_bytes,
)
from modules.fun_asr_service import fun_asr_service
from modules.ws_manager import manager


router = APIRouter(prefix="/api/asr/funasr", tags=["FunASR"])


@router.get("/acceleration-status")
async def get_fun_asr_acceleration() -> Dict[str, Any]:
    data = {
        "acceleration": get_fun_asr_acceleration_status(),
        "runtime": fun_asr_service.get_runtime_status(),
    }
    return {"success": True, "data": data, "message": "ok"}


_download_tasks: Dict[str, asyncio.Task] = {}
_download_states: Dict[str, Dict[str, Any]] = {}
_download_lock = asyncio.Lock()
_download_processes: Dict[str, multiprocessing.Process] = {}
_download_result_queues: Dict[str, multiprocessing.Queue] = {}


async def _broadcast_download_event(payload: Dict[str, Any]) -> None:
    try:
        await manager.broadcast(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


async def _update_download_state(key: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    async with _download_lock:
        current = _download_states.get(key, {"key": key})
        current.update(updates)
        _download_states[key] = current
        return current


async def _remove_download_task(key: str) -> None:
    async with _download_lock:
        _download_tasks.pop(key, None)
        _download_processes.pop(key, None)
        _download_result_queues.pop(key, None)


def _download_worker(key: str, provider: str, target_dir: str, result_queue: multiprocessing.Queue) -> None:
    total_bytes = get_model_total_bytes(key, provider)
    stop_event = threading.Event()
    target_path = Path(target_dir)

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
                result_queue.put(
                    {
                        "type": "progress",
                        "key": key,
                        "provider": provider,
                        "downloaded_bytes": current,
                        "total_bytes": total_bytes,
                    }
                )
                last_reported = current
            time.sleep(0.5)

    reporter = threading.Thread(target=report_progress, daemon=True)
    reporter.start()
    try:
        ret = download_model_snapshot(key, provider, Path(target_dir))
        result_queue.put({"type": "result", "ok": True, "data": ret})
    except Exception as e:
        result_queue.put({"type": "result", "ok": False, "error": str(e)})
    finally:
        stop_event.set()
        reporter.join(timeout=1)


async def _run_download_task(key: str, provider: str) -> None:
    pm = FunASRPathManager()
    target_dir = pm.model_path(key)
    total_bytes = get_model_total_bytes(key, provider)
    resolved_total_bytes = total_bytes if total_bytes is not None else 0
    await _update_download_state(
        key,
        {
            "key": key,
            "provider": provider,
            "status": "running",
            "phase": "download_start",
            "progress": 1,
            "message": f"开始下载模型 {key}",
            "downloaded_bytes": 0,
            "total_bytes": resolved_total_bytes,
        },
    )
    await _broadcast_download_event(
        {
            "type": "progress",
            "scope": "fun_asr_models",
            "project_id": None,
            "phase": "download_start",
            "message": f"开始下载模型 {key}",
            "progress": 1,
            "model_key": key,
            "provider": provider,
            "downloaded_bytes": 0,
            "total_bytes": resolved_total_bytes,
        }
    )
    async with _download_lock:
        if _download_states.get(key, {}).get("status") == "stopped":
            return
        result_queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_download_worker,
            args=(key, provider, str(target_dir), result_queue),
            daemon=True,
        )
        _download_processes[key] = proc
        _download_result_queues[key] = result_queue
        proc.start()
    try:
        result = None
        while True:
            if _download_states.get(key, {}).get("status") in {"stopped", "cancelled"}:
                return
            drained = False
            try:
                while True:
                    msg = result_queue.get_nowait()
                    drained = True
                    if isinstance(msg, dict) and msg.get("type") == "progress":
                        downloaded_bytes = msg.get("downloaded_bytes")
                        total_bytes_msg = msg.get("total_bytes")

                        if not isinstance(downloaded_bytes, (int, float)):
                            downloaded_bytes = 0

                        prev_state = _download_states.get(key, {})
                        prev_progress = prev_state.get("progress", 1) or 1
                        prev_total = prev_state.get("total_bytes")

                        reliable_total = None
                        if isinstance(total_bytes_msg, (int, float)) and total_bytes_msg >= 1024 * 1024:
                            reliable_total = total_bytes_msg
                        elif isinstance(prev_total, (int, float)) and prev_total >= 1024 * 1024:
                            reliable_total = prev_total

                        used_fallback = False
                        if reliable_total is not None:
                            resolved_total_bytes = reliable_total
                            if isinstance(downloaded_bytes, (int, float)) and downloaded_bytes > resolved_total_bytes:
                                used_fallback = True
                                resolved_total_bytes = downloaded_bytes
                        else:
                            used_fallback = True
                            if isinstance(prev_total, (int, float)) and prev_total > 0:
                                if isinstance(downloaded_bytes, (int, float)):
                                    resolved_total_bytes = max(prev_total, downloaded_bytes)
                                else:
                                    resolved_total_bytes = prev_total
                            elif isinstance(downloaded_bytes, (int, float)):
                                resolved_total_bytes = downloaded_bytes
                            else:
                                resolved_total_bytes = 0

                        progress = None
                        if isinstance(resolved_total_bytes, (int, float)) and resolved_total_bytes > 0:
                            if not used_fallback and isinstance(downloaded_bytes, (int, float)):
                                ratio = downloaded_bytes / resolved_total_bytes * 100
                                progress = min(99, max(0, ratio))
                            else:
                                inc = 1
                                if prev_progress < 20:
                                    inc = 5
                                elif prev_progress < 50:
                                    inc = 3
                                elif prev_progress < 80:
                                    inc = 2
                                progress = min(95, max(prev_progress, prev_progress + inc))

                        state = await _update_download_state(
                            key,
                            {
                                "status": "running",
                                "phase": "download_running",
                                "progress": progress if progress is not None else prev_progress,
                                "message": "下载中…",
                                "downloaded_bytes": downloaded_bytes,
                                "total_bytes": resolved_total_bytes,
                            },
                        )
                        await _broadcast_download_event(
                            {
                                "type": "progress",
                                "scope": "fun_asr_models",
                                "project_id": None,
                                "phase": state.get("phase"),
                                "message": state.get("message"),
                                "progress": state.get("progress"),
                                "model_key": key,
                                "provider": provider,
                                "downloaded_bytes": downloaded_bytes,
                                "total_bytes": resolved_total_bytes,
                            }
                        )
                    elif isinstance(msg, dict) and msg.get("type") == "result":
                        result = msg
            except Exception:
                pass
            if result and not proc.is_alive():
                break
            if proc.is_alive():
                await asyncio.sleep(0.4)
            elif not drained:
                await asyncio.sleep(0.1)

        if not result or not result.get("ok"):
            detail = result.get("error") if isinstance(result, dict) else f"process_exit_{proc.exitcode}"
            raise RuntimeError(detail or "download_failed")

        ok, missing = validate_model_dir(key, target_dir)
        payload = {
            "type": "completed" if ok else "error",
            "scope": "fun_asr_models",
            "project_id": None,
            "phase": "download_done",
            "message": f"模型 {key} 下载完成" if ok else f"模型 {key} 下载完成但校验失败",
            "progress": 100 if ok else 99,
            "model_key": key,
            "provider": provider,
            "missing": missing,
            "download": result.get("data"),
            "downloaded_bytes": _download_states.get(key, {}).get("downloaded_bytes"),
            "total_bytes": _download_states.get(key, {}).get("total_bytes"),
        }
        await _update_download_state(
            key,
            {
                "status": "completed" if ok else "error",
                "phase": "download_done",
                "progress": 100 if ok else 99,
                "message": payload["message"],
                "missing": missing,
            },
        )
        await _broadcast_download_event(payload)
    except Exception as e:
        await _update_download_state(
            key,
            {
                "status": "error",
                "phase": "download_error",
                "message": f"模型下载失败: {e}",
            },
        )
        await _broadcast_download_event(
            {
                "type": "error",
                "scope": "fun_asr_models",
                "project_id": None,
                "phase": "download_error",
                "message": f"模型下载失败: {e}",
                "model_key": key,
                "provider": provider,
                "downloaded_bytes": _download_states.get(key, {}).get("downloaded_bytes"),
                "total_bytes": _download_states.get(key, {}).get("total_bytes"),
            }
        )
    finally:
        await _remove_download_task(key)


async def _stop_download_task(key: str) -> Dict[str, Any]:
    async with _download_lock:
        proc = _download_processes.get(key)
        state = _download_states.get(key) or {"key": key}
        state.update(
            {
                "status": "cancelled",
                "phase": "download_cancelled",
                "message": f"模型 {key} 下载已停止",
                "progress": 0,
            }
        )
        _download_states[key] = state
    if proc and proc.is_alive():
        try:
            proc.terminate()
        except Exception:
            pass
    await _broadcast_download_event(
        {
            "type": "cancelled",
            "scope": "fun_asr_models",
            "project_id": None,
            "phase": "download_cancelled",
            "message": f"模型 {key} 下载已停止",
            "model_key": key,
            "progress": 0,
        }
    )
    return {"success": True, "data": {"key": key, "status": "cancelled"}, "message": "下载任务已停止"}


class FunASRDownloadRequest(BaseModel):
    key: str = Field(..., description="模型key，如 fun_asr_nano_2512")
    provider: str = Field(default="modelscope", description="hf 或 modelscope")


class FunASRStopDownloadRequest(BaseModel):
    key: str = Field(..., description="模型key")


class FunASRValidateRequest(BaseModel):
    key: str = Field(..., description="模型key")


class FunASRTestRequest(BaseModel):
    key: str = Field(..., description="模型key")
    device: Optional[str] = Field(default=None, description="cuda:0 或 cpu；为空自动")
    language: str = Field(default="中文", description="语言名称，如 中文/英文/日文/粤语…")
    itn: bool = Field(default=True, description="是否启用逆文本归一化")


@router.get("/models", summary="获取 FunASR 本地模型状态")
async def list_fun_asr_models() -> Dict[str, Any]:
    try:
        pm = FunASRPathManager()
        data = []
        for s in pm.list_status():
            ok, missing = validate_model_dir(s.key, Path(s.path))
            data.append(
                {
                    "key": s.key,
                    "path": s.path,
                    "exists": s.exists,
                    "valid": ok,
                    "missing": missing,
                    "display_name": s.display_name,
                    "languages": s.languages,
                    "sources": s.sources,
                    "description": s.description,
                }
            )
        return {"success": True, "data": data, "message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/validate", summary="校验 FunASR 模型目录完整性")
async def validate_fun_asr_model(req: FunASRValidateRequest) -> Dict[str, Any]:
    try:
        pm = FunASRPathManager()
        p = pm.model_path(req.key)
        ok, missing = validate_model_dir(req.key, p)
        return {"success": True, "data": {"key": req.key, "path": str(p), "valid": ok, "missing": missing}}
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/download", summary="下载 FunASR 模型到本地")
async def download_fun_asr_model(req: FunASRDownloadRequest) -> Dict[str, Any]:
    try:
        pm = FunASRPathManager()
        if req.key not in FUN_ASR_MODEL_REGISTRY:
            raise HTTPException(status_code=404, detail="unknown_model_key")

        provider = (req.provider or "").strip().lower()
        if provider not in {"hf", "modelscope"}:
            raise HTTPException(status_code=400, detail="provider_must_be_hf_or_modelscope")

        target_dir = pm.model_path(req.key)
        total_bytes = get_model_total_bytes(req.key, provider)
        async with _download_lock:
            existing = _download_tasks.get(req.key)
            if existing and not existing.done():
                data = _download_states.get(req.key) or {
                    "key": req.key,
                    "provider": provider,
                    "status": "running",
                    "phase": "download_start",
                    "progress": 1,
                    "message": f"开始下载模型 {req.key}",
                    "downloaded_bytes": 0,
                    "total_bytes": total_bytes,
                }
                if data.get("downloaded_bytes") is None:
                    data["downloaded_bytes"] = 0
                if data.get("total_bytes") is None and total_bytes is not None:
                    data["total_bytes"] = total_bytes
                return {"success": True, "data": {**data, "path": str(target_dir)}, "message": "下载任务已在运行"}

            task = asyncio.create_task(_run_download_task(req.key, provider))
            _download_tasks[req.key] = task
            _download_states[req.key] = {
                "key": req.key,
                "provider": provider,
                "status": "running",
                "phase": "download_start",
                "progress": 1,
                "message": f"开始下载模型 {req.key}",
                "downloaded_bytes": 0,
                "total_bytes": total_bytes,
            }
        return {
            "success": True,
            "data": {
                "key": req.key,
                "path": str(target_dir),
                "status": "running",
                "downloaded_bytes": 0,
                "total_bytes": total_bytes,
            },
            "message": "下载任务已启动",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/downloads", summary="获取 FunASR 模型下载任务")
async def list_fun_asr_model_downloads() -> Dict[str, Any]:
    async with _download_lock:
        items: List[Dict[str, Any]] = [v for v in _download_states.values() if v.get("status") == "running"]
    return {"success": True, "data": items, "message": "ok"}


@router.post("/models/downloads/stop", summary="停止 FunASR 模型下载任务")
async def stop_fun_asr_model_download(req: FunASRStopDownloadRequest) -> Dict[str, Any]:
    if req.key not in FUN_ASR_MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    return await _stop_download_task(req.key)


@router.post("/models/downloads/{key}/stop", summary="停止 FunASR 模型下载任务")
async def stop_fun_asr_model_download_by_key(key: str) -> Dict[str, Any]:
    if key not in FUN_ASR_MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    return await _stop_download_task(key)


@router.get("/models/open-path", summary="在系统文件管理器中打开 FunASR 模型目录")
async def open_fun_asr_model_path(key: str = Query(..., description="模型key")) -> Dict[str, Any]:
    try:
        pm = FunASRPathManager()
        model_path = pm.model_path(key)
        base_dir = model_path.parent
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        target_dir = model_path if model_path.exists() else base_dir
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail="路径不存在")
        sysname = platform.system().lower()
        if "windows" in sysname:
            subprocess.Popen(["explorer", str(target_dir)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif "darwin" in sysname:
            subprocess.Popen(["open", str(target_dir)])
        else:
            subprocess.Popen(["xdg-open", str(target_dir)])
        return {"success": True, "data": {"key": key, "path": str(target_dir)}, "message": "已打开文件管理器"}
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test", summary="使用默认音频测试 FunASR 模型是否可用")
async def fun_asr_test(req: FunASRTestRequest) -> Dict[str, Any]:
    try:
        ok = await fun_asr_service.run_default_test(
            model_key=req.key,
            device=req.device,
            language=req.language,
            itn=bool(req.itn),
        )
        return {"success": True, "data": ok, "message": "ok"}
    except ValueError as e:
        if str(e) == "unknown_model_key":
            raise HTTPException(status_code=404, detail="unknown_model_key")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        if "missing_dependency:" in msg or "model_invalid_or_missing:" in msg:
            raise HTTPException(status_code=503, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
