import json
import math
import os
import time
from typing import Any, Dict, List, Tuple


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


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return float("nan")
    if len(a) != len(b):
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


def _get_embedding(obj: Any) -> List[float]:
    emb = None
    if isinstance(obj, dict):
        emb = obj.get("embedding")
    if not isinstance(emb, list):
        return []
    out: List[float] = []
    for x in emb:
        try:
            out.append(float(x))
        except Exception:
            return []
    return out


def _pick_shot_fields(shot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "shot_id": shot.get("shot_id"),
        "start": shot.get("start"),
        "end": shot.get("end"),
        "duration": shot.get("duration"),
        "frame": shot.get("frame"),
        "subtitle_full_text": shot.get("subtitle_full_text", "") or "",
        "summary": shot.get("summary", "") or "",
    }


def run_search_shots(config_path: str = None) -> str:
    """
    用解说文案 embedding 去匹配镜头 embedding，按每条文案取 TopK 镜头并打分输出为 JSON。

    依赖 config.json:
      - search_shots:
          copywriting_embeddings_json: output/copywriting_format_embeddings.json
          shots_multimodal_json: output/video_1_shots_multimodal.json
          output_json: output/copywriting_to_shots_top{top_k}.json  # 可省略；会随 top_k 自动生成
          top_k: 20
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    if config_path is None:
        config_path = os.path.join(project_root, "config.json")

    cfg = _read_json(config_path) if os.path.exists(config_path) else {}
    s_cfg = cfg.get("search_shots") or {}
    struct_cfg = cfg.get("copywriting_structuring") or {}
    prompt_language = str(struct_cfg.get("prompt_language") or "").lower()

    copy_json = s_cfg.get("copywriting_embeddings_json") or "output/copywriting_format_embeddings.json"
    shots_json = s_cfg.get("shots_multimodal_json") or "output/video_1_shots_multimodal.json"
    top_k = int(s_cfg.get("top_k", 20) or 20)
    if top_k <= 0:
        top_k = 20

    output_json_cfg = s_cfg.get("output_json")
    if output_json_cfg:
        output_json = output_json_cfg
    else:
        output_json = f"output/copywriting_to_shots_top{top_k}.json"

    copy_abs = _abs_path(project_root, copy_json)
    shots_abs = _abs_path(project_root, shots_json)
    out_abs = _abs_path(project_root, output_json)

    copy_payload = _read_json(copy_abs)
    items = (copy_payload.get("items") if isinstance(copy_payload, dict) else None) or []
    if not isinstance(items, list):
        raise ValueError(f"copywriting_format_embeddings.json 的 items 必须是数组(list)，实际是: {type(items)}")

    shots_payload = _read_json(shots_abs)
    shots = (shots_payload.get("shots") if isinstance(shots_payload, dict) else None) or []
    if not isinstance(shots, list):
        raise ValueError(f"video_1_shots_multimodal.json 的 shots 必须是数组(list)，实际是: {type(shots)}")

    shot_embeddings: List[Tuple[int, Dict[str, Any], List[float]]] = []
    for idx, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        emb = _get_embedding(shot)
        if emb:
            shot_embeddings.append((idx, shot, emb))

    results: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            item = {"text": str(item)}
        q_emb = _get_embedding(item)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        if q_emb and shot_embeddings:
            for _, shot, s_emb in shot_embeddings:
                score = _cosine_similarity(q_emb, s_emb)
                if math.isnan(score):
                    continue
                scored.append((score, shot))

            scored.sort(key=lambda x: x[0], reverse=True)
            scored = scored[:top_k]

        matches = [
            {
                **_pick_shot_fields(shot),
                "score": float(score),
            }
            for score, shot in scored
        ]

        result_item = {
            "item_index": i,
            "text": item.get("text", "") or "",
            "embedding_model": item.get("embedding_model") or copy_payload.get("meta", {}).get("embedding_model"),
            "matches": matches,
        }
        if prompt_language == "en":
            result_item["translation"] = item.get("translation", "") or ""

        results.append(result_item)

    payload = {
        "meta": {
            "copywriting_embeddings_json": copy_json,
            "shots_multimodal_json": shots_json,
            "output_json": output_json,
            "top_k": top_k,
            "score_method": "cosine_similarity",
            "count_copywriting_items": len(items),
            "count_shots_total": len(shots),
            "count_shots_with_embedding": len(shot_embeddings),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        },
        "results": results,
    }

    _write_json(out_abs, payload)
    return out_abs


if __name__ == "__main__":
    out = run_search_shots()
    print(out)

