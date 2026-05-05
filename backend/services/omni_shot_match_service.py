#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni：在「文案结构化 + 向量化」与「多模态镜头 JSON」之上做镜头粗筛（本地 BGE 向量 cosine）、
粗排（与向量分数一致，无在线 rerank）、精排（content 模型）与连续性融合重排。
独立目录 uploads/omni_shot_match/{project_id}/；与 visual、copywriting_embed 任务 scope 隔离。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.ai import ChatMessage
from modules.omni_copywriting_struct_embed import build_omni_embedding_input
from modules.omni_shot_match import (
    build_embedding_search_results,
    build_narration_block,
    build_rerank_documents,
    build_shot_embedding_text,
    get_item_embedding,
    get_shot_embedding,
    get_timeline_info,
    load_fine_prompt_template,
    merge_fine_scores_and_continuity,
    normalize_llm_scores,
    parse_fine_llm_payload,
)
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from modules.project_task_queue import project_task_queue
from services.ai_models.ai_service import ai_service
from services.ai_models.unified_model_usage import LlmModelUsage
from services.asr.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.multimodal_json_crypto import read_multimodal_json
from services.ai_models.omni_local_bge_embedding import (
    LOCAL_BGE_MODEL_DISPLAY_NAME,
    assert_local_bge_model_available,
    encode_text_async,
)

logger = logging.getLogger(__name__)

# 为 True 时，精排 send_chat 失败时在同目录写 JSON（与 omni_generate_script 的 messages log 类似，便于对 HTTP 5xx/空体 对照排查）
_OMNI_SM_LOG_RERANK_ON_FAILURE = True

_SCOPE = "omni_shot_match"


def _safe_log_sm_segment(s: str) -> str:
    bad = "<>:\"/\\|?*"
    out = "".join(c if c not in bad else "_" for c in (s or ""))
    return (out or "x")[:180]


