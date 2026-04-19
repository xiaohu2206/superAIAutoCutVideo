import json
import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from utils.aiModels import build_model_client


logger = logging.getLogger("AIShotSearch.copywritingStructuring")


def _output_schema_copywriting_segments(*, include_translation: bool) -> Dict[str, Any]:
    """结构化输出 schema；仅 prompt_language=en 时需要 translation。"""
    properties: Dict[str, Any] = {
        "text": {"type": "string"},
    }
    if include_translation:
        properties["translation"] = {"type": "string"}
    properties.update(
        {
            "event": {"type": "string"},
            "subject": {"type": "string"},
            "emotion": {"type": "string"},
            "scene_type": {"type": "string"},
            "visual_keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
            "action": {"type": "string"},
            "camera_hint": {"type": "string"},
        }
    )
    required = [
        "text",
        "event",
        "subject",
        "emotion",
        "scene_type",
        "visual_keywords",
        "action",
        "camera_hint",
    ]
    if include_translation:
        required.insert(1, "translation")
    return {
        "name": "copywriting_segments",
        "strict": True,
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


SPLIT_PUNCTUATION_PRIORITIES: List[List[str]] = [
    ["\n", "\r"],
    ["。", "！", "？", "!", "?", ".", ";", "；"],
    ["，", ",", "、", ":", "："],
]


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _abs_path(project_root: str, p: str) -> str:
    if not p:
        return project_root
    return p if os.path.isabs(p) else os.path.join(project_root, p)


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _compute_dynamic_chunk_target(total_len: int, base_chunk_chars: int) -> int:
    if total_len <= 0:
        return max(1, base_chunk_chars)
    base = max(1, int(base_chunk_chars or 500))
    chunk_count = max(1, -(-total_len // base))
    return max(1, total_len // chunk_count)


def split_copywriting_text(
    text: str,
    *,
    target_chunk_chars: int = 500,
    lookback_chars: int = 100,
) -> List[str]:
    normalized = _normalize_newlines(text).strip()
    if not normalized:
        return []

    chunks: List[str] = []
    start = 0
    total_len = len(normalized)
    dynamic_target_chunk_chars = _compute_dynamic_chunk_target(total_len, target_chunk_chars)

    while start < total_len:
        remaining = normalized[start:]
        if len(remaining) <= dynamic_target_chunk_chars:
            final_chunk = remaining.strip()
            if final_chunk:
                chunks.append(final_chunk)
            break

        tentative_end = min(total_len, start + max(1, dynamic_target_chunk_chars))
        search_start = max(start, tentative_end - max(0, lookback_chars))
        split_at = -1

        for punctuation_group in SPLIT_PUNCTUATION_PRIORITIES:
            for idx in range(tentative_end - 1, search_start - 1, -1):
                if normalized[idx] in punctuation_group:
                    split_at = idx + 1
                    break
            if split_at != -1:
                break

        if split_at == -1 or split_at <= start:
            split_at = tentative_end

        chunk = normalized[start:split_at].strip()
        if chunk:
            chunks.append(chunk)

        next_start = split_at
        while next_start < total_len and normalized[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks


def _normalize_segment(item: Dict[str, Any]) -> Dict[str, Any]:
    visual_keywords = item.get("visual_keywords")
    if isinstance(visual_keywords, list):
        normalized_keywords = [str(x).strip() for x in visual_keywords if str(x).strip()]
    elif visual_keywords is None:
        normalized_keywords = []
    else:
        normalized_keywords = [str(visual_keywords).strip()] if str(visual_keywords).strip() else []

    return {
        "text": str(item.get("text") or "").strip(),
        "translation": str(item.get("translation") or "").strip(),
        "event": str(item.get("event") or "").strip(),
        "subject": str(item.get("subject") or "").strip(),
        "emotion": str(item.get("emotion") or "").strip(),
        "scene_type": str(item.get("scene_type") or "").strip(),
        "visual_keywords": normalized_keywords,
        "action": str(item.get("action") or "").strip(),
        "camera_hint": str(item.get("camera_hint") or "").strip(),
    }


def _validate_segment(
    item: Dict[str, Any],
    chunk_index: int,
    item_index: int,
    *,
    require_translation: bool,
) -> None:
    fields = ["text", "event", "subject", "emotion", "scene_type", "action", "camera_hint"]
    if require_translation:
        fields.insert(1, "translation")
    for field in fields:
        if not item.get(field):
            raise ValueError(f"chunk={chunk_index} item={item_index} 缺少字段或为空: {field}")
    if not isinstance(item.get("visual_keywords"), list):
        raise ValueError(f"chunk={chunk_index} item={item_index} visual_keywords 必须是数组")
    if not item.get("text"):
        raise ValueError(f"chunk={chunk_index} item={item_index} text 不能为空")


def _load_prompt_template(project_root: str, prompt_language: str, prompt_path: str = "") -> str:
    if prompt_path:
        return _read_text(_abs_path(project_root, prompt_path))

    language = str(prompt_language or "zh").strip().lower()
    if language == "en":
        return _read_text(os.path.join(project_root, "copywritingStructuring", "prompt_en.md"))
    return _read_text(os.path.join(project_root, "copywritingStructuring", "prompt_zh.md"))


def _get_llm_model_name(cfg: Dict[str, Any]) -> str:
    provider = str((cfg.get("model_provider") or "yunwu")).strip().lower()
    provider_cfg = cfg.get("custom_openai") if provider in {"custom", "custom_openai", "openai_compatible"} else cfg.get("yunwu")
    provider_cfg = provider_cfg or {}
    return str(provider_cfg.get("llm_model") or provider_cfg.get("vl_model") or "").strip()


def _process_chunk(
    cfg: Dict[str, Any],
    llm_model: str,
    prompt_template: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
    temperature: float,
    max_retries: int,
    retry_sleep_seconds: float,
    prompt_language: str,
) -> List[Dict[str, Any]]:
    logger.info("[copywriting_structuring] chunk %s/%s start", chunk_index, total_chunks)
    t0 = time.time()
    prompt = prompt_template.replace("{copywriting}", chunk_text)
    client = build_model_client(cfg)
    lang = str(prompt_language or "zh").strip().lower()
    # 与 _load_prompt_template 一致：仅英文提示词要求 translation 字段
    require_translation = lang == "en"
    response = client.chat_json(
        model=llm_model,
        user_prompt=prompt,
        json_schema=_output_schema_copywriting_segments(include_translation=require_translation),
        temperature=temperature,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )

    if not isinstance(response, list):
        raise ValueError(f"chunk={chunk_index} 模型输出不是数组: {type(response)}")

    normalized_chunk_items: List[Dict[str, Any]] = []
    for item_index, raw_item in enumerate(response, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"chunk={chunk_index} item={item_index} 不是对象")
        normalized_item = _normalize_segment(raw_item)
        _validate_segment(
            normalized_item,
            chunk_index,
            item_index,
            require_translation=require_translation,
        )
        normalized_chunk_items.append(normalized_item)

    logger.info(
        "[copywriting_structuring] chunk %s/%s done items=%s elapsed=%.2fs",
        chunk_index,
        total_chunks,
        len(normalized_chunk_items),
        time.time() - t0,
    )
    return normalized_chunk_items


def run_copywriting_structuring(config_path: str = None) -> str:
    project_root = os.path.dirname(os.path.dirname(__file__))
    if config_path is None:
        config_path = os.path.join(project_root, "config.json")

    cfg = _read_json(config_path)
    struct_cfg = cfg.get("copywriting_structuring") or {}

    input_text_path = struct_cfg.get("input_text") or "inputFile/copywriting.txt"
    output_json_path = struct_cfg.get("output_json") or "inputFile/copywriting_format.json"
    prompt_language = struct_cfg.get("prompt_language") or "zh"
    prompt_path = struct_cfg.get("prompt_path") or ""
    chunk_target_chars = int(struct_cfg.get("chunk_target_chars", 500) or 500)
    chunk_lookback_chars = int(struct_cfg.get("chunk_lookback_chars", 100) or 100)
    temperature = float(struct_cfg.get("temperature", 0.2) or 0.2)
    max_retries = int(struct_cfg.get("max_retries", 2) or 0)
    retry_sleep_seconds = float(struct_cfg.get("retry_sleep_seconds", 2) or 0)
    request_sleep_seconds = float(struct_cfg.get("request_sleep_seconds", 1) or 0)

    llm_model = struct_cfg.get("model") or _get_llm_model_name(cfg)
    if not llm_model:
        raise ValueError("未找到可用的结构化模型，请在 copywriting_structuring.model 或 provider 配置中设置 llm_model / vl_model")

    input_abs = _abs_path(project_root, input_text_path)
    output_abs = _abs_path(project_root, output_json_path)

    copywriting_text = _read_text(input_abs).strip()
    if not copywriting_text:
        raise ValueError(f"解说文案为空: {input_abs}")

    prompt_template = _load_prompt_template(project_root, prompt_language, prompt_path)
    chunks = split_copywriting_text(
        copywriting_text,
        target_chunk_chars=max(1, chunk_target_chars),
        lookback_chars=max(0, chunk_lookback_chars),
    )
    if not chunks:
        raise ValueError("解说文案拆分后为空")

    merged_items: List[Dict[str, Any]] = []
    chunk_results: Dict[int, List[Dict[str, Any]]] = {}
    submitted_tasks: List[Tuple[int, Future[List[Dict[str, Any]]]]] = []

    with ThreadPoolExecutor(max_workers=max(1, len(chunks))) as executor:
        for chunk_index, chunk_text in enumerate(chunks, start=1):
            future = executor.submit(
                _process_chunk,
                cfg,
                llm_model,
                prompt_template,
                chunk_text,
                chunk_index,
                len(chunks),
                temperature,
                max_retries,
                retry_sleep_seconds,
                prompt_language,
            )
            submitted_tasks.append((chunk_index, future))
            if request_sleep_seconds > 0:
                time.sleep(request_sleep_seconds)

        for chunk_index, future in submitted_tasks:
            chunk_results[chunk_index] = future.result()

    for chunk_index in range(1, len(chunks) + 1):
        merged_items.extend(chunk_results[chunk_index])

    _write_json(output_abs, merged_items)
    logger.info("[copywriting_structuring] done chunks=%s items=%s output=%s", len(chunks), len(merged_items), output_abs)
    return output_abs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(run_copywriting_structuring())
