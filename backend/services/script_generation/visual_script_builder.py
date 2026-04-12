import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ai import ChatMessage
from modules.json_sanitizer import sanitize_json_text_to_dict, validate_script_items
from services.ai_service import ai_service

from .constants import MAX_SUBTITLE_CHARS_PER_CALL
from .subtitle_utils import _format_timestamp_range, _parse_timestamp_pair
from modules.prompts.common.output_format_blocks import movie, short_drama

logger = logging.getLogger(__name__)

_VISUAL_SCRIPT_MD_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "cache"


def _markdown_fenced_block(info: str, body: str) -> str:
    fence_len = 3
    while True:
        fence = "`" * fence_len
        if fence not in body:
            return f"{fence}{info}\n{body}\n{fence}\n"
        fence_len += 1


def _write_visual_script_chat_cache_md(
    *,
    messages: List[ChatMessage],
    response_content: str,
    chunk_idx: int,
    chunk_total: int,
    drama_name: str,
    project_id: Optional[str],
    attempt: int,
) -> None:
    """将本次 visual script 的 send_chat 请求与响应写入 backend/docs/cache 下的 .md 文件。"""
    try:
        _VISUAL_SCRIPT_MD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_drama = "".join(c if c.isalnum() or c in "._- " else "_" for c in drama_name)[:80].strip() or "script"
        pid = (project_id or "noproject").replace("/", "_")[:48]
        fname = f"visual_script_{pid}_c{chunk_idx + 1}of{chunk_total}_a{attempt + 1}_{ts}.md"
        path = _VISUAL_SCRIPT_MD_CACHE_DIR / fname
        parts: List[str] = [
            "# Visual script generation (send_chat)",
            "",
            f"- **time (UTC)**: {datetime.now(timezone.utc).isoformat()}",
            f"- **chunk**: {chunk_idx + 1} / {chunk_total}",
            f"- **drama**: {drama_name}",
            f"- **project_id**: {project_id or ''}",
            f"- **attempt**: {attempt + 1}",
            "",
            "## Messages",
            "",
        ]
        for i, m in enumerate(messages):
            role = m.role or "unknown"
            raw = m.content
            content = raw if isinstance(raw, str) else (str(raw) if raw is not None else "")
            parts.append(f"### {role} ({i + 1})")
            parts.append("")
            parts.append(_markdown_fenced_block("text", content))
            parts.append("")
        parts.append("## Response")
        parts.append("")
        parts.append(_markdown_fenced_block("json", response_content))
        path.write_text("\n".join(parts), encoding="utf-8")
    except Exception as ex:
        logger.warning("写入 visual script MD 缓存失败: %s", ex)


def _normalize_original_ratio(value: Optional[int]) -> int:
    try:
        num = int(value)
    except Exception:
        return 70
    if num < 0:
        return 0
    if num > 100:
        return 100
    return num


def _build_ost_system_hint(original_ratio: Optional[int]) -> str:
    if original_ratio is None:
        return "原声片段标识：OST=1表示原声，OST=0表示解说。"
    ratio_val = _normalize_original_ratio(original_ratio)
    if ratio_val <= 0:
        return "本次只生成解说片段：所有条目的OST必须为0，且narration为解说文案；不得使用“播放原片+序号”格式。"
    if ratio_val >= 100:
        return "本次只生成原声片段：所有条目的OST必须为1，且narration必须使用“播放原片+序号”格式；不得输出解说文案。"
    return (
        f"原片占比范围：本次原片占比为{ratio_val}%，解说占比为{100 - ratio_val}%。"
        "原声片段标识：OST=1表示原声，OST=0表示解说。"
    )


def _detect_narration_type(project_id: Optional[str]) -> str:
    if not project_id:
        return "short_drama_narration"
    try:
        from modules.projects_store import projects_store

        p = projects_store.get_project(project_id)
        if p:
            t = str(getattr(p, "narration_type", "") or "")
            if t == "电影解说":
                return "movie_narration"
    except Exception:
        pass
    return "short_drama_narration"