def _log_omni_shot_match_rerank_failure(
    out_dir: Path,
    pos: int,
    project_id: str,
    task_id: str,
    exc: str,
    user_content: str,
) -> None:
    if not _OMNI_SM_LOG_RERANK_ON_FAILURE:
        return
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = f"omni_sm_rerank_fail_{_safe_log_sm_segment(task_id)}_i{pos:05d}_{ts}.json"
        path = out_dir / fn
        payload = {
            "meta": {
                "source": "omni_shot_match",
                "project_id": project_id,
                "task_id": task_id,
                "row_index": pos,
                "logged_at": datetime.now().isoformat(),
            },
            "exception": exc,
            "user_content": user_content,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as werr:  # noqa: BLE001
        logger.warning("omni_shot_match: 写入精排失败调试 log 失败: %s", werr)
_TOP_K = 20
_STAGE1_TOP_N = 15
_STAGE2_TOP_N = 15
_STAGE2_RETURN_N = 3
_OUTPUT_TOP_K = 0
_CONCURRENCY = 32


def _work_dir(project_id: str) -> Path:
    return _uploads_dir() / "omni_shot_match" / project_id


class OmniShotMatchService:
    SCOPE = _SCOPE

    async def submit_run(
        self,
        project_id: str,
        *,
        force: bool = False,
        task_id: Optional[str] = None,
        rerank_instruct: Optional[str] = None,
        temperature: float = 0.2,
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        p = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        if str(getattr(p, "project_type", "") or "").strip().lower() != "omni":
            raise ValueError("仅 omni 类型项目可运行镜头匹配与重排")

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
            task_id = f"omni_sm_{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        w_rerank = float((weights or {}).get("rerank_score", 0.55) or 0.55)
        w_embed = float((weights or {}).get("embedding_score", 0.30) or 0.30)
        w_cont = float((weights or {}).get("continuity_score", 0.15) or 0.15)

        task_progress_store.set_state(
            scope=self.SCOPE,
            project_id=project_id,
            task_id=task_id,
            status="pending",
            progress=0,
            message="准备步骤二…",
            phase="preparing",
        )

        sem_n = _CONCURRENCY

        async def _run() -> None:
            await project_task_queue.acquire(project_id, self.SCOPE, task_id)
            try:
                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                cur = projects_store.get_project(project_id)
                if not cur:
                    raise ValueError("项目不存在")
                emb_web = getattr(cur, "omni_copywriting_embeddings_path", None) or ""
                mm_web = getattr(cur, "omni_multimodal_json_path", None) or ""
                if not str(emb_web).strip():
                    raise ValueError("请先完成「文案结构化 + 向量化」（缺少 omni_copywriting_embeddings_path）")
                if not str(mm_web).strip():
                    raise ValueError("请先完成 Omni 多模态管线（缺少 omni_multimodal_json_path）")

                emb_abs = _resolve_path(str(emb_web))
                mm_abs = _resolve_path(str(mm_web))
                if not emb_abs.exists():
                    raise FileNotFoundError(f"文案向量文件不存在: {emb_web}")
                if not mm_abs.exists():
                    raise FileNotFoundError(f"多模态镜头文件不存在: {mm_web}")

                copy_payload = json.loads(emb_abs.read_text(encoding="utf-8"))
                items = (copy_payload.get("items") if isinstance(copy_payload, dict) else None) or []
                if not isinstance(items, list) or not items:
                    raise ValueError("copywriting_embeddings.json 中 items 为空")

                meta = copy_payload.get("meta") if isinstance(copy_payload, dict) else {}
                prompt_language = str((meta or {}).get("prompt_language") or "zh").strip().lower()
                if prompt_language not in ("zh", "en"):
                    prompt_language = "zh"

                mm_data = await asyncio.to_thread(read_multimodal_json, mm_abs)
                shots = (mm_data.get("shots") if isinstance(mm_data, dict) else None) or []
                if not isinstance(shots, list) or not shots:
                    raise ValueError("多模态 JSON 中 shots 为空")

                # 以解说侧向量为基准维度，避免仅重跑多模态时误删新镜头向量
                ref_dim = 0
                for it in items:
                    if isinstance(it, dict):
                        e = get_item_embedding(it)
                        if e:
                            ref_dim = len(e)
                            break
                if ref_dim == 0:
                    for sh in shots:
                        if isinstance(sh, dict):
                            e = get_shot_embedding(sh)
                            if e:
                                ref_dim = len(e)
                                break
                if ref_dim > 0:
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        e = get_item_embedding(it)
                        if e and len(e) != ref_dim:
                            it.pop("embedding", None)
                            it.pop("embedding_model", None)
                            it.pop("embedding_input", None)
                    for sh in shots:
                        if not isinstance(sh, dict):
                            continue
                        e = get_shot_embedding(sh)
                        if e and len(e) != ref_dim:
                            sh.pop("embedding", None)
                            sh.pop("embedding_model", None)
                            sh.pop("embedding_input", None)

                try:
                    assert_local_bge_model_available()
                except (FileNotFoundError, RuntimeError) as e:
                    raise ValueError(str(e)) from e

                missing_items = sum(1 for it in items if isinstance(it, dict) and not get_item_embedding(it))
                missing_shots = sum(1 for sh in shots if isinstance(sh, dict) and not get_shot_embedding(sh))
                if missing_items or missing_shots:
                    task_progress_store.set_state(
                        scope=self.SCOPE,
                        project_id=project_id,
                        task_id=task_id,
                        status="processing",
                        progress=4,
                        message=f"本地（解说 {missing_items} 条、镜头 {missing_shots} 个）…",
                        phase="embedding_backfill",
                    )
                    fill_sem = asyncio.Semaphore(min(8, max(sem_n, 4)))

                    async def _fill_item(it: Dict[str, Any]) -> None:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        if get_item_embedding(it):
                            return
                        async with fill_sem:
                            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError()
                            txt = build_omni_embedding_input(it, prompt_language=prompt_language)
                            it["embedding"] = await encode_text_async(txt)
                            it["embedding_model"] = LOCAL_BGE_MODEL_DISPLAY_NAME
                            it["embedding_input"] = txt

                    async def _fill_shot(sh: Dict[str, Any]) -> None:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        if get_shot_embedding(sh):
                            return
                        async with fill_sem:
                            if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                                raise asyncio.CancelledError()
                            txt = build_shot_embedding_text(sh, prompt_language=prompt_language)
                            sh["embedding"] = await encode_text_async(txt)
                            sh["embedding_model"] = LOCAL_BGE_MODEL_DISPLAY_NAME
                            sh["embedding_input"] = txt

                    await asyncio.gather(
                        *(_fill_item(it) for it in items if isinstance(it, dict)),
                        *(_fill_shot(sh) for sh in shots if isinstance(sh, dict)),
                    )

                embedding_model_hint = LOCAL_BGE_MODEL_DISPLAY_NAME

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=8,
                    message="正在匹配…",
                    phase="embedding_topk",
                )

                search_rows = build_embedding_search_results(
                    copy_items=items,
                    shots=shots,
                    top_k=_TOP_K,
                    embedding_model_hint=embedding_model_hint,
                    prompt_language=prompt_language,
                )

                work = _work_dir(project_id)
                work.mkdir(parents=True, exist_ok=True)
                topk_path = work / "search_topk.json"
                topk_payload = {
                    "meta": {
                        "project_id": project_id,
                        "copywriting_embeddings_path": str(emb_web),
                        "omni_multimodal_json_path": str(mm_web),
                        "top_k": _TOP_K,
                        "score_method": "cosine_similarity",
                        "count_copywriting_items": len(items),
                        "count_shots_total": len(shots),
                        "prompt_language": prompt_language,
                        "embedding_model": LOCAL_BGE_MODEL_DISPLAY_NAME,
                        "generated_at": datetime.now().isoformat(),
                    },
                    "results": search_rows,
                }
                topk_path.write_text(json.dumps(topk_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                topk_web = _to_web_path(topk_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_shot_match_topk_path": topk_web,
                        "omni_shot_match_updated_at": datetime.now().isoformat(),
                    },
                )

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                stage1_model = LOCAL_BGE_MODEL_DISPLAY_NAME

                fine_template = load_fine_prompt_template(prompt_language)
                llm_info = ai_service.get_provider_info(LlmModelUsage.LLM_RERANK)
                llm_label = f"{llm_info.get('active_provider') or ''}/{llm_info.get('active_model') or ''}".strip("/")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=35,
                    message="正在排序…",
                    phase="rerank_fine",
                )

                sem = asyncio.Semaphore(sem_n)
                total = len(search_rows)
                partial: Dict[int, Dict[str, Any]] = {}
                done = 0
                lock = asyncio.Lock()

                async def _one_item(pos: int, r: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
                    if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                        raise asyncio.CancelledError()
                    async with sem:
                        if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                            raise asyncio.CancelledError()
                        return await _process_row(
                            pos=pos,
                            r=r,
                            items=items,
                            search_rows=search_rows,
                            prompt_language=prompt_language,
                            stage1_model=stage1_model,
                            stage1_top_n=_STAGE1_TOP_N,
                            stage2_top_n=_STAGE2_TOP_N,
                            stage2_return_n=_STAGE2_RETURN_N,
                            fine_template=fine_template,
                            temperature=temperature,
                            w_rerank=w_rerank,
                            w_embed=w_embed,
                            w_cont=w_cont,
                            llm_label=llm_label,
                            project_id=project_id,
                            task_id=task_id,
                            rerank_work_dir=work,
                        )

                async def _wrapped(pos: int, r: Dict[str, Any]) -> None:
                    nonlocal done
                    try:
                        idx, out_row = await _one_item(pos, r)
                        partial[idx] = out_row
                    except Exception as e:
                        logger.exception("omni_shot_match row failed item_index=%s", pos)
                        partial[pos] = {"error": str(e), **(search_rows[pos] if isinstance(search_rows[pos], dict) else {})}
                    async with lock:
                        done += 1
                        pct = 35.0 + 55.0 * (done / max(1, total))
                        task_progress_store.set_state(
                            scope=self.SCOPE,
                            project_id=project_id,
                            task_id=task_id,
                            status="processing",
                            progress=min(92.0, pct),
                            message=f"排序进度 {done}/{total}",
                            phase="rerank_fine",
                        )

                await asyncio.gather(*[_wrapped(i, row) for i, row in enumerate(search_rows) if isinstance(row, dict)])

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                out_rows = merge_fine_scores_and_continuity(
                    search_results=search_rows,
                    partial_by_index=partial,
                    output_top_k=_OUTPUT_TOP_K,
                    w_rerank=w_rerank,
                    w_embed=w_embed,
                    w_cont=w_cont,
                )

                rerank_path = work / "rerank.json"
                rerank_payload = {
                    "meta": {
                        "project_id": project_id,
                        "input_search_topk_path": topk_web,
                        "copywriting_embeddings_path": str(emb_web),
                        "omni_multimodal_json_path": str(mm_web),
                        "output_top_k": _OUTPUT_TOP_K,
                        "stage1_top_n": _STAGE1_TOP_N,
                        "stage2_top_n": _STAGE2_TOP_N,
                        "stage2_return_n": _STAGE2_RETURN_N,
                        "stage1_mode": "embedding",
                        "models": {"stage1": stage1_model, "stage2": llm_label},
                        "weights": {"rerank_score": w_rerank, "embedding_score": w_embed, "continuity_score": w_cont},
                        "generated_at": datetime.now().isoformat(),
                    },
                    "results": out_rows,
                }
                rerank_path.write_text(json.dumps(rerank_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                rerank_web = _to_web_path(rerank_path)
                projects_store.update_project(
                    project_id,
                    {
                        "omni_shot_match_rerank_path": rerank_web,
                        "omni_shot_match_updated_at": datetime.now().isoformat(),
                    },
                )

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="completed",
                    progress=100,
                    message="排序完成",
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
                logger.exception("omni_shot_match failed")
                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="failed",
                    message=f"失败: {e}",
                    phase="failed",
                )
            finally:
                await project_task_queue.release(project_id)

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


async def _process_row(
    *,
    pos: int,
    r: Dict[str, Any],
    items: List[Dict[str, Any]],
    search_rows: List[Dict[str, Any]],
    prompt_language: str,
    stage1_model: str,
    stage1_top_n: int,
    stage2_top_n: int,
    stage2_return_n: int,
    fine_template: str,
    temperature: float,
    w_rerank: float,
    w_embed: float,
    w_cont: float,
    llm_label: str,
    project_id: str,
    task_id: str,
    rerank_work_dir: Path,
) -> Tuple[int, Dict[str, Any]]:
    import time as _time

    t0 = _time.time()
    item_index = int(r.get("item_index", pos) or pos)
    use_translation = str(prompt_language or "zh").strip().lower() == "en"
    text = (
        ((r.get("translation") or r.get("text") or "") if use_translation else (r.get("text") or "")).strip()
    )
    matches = r.get("matches") or []
    if not isinstance(matches, list) or not matches:
        return pos, dict(r)

    emb_item: Dict[str, Any] = items[item_index] if 0 <= item_index < len(items) and isinstance(items[item_index], dict) else {}
    narr: Dict[str, Any] = {"text": text}
    for k in ["event", "subject", "emotion", "scene_type", "action", "camera_hint"]:
        if isinstance(emb_item, dict):
            narr[k] = emb_item.get(k)

    prev_text = ""
    next_text = ""
    if item_index - 1 >= 0 and isinstance(search_rows[item_index - 1], dict):
        _p = search_rows[item_index - 1]
        prev_text = (
            ((_p.get("translation") or _p.get("text") or "") if use_translation else (_p.get("text") or "")).strip()
        )
    if item_index + 1 < len(search_rows) and isinstance(search_rows[item_index + 1], dict):
        _n = search_rows[item_index + 1]
        next_text = (
            ((_n.get("translation") or _n.get("text") or "") if use_translation else (_n.get("text") or "")).strip()
        )

    docs = build_rerank_documents(matches, prompt_language)
    total_shots, last_shot_end = get_timeline_info(docs)
    query_block = build_narration_block(
        narr,
        prev_text,
        next_text,
        item_index,
        len(search_rows),
        total_shots,
        last_shot_end,
        prompt_language,
    )

    coarse_cost = 0.0
    coarse_score_map: Dict[Any, float] = {}
    stage1_mode = "embedding"
    t1 = _time.time()
    for d in docs:
        sid = d.get("shot_id")
        if sid is not None:
            coarse_score_map[sid] = float(d.get("embedding_score") or 0.0)
    coarse_cost = _time.time() - t1

    docs_sorted = sorted(docs, key=lambda d: coarse_score_map.get(d.get("shot_id"), 0.0), reverse=True)
    top_stage1 = docs_sorted[: max(1, min(int(stage1_top_n or 15), len(docs_sorted)))]

    fine_docs = [
        {
            "shot_id": d["shot_id"],
            "start": d.get("start"),
            "end": d.get("end"),
            "summary": d.get("summary_no_abstract"),
            "embedding_score": d.get("embedding_score"),
        }
        for d in top_stage1[: max(1, min(int(stage2_top_n or 15), len(top_stage1)))]
    ]
    n_ret = max(1, int(stage2_return_n or 3))
    fine_prompt = fine_template.format(
        query=query_block,
        candidates_json=json.dumps(fine_docs, ensure_ascii=False),
        stage2_return_n=n_ret,
    )
    machine_hint = (
        "\n\n【最终输出（硬性约束）】除相邻两行之间的单个换行外，不要输出任何其它文字。"
        f"至多 {n_ret} 行，每行唯一格式：shot_id|score（ASCII 竖线 |，score 为 0~1 小数）；"
        "shot_id 须与候选 JSON 中完全一致；按 score 从高到低；行末不要空格。"
        "禁止：标题、##、**、列表、分析、理由、空行、markdown、代码块。"
    )
    user_full = fine_prompt + machine_hint
    t2 = _time.time()
    try:
        resp = await ai_service.send_chat(
            [ChatMessage(role="user", content=user_full)],
            temperature=float(temperature),
            usage=LlmModelUsage.LLM_RERANK,
            timeout=300,
        )
    except Exception as e:
        await asyncio.to_thread(
            _log_omni_shot_match_rerank_failure,
            rerank_work_dir,
            pos,
            project_id,
            task_id,
            f"{type(e).__name__}: {e}",
            user_full,
        )
        raise
    fine_cost = _time.time() - t2
    fine_items = normalize_llm_scores(parse_fine_llm_payload(resp.content or ""))[:n_ret]
    fine_map: Dict[Any, Dict[str, Any]] = {it.get("shot_id"): it for it in fine_items if isinstance(it, dict)}

    reranked_matches: List[Dict[str, Any]] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        sid = m.get("shot_id")
        emb_score = float(m.get("score") or 0.0)
        llm_item = fine_map.get(sid) or {}
        rerank_score = float(llm_item.get("score") or coarse_score_map.get(sid, 0.0) or 0.0)
        reason = (llm_item.get("reason") or "").strip()
        out_m = dict(m)
        out_m["embedding_score"] = emb_score
        out_m["coarse_rerank_score"] = float(coarse_score_map.get(sid, 0.0) or 0.0)
        out_m["rerank_score"] = rerank_score
        if reason:
            out_m["reason"] = reason
        reranked_matches.append(out_m)

    reranked_matches.sort(
        key=lambda x: (float(x.get("rerank_score") or 0.0), float(x.get("embedding_score") or 0.0)),
        reverse=True,
    )

    elapsed = _time.time() - t0
    out_row = {
        **dict(r),
        "rerank": {
            "models": {"stage1": stage1_model, "stage2": llm_label},
            "stage1_mode": stage1_mode,
            "weights": {"rerank_score": w_rerank, "embedding_score": w_embed, "continuity_score": w_cont},
            "timing_seconds": {"stage1": float(coarse_cost), "stage2": float(fine_cost), "total": float(elapsed)},
        },
        "matches": reranked_matches,
    }
    return pos, out_row


omni_shot_match_service = OmniShotMatchService()
