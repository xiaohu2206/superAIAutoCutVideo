#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni：在「文案结构化 + 向量化」与「多模态镜头 JSON」之上做镜头粗筛（向量）、
粗排（召回 rerank API）、精排（content 模型）与连续性融合重排。
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

import httpx

from modules.ai import ChatMessage
from modules.config.ai_search_shot_model_config import ai_search_shot_model_config_manager
from modules.omni_shot_match import (
    build_embedding_search_results,
    build_narration_block,
    build_rerank_documents,
    get_timeline_info,
    load_fine_prompt_template,
    merge_fine_scores_and_continuity,
    normalize_llm_scores,
    parse_fine_llm_payload,
)
from modules.projects_store import projects_store
from modules.task_cancel_store import task_cancel_store
from modules.task_progress_store import task_progress_store
from services.ai_service import ai_service
from services.extract_subtitle_service import _resolve_path, _to_web_path, _uploads_dir
from services.omni_internal.multimodal_json_crypto import read_multimodal_json

logger = logging.getLogger(__name__)

_SCOPE = "omni_shot_match"

# 常量开关：为 True 时跳过 Stage1 rerank HTTP 调用，直接用 embedding_score 作为粗排分数
SKIP_STAGE1_RERANK = True


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
        top_k: int = 20,
        stage1_top_n: int = 10,
        stage2_top_n: int = 3,
        stage2_return_n: int = 3,
    output_top_k: int = 0,
    concurrency: int = 4,
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
            message="准备镜头粗筛与重排…",
            phase="preparing",
        )

        sem_n = max(1, int(concurrency or 4))

        async def _run() -> None:
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
                embedding_model_hint = (meta or {}).get("embedding_model") if isinstance(meta, dict) else None

                mm_data = await asyncio.to_thread(read_multimodal_json, mm_abs)
                shots = (mm_data.get("shots") if isinstance(mm_data, dict) else None) or []
                if not isinstance(shots, list) or not shots:
                    raise ValueError("多模态 JSON 中 shots 为空")

                cfg = ai_search_shot_model_config_manager.get_config()
                if not cfg or not (cfg.api_key or "").strip():
                    raise ValueError("请先在「向量模型」设置中配置 API Key")
                if not SKIP_STAGE1_RERANK and not str(cfg.rerank_base_url or "").strip():
                    raise ValueError("未配置召回/重排接口 rerank_base_url")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=8,
                    message="向量粗筛（cosine TopK）…",
                    phase="embedding_topk",
                )

                search_rows = build_embedding_search_results(
                    copy_items=items,
                    shots=shots,
                    top_k=max(1, int(top_k or 20)),
                    embedding_model_hint=str(embedding_model_hint) if embedding_model_hint else None,
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
                        "top_k": max(1, int(top_k or 20)),
                        "score_method": "cosine_similarity",
                        "count_copywriting_items": len(items),
                        "count_shots_total": len(shots),
                        "prompt_language": prompt_language,
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

                rerank_model = str(cfg.rerank_model or "")
                stage1_instruct = (rerank_instruct or "").strip()
                if not stage1_instruct:
                    if prompt_language == "en":
                        stage1_instruct = (
                            "Given a narration query, retrieve the most relevant shot descriptions "
                            "that best match the query."
                        )
                    else:
                        stage1_instruct = "给定一段解说文案，检索与其最相关、最匹配的镜头描述。"

                fine_template = load_fine_prompt_template(prompt_language)
                llm_info = ai_service.get_provider_info()
                llm_label = f"{llm_info.get('active_provider') or ''}/{llm_info.get('active_model') or ''}".strip("/")

                task_progress_store.set_state(
                    scope=self.SCOPE,
                    project_id=project_id,
                    task_id=task_id,
                    status="processing",
                    progress=35,
                    message="粗排 + 精排（每条解说）…",
                    phase="rerank_fine",
                )

                sem = asyncio.Semaphore(sem_n)
                total = len(search_rows)
                partial: Dict[int, Dict[str, Any]] = {}
                done = 0
                lock = asyncio.Lock()

                async def _rerank_http(
                    query: str,
                    documents: List[str],
                    top_n: int,
                ) -> List[Dict[str, Any]]:
                    headers = {
                        "Authorization": f"Bearer {cfg.api_key}",
                        "Content-Type": "application/json",
                    }
                    payload: Dict[str, Any] = {
                        "model": rerank_model,
                        "query": query,
                        "documents": documents,
                        "top_n": max(1, min(top_n, len(documents))),
                    }
                    if stage1_instruct:
                        payload["instruct"] = stage1_instruct
                    timeout = httpx.Timeout(float(cfg.timeout_seconds or 300))
                    retries = max(1, int(cfg.max_retries or 3))
                    base_sleep = float(cfg.retry_sleep_seconds or 2.0)
                    last_err: Optional[Exception] = None
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        for attempt in range(retries):
                            try:
                                r = await client.post(str(cfg.rerank_base_url), headers=headers, json=payload)
                                r.raise_for_status()
                                data = r.json()
                                results = None
                                if isinstance(data, list):
                                    results = data
                                elif isinstance(data, dict):
                                    if isinstance(data.get("results"), list):
                                        results = data.get("results")
                                    elif isinstance(data.get("data"), list):
                                        results = data.get("data")
                                if not isinstance(results, list):
                                    raise RuntimeError(f"rerank 返回结构异常: {data}")
                                out: List[Dict[str, Any]] = []
                                for row in results:
                                    if isinstance(row, dict):
                                        out.append(row)
                                return out
                            except asyncio.CancelledError:
                                raise
                            except Exception as e:
                                last_err = e
                                if attempt + 1 >= retries:
                                    break
                                await asyncio.sleep(min(60.0, base_sleep * (2**attempt)))
                    raise RuntimeError(f"rerank 调用失败: {last_err}")

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
                            skip_stage1_rerank=SKIP_STAGE1_RERANK,
                            rerank_model=rerank_model,
                            stage1_instruct=stage1_instruct,
                            stage1_top_n=stage1_top_n,
                            stage2_top_n=stage2_top_n,
                            stage2_return_n=stage2_return_n,
                            fine_template=fine_template,
                            temperature=temperature,
                            w_rerank=w_rerank,
                            w_embed=w_embed,
                            w_cont=w_cont,
                            llm_label=llm_label,
                            _rerank_http=_rerank_http,
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
                            message=f"重排进度 {done}/{total}",
                            phase="rerank_fine",
                        )

                await asyncio.gather(*[_wrapped(i, row) for i, row in enumerate(search_rows) if isinstance(row, dict)])

                if task_cancel_store.is_cancelled(self.SCOPE, project_id, task_id):
                    raise asyncio.CancelledError()

                out_rows = merge_fine_scores_and_continuity(
                    search_results=search_rows,
                    partial_by_index=partial,
                    output_top_k=max(0, int(output_top_k or 0)),
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
                        "output_top_k": int(output_top_k or 0),
                        "stage1_top_n": int(stage1_top_n or 10),
                        "stage2_top_n": int(stage2_top_n or 3),
                        "stage2_return_n": int(stage2_return_n or 3),
                        "skip_stage1_rerank": bool(SKIP_STAGE1_RERANK),
                        "models": {"stage1": rerank_model, "stage2": llm_label},
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
                    message="镜头粗筛与重排完成",
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

        asyncio.create_task(_run())
        return {"task_id": task_id, "status": "pending", "message": "任务已提交"}


async def _process_row(
    *,
    pos: int,
    r: Dict[str, Any],
    items: List[Dict[str, Any]],
    search_rows: List[Dict[str, Any]],
    prompt_language: str,
    skip_stage1_rerank: bool,
    rerank_model: str,
    stage1_instruct: str,
    stage1_top_n: int,
    stage2_top_n: int,
    stage2_return_n: int,
    fine_template: str,
    temperature: float,
    w_rerank: float,
    w_embed: float,
    w_cont: float,
    llm_label: str,
    _rerank_http: Any,
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
    stage1_mode = "rerank"
    t1 = _time.time()
    if skip_stage1_rerank:
        stage1_mode = "embedding"
        for d in docs:
            sid = d.get("shot_id")
            if sid is not None:
                coarse_score_map[sid] = float(d.get("embedding_score") or 0.0)
    else:
        documents = [d.get("text", "") or "" for d in docs]
        coarse_raw = await _rerank_http(
            query=(narr.get("text", "") or ""),
            documents=documents,
            top_n=max(1, min(int(stage1_top_n or 10), len(documents))),
        )
        coarse_cost = _time.time() - t1
        if isinstance(coarse_raw, list):
            for rr_item in coarse_raw:
                if not isinstance(rr_item, dict):
                    continue
                try:
                    idx = int(rr_item.get("index"))
                    sc = float(rr_item.get("relevance_score"))
                except Exception:
                    continue
                if 0 <= idx < len(docs):
                    sid = docs[idx].get("shot_id")
                    coarse_score_map[sid] = sc

    docs_sorted = sorted(docs, key=lambda d: coarse_score_map.get(d.get("shot_id"), 0.0), reverse=True)
    top_stage1 = docs_sorted[: max(1, min(int(stage1_top_n or 10), len(docs_sorted)))]

    fine_docs = [
        {
            "shot_id": d["shot_id"],
            "start": d.get("start"),
            "end": d.get("end"),
            "summary": d.get("summary"),
            "embedding_score": d.get("embedding_score"),
        }
        for d in top_stage1[: max(1, min(int(stage2_top_n or 3), len(top_stage1)))]
    ]
    n_ret = max(1, int(stage2_return_n or 3))
    fine_prompt = fine_template.format(
        query=query_block,
        candidates_json=json.dumps(fine_docs, ensure_ascii=False),
        stage2_return_n=n_ret,
    )
    # 与 omni_copywriting_struct_embed 一致：content 模型 + response_format json_object（对应 demo 的 chat_json）
    machine_hint = (
        "\n\n【机器可读输出】仅输出一个 JSON 对象（不要 markdown 代码块、不要其它说明文字）。"
        "格式：{\"items\":[{\"shot_id\":<与候选一致>,\"score\":0到1的小数,\"reason\":\"一句简短理由\"},...]}；"
        f"items 按 score 从高到低排序，最多 {n_ret} 条；reason 勿为空。"
    )
    t2 = _time.time()
    resp = await ai_service.send_chat(
        [ChatMessage(role="user", content=fine_prompt + machine_hint)],
        response_format={"type": "json_object"},
        temperature=float(temperature),
    )
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
            "models": {"stage1": rerank_model, "stage2": llm_label},
            "stage1_mode": stage1_mode,
            "weights": {"rerank_score": w_rerank, "embedding_score": w_embed, "continuity_score": w_cont},
            "timing_seconds": {"stage1": float(coarse_cost), "stage2": float(fine_cost), "total": float(elapsed)},
        },
        "matches": reranked_matches,
    }
    return pos, out_row


omni_shot_match_service = OmniShotMatchService()
