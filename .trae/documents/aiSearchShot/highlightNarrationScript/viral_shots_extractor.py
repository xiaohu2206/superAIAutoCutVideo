"""
在解说脚本生成前，按与 runner 相同的分组与时间窗，对本批镜头调用大模型预提取「爆款/爆点」镜头，
将结果格式化为可拼入 user prompt 的文本块。
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set

VIRAL_SHOTS_JSON_SCHEMA: Dict[str, Any] = {
    "name": "viral_shots_preextract",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "shot_id": {"type": "integer"},
                        "timestamp": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["shot_id", "timestamp", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}

DEFAULT_VIRAL_SYSTEM_PROMPT = (
    "你是专业短视频剪辑与影视叙事分析师，擅长从镜头描述中识别情绪高潮、剧情反转、名场面、"
    "强冲突、高光动作、关键对白或声音驱动的戏剧性瞬间（爆点/爆款镜头）。"
    "你必须只输出符合给定 JSON Schema 的 JSON，不得输出任何其他文字、说明或 Markdown。"
)

VIRAL_USER_PROMPT_TEMPLATE = """# 任务
从下方「本批镜头列表」中，仅依据已给出的 shot_id、时间戳与画面/字幕信息，识别本时间窗口内最值得作为**爆款/爆点**保留的镜头（适合优先原声 OST 或作为叙事高潮锚点）。

## 分批上下文
- 第 {batch_cur} / {batch_total} 批
- 本批解说文案条目序号：第 {line_start}～{line_end} 条（供你理解叙事阶段，**不得编造**与镜头无关的剧情）
- 本批影片时间窗口：{win_start_fmt} - {win_end_fmt}（约 {win_start_sec:.1f}s～{win_end_sec:.1f}s）

## 本批解说文案条目摘要（仅作节奏参考）
{copywriting_outline}

## 本批镜头列表（须且只能从中挑选 shot_id）
<timeline_scenes>
{timeline_text}
</timeline_scenes>

## 输出要求
1. 仅输出一个 JSON 对象，键为 `items`。**items 可为空数组**（若本批确实无明显爆点）。
2. 每条须含 `shot_id`（整数，**必须出现在上方列表中**）、`timestamp`（与该 shot 一致，格式 HH:MM:SS,mmm-HH:MM:SS,mmm）、`reason`（中文，简短说明为何是爆点）。
3. 按时间顺序排列；**同一 shot_id 不得重复**。
4. 条数上限 {max_items} 条，优先保留冲击力最强的镜头。
5. 不得编造列表中不存在的 shot_id 或时间戳。
"""


_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}$")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_ts(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000.0))
    h = total_ms // 3600000
    m = (total_ms % 3600000) // 60000
    s = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _shot_id_int(shot: Dict[str, Any]) -> Optional[int]:
    sid = shot.get("shot_id")
    if sid is None:
        return None
    try:
        return int(sid)
    except (TypeError, ValueError):
        return None


def _build_shot_id_index(timeline_shots: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for s in timeline_shots:
        i = _shot_id_int(s)
        if i is not None:
            out[i] = s
    return out


def _normalize_timestamp_for_shot(
    shot: Dict[str, Any], timestamp: str
) -> str:
    if _TS_RE.match((timestamp or "").strip()):
        return (timestamp or "").strip()
    s = _format_ts(_safe_float(shot.get("start")))
    e = _format_ts(_safe_float(shot.get("end")))
    return f"{s}-{e}"


def _post_filter_and_sort_items(
    raw_items: Any,
    shot_by_id: Dict[int, Dict[str, Any]],
    max_items: int,
) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        try:
            sid = int(it.get("shot_id"))
        except (TypeError, ValueError):
            continue
        if sid in seen or sid not in shot_by_id:
            continue
        shot = shot_by_id[sid]
        reason = (it.get("reason") or "").strip()
        if not reason:
            reason = "（模型未给出理由）"
        ts = _normalize_timestamp_for_shot(shot, str(it.get("timestamp", "")))
        cleaned.append({"shot_id": sid, "timestamp": ts, "reason": reason})
        seen.add(sid)
    cleaned.sort(key=lambda x: _safe_float(shot_by_id[x["shot_id"]].get("start")))
    return cleaned[:max(0, max_items)]


def _format_prompt_section_body(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "本批未识别到明确爆款镜头（或列表过短）。请仍从下方全片镜头列表中自行识别爆点并编排解说。"
    lines: List[str] = []
    for i, it in enumerate(items, start=1):
        lines.append(
            f"{i}. shot_id={it['shot_id']} | {it['timestamp']} | {it['reason']}"
        )
    return "\n".join(lines)


def extract_viral_shots_prompt_section(
    client: Any,
    *,
    model: str,
    system_prompt: str,
    timeline_text: str,
    timeline_shots: List[Dict[str, Any]],
    copywriting_outline: str,
    batch_cur: int,
    batch_total: int,
    line_start: int,
    line_end: int,
    win_start_fmt: str,
    win_end_fmt: str,
    win_start_sec: float,
    win_end_sec: float,
    temperature: float,
    max_retries: int,
    retry_sleep_seconds: float,
    max_items: int = 15,
) -> str:
    """
    调用大模型提取本批爆款镜头，返回可嵌入解说脚本 user prompt 的纯文本正文（不含外层 XML 标签）。
    """
    if not (timeline_text or "").strip():
        return "本批无镜头文本输入，跳过爆款预提取；请仅从后续镜头列表中识别爆点。"

    shot_by_id = _build_shot_id_index(timeline_shots)
    if not shot_by_id:
        return "本批无有效 shot_id，跳过爆款预提取。"

    max_items = max(1, min(int(max_items or 15), 50))
    user_prompt = VIRAL_USER_PROMPT_TEMPLATE.format(
        batch_cur=batch_cur,
        batch_total=batch_total,
        line_start=line_start,
        line_end=line_end,
        win_start_fmt=win_start_fmt,
        win_end_fmt=win_end_fmt,
        win_start_sec=win_start_sec,
        win_end_sec=win_end_sec,
        copywriting_outline=(copywriting_outline or "").strip() or "（无）",
        timeline_text=timeline_text,
        max_items=max_items,
    )

    t0 = time.perf_counter()
    print(
        "[爆款镜头预提取] 调用开始 | 批次 {}/{} | model={} | shots={} | user_chars={}".format(
            batch_cur,
            batch_total,
            model,
            len(timeline_shots),
            len(user_prompt),
        ),
        flush=True,
    )

    result = client.chat_json(
        model=model,
        user_prompt=user_prompt,
        json_schema=VIRAL_SHOTS_JSON_SCHEMA,
        system_prompt=system_prompt,
        temperature=temperature,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    elapsed = time.perf_counter() - t0

    raw_items = result.get("items") if isinstance(result, dict) else None
    items = _post_filter_and_sort_items(raw_items, shot_by_id, max_items)

    print(
        "[爆款镜头预提取] 调用结束 | 批次 {}/{} | 保留条数={}/{} | 耗时 {:.2f}s".format(
            batch_cur,
            batch_total,
            len(items),
            len(raw_items) if isinstance(raw_items, list) else 0,
            elapsed,
        ),
        flush=True,
    )

    return _format_prompt_section_body(items)
