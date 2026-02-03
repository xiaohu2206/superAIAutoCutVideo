import asyncio
import os
import json
import multiprocessing
import threading
import time
import shutil
import uuid
import wave
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from modules.qwen3_tts_model_manager import (
    Qwen3TTSPathManager,
    QWEN3_TTS_MODEL_REGISTRY,
    download_model_snapshot,
    validate_model_dir,
    get_model_total_bytes,
)
from modules.qwen3_tts_voice_store import qwen3_tts_voice_store
from modules.ws_manager import manager


from modules.qwen3_tts_service import qwen3_tts_service
from modules.qwen3_tts_acceleration import get_qwen3_tts_acceleration_status

router = APIRouter(prefix="/api/tts/qwen3", tags=["Qwen3-TTS"])


@router.get("/acceleration-status")
async def get_qwen3_tts_acceleration() -> Dict[str, Any]:
    data = {
        "acceleration": get_qwen3_tts_acceleration_status(),
        "runtime": qwen3_tts_service.get_runtime_status(),
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
    cache_path = target_path / ".modelscope_cache"

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
            # 注意：calc_dir_size 使用 os.walk 会递归计算子目录，包括 .modelscope_cache
            # 所以不需要额外加上 cache_path 的大小，否则会导致重复计算
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
    pm = Qwen3TTSPathManager()
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
            "scope": "qwen3_tts_models",
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

                        resolved_total_bytes = None
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
                                "scope": "qwen3_tts_models",
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
            "scope": "qwen3_tts_models",
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
                "scope": "qwen3_tts_models",
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
            "scope": "qwen3_tts_models",
            "project_id": None,
            "phase": "download_cancelled",
            "message": f"模型 {key} 下载已停止",
            "model_key": key,
            "progress": 0,
        }
    )
    return {"success": True, "data": {"key": key, "status": "cancelled"}, "message": "下载任务已停止"}
class Qwen3TTSDownloadRequest(BaseModel):
    key: str = Field(..., description="模型key，如 base_0_6b")
    provider: str = Field(..., description="hf 或 modelscope")


class Qwen3TTSStopDownloadRequest(BaseModel):
    key: str = Field(..., description="模型key，如 base_0_6b")


class Qwen3TTSValidateRequest(BaseModel):
    key: str = Field(..., description="模型key")


class Qwen3TTSCustomRoleCreateRequest(BaseModel):
    name: str
    model_key: str
    language: str
    speaker: str
    instruct: Optional[str] = None


class Qwen3TTSDesignCloneCreateRequest(BaseModel):
    name: str
    model_key: str  # base model key
    voice_design_model_key: str  # voice design model key
    language: str
    text: str
    instruct: str


@router.get("/models", summary="获取Qwen3-TTS本地模型状态")
async def list_qwen3_models() -> Dict[str, Any]:
    try:
        pm = Qwen3TTSPathManager()
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
                    "model_type": getattr(s, "model_type", "base"),
                    "size": getattr(s, "size", ""),
                    "display_names": getattr(s, "display_names", []),
                    "sources": getattr(s, "sources", {}),
                }
            )
        return {"success": True, "data": data, "message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/validate", summary="校验Qwen3-TTS模型目录完整性")
async def validate_qwen3_model(req: Qwen3TTSValidateRequest) -> Dict[str, Any]:
    try:
        pm = Qwen3TTSPathManager()
        p = pm.model_path(req.key)
        ok, missing = validate_model_dir(req.key, p)
        return {"success": True, "data": {"key": req.key, "path": str(p), "valid": ok, "missing": missing}}
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/download", summary="下载Qwen3-TTS模型到本地")
async def download_qwen3_model(req: Qwen3TTSDownloadRequest) -> Dict[str, Any]:
    try:
        pm = Qwen3TTSPathManager()
        if req.key not in QWEN3_TTS_MODEL_REGISTRY:
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
                return {
                    "success": True,
                    "data": {**data, "path": str(target_dir)},
                    "message": "下载任务已在运行",
                }
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


