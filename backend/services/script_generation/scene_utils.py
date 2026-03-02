from typing import Any, Dict, List, Optional


def _clean_text(s: Any) -> str:
    t = str(s or "").strip()
    return " ".join(t.split())


def _normalize_subtitle(sub: Any) -> str:
    t = _clean_text(sub)
    if not t or t in {"无", "N/A", "NA", "none", "None"}:
        return ""
    return t


def _collect_vision_text(vision: Any) -> str:
    if isinstance(vision, str):
        return _clean_text(vision)
    if not isinstance(vision, list):
        return ""
    texts: List[str] = []
    for v in vision:
        if not isinstance(v, dict):
            continue
        if str(v.get("status") or "").strip().lower() not in {"ok", "success"}:
            continue
        txt = _clean_text(v.get("text"))
        if txt:
            texts.append(txt)
    return "；".join(texts)


def _build_scene_text(scene: Dict[str, Any], max_chars: int = 900) -> str:
    scene_id = scene.get("id") or scene.get("index") or scene.get("_id") or ""
    time_range = _clean_text(scene.get("time_range"))
    head = f"镜头{scene_id}" if scene_id != "" else "镜头"
    if time_range:
        head = f"{head} {time_range}"

    subtitle = _normalize_subtitle(scene.get("subtitle"))
    vision_text = _collect_vision_text(scene.get("vision"))

    parts: List[str] = [head]
    if subtitle:
        parts.append(f"字幕：{subtitle}")
    if vision_text:
        parts.append(f"画面：{vision_text}")
    if not subtitle and not vision_text:
        parts.append("画面：无有效信息")

    out = "\n".join([p for p in parts if p])
    if len(out) > int(max_chars):
        out = out[: int(max_chars)]
    return out


def scenes_to_timeline_items(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    idx = 1
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        try:
            start_s = float(scene.get("start_time") or 0.0)
            end_s = float(scene.get("end_time") or start_s)
        except Exception:
            continue
        if end_s < start_s:
            start_s, end_s = end_s, start_s
        if end_s <= 0 and start_s <= 0:
            continue
        text = _build_scene_text(scene)
        if not text:
            continue
        items.append(
            {
                "index": idx,
                "start": start_s,
                "end": end_s,
                "text": text,
            }
        )
        idx += 1
    items.sort(key=lambda s: (float(s.get("start") or 0.0), float(s.get("end") or 0.0)))
    return items