def _build_fixed_visual_script_prompt(
    drama_name: str,
    scenes_text: str,
    script_language: Optional[str],
    original_ratio: Optional[int] = None,
) -> str:
    lang = "en" if script_language and str(script_language).strip().lower() in {"en", "en-us", "英文", "english"} else "zh"
    ratio_val = _normalize_original_ratio(original_ratio) if original_ratio is not None else None

    requirements_extra = ""
    ost_rules = ""
    if ratio_val is None:
        requirements_extra = "- 合理分配原声片段（OST=1）和解说片段（OST=0）\n"
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
            "- 在关键情绪爆发点、重要对白、爽点瞬间保留原声\n"
        )
    elif ratio_val <= 0:
        requirements_extra = "- 本次只生成解说片段（OST 必须为 0），不得输出原声片段\n"
        ost_rules = (
            "## 解说片段规则\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
        )
    elif ratio_val >= 100:
        requirements_extra = "- 本次只生成原声片段（OST 必须为 1），不得输出解说片段\n"
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
        )
    else:
        requirements_extra = (
            f"- 合理分配原声片段（OST=1）和解说片段（OST=0），原片占比约 {ratio_val}%\n"
        )
        ost_rules = (
            "## 原声片段规则\n"
            "- OST=1 表示保留原声，narration 使用\"播放原片+序号\"格式\n"
            "- OST=0 表示解说，narration 填写对应的解说文案内容\n"
            "- 在关键情绪爆发点、重要对白、爽点瞬间保留原声\n"
        )

    prompt = f"""# 解说脚本生成任务（视觉推理）

## 任务目标
从整部视频中挑选“值得解说的精彩片段”，结合镜头（scene）时间轴信息，把解说文案的关键内容对齐到对应时间段，生成带时间轴的解说脚本。
你不需要覆盖整部影片，允许大段跳过；目标是“只讲精彩、节奏紧凑”。
尽量保留“解说文案”完整拆分并全部对齐到镜头（scene）时间轴中对应的时间段，生成带时间轴的解说脚本；尽量不遗漏任何文案内容。允许必要压缩但不得改变原意。

## 输入说明
1. **解说文案**：一段完整的叙述文本，这是要使用的解说内容（必须完整使用并严格基于该文案拆分）
2. **镜头信息**：带有精确时间戳的镜头列表，每个镜头包含字幕（如果有）与画面理解（vision）

## 任务要求
- 不需要按时间顺序抽取镜头（时间戳可以大幅跳跃，不要求连续覆盖全片），但尽量覆盖完整“解说文案”内容；
- 只输出需要解说的精彩片段；允许时间戳不连续
- 对于没有字幕的镜头，必须基于画面理解（vision）来判断剧情/动作/情绪变化，从而确定解说拆分位置
- 对于有字幕的镜头，可以结合字幕与画面理解来对齐解说内容
{requirements_extra}- 时间戳格式必须为 HH:MM:SS,mmm-HH:MM:SS,mmm
{ost_rules}

## 镜头信息（含精确时间戳）
<scenes>
{scenes_text}
</scenes>

## 剧名
《{drama_name}》

## 输出语言
{lang}
"""
    return prompt


