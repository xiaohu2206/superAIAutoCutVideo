#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 项目：解说文案结构化（与在线视觉共用「视频理解模型」）+ 向量化（本地 BGE-base-zh-v1.5）。
与 visual / generate_script 等业务模块解耦；产出 uploads/omni_copywriting_embed/{project_id}/。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ai import AIModelConfig, ChatMessage, get_provider_class
from services.ai_models.unified_model_usage import resolve_video_model_for_online_vision
from modules.omni_copywriting_struct_embed import (
    build_omni_embedding_input,
    load_structuring_prompt,
    normalize_segment,
    parse_model_json_array,
    split_copywriting_text,
    validate_segment,
)
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.ai_models.ai_service import LLM_HTTP_TIMEOUT_SEC
from services.asr.extract_subtitle_service import _to_web_path, _uploads_dir
from services.ai_models.omni_local_bge_embedding import (
    LOCAL_BGE_MODEL_DISPLAY_NAME,
    assert_local_bge_model_available,
    encode_text_async,
)

logger = logging.getLogger(__name__)

_SCOPE = "omni_copywriting_embed"

# 与 omni_multimodal_pipeline Step2 / vision_frame_analysis 在线视觉一致，需可调 chat completions 的在线 VL
_STRUCT_ONLINE_VL_PROVIDERS = frozenset({"yunwu", "302ai", "qwen", "doubao", "custom_openai_vision"})


def _video_cfg_to_ai_cfg(cfg: Any) -> AIModelConfig:
    return AIModelConfig(
        provider=cfg.provider,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model_name=cfg.model_name,
        temperature=cfg.temperature,
        timeout=LLM_HTTP_TIMEOUT_SEC,
        extra_params={
            **(cfg.extra_params or {}),
            "stream_output": bool(getattr(cfg, "stream_output", False)),
        },
    )


def _work_dir(project_id: str) -> Path:
    return _uploads_dir() / "omni_copywriting_embed" / project_id


def _load_project_copywriting_text(project_id: str) -> str:
    p = projects_store.get_project(project_id)
    if not p:
        raise ValueError("项目不存在")
    data = getattr(p, "narration_copywriting", None)
    if not isinstance(data, dict):
        raise ValueError("请先生成并保存解说文案（narration_copywriting）")
    text = str(data.get("content", "")).strip()
    if not text:
        raise ValueError("解说文案 content 为空，请先生成并保存解说文案")
    return text


async def _call_structuring_chunk(
    *,
    prompt_template: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
    prompt_language: str,
) -> List[Dict[str, Any]]:
    lang = str(prompt_language or "zh").strip().lower()
    require_translation = lang == "en"
    prompt = prompt_template.replace("{copywriting}", chunk_text)
    messages = [ChatMessage(role="user", content=prompt)]

    active_vl = resolve_video_model_for_online_vision()
    if not active_vl or active_vl.provider not in _STRUCT_ONLINE_VL_PROVIDERS:
        raise ValueError(
            "文案结构化需与在线视觉分析共用「视频理解模型」：请在设置中选择 "
            "yunwu / 302ai / qwen / doubao / custom_openai_vision 之一并配置密钥"
        )

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            provider_cls = get_provider_class(active_vl.provider)
            if not provider_cls:
                raise RuntimeError(f"不支持的AI提供商: {active_vl.provider}")
            ai_cfg = _video_cfg_to_ai_cfg(active_vl)
            provider = provider_cls(ai_cfg)
            try:
                resp = await provider.chat_completion(
                    messages,
                    extra_params={"response_format": {"type": "json_object"}},
                )
            finally:
                await provider.close()
            raw = (resp.content or "").strip()
            parsed = parse_model_json_array(raw)
            out: List[Dict[str, Any]] = []
            for item_index, raw_item in enumerate(parsed, start=1):
                if not isinstance(raw_item, dict):
                    raise ValueError(f"chunk={chunk_index} item={item_index} 不是对象")
                normalized_item = normalize_segment(raw_item)
                validate_segment(
                    normalized_item,
                    chunk_index,
                    item_index,
                    require_translation=require_translation,
                )
                out.append(normalized_item)
            logger.info(
                "[omni_copywriting_embed] structuring chunk %s/%s items=%s",
                chunk_index,
                total_chunks,
                len(out),
            )
            return out
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "[omni_copywriting_embed] structuring chunk %s/%s failed "
                    "(attempt %s/%s): %s. Retrying…",
                    chunk_index,
                    total_chunks,
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                continue
            logger.error(
                "[omni_copywriting_embed] structuring chunk %s/%s failed after %s retries: %s",
                chunk_index,
                total_chunks,
                max_retries,
                e,
            )
            raise
    return []


