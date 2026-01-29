import asyncio
import json
import shutil
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from modules.qwen3_tts_model_manager import (
    Qwen3TTSPathManager,
    QWEN3_TTS_MODEL_REGISTRY,
    download_model_snapshot,
    validate_model_dir,
)
from modules.qwen3_tts_voice_store import qwen3_tts_voice_store
from modules.ws_manager import manager


from modules.qwen3_tts_service import qwen3_tts_service

router = APIRouter(prefix="/api/tts/qwen3", tags=["Qwen3-TTS"])


class Qwen3TTSDownloadRequest(BaseModel):
    key: str = Field(..., description="模型key，如 base_0_6b")
    provider: str = Field(..., description="hf 或 modelscope")


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

        target_dir = pm.model_path(req.key)
        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "progress",
                        "scope": "qwen3_tts_models",
                        "project_id": None,
                        "phase": "download_start",
                        "message": f"开始下载模型 {req.key}",
                        "progress": 1,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass

        ret = await __import__("asyncio").get_running_loop().run_in_executor(
            None, lambda: download_model_snapshot(req.key, req.provider, target_dir)
        )

        ok, missing = validate_model_dir(req.key, target_dir)

        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "completed" if ok else "error",
                        "scope": "qwen3_tts_models",
                        "project_id": None,
                        "phase": "download_done",
                        "message": f"模型 {req.key} 下载完成" if ok else f"模型 {req.key} 下载完成但校验失败",
                        "progress": 100 if ok else 99,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass

        return {
            "success": ok,
            "data": {"key": req.key, "path": str(target_dir), "valid": ok, "missing": missing, "download": ret},
            "message": "下载完成" if ok else "下载完成但校验失败",
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            await manager.broadcast(
                json.dumps(
                    {
                        "type": "error",
                        "scope": "qwen3_tts_models",
                        "project_id": None,
                        "phase": "download_error",
                        "message": f"模型下载失败: {e}",
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/open-path", summary="返回Qwen3-TTS模型本地路径")
async def open_qwen3_model_path(key: str = Query(..., description="模型key")) -> Dict[str, Any]:
    try:
        pm = Qwen3TTSPathManager()
        p = pm.model_path(key)
        return {"success": True, "data": {"key": key, "path": str(p)}}
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown_model_key")
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


async def _broadcast_voice_clone(payload: Dict[str, Any]) -> None:
    try:
        await manager.broadcast(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


async def _convert_to_16k_mono_wav(raw_path: Path, out_wav: Path) -> Dict[str, Any]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Missing dependency 'ffmpeg'. Please install it on server.")

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
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
        if shutil.which("ffmpeg") is None:
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
