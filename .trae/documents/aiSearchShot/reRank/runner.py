import json
import logging
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from utils import build_model_client


logger = logging.getLogger("AIShotSearch")


logger = logging.getLogger("AIShotSearch")


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _abs_path(project_root: str, p: str) -> str:
    if not p:
        return project_root
    return p if os.path.isabs(p) else os.path.join(project_root, p)


def _get_stage(i: int, total: int, language: str = "zh") -> str:
    if total <= 0:
        return "unknown" if language == "en" else "未知"
    ratio = float(i) / float(total)
    if ratio < 0.15:
        return "opening - world building" if language == "en" else "开头-建立世界观"
    if ratio < 0.4:
        return "development - character setup" if language == "en" else "发展-人物展开"
    if ratio < 0.7:
        return "conflict - tension rising" if language == "en" else "冲突-矛盾激化"
    if ratio < 0.9:
        return "climax - emotional peak" if language == "en" else "高潮-情绪爆发"
    return "ending - resolution" if language == "en" else "结尾-收束"


def _get_position_hint(idx: int, total: int, language: str = "zh") -> str:
    if total <= 0:
        return "position unknown" if language == "en" else "位置未知"
    ratio = float(idx) / float(total)
    if ratio <= 0.33:
        return "early" if language == "en" else "前部"
    if ratio <= 0.66:
        return "middle" if language == "en" else "中部"
    return "late" if language == "en" else "后部"


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_prompt_template(project_root: str, prompt_language: str, filename_zh: str, filename_en: str) -> str:
    language = str(prompt_language or "zh").strip().lower()
    filename = filename_en if language == "en" else filename_zh
    return _read_text(os.path.join(project_root, "reRank", filename))


def _get_timeline_info(matches: List[Dict[str, Any]]) -> Tuple[int, Optional[float]]:
    shot_ids: List[int] = []
    max_end: Optional[float] = None
    for m in matches:
        if not isinstance(m, dict):
            continue
        try:
            sid = int(m.get("shot_id"))
            shot_ids.append(sid)
        except Exception:
            pass
        end_val = _safe_float(m.get("end"))
        if end_val is not None:
            max_end = end_val if max_end is None else max(max_end, end_val)
    return (max(shot_ids) + 1) if shot_ids else 0, max_end


def _build_query(
    narr: Dict[str, Any],
    prev_text: str,
    next_text: str,
    idx: int,
    total: int,
    total_shots: int,
    last_shot_end: Optional[float],
    prompt_language: str = "zh",
) -> str:
    def _g(k: str) -> str:
        v = narr.get(k)
        return (str(v) if v is not None else "").strip()

    language = str(prompt_language or "zh").strip().lower()
    position_hint = _get_position_hint(idx, total, language)

    if language == "en":
        last_shot_end_text = f"{last_shot_end:.0f}s" if last_shot_end is not None else "unknown"
        prev_text_value = (prev_text or "none").strip()
        next_text_value = (next_text or "none").strip()
        parts = [
            "[Current Narration]",
            f"<< {_g('text')} >>\n",
            "",
            "[Semantic Info]",
            f"event: {_g('event')}",
            f"subject: {_g('subject')}",
            f"emotion: {_g('emotion')}",
            f"action: {_g('action')}",
            f"scene_type: {_g('scene_type')}",
            f"camera_hint: {_g('camera_hint')}",
            "",
            "[Context]",
            f"previous: {prev_text_value}",
            f"next: {next_text_value}",
            "",
            "[Narrative Position]",
            f"segment: {idx} / {total}",
            f"stage: {_get_stage(idx, total, language)}",
            f"narration position: {position_hint} (usually prefer shots located in the {position_hint} part of the film as well, but this is not an absolute rule)",
            "",
            "[Film Shot Info]",
            f"total shots: {total_shots}",
            f"latest shot end time: {last_shot_end_text}",
            "shot_id is the sequential index of the shot in the full film. Smaller values are earlier, larger values are later.",
            "start is the shot start time in seconds, and end is the shot end time in seconds.",
            "summary is the visual summary of the shot, and embedding_score is the initial semantic retrieval score for the current narration.",
            "",
            "[Editing Goal]",
            "Choose the shot that best matches the semantics, emotion, and current narrative stage.",
        ]
        return "\n".join(parts).strip()

    last_shot_end_text = f"{last_shot_end:.0f}s" if last_shot_end is not None else "未知"
    parts = [
        "【当前文案】",
        f"<< {_g('text')} >>\n",
        "",
        "【语义信息】",
        f"事件：{_g('event')}",
        f"主体：{_g('subject')}",
        f"情绪：{_g('emotion')}",
        f"动作：{_g('action')}",
        f"场景：{_g('scene_type')}",
        f"镜头建议：{_g('camera_hint')}",
        "",
        "【上下文】",
        f"前文：{(prev_text or '无').strip()}",
        f"后文：{(next_text or '无').strip()}",
        "",
        "【剧情位置】",
        f"第 {idx} 段 / 共 {total} 段",
        f"阶段：{_get_stage(idx, total, language)}",
        f"当前文案位置：{position_hint}（通常优先匹配同样位于影片{position_hint}的镜头，但不是绝对规则）",
        "",
        "【影片镜头信息】",
        f"总镜头数：{total_shots} 个",
        f"末尾镜头时间：{last_shot_end_text}",
        "shot_id 代表镜头在整部影片中的顺序编号，数值越小越靠前，数值越大越靠后。",
        "start 表示该镜头开始时间（秒），end 表示该镜头结束时间（秒）。",
        "summary 表示该镜头的画面内容摘要，embedding_score 表示该镜头与当前文案的初始语义召回分数。",
        "",
        "【剪辑目标】",
        "选择最符合语义、情绪，并且适合当前剧情阶段的镜头",
    ]
    return "\n".join(parts).strip()