async def _generate_visual_script_chunk(
    chunk_idx: int,
    chunk_total: int,
    start_time: float,
    end_time: float,
    scenes: List[Dict[str, Any]],
    copywriting_text: str,
    drama_name: str,
    project_id: Optional[str] = None,
    target_items_count: Optional[int] = None,
    original_ratio: Optional[int] = None,
    script_language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    scenes_text_lines: List[str] = []
    for s in scenes:
        ts = _format_timestamp_range(float(s["start"]), float(s["end"]))
        scenes_text_lines.append(f"[{ts}] {s['text']}")
    scenes_text = "\n".join(scenes_text_lines)

    narration_type = _detect_narration_type(project_id)
    lang_key = "en" if script_language and str(script_language).strip().lower() in {"en", "en-us", "英文", "english"} else "zh"

    user_prompt = _build_fixed_visual_script_prompt(
        drama_name=drama_name,
        scenes_text=scenes_text,
        script_language=script_language,
        original_ratio=original_ratio,
    )

    system_prompt = (
        "你是一位专业的视频脚本时间轴编辑器。"
        "你必须严格按照JSON格式输出，绝不能包含任何其他文字、说明或代码块标记。\n\n"
    )
    ratio_for_blocks = _normalize_original_ratio(original_ratio) if original_ratio is not None else None
    if narration_type == "movie_narration":
        system_prompt += movie(lang_key, ratio_for_blocks)
    else:
        system_prompt += short_drama(lang_key, ratio_for_blocks)

    messages: List[ChatMessage] = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content=(
                "## 解说文案\n"
                "<copywriting>\n"
                f"{copywriting_text}\n"
                "</copywriting>"
            ),
        ),
        ChatMessage(role="user", content=user_prompt),
    ]

    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=(
                "以下为必须严格使用的解说文案文本：所有条目的'narration'必须仅基于该文案进行时间轴拆分；"
                "不得编造或新增任何未出现的内容；允许必要压缩但不得改变含义；如果一段文案太长，匹配不到好的镜头，可以修改文案"
            ),
        ),
    )
    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=(
                "你必须保证每条'narration'的配音时长与对应timestamp镜头时长匹配。"
                "按自然语速估算：中文约3-4字/秒（例如10个字约2.5-3.5秒），英文约2-3词/秒。"
                "若文本预计配音时长明显短于或长于镜头时长，必须增删或改写该条文本以匹配镜头长度。"
                "每条预计配音时长与镜头时长误差尽量控制在±0.5秒内。"
            ),
        ),
    )

    if int(chunk_total or 0) > 0:
        total = int(chunk_total)
        idx = int(chunk_idx)
        if idx <= 0:
            pos_label = "开始段"
        elif idx >= total - 1:
            pos_label = "末尾段"
        else:
            pos_label = "中间段"
        messages.insert(
            0,
            ChatMessage(
                role="system",
                content=(
                    f"这是分段生成脚本的第{idx + 1}段/共{total}段，位置为{pos_label}。"
                    "本段不得输出0条（items 不可为空），并将本时间段内的解说文案对齐到镜头时间轴。"
                    "避免重复的开场白/总结句等套话。"
                ),
            ),
        )

    if target_items_count and int(target_items_count) > 0:
        n = int(target_items_count)
        messages.insert(
            0,
            ChatMessage(
                role="system",
                content=(
                    f"你必须仅输出一个JSON对象，键为'items'。"
                    # f"items数组长度大约控制为{n}条"
                    "每条时间段长度不能低于1秒。"
                    "每条必须包含'_id','timestamp','narration','OST'。"
                    "不得输出除JSON以外的任何文字。"
                ),
            ),
        )

    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=_build_ost_system_hint(original_ratio),
        ),
    )

    if script_language:
        lang = str(script_language).strip().lower()
        if lang in {"en", "en-us", "英文", "english"}:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content="你必须将所有 'narration' 文本严格用英文撰写；不得输出中文或其他语言。",
                ),
            )
        elif lang in {"zh", "zh-cn", "中文", "chinese"}:
            messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content="你必须将所有 'narration' 文本严格用中文撰写；不得输出英文或其他语言。",
                ),
            )

    system_contents: List[str] = []
    non_system_messages: List[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            if message.content is not None:
                system_contents.append(str(message.content))
        else:
            non_system_messages.append(message)
    if system_contents:
        merged_system = "\n".join([c for c in system_contents if c])
        messages = [ChatMessage(role="system", content=merged_system), *non_system_messages]
    else:
        messages = non_system_messages

    logger.info(f"⚡ 正在生成分段 {int(chunk_idx) + 1}/{chunk_total} (visual)...")

    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            resp = await ai_service.send_chat(messages, response_format={"type": "json_object"})
            _write_visual_script_chat_cache_md(
                messages=messages,
                response_content=resp.content or "",
                chunk_idx=chunk_idx,
                chunk_total=chunk_total,
                drama_name=drama_name,
                project_id=project_id,
                attempt=attempt,
            )
            data, _ = sanitize_json_text_to_dict(resp.content)
            data = validate_script_items(data)
            items = data.get("items") or []
            logger.info(f"v{int(chunk_idx) + 1} 生成分段(visual), 共{len(items)}条")
            valid_items: List[Dict[str, Any]] = []
            for it in items:
                try:
                    s_t, e_t = _parse_timestamp_pair(str(it.get("timestamp")))
                    if e_t < start_time - 5 or s_t > end_time + 5:
                        continue
                    valid_items.append(
                        {
                            "_id": it.get("_id"),
                            "timestamp": str(it.get("timestamp")),
                            "narration": str(it.get("narration", "")),
                            "OST": 1 if it.get("OST") == 1 else 0,
                            "_chunk_idx": chunk_idx,
                        }
                    )
                except Exception:
                    continue
            if target_items_count and int(target_items_count) > 0:
                n = int(target_items_count)
                out: List[Dict[str, Any]] = []
                for it in valid_items:
                    if len(out) >= n:
                        break
                    out.append(it)
                return out
            return valid_items
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Chunk {chunk_idx} generation failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying..."
                )
                continue
            logger.error(f"Chunk {chunk_idx} generation failed after {max_retries} retries: {e}")
            raise e
    return []
