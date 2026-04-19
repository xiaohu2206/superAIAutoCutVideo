import json
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from utils.aiModels import build_model_client


logger = logging.getLogger("AIShotSearch.copywritingEmbeddings")


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def buildNarrationEmbeddingInput(n: Dict[str, Any], prompt_language: str = "zh") -> str:
    visual_keywords = n.get("visual_keywords") or []
    if not isinstance(visual_keywords, list):
        visual_keywords = [str(visual_keywords)]

    language = str(prompt_language or "zh").strip().lower()
    if language == "en":
        translation = str(n.get("translation") or "").strip()
        return "\n".join([
            f"event: {n.get('event', '')}",
            f"subject: {n.get('subject', '')}",
            f"emotion: {n.get('emotion', '')}",
            f"scene_type: {n.get('scene_type', '')}",
            f"action: {n.get('action', '')}",
            f"visual_keywords: {', '.join([str(x) for x in visual_keywords])}",
            f"translation: {translation}",
        ])

    return "\n".join([
        f"事件:{n.get('event', '')}",
        f"主体:{n.get('subject', '')}",
        f"情绪:{n.get('emotion', '')}",
        f"场景:{n.get('scene_type', '')}",
        f"动作:{n.get('action', '')}",
        f"关键词:{','.join([str(x) for x in visual_keywords])}",
        f"描述:{n.get('text', '')}",
    ])


def _abs_path(project_root: str, p: str) -> str:
    if not p:
        return project_root
    return p if os.path.isabs(p) else os.path.join(project_root, p)


def run_copywriting_embeddings(config_path: str = None) -> str:
    """
    将结构化解说文案（copywriting_format.json）向量化，输出包含 embedding 的 JSON 文件。
    依赖 config.json:
      - yunwu: api_key/chat_completions_url/embeddings_url/embedding_model/timeout_seconds
      - copywriting_embeddings: input_json/output_json/concurrency/max_retries/retry_sleep_seconds/continue_on_error/save_every_n
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    if config_path is None:
        config_path = os.path.join(project_root, "config.json")

    cfg = _read_json(config_path)

    emb_cfg = cfg.get("copywriting_embeddings") or {}
    struct_cfg = cfg.get("copywriting_structuring") or {}
    prompt_language = str(struct_cfg.get("prompt_language") or "zh").strip().lower()

    input_json = emb_cfg.get("input_json") or "output/copywriting_format.json"
    output_json = emb_cfg.get("output_json") or "output/copywriting_format_embeddings.json"

    input_abs = _abs_path(project_root, input_json)
    output_abs = _abs_path(project_root, output_json)

    items = _read_json(input_abs)
    if not isinstance(items, list):
        raise ValueError(f"copywriting_format.json 必须是数组(list)，实际是: {type(items)}")

    client = build_model_client(cfg)
    provider = str((cfg.get("model_provider") or "yunwu")).strip().lower()
    provider_cfg = (
        cfg.get("custom_openai")
        if provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}
    embedding_provider = str(provider_cfg.get("embedding_provider") or provider).strip().lower()
    embedding_cfg = (
        cfg.get("custom_openai")
        if embedding_provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}
    llm_model = provider_cfg.get("llm_model") or provider_cfg.get("vl_model") or ""
    embedding_model = embedding_cfg.get("embedding_model") or "text-embedding-3-large"

    concurrency = int(emb_cfg.get("concurrency", 8) or 1)
    max_retries = int(emb_cfg.get("max_retries", 2) or 0)
    retry_sleep_seconds = float(emb_cfg.get("retry_sleep_seconds", 2) or 0)
    continue_on_error = bool(emb_cfg.get("continue_on_error", True))
    save_every_n = int(emb_cfg.get("save_every_n", 10) or 0)

    enriched: List[Dict[str, Any]] = [None] * len(items)  # type: ignore[list-item]
    lock = threading.Lock()
    completed = 0

    def _process_one(i: int, n: Dict[str, Any]) -> Tuple[int, bool, Dict[str, Any], float, str]:
        t0 = time.time()
        try:
            embedding_input = buildNarrationEmbeddingInput(n, prompt_language=prompt_language)
            embedding = client.embed_text(
                model=embedding_model,
                text=embedding_input,
                max_retries=max_retries,
                retry_sleep_seconds=retry_sleep_seconds,
                provider_override=(embedding_provider, embedding_cfg),
            )
            out = dict(n)
            out["embedding_input"] = embedding_input
            out["embedding_model"] = embedding_model
            out["embedding"] = embedding
            return i, True, out, time.time() - t0, ""
        except Exception as e:
            out = dict(n)
            out["error"] = str(e)
            return i, False, out, time.time() - t0, str(e)

    def _save_partial() -> None:
        payload = {
            "meta": {
                "input_json": input_json,
                "embedding_model": embedding_model,
                "llm_model": llm_model,
                "count_total": len(items),
                "count_done": len([x for x in enriched if x is not None]),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            },
            "items": [x for x in enriched if x is not None],
        }
        _write_json(output_abs, payload)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futures = {
            ex.submit(_process_one, i, (n if isinstance(n, dict) else {"text": str(n)})): i
            for i, n in enumerate(items)
        }
        for fut in as_completed(futures):
            i, ok, out, elapsed, err = fut.result()
            with lock:
                enriched[i] = out
                completed += 1
                if ok:
                    logger.info(f"[copywriting] ok index={i} elapsed={elapsed:.2f}s ({completed}/{len(items)})")
                else:
                    logger.error(f"[copywriting] fail index={i} elapsed={elapsed:.2f}s err={err} ({completed}/{len(items)})")
                    if not continue_on_error:
                        raise RuntimeError(err)
                if save_every_n > 0 and (completed % save_every_n == 0):
                    _save_partial()

    _save_partial()
    return output_abs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = run_copywriting_embeddings()
    print(out)

