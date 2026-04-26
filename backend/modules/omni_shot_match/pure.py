# -*- coding: utf-8 -*-
"""Omni 镜头匹配：纯函数（与 visual / demo 脚本无 import 耦合）。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("nan")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return float("nan")
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def get_stage(i: int, total: int, language: str = "zh") -> str:
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


def get_position_hint(idx: int, total: int, language: str = "zh") -> str:
    if total <= 0:
        return "position unknown" if language == "en" else "位置未知"
    ratio = float(idx) / float(total)
    if ratio <= 0.33:
        return "early" if language == "en" else "前部"
    if ratio <= 0.66:
        return "middle" if language == "en" else "中部"
    return "late" if language == "en" else "后部"


def get_timeline_info(matches: List[Dict[str, Any]]) -> Tuple[int, Optional[float]]:
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


def build_narration_block(
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
    position_hint = get_position_hint(idx, total, language)

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
            f"stage: {get_stage(idx, total, language)}",
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
        f"阶段：{get_stage(idx, total, language)}",
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


def _strip_abstract(summary: str) -> str:
    """从 summary 中去除"摘要："段落，只保留"详细"和"字幕"部分。

    summary 格式示例：
        详细：中景，侧机位...画面描述。
        摘要：一家人围坐在餐桌前用餐...。
        字幕：哎呀，真没教养
    """
    import re

    if not summary:
        return summary
    # 移除 "摘要：" 开头到下一个标签（详细/字幕）或结尾的整个段落
    # 标签可能是中文冒号或英文冒号
    result = re.sub(r'\n?摘要[：:][^\n]*(\n|$)', '', summary)
    return result.strip()


def build_rerank_documents(matches: List[Dict[str, Any]], prompt_language: str = "zh") -> List[Dict[str, Any]]:
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
        # 提取 "详细"+"字幕"，去掉 "摘要" 段落
        summary_no_abstract = _strip_abstract(summary)
        if language == "en":
            text = f"Visual: {summary}\nTime: {start}-{end}".strip()
            text_no_abstract = f"Visual: {summary_no_abstract}\nTime: {start}-{end}".strip()
        else:
            text = f"画面：{summary}\n时间：{start}-{end}".strip()
            text_no_abstract = f"画面：{summary_no_abstract}\n时间：{start}-{end}".strip()
        docs.append(
            {
                "shot_id": shot_id,
                "start": start,
                "end": end,
                "summary": summary,
                "summary_no_abstract": summary_no_abstract,
                "text": text,
                "text_no_abstract": text_no_abstract,
                "embedding_score": embedding_score,
            }
        )
    return docs


def guess_scene_tag(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if "室内" in t:
        return "室内"
    if "室外" in t:
        return "室外"
    return ""


def continuity_score(prev_shot: Optional[Dict[str, Any]], cur: Dict[str, Any]) -> float:
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

    prev_scene = guess_scene_tag(str(prev_shot.get("summary") or ""))
    cur_scene = guess_scene_tag(str(cur.get("summary") or ""))
    if prev_scene and cur_scene and prev_scene != cur_scene:
        score -= 0.2
    if score < 0.0:
        score = 0.0
    return float(score)


def normalize_llm_scores(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def pick_shot_match_fields(shot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "shot_id": shot.get("shot_id"),
        "start": shot.get("start"),
        "end": shot.get("end"),
        "summary": shot.get("summary") or "",
    }


def get_item_embedding(item: Dict[str, Any]) -> Optional[List[float]]:
    emb = item.get("embedding")
    if isinstance(emb, list) and emb:
        try:
            return [float(x) for x in emb]
        except Exception:
            return None
    return None


def get_shot_embedding(shot: Dict[str, Any]) -> Optional[List[float]]:
    return get_item_embedding(shot)


def build_shot_embedding_text(shot: Dict[str, Any], *, prompt_language: str = "zh") -> str:
    """
    与 omni_multimodal_pipeline Step2 写入 embedding 时一致：优先 summary；
    否则由 visual + 字幕拼出与 _build_shot_embedding_summary 相同的文本。
    """
    summary = str(shot.get("summary") or "").strip()
    if summary:
        return summary
    visual = shot.get("visual") if isinstance(shot.get("visual"), dict) else {}
    subtitle_text = str(shot.get("subtitle_full_text") or "")
    language = str(prompt_language or "zh").strip().lower()
    desc = str(visual.get("desc", "") or "")
    brief = str(visual.get("brief", "") or "")
    if language == "en":
        return (f"Detail: {desc}\n" f"Brief: {brief}\n" f"Subtitles: {subtitle_text}").strip()
    return (f"详细：{desc}\n" f"摘要：{brief}\n" f"字幕：{subtitle_text}").strip()


def fine_rerank_json_schema() -> Dict[str, Any]:
    return {
        "name": "omni_fine_rerank",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "shot_id": {},
                            "score": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["shot_id", "score", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


def load_fine_prompt_template(prompt_language: str) -> str:
    lang = str(prompt_language or "zh").strip().lower()
    name = "fine_prompt_en.md" if lang == "en" else "fine_prompt_zh.md"
    base = Path(__file__).resolve().parents[1] / "reRank" / name
    return base.read_text(encoding="utf-8")


def build_embedding_search_results(
    *,
    copy_items: List[Dict[str, Any]],
    shots: List[Dict[str, Any]],
    top_k: int,
    embedding_model_hint: Optional[str],
    prompt_language: str,
) -> List[Dict[str, Any]]:
    if top_k <= 0:
        top_k = 20
    shot_embeddings: List[Tuple[int, Dict[str, Any], List[float]]] = []
    for idx, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        emb = get_shot_embedding(shot)
        if emb:
            shot_embeddings.append((idx, shot, emb))

    results: List[Dict[str, Any]] = []
    pl = str(prompt_language or "zh").strip().lower()
    for i, item in enumerate(copy_items):
        if not isinstance(item, dict):
            item = {"text": str(item)}
        q_emb = get_item_embedding(item)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        if q_emb and shot_embeddings:
            for _, shot, s_emb in shot_embeddings:
                score = cosine_similarity(q_emb, s_emb)
                if math.isnan(score):
                    continue
                scored.append((score, shot))

            scored.sort(key=lambda x: x[0], reverse=True)
            scored = scored[:top_k]

        matches = [
            {
                **pick_shot_match_fields(shot),
                "score": float(score),
            }
            for score, shot in scored
        ]

        result_item: Dict[str, Any] = {
            "item_index": i,
            "text": item.get("text", "") or "",
            "embedding_model": item.get("embedding_model") or embedding_model_hint,
            "matches": matches,
        }
        if pl == "en":
            result_item["translation"] = item.get("translation", "") or ""
        results.append(result_item)

    return results


def merge_fine_scores_and_continuity(
    *,
    search_results: List[Dict[str, Any]],
    partial_by_index: Dict[int, Dict[str, Any]],
    output_top_k: int,
    w_rerank: float,
    w_embed: float,
    w_cont: float,
) -> List[Dict[str, Any]]:
    total = len(search_results)
    out_results: List[Dict[str, Any]] = []
    prev_selected: Optional[Dict[str, Any]] = None
    for pos in range(total):
        base = search_results[pos] if isinstance(search_results[pos], dict) else {}
        r = partial_by_index.get(pos) or base
        if not isinstance(r, dict):
            continue
        if r.get("error"):
            out_results.append(dict(r))
            continue
        matches = r.get("matches") or []
        if not isinstance(matches, list) or not matches:
            out_results.append(dict(r))
            continue

        reranked_matches: List[Dict[str, Any]] = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            cont = continuity_score(
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
            top0 = reranked_matches[0]
            prev_selected = {
                "shot_id": top0.get("shot_id"),
                "start": top0.get("start"),
                "end": top0.get("end"),
                "summary": top0.get("summary"),
            }

        meta = r.get("rerank") if isinstance(r.get("rerank"), dict) else None
        row = {**dict(r), "matches": reranked_matches}
        if meta:
            row["rerank"] = meta
        out_results.append(row)

    return out_results


def _coerce_parsed_shot_id(token: str) -> Any:
    t = (token or "").strip().strip('"').strip("'")
    if not t:
        return t
    if t.isdigit():
        return int(t)
    return t


def _parse_fine_llm_lines(s: str) -> List[Dict[str, Any]]:
    """从模型纯文本中解析「shot_id|score」或「shot_id<TAB>score」行（score 在最后一列）。"""
    out: List[Dict[str, Any]] = []
    for line in (s or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "｜" in line:
            parts = line.rsplit("｜", 1)
        elif "|" in line:
            parts = line.rsplit("|", 1)
        elif "\t" in line:
            parts = line.rsplit("\t", 1)
        else:
            continue
        if len(parts) != 2:
            continue
        left, right = parts[0].strip(), parts[1].strip()
        if not left:
            continue
        try:
            score = float(right)
        except (TypeError, ValueError):
            continue
        out.append({"shot_id": _coerce_parsed_shot_id(left), "score": score})
    return out


def parse_fine_llm_payload(raw: str) -> List[Dict[str, Any]]:
    s = (raw or "").strip()
    if not s:
        return []
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        data = json.loads(s)
    except Exception:
        return _parse_fine_llm_lines(s)
    if isinstance(data, list):
        got = [x for x in data if isinstance(x, dict) and "shot_id" in x]
        return got if got else _parse_fine_llm_lines(s)
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            got = [x for x in items if isinstance(x, dict) and "shot_id" in x]
            return got if got else _parse_fine_llm_lines(s)
    return _parse_fine_llm_lines(s)
