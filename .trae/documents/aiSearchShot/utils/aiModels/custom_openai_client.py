import http.client
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .openai_compatible_base import OpenAICompatibleClientBase


class CustomOpenAIClient(OpenAICompatibleClientBase):
    """
    自定义 OpenAI 兼容接口调用封装：
    - 支持配置 api_key、模型名称、base_url
    - 默认将 base_url 自动补全为 OpenAI 兼容路径
    - rerank 非必需，若未配置则不支持重排
    - chat 接口强制走流式聚合，适配仅支持 stream 输出的服务
    """

    provider_name = "CustomOpenAI"
    config_section_name = "custom_openai"
    default_chat_completions_url = "https://api.openai.com/v1/chat/completions"
    default_embeddings_url = "https://api.openai.com/v1/embeddings"
    default_rerank_url = ""
    default_user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        chat_completions_url: str = "",
        embeddings_url: str = "",
        rerank_url: str = "",
        timeout_seconds: int = 120,
    ):
        normalized_base_url = (base_url or "").strip().strip("`").rstrip("/")

        if normalized_base_url:
            chat_completions_url = chat_completions_url or f"{normalized_base_url}/chat/completions"
            embeddings_url = embeddings_url or f"{normalized_base_url}/embeddings"
            if not rerank_url and normalized_base_url.endswith("/v1"):
                rerank_url = f"{normalized_base_url}/rerank"

        super().__init__(
            api_key=api_key,
            chat_completions_url=chat_completions_url,
            embeddings_url=embeddings_url,
            rerank_url=rerank_url,
            timeout_seconds=timeout_seconds,
        )

    def _build_headers(self) -> Dict[str, str]:
        headers = super()._build_headers()
        headers.update(
            {
                "User-Agent": self.default_user_agent,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Origin": self._infer_origin(),
                "Referer": f"{self._infer_origin()}/",
            }
        )
        return headers

    def _infer_origin(self) -> str:
        for url in [self.chat_completions_url, self.embeddings_url, self.rerank_url]:
            value = (url or "").strip()
            if value.startswith("http://") or value.startswith("https://"):
                parts = value.split("/", 3)
                if len(parts) >= 3:
                    return f"{parts[0]}//{parts[2]}"
        return "https://api.openai.com"

    def _post_json(self, url: str, payload: Dict[str, Any], headers_override: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if url == self.chat_completions_url:
            return self._post_json_streaming(url, payload, headers_override=headers_override)
        return super()._post_json(url, payload, headers_override=headers_override)

    def _post_json_streaming(self, url: str, payload: Dict[str, Any], headers_override: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if not url:
            raise ValueError(f"{self.provider_name} 请求 URL 不能为空")

        stream_payload = dict(payload)
        stream_payload["stream"] = True
        data = json.dumps(stream_payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            method="POST",
            headers=headers_override or self._build_headers(),
        )

        aggregated_content: List[str] = []
        final_chunk: Optional[Dict[str, Any]] = None
        response_model: Optional[str] = None
        finish_reason: Optional[str] = None
        usage: Dict[str, Any] = {}

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_line = line[5:].strip()
                    if not data_line:
                        continue
                    if data_line == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_line)
                    except Exception:
                        continue
                    if not isinstance(chunk_data, dict):
                        continue

                    final_chunk = chunk_data
                    response_model = chunk_data.get("model") or response_model
                    if isinstance(chunk_data.get("usage"), dict):
                        usage = chunk_data.get("usage") or usage

                    choices = chunk_data.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        finish_reason = choices[0].get("finish_reason") or finish_reason

                    content = self._extract_stream_content(chunk_data)
                    if content:
                        aggregated_content.append(content)
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                detail = str(e)
            raise RuntimeError(f"{self.provider_name} HTTPError {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"{self.provider_name} URLError: {e}")
        except http.client.RemoteDisconnected as e:
            raise RuntimeError(f"{self.provider_name} RemoteDisconnected: {e}")
        except OSError as e:
            # 流式读过程中对端关闭、TLS/套接字错误（urllib 未必包成 URLError）
            raise RuntimeError(f"{self.provider_name} 流式请求 I/O 错误: {e}")

        merged_content = "".join(aggregated_content)
        message: Dict[str, Any] = {"role": "assistant", "content": merged_content}
        choice_payload: Dict[str, Any] = {
            "index": 0,
            "message": message,
            "finish_reason": finish_reason or "stop",
        }

        return {
            "id": (final_chunk or {}).get("id") or "chatcmpl-stream-aggregated",
            "object": "chat.completion",
            "created": (final_chunk or {}).get("created"),
            "model": response_model or payload.get("model") or "",
            "choices": [choice_payload],
            "usage": usage,
        }

    @staticmethod
    def _extract_stream_content(chunk_data: Dict[str, Any]) -> Optional[str]:
        try:
            choices = chunk_data.get("choices", [])
            if not choices or not isinstance(choices[0], dict):
                return None

            delta = choices[0].get("delta", {}) or {}
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: List[str] = []
                    for item in content:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict) and isinstance(item.get("text"), str):
                            parts.append(item["text"])
                    if parts:
                        return "".join(parts)

            message = choices[0].get("message", {}) or {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "".join(parts)
            return None
        except Exception:
            return None