@router.get("/models/downloads", summary="获取Qwen3-TTS模型下载任务")
async def list_qwen3_model_downloads() -> Dict[str, Any]:
    async with _download_lock:
        items: List[Dict[str, Any]] = [
            v for v in _download_states.values() if v.get("status") == "running"
        ]
    return {"success": True, "data": items, "message": "ok"}


@router.post("/models/downloads/stop", summary="停止Qwen3-TTS模型下载任务")
async def stop_qwen3_model_download(req: Qwen3TTSStopDownloadRequest) -> Dict[str, Any]:
    if req.key not in QWEN3_TTS_MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    return await _stop_download_task(req.key)


@router.post("/models/downloads/{key}/stop", summary="停止Qwen3-TTS模型下载任务")
async def stop_qwen3_model_download_by_key(key: str) -> Dict[str, Any]:
    if key not in QWEN3_TTS_MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    return await _stop_download_task(key)


@router.get("/models/open-path", summary="在系统文件管理器中打开Qwen3-TTS模型目录")
async def open_qwen3_model_path(key: str = Query(..., description="模型key")) -> Dict[str, Any]:
    try:
        pm = Qwen3TTSPathManager()
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
        return {
            "success": True,
            "data": {"key": key, "path": str(target_dir)},
            "message": "已打开文件管理器",
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown_model_key")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class Qwen3TTSVoiceUpdateRequest(BaseModel):
    name: Any = Field(None, description="展示名称")
    model_key: Any = Field(None, description="模型key，如 base_0_6b")
    language: Any = Field(None, description="语言，如 Auto/zh/en")
    ref_text: Any = Field(None, description="参考文本（可选）")
    instruct: Any = Field(None, description="指令（可选）")
    x_vector_only_mode: Any = Field(None, description="是否仅使用 x-vector 模式")


@router.get("/voices", summary="获取Qwen3-TTS克隆音色列表")
async def list_qwen3_voices() -> Dict[str, Any]:
    try:
        data = [v.model_dump() for v in qwen3_tts_voice_store.list()]
        return {"success": True, "data": data, "message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voices/{voice_id}", summary="获取Qwen3-TTS克隆音色详情")
async def get_qwen3_voice(voice_id: str) -> Dict[str, Any]:
    try:
        v = qwen3_tts_voice_store.get(voice_id)
        if not v:
            raise HTTPException(status_code=404, detail="voice_not_found")
        return {"success": True, "data": v.model_dump(), "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voices/upload", summary="上传参考音频并创建克隆音色")
async def upload_qwen3_voice(
    file: UploadFile = File(..., description="音频文件"),
    name: str = Form("", description="音色名称（可选）"),
    model_key: str = Form("base_0_6b", description="模型key"),
    language: str = Form("Auto", description="语言"),
    ref_text: str = Form("", description="参考文本（可选）"),
    instruct: str = Form("", description="指令（可选）"),
    x_vector_only_mode: bool = Form(True, description="是否仅使用 x-vector 模式"),
) -> Dict[str, Any]:
    try:
        content = await file.read()
        v = qwen3_tts_voice_store.create_from_upload(
            upload_bytes=content,
            original_filename=file.filename or "ref.wav",
            name=name or None,
            model_key=model_key,
            language=language,
            ref_text=ref_text or None,
            instruct=instruct or None,
            x_vector_only_mode=bool(x_vector_only_mode),
        )
        return {"success": True, "data": v.model_dump(), "message": "uploaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/voices/{voice_id}", summary="更新Qwen3-TTS克隆音色")
async def patch_qwen3_voice(voice_id: str, req: Qwen3TTSVoiceUpdateRequest) -> Dict[str, Any]:
    try:
        v = qwen3_tts_voice_store.get(voice_id)
        if not v:
            raise HTTPException(status_code=404, detail="voice_not_found")
        updates: Dict[str, Any] = {}
        for k in ["name", "model_key", "language", "ref_text", "instruct", "x_vector_only_mode"]:
            val = getattr(req, k, None)
            if val is not None:
                updates[k] = val
        updated = qwen3_tts_voice_store.update(voice_id, updates)
        if not updated:
            raise HTTPException(status_code=404, detail="voice_not_found")
        return {"success": True, "data": updated.model_dump(), "message": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/voices/{voice_id}", summary="删除Qwen3-TTS克隆音色")
async def delete_qwen3_voice(voice_id: str, remove_files: bool = Query(False, description="是否删除本地音频文件")) -> Dict[str, Any]:
    try:
        ok = qwen3_tts_voice_store.delete(voice_id, remove_files=bool(remove_files))
        if not ok:
            raise HTTPException(status_code=404, detail="voice_not_found")
        return {"success": True, "data": {"id": voice_id, "removed_files": bool(remove_files)}, "message": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voices/custom-role", summary="创建固定角色音色")
async def create_qwen3_custom_role_voice(req: Qwen3TTSCustomRoleCreateRequest) -> Dict[str, Any]:
    try:
        v = qwen3_tts_voice_store.create_custom_role(
            name=req.name,
            model_key=req.model_key,
            language=req.language,
            speaker=req.speaker,
            instruct=req.instruct,
        )
        return {"success": True, "data": v.model_dump(), "message": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voices/design-clone", summary="创建设计克隆音色（异步）")
async def create_qwen3_design_clone_voice(req: Qwen3TTSDesignCloneCreateRequest) -> Dict[str, Any]:
    try:
        v = qwen3_tts_voice_store.create_design_clone(
            name=req.name,
            model_key=req.model_key,
            language=req.language,
            text=req.text,
            instruct=req.instruct,
        )
        qwen3_tts_voice_store.update(v.id, {"meta": {**v.meta, "voice_design_model_key": req.voice_design_model_key}})

        job_id = str(uuid.uuid4())
        __import__("asyncio").create_task(_run_voice_design_clone_job(voice_id=v.id, job_id=job_id))
        return {"success": True, "data": {"voice_id": v.id, "job_id": job_id}, "message": "started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_key}/capabilities", summary="获取模型支持的语言与角色")
async def get_qwen3_model_capabilities(model_key: str) -> Dict[str, Any]:
    try:
        langs = await qwen3_tts_service.list_supported_languages(model_key)
        speakers = await qwen3_tts_service.list_supported_speakers(model_key)
        return {"success": True, "data": {"languages": langs, "speakers": speakers}, "message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _find_ffmpeg() -> Optional[str]:
    name = "ffmpeg.exe" if "windows" in platform.system().lower() else "ffmpeg"
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        try:
            p = Path(env_path)
            if p.exists():
                return str(p)
        except Exception:
            pass
    env_dir = os.environ.get("FFMPEG_DIR") or os.environ.get("FFMPEG_HOME")
    if env_dir:
        try:
            p = Path(env_dir) / name
            if p.exists():
                return str(p)
        except Exception:
            pass
    hit = shutil.which("ffmpeg")
    if hit:
        return hit
    candidates: List[Path] = []
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "resources" / name)
        candidates.append(exe_dir / name)
    except Exception:
        pass
    try:
        root = Path(__file__).resolve().parents[2]
        candidates.append(root / "src-tauri" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "debug" / "resources" / name)
        candidates.append(root / "src-tauri" / "target" / "release" / "resources" / name)
    except Exception:
        pass
    install_dir = os.environ.get("SACV_INSTALL_DIR")
    if install_dir:
        try:
            candidates.append(Path(install_dir) / "resources" / name)
        except Exception:
            pass
    try:
        here = Path(__file__).resolve()
        candidates.append(here.parent.parent / "resources" / name)
    except Exception:
        pass
    try:
        candidates.append(Path.cwd() / "resources" / name)
    except Exception:
        pass
    try:
        if os.name == "nt":
            candidates.append(Path("C:/Program Files/ffmpeg/bin") / "ffmpeg.exe")
            candidates.append(Path("C:/ffmpeg/bin") / "ffmpeg.exe")
            candidates.append(Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe")
            candidates.append(Path("C:/ProgramData/chocolatey/bin") / "ffmpeg.exe")
    except Exception:
        pass
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except Exception:
            continue
    return None
 
async def _broadcast_voice_clone(payload: Dict[str, Any]) -> None:
    try:
        await manager.broadcast(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


async def _convert_to_16k_mono_wav(raw_path: Path, out_wav: Path) -> Dict[str, Any]:
    ffmpeg_bin = _find_ffmpeg()
    if not ffmpeg_bin:
        raise RuntimeError("Missing dependency 'ffmpeg'. Please install it on server.")

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(raw_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **({"creationflags": __import__("subprocess").CREATE_NO_WINDOW} if __import__("os").name == "nt" else {})
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg_convert_failed: {stderr.decode(errors='ignore').strip()}")

    with wave.open(str(out_wav), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        dur = float(frames) / float(rate) if rate else None
    return {"duration": dur, "sample_rate": 16000}


async def _run_voice_clone_job(voice_id: str, job_id: str) -> None:
    await _broadcast_voice_clone(
        {
            "type": "progress",
            "scope": "qwen3_tts_voice_clone",
            "project_id": None,
            "voice_id": voice_id,
            "job_id": job_id,
            "phase": "clone_start",
            "message": "开始预处理参考音频",
            "progress": 1,
        }
    )
    qwen3_tts_voice_store.set_clone_progress(voice_id, status="cloning", progress=1)

    try:
        raw_path, out_wav = qwen3_tts_voice_store.prepare_clone_paths(voice_id)
    except Exception as e:
        # 出错时删除该记录，避免在列表中残留无效数据
        qwen3_tts_voice_store.delete(voice_id, remove_files=True)
        await _broadcast_voice_clone(
            {
                "type": "error",
                "scope": "qwen3_tts_voice_clone",
                "project_id": None,
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "clone_error",
                "message": f"音色不存在或路径异常: {e}",
            }
        )
        return

    try:
        await _broadcast_voice_clone(
            {
                "type": "progress",
                "scope": "qwen3_tts_voice_clone",
                "project_id": None,
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "load_audio",
                "message": "读取并重采样音频",
                "progress": 20,
            }
        )
        qwen3_tts_voice_store.set_clone_progress(voice_id, status="cloning", progress=20)

        await _broadcast_voice_clone(
            {
                "type": "progress",
                "scope": "qwen3_tts_voice_clone",
                "project_id": None,
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "write_wav",
                "message": "写入标准化 wav 文件",
                "progress": 70,
            }
        )
        qwen3_tts_voice_store.set_clone_progress(voice_id, status="cloning", progress=70)

        meta = await _convert_to_16k_mono_wav(raw_path, out_wav)
        existing = qwen3_tts_voice_store.get(voice_id)
        if not existing:
            raise ValueError("voice_not_found_during_process")

        base_meta: Dict[str, Any] = dict(existing.meta)
        qwen3_tts_voice_store.update(
            voice_id,
            {
                "ref_audio_path": str(out_wav),
                "status": "ready",
                "progress": 100,
                "meta": dict(base_meta, **meta),
                "last_error": None,
            },
        )
        await _broadcast_voice_clone(
            {
                "type": "completed",
                "scope": "qwen3_tts_voice_clone",
                "project_id": None,
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "clone_done",
                "message": "音色预处理完成，可用于合成",
                "progress": 100,
            }
        )
    except Exception as e:
        # 出错时删除该记录，避免在列表中残留无效数据
        qwen3_tts_voice_store.delete(voice_id, remove_files=True)
        await _broadcast_voice_clone(
            {
                "type": "error",
                "scope": "qwen3_tts_voice_clone",
                "project_id": None,
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "clone_error",
                "message": f"音色预处理失败: {e}",
            }
        )


async def _run_voice_design_clone_job(voice_id: str, job_id: str) -> None:
    await _broadcast_voice_clone(
        {
            "type": "progress",
            "scope": "qwen3_tts_voice_clone",
            "voice_id": voice_id,
            "job_id": job_id,
            "phase": "design_generate",
            "message": "正在生成设计参考音频...",
            "progress": 10,
        }
    )
    qwen3_tts_voice_store.set_clone_progress(voice_id, status="cloning", progress=10)

    try:
        v = qwen3_tts_voice_store.get(voice_id)
        if not v:
            raise ValueError("voice_not_found")

        raw_path, out_wav = qwen3_tts_voice_store.prepare_clone_paths(voice_id)

        design_model_key = v.meta.get("voice_design_model_key", "voice_design_1_7b")
        text = v.meta.get("voice_design_text", "")
        instruct = v.meta.get("voice_design_instruct", "")

        await qwen3_tts_service.synthesize_voice_design_to_wav(
            text=text,
            out_path=raw_path,
            model_key=design_model_key,
            language=v.language,
            instruct=instruct,
        )

        await _broadcast_voice_clone(
            {
                "type": "progress",
                "scope": "qwen3_tts_voice_clone",
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "load_audio",
                "message": "处理参考音频...",
                "progress": 50,
            }
        )
        qwen3_tts_voice_store.set_clone_progress(voice_id, status="cloning", progress=50)
        meta = await _convert_to_16k_mono_wav(raw_path, out_wav)
        existing = qwen3_tts_voice_store.get(voice_id)
        base_meta: Dict[str, Any] = dict(existing.meta) if existing else {}

        qwen3_tts_voice_store.update(
            voice_id,
            {
                "ref_audio_path": str(out_wav),
                "status": "ready",
                "progress": 100,
                "meta": dict(base_meta, **meta),
                "last_error": None,
            },
        )

        await _broadcast_voice_clone(
            {
                "type": "completed",
                "scope": "qwen3_tts_voice_clone",
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "clone_done",
                "message": "设计克隆音色创建完成",
                "progress": 100,
            }
        )

    except Exception as e:
        # 出错时删除该记录
        qwen3_tts_voice_store.delete(voice_id, remove_files=True)
        await _broadcast_voice_clone(
            {
                "type": "error",
                "scope": "qwen3_tts_voice_clone",
                "voice_id": voice_id,
                "job_id": job_id,
                "phase": "clone_error",
                "message": f"设计克隆失败: {e}",
            }
        )


@router.post("/voices/{voice_id}/clone", summary="开始克隆音色（预处理参考音频）")
async def start_qwen3_voice_clone(voice_id: str) -> Dict[str, Any]:
    try:
        # 预先检查依赖
        if _find_ffmpeg() is None:
            qwen3_tts_voice_store.delete(voice_id, remove_files=True)
            raise HTTPException(status_code=500, detail="Missing dependency 'ffmpeg'. Please install it on server.")

        v = qwen3_tts_voice_store.get(voice_id)
        if not v:
            raise HTTPException(status_code=404, detail="voice_not_found")
        job_id = str(uuid.uuid4())
        __import__("asyncio").create_task(_run_voice_clone_job(voice_id=voice_id, job_id=job_id))
        return {"success": True, "data": {"voice_id": voice_id, "job_id": job_id}, "message": "started"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voices/{voice_id}/clone-status", summary="查询克隆音色处理状态")
async def get_qwen3_voice_clone_status(voice_id: str) -> Dict[str, Any]:
    try:
        v = qwen3_tts_voice_store.get(voice_id)
        if not v:
            raise HTTPException(status_code=404, detail="voice_not_found")
        return {
            "success": True,
            "data": {
                "voice_id": voice_id,
                "status": v.status,
                "progress": v.progress,
                "last_error": v.last_error,
                "ref_audio_path": v.ref_audio_path,
                "ref_audio_url": v.ref_audio_url,
            },
            "message": "ok",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