class OmniCopywritingStructEmbedService:
    SCOPE = _SCOPE

    async def submit_run(
        self,
        project_id: str,
        *,
        force: bool = False,
        task_id: Optional[str] = None,
        chunk_target_chars: int = 500,
        chunk_lookback_chars: int = 100,
        structuring_concurrency: int = 3,
        embedding_concurrency: int = 8,
        prompt_language: str = "zh",
        continue_on_embedding_error: bool = True,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可运行文案结构化与向量化")

        running = task_progress_store.get_latest_running(self.SCOPE, project_id)
        if running:
            r_status = str(running.get("status") or "").strip().lower()
            r_task_id = running.get("task_id")
            if not force:
                if r_status in ("pending", "processing", "running"):
                    return {"task_id": r_task_id, "status": r_status, "message": "已有任务在运行"}
            else:
                if r_task_id and r_status in ("pending", "processing", "running"):
                    try:
                        await task_cancel_store.cancel(self.SCOPE, project_id, str(r_task_id))
                    except Exception:
                        pass
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=str(r_task_id),
                        status="cancelled",
                        message="已取消旧任务，准备重新执行",
                    )

        if not task_id:
            task_id = f"omni_cwe_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="正在解析内容…",
            phase="preparing",
        )

        sem_struct = max(1, int(structuring_concurrency or 1))
        sem_emb = max(1, int(embedding_concurrency or 1))
        chunk_target = max(200, int(chunk_target_chars or 500))
        chunk_lookback = max(0, int(chunk_lookback_chars or 100))
        plang = str(prompt_language or "zh").strip().lower()

        async def _run() -> None:
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                copywriting_text = _load_project_copywriting_text(project_id)
                prompt_template = load_structuring_prompt(prompt_language=plang)

                chunks = split_copywriting_text(
                    copywriting_text,
                    target_chunk_chars=chunk_target,
                    lookback_chars=chunk_lookback,
                )
                if not chunks:
                    raise ValueError("解说文案拆分后为空")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=5,
                    message=f"结构化中（共 {len(chunks)} 段）…",
                    phase="structuring",
                )

                struct_sem = asyncio.Semaphore(sem_struct)
                chunk_results: Dict[int, List[Dict[str, Any]]] = {}

                async def _one_chunk(idx: int, chunk: str) -> None:
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    async with struct_sem:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        items = await _call_structuring_chunk(
                            prompt_template=prompt_template,
                            chunk_text=chunk,
                            chunk_index=idx + 1,
                            total_chunks=len(chunks),
                            prompt_language=plang,
                        )
                        chunk_results[idx + 1] = items

                await asyncio.gather(*[_one_chunk(i, c) for i, c in enumerate(chunks)])

                merged_items: List[Dict[str, Any]] = []
                for i in range(1, len(chunks) + 1):
                    merged_items.extend(chunk_results[i])

                work = _work_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)
                structured_path = work / "copywriting_structured.json"
                structured_path.write_text(
                    json.dumps(merged_items, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                structured_web = _to_web_path(structured_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_copywriting_structured_path": structured_web,
                        "omni_copywriting_embed_updated_at": datetime.now().isoformat(),
                    },
                )

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                try:
                    assert_local_bge_model_available()
                except (FileNotFoundError, RuntimeError) as e:
                    raise ValueError(str(e)) from e

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=55,
                    message=f"向量化中（{len(merged_items)} 条）…",
                    phase="embedding",
                )

                emb_sem = asyncio.Semaphore(sem_emb)
                enriched: List[Optional[Dict[str, Any]]] = [None] * len(merged_items)
                done = 0
                lock = asyncio.Lock()
                llm_label = ""
                try:
                    try:
                        av = resolve_video_model_for_online_vision()
                    except Exception:
                        av = None
                    if av:
                        llm_label = f"{av.provider}/{av.model_name}".strip("/")
                except Exception:
                    llm_label = ""

                async def _one_emb(i: int, row: Dict[str, Any]) -> None:
                    nonlocal done
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    async with emb_sem:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        out = dict(row)
                        try:
                            emb_in = build_omni_embedding_input(row, prompt_language=plang)
                            emb = await encode_text_async(emb_in)
                            out["embedding_input"] = emb_in
                            out["embedding_model"] = LOCAL_BGE_MODEL_DISPLAY_NAME
                            out["embedding"] = emb
                        except Exception as e:
                            out["error"] = str(e)
                            if not continue_on_embedding_error:
                                raise
                        async with lock:
                            enriched[i] = out
                            done += 1
                            pct = 55.0 + 40.0 * (done / max(1, len(merged_items)))
                            task_progress_store.set_state(
                                scope=self.SCOPE,
                                project_id=project_id,
                                task_id=task_id,
                                status="processing",
                                progress=min(95.0, pct),
                                message=f"向量化 {done}/{len(merged_items)}",
                                phase="embedding",
                            )

                await asyncio.gather(*[_one_emb(i, row) for i, row in enumerate(merged_items)])

                payload = {
                    "meta": {
                        "project_id": project_id,
                        "structured_count": len(merged_items),
                        "embedding_model": LOCAL_BGE_MODEL_DISPLAY_NAME,
                        "content_model_hint": llm_label,
                        "prompt_language": plang,
                        "generated_at": datetime.now().isoformat(),
                    },
                    "items": [x for x in enriched if x is not None],
                }
                emb_path = work / "copywriting_embeddings.json"
                emb_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                emb_web = _to_web_path(emb_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_copywriting_embeddings_path": emb_web,
                        "omni_copywriting_embed_updated_at": datetime.now().isoformat(),
                    },
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message="任务已完成",
                    phase="done",
                )
            except asyncio.CancelledError:
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="cancelled",
                    message="任务已取消",
                    phase="cancelled",
                )
            except Exception as e:
                logger.exception("omni copywriting struct+embed failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"失败: {e}",
                    phase="failed",
                )

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


omni_copywriting_struct_embed_service = OmniCopywritingStructEmbedService()
