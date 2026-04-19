from typing import Any, Dict

from .custom_openai_client import CustomOpenAIClient
from .openai_compatible_base import OpenAICompatibleClientBase
from .yunwu_client import YunwuClient


def build_model_client(cfg: Dict[str, Any]) -> OpenAICompatibleClientBase:
    provider = str((cfg.get("model_provider") or "yunwu")).strip().lower()

    if provider == "yunwu":
        provider_cfg = cfg.get("yunwu") or {}
        return YunwuClient(
            api_key=provider_cfg.get("api_key", ""),
            chat_completions_url=provider_cfg.get("chat_completions_url", "https://yunwu.ai/v1/chat/completions"),
            embeddings_url=provider_cfg.get("embeddings_url", "https://yunwu.ai/v1/embeddings"),
            rerank_url=provider_cfg.get("rerank_url", "https://yunwu.ai/v1/rerank"),
            timeout_seconds=int(provider_cfg.get("timeout_seconds", 120) or 120),
        )

    if provider in {"custom", "custom_openai", "openai_compatible"}:
        provider_cfg = cfg.get("custom_openai") or {}
        return CustomOpenAIClient(
            api_key=provider_cfg.get("api_key", ""),
            base_url=provider_cfg.get("base_url", ""),
            chat_completions_url=provider_cfg.get("chat_completions_url", ""),
            embeddings_url=provider_cfg.get("embeddings_url", ""),
            rerank_url=provider_cfg.get("rerank_url", ""),
            timeout_seconds=int(provider_cfg.get("timeout_seconds", 120) or 120),
        )

    raise ValueError(f"不支持的 model_provider: {provider}，可选值：yunwu / custom_openai")