def _build_docs(matches: List[Dict[str, Any]], prompt_language: str = "zh") -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    language = str(prompt_language or "zh").strip().lower()
    for m in matches:
        if not isinstance(m, dict):
            continue
        shot_id = m.get("shot_id")
        start = m.get("start")
        end = m.get("end")
        summary = (m.get("summary") or "").strip()
        embedding_score = float(m.get("score") or 0.0)
        if language == "en":
            text = f"Visual: {summary}\nTime: {start}-{end}".strip()
        else:
            text = f"画面：{summary}\n时间：{start}-{end}".strip()
        docs.append(
            {
                "shot_id": shot_id,
                "start": start,
                "end": end,
                "summary": summary,
                "text": text,
                "embedding_score": embedding_score,
            }
        )
    return docs


def _guess_scene_tag(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if "室内" in t:
        return "室内"
    if "室外" in t:
        return "室外"
    return ""


def _continuity_score(prev_shot: Optional[Dict[str, Any]], cur: Dict[str, Any]) -> float:
    score = 1.0
    if not prev_shot:
        return score
    try:
        prev_end = float(prev_shot.get("end") or 0.0)
        cur_start = float(cur.get("start") or 0.0)
        if abs(cur_start - prev_end) > 30.0:
            score -= 0.3
    except Exception:
        pass

    prev_scene = _guess_scene_tag(str(prev_shot.get("summary") or ""))
    cur_scene = _guess_scene_tag(str(cur.get("summary") or ""))
    if prev_scene and cur_scene and prev_scene != cur_scene:
        score -= 0.2
    if score < 0.0:
        score = 0.0
    return float(score)


def _normalize_llm_scores(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return items
    scores: List[float] = []
    for it in items:
        try:
            s = float(it.get("score"))
        except Exception:
            s = 0.0
        if not (0.0 <= s <= 1.0):
            scores.append(max(0.0, min(1.0, s)))
        else:
            scores.append(s)
    mx = max(scores) if scores else 0.0
    mn = min(scores) if scores else 0.0
    if mx <= 1.0 and mn >= 0.0:
        return items
    span = mx - mn
    if span <= 1e-9:
        for it in items:
            it["score"] = 0.5
        return items
    for it, s in zip(items, scores):
        it["score"] = (s - mn) / span
    return items


def _safe_json_parse(s: str) -> Any:
    raw = (s or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(\w+)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def run_rerank(config_path: str = None) -> str:
    """
    Step4.5 重排序（Re-rank）：
    - 输入 Step4 的 TopK 召回结果（output/copywriting_to_shots_top20.json）
    - 结合 Step3 / 原始结构化文案（copywriting_format_embeddings.json / copywriting_format.json）
    - 默认：云雾 rerank 粗排 + LLM 精排；若配置 skip_stage1_rerank=true，则跳过 rerank API，按 embedding 取 TopN 后直接进入 LLM 精排
    - 再融合 embedding_score 与 continuity_score 输出最终 matches 顺序
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    if config_path is None:
        config_path = os.path.join(project_root, "config.json")

    cfg = _read_json(config_path) if os.path.exists(config_path) else {}
    rr = cfg.get("step4_5_rerank") or {}
    c_cfg = cfg.get("copywriting_structuring") or {}
    prompt_language = str(c_cfg.get("prompt_language") or "zh").strip().lower()

    # Step4.5 输入：可显式配置 input_topk_json；否则从 Step4 的配置推导。
    input_topk_json = rr.get("input_topk_json")
    if not input_topk_json:
        ss = cfg.get("search_shots") or {}
        ss_out = ss.get("output_json")
        if ss_out:
            input_topk_json = ss_out
        else:
            try:
                top_k = int(ss.get("top_k", 20) or 20)
            except Exception:
                top_k = 20
            if top_k <= 0:
                top_k = 20
            input_topk_json = f"output/copywriting_to_shots_top{top_k}.json"
    copy_emb_json = rr.get("copywriting_embeddings_json") or "output/copywriting_format_embeddings.json"
    copy_fmt_json = rr.get("copywriting_format_json") or "inputFile/copywriting_format.json"
    output_json = rr.get("output_json") or "output/copywriting_to_shots_rerank.json"

    stage1_top_n = int(rr.get("stage1_top_n", 10) or 10)
    stage2_top_n = int(rr.get("stage2_top_n", 3) or 3)
    stage2_return_n = int(rr.get("stage2_return_n", 3) or 3)
    output_top_k_cfg = rr.get("output_top_k", 0)
    try:
        output_top_k = int(output_top_k_cfg)
    except Exception:
        output_top_k = 0
    concurrency_cfg = rr.get("concurrency", 0)
    try:
        concurrency = int(concurrency_cfg)
    except Exception:
        concurrency = 0

    weights = rr.get("weights") or {}
    w_rerank = float(weights.get("rerank_score", 0.55) or 0.55)
    w_embed = float(weights.get("embedding_score", 0.30) or 0.30)
    w_cont = float(weights.get("continuity_score", 0.15) or 0.15)

    stage1_instruct = rr.get("stage1_instruct")
    if not stage1_instruct:
        if prompt_language == "en":
            stage1_instruct = "Given a narration query, retrieve the most relevant shot descriptions that best match the query."
        else:
            stage1_instruct = "给定一段解说文案，检索与其最相关、最匹配的镜头描述。"
    temperature = float(rr.get("temperature", 0.2) or 0.2)
    max_retries = int(rr.get("max_retries", 2) or 0)
    retry_sleep_seconds = float(rr.get("retry_sleep_seconds", 2) or 1.0)

    input_abs = _abs_path(project_root, input_topk_json)
    copy_emb_abs = _abs_path(project_root, copy_emb_json)
    copy_fmt_abs = _abs_path(project_root, copy_fmt_json)
    out_abs = _abs_path(project_root, output_json)
    reuse_existing = bool(rr.get("reuse_existing_output", True))
    skip_stage1_rerank = bool(rr.get("skip_stage1_rerank", False))

    # 断点复用：如果输出已存在，则跳过阶段1粗排，直接进入阶段2 LLM（与 skip_stage1_rerank 互斥：跳过 rerank 时不复用文件里的 coarse）
    existing_payload: Optional[Dict[str, Any]] = None
    if reuse_existing and os.path.exists(out_abs):
        try:
            existing_payload = _read_json(out_abs)
        except Exception:
            existing_payload = None

    top20_payload = _read_json(input_abs)
    results = top20_payload.get("results") if isinstance(top20_payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("input_topk_json 格式不正确，必须包含 results 数组")

    copy_emb_payload = _read_json(copy_emb_abs)
    emb_items = copy_emb_payload.get("items") if isinstance(copy_emb_payload, dict) else None
    if not isinstance(emb_items, list):
        emb_items = []

    try:
        copy_fmt_payload = _read_json(copy_fmt_abs)
        fmt_items = copy_fmt_payload if isinstance(copy_fmt_payload, list) else []
    except Exception:
        fmt_items = []

    client = build_model_client(cfg)
    provider = str((cfg.get("model_provider") or "yunwu")).strip().lower()
    provider_cfg = (
        cfg.get("custom_openai")
        if provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}

    # 模型选择：
    # - 优先使用 step4_5_rerank.models 显式配置
    # - 若使用 custom_openai 且未显式配置 llm_model，则回落到 custom_openai.llm_model
    models = rr.get("models") or {}
    rerank_model = models.get("rerank_model") or "qwen3-rerank"
    llm_model = models.get("llm_model") or provider_cfg.get("llm_model") or "glm-4"
    rerank_provider = str(provider_cfg.get("rerank_provider") or provider).strip().lower()
    rerank_provider_cfg = (
        cfg.get("custom_openai")
        if rerank_provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}

    total = len(results)
    if concurrency <= 0:
        # “无限并发”：按任务数开到最大（注意这会非常吃带宽/额度）
        concurrency = max(1, total)

    lock = threading.Lock()
    completed = 0

    # 第一段：并发跑模型，只拿 rerank_score/reason 等，不计算 continuity/final（连续性需要按顺序）
    partial_results: List[Optional[Dict[str, Any]]] = [None] * total

    def _process_one(pos: int, r: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        t0 = time.time()
        item_index = int(r.get("item_index", pos) or pos)
        _use_translation = str(prompt_language or "zh").strip().lower() == "en"
        text = ((r.get("translation") or r.get("text") or "") if _use_translation else (r.get("text") or "")).strip()
        matches = r.get("matches") or []
        if not isinstance(matches, list) or not matches:
            return pos, dict(r)

        narr: Dict[str, Any] = {"text": text}
        if 0 <= item_index < len(emb_items) and isinstance(emb_items[item_index], dict):
            narr.update(
                {k: emb_items[item_index].get(k) for k in ["event", "subject", "emotion", "scene_type", "action", "camera_hint"]}
            )
        elif 0 <= item_index < len(fmt_items) and isinstance(fmt_items[item_index], dict):
            narr.update(
                {k: fmt_items[item_index].get(k) for k in ["event", "subject", "emotion", "scene_type", "action", "camera_hint"]}
            )

        prev_text = ""
        next_text = ""
        if item_index - 1 >= 0 and (item_index - 1) < len(results) and isinstance(results[item_index - 1], dict):
            _prev = results[item_index - 1]
            prev_text = ((_prev.get("translation") or _prev.get("text") or "") if _use_translation else (_prev.get("text") or "")).strip()
        if item_index + 1 < len(results) and isinstance(results[item_index + 1], dict):
            _next = results[item_index + 1]
            next_text = ((_next.get("translation") or _next.get("text") or "") if _use_translation else (_next.get("text") or "")).strip()

        
        docs = _build_docs(matches, prompt_language)
        total_shots, last_shot_end = _get_timeline_info(docs)
        query = _build_query(
            narr,
            prev_text,
            next_text,
            item_index,
            total,
            total_shots,
            last_shot_end,
            prompt_language,
        )
        coarse_cost = 0.0
        coarse_score_map: Dict[Any, float] = {}

        reused_stage1 = False
        stage1_mode = "rerank"
        if skip_stage1_rerank:
            stage1_mode = "embedding"
            for d in docs:
                sid = d.get("shot_id")
                if sid is not None:
                    coarse_score_map[sid] = float(d.get("embedding_score") or 0.0)
        elif existing_payload and isinstance(existing_payload.get("results"), list):
            # 如果已有输出文件：直接读取该 item 的 coarse_rerank_score 作为阶段1结果
            for ex_item in existing_payload["results"]:
                if not isinstance(ex_item, dict):
                    continue
                if int(ex_item.get("item_index", -1) or -1) != item_index:
                    continue
                ex_matches = ex_item.get("matches") or []
                if isinstance(ex_matches, list):
                    for em in ex_matches:
                        if not isinstance(em, dict):
                            continue
                        sid = em.get("shot_id")
                        if sid is None:
                            continue
                        try:
                            sc = float(em.get("coarse_rerank_score") or 0.0)
                        except Exception:
                            sc = 0.0
                        coarse_score_map[sid] = sc
                    reused_stage1 = True
                break
            if reused_stage1:
                stage1_mode = "reused"

        # 阶段1：粗排用 /v1/rerank（qwen3-rerank 不支持 chat.completions）；skip_stage1_rerank 时已用 embedding 填好 coarse_score_map
        if not skip_stage1_rerank and not reused_stage1:
            documents = [d.get("text", "") or "" for d in docs]
            t1 = time.time()
            coarse_results = client.rerank(
                model=rerank_model,
                query=(narr.get("text", "") or ""),
                documents=documents,
                top_n=max(1, min(stage1_top_n, len(documents))),
                instruct=str(stage1_instruct),
                max_retries=max_retries,
                retry_sleep_seconds=retry_sleep_seconds,
                provider_override=(rerank_provider, rerank_provider_cfg),
            )
            coarse_cost = time.time() - t1
            logger.info("[stage1 rerank] coarse_results: %s", json.dumps(coarse_results, ensure_ascii=False) if isinstance(coarse_results, (list, dict)) else str(coarse_results))

            if isinstance(coarse_results, list):
                for rr_item in coarse_results:
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
        top_stage1 = docs_sorted[: max(1, min(stage1_top_n, len(docs_sorted)))]

        fine_schema = {
            "name": "fine_rerank",
            "strict": True,
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"shot_id": {}, "score": {"type": "number"}, "reason": {"type": "string"}},
                    "required": ["shot_id", "score", "reason"],
                    "additionalProperties": False,
                },
            },
        }
        fine_docs = [
            {
                "shot_id": d["shot_id"],
                "start": d.get("start"),
                "end": d.get("end"),
                "summary": d.get("summary"),
                "embedding_score": d.get("embedding_score"),
            }
            for d in top_stage1[: max(1, min(stage2_top_n, len(top_stage1)))]
        ]
        fine_prompt_template = _load_prompt_template(project_root, prompt_language, "fine_prompt_zh.md", "fine_prompt_en.md")
        fine_prompt = fine_prompt_template.format(
            query=query,
            candidates_json=json.dumps(fine_docs, ensure_ascii=False),
            stage2_return_n=max(1, stage2_return_n),
        )

        t2 = time.time()
        fine_resp_raw = client.chat_json(
            model=llm_model,
            user_prompt=fine_prompt,
            json_schema=fine_schema,
            temperature=temperature,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        fine_cost = time.time() - t2
        logger.info("[stage2 fine rerank] fine_resp_raw: %s", json.dumps(fine_resp_raw, ensure_ascii=False) if isinstance(fine_resp_raw, (list, dict)) else str(fine_resp_raw))

        fine_items: List[Dict[str, Any]] = []
        if isinstance(fine_resp_raw, list):
            for it in fine_resp_raw:
                if isinstance(it, dict) and "shot_id" in it:
                    fine_items.append(it)
        elif isinstance(fine_resp_raw, dict) and "items" in fine_resp_raw and isinstance(fine_resp_raw["items"], list):
            fine_items = [x for x in fine_resp_raw["items"] if isinstance(x, dict)]
        fine_items = _normalize_llm_scores(fine_items)[: max(1, stage2_return_n)]
        fine_map: Dict[Any, Dict[str, Any]] = {it.get("shot_id"): it for it in fine_items if isinstance(it, dict)}

        # 先写入 rerank_score（优先 fine，否则 coarse），reason 也写入；不做 continuity/final
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

        # 先按 rerank_score + embedding_score 做一个初排，方便后面 continuity 融合
        reranked_matches.sort(
            key=lambda x: (float(x.get("rerank_score") or 0.0), float(x.get("embedding_score") or 0.0)), reverse=True
        )

        elapsed = time.time() - t0
        return (
            pos,
            {
                **dict(r),
                "rerank": {
                    "models": {"stage1": rerank_model, "stage2": llm_model},
                    "stage1_mode": stage1_mode,
                    "weights": {"rerank_score": w_rerank, "embedding_score": w_embed, "continuity_score": w_cont},
                    "timing_seconds": {"stage1": float(coarse_cost), "stage2": float(fine_cost), "total": float(elapsed)},
                    "reused_stage1": bool(reused_stage1),
                },
                "matches": reranked_matches,
            },
        )

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = {}
        for pos, r in enumerate(results):
            if not isinstance(r, dict):
                continue
            futs[ex.submit(_process_one, pos, r)] = pos

        for fut in as_completed(futs):
            pos = futs[fut]
            try:
                idx_out, out_item = fut.result()
                partial_results[idx_out] = out_item
                ok = True
                err_msg = ""
            except Exception as e:
                ok = False
                err_msg = str(e)
                partial_results[pos] = {"error": err_msg, **(results[pos] if isinstance(results[pos], dict) else {})}

            with lock:
                completed += 1
                if ok:
                    logger.info(f"[step4.5] {completed:02d}/{total:02d} ok item_index={pos}")
                else:
                    logger.error(f"[step4.5] {completed:02d}/{total:02d} fail item_index={pos} err={err_msg}")

    # 第二段：按顺序计算 continuity + final_score，并把 score 写回（Step5 直接用）
    out_results: List[Dict[str, Any]] = []
    prev_selected: Optional[Dict[str, Any]] = None
    for pos in range(total):
        r = partial_results[pos]
        if not isinstance(r, dict):
            continue
        matches = r.get("matches") or []
        if not isinstance(matches, list) or not matches:
            out_results.append(dict(r))
            continue

        reranked_matches: List[Dict[str, Any]] = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            cont = _continuity_score(
                prev_selected,
                {"start": m.get("start"), "end": m.get("end"), "summary": m.get("summary")},
            )
            rerank_score = float(m.get("rerank_score") or 0.0)
            emb_score = float(m.get("embedding_score") or m.get("score") or 0.0)
            final_score = w_rerank * rerank_score + w_embed * emb_score + w_cont * cont
            out_m = dict(m)
            out_m["continuity_score"] = float(cont)
            out_m["final_score"] = float(final_score)
            out_m["score"] = float(final_score)
            reranked_matches.append(out_m)

        reranked_matches.sort(key=lambda x: float(x.get("final_score") or 0.0), reverse=True)
        if output_top_k and output_top_k > 0:
            reranked_matches = reranked_matches[:output_top_k]
        if reranked_matches:
            prev_selected = {
                "shot_id": reranked_matches[0].get("shot_id"),
                "start": reranked_matches[0].get("start"),
                "end": reranked_matches[0].get("end"),
                "summary": reranked_matches[0].get("summary"),
            }

        out_results.append({**dict(r), "matches": reranked_matches})

    payload = {
        "meta": {
            "input_topk_json": input_topk_json,
            "copywriting_embeddings_json": copy_emb_json,
            "copywriting_format_json": copy_fmt_json,
            "output_json": output_json,
            "stage1_top_n": stage1_top_n,
            "stage2_top_n": stage2_top_n,
            "stage2_return_n": stage2_return_n,
            "concurrency": concurrency,
            "models": {"stage1": rerank_model, "stage2": llm_model},
            "skip_stage1_rerank": skip_stage1_rerank,
            "weights": {"rerank_score": w_rerank, "embedding_score": w_embed, "continuity_score": w_cont},
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        },
        "results": out_results,
    }

    _write_json(out_abs, payload)
    return out_abs


if __name__ == "__main__":
    print(run_rerank())

