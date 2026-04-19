import base64
import http.client
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger("AIShotSearch.aiModels.openai_compatible")


PROMPT_FILES = {
    "zh": "frame_analysis_zh.md",
    "en": "frame_analysis_en.md",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_frame_analysis_prompt(prompt_language: str, subtitle_text: str) -> str:
    language = str(prompt_language or "zh").strip().lower()
    prompt_name = PROMPT_FILES.get(language, PROMPT_FILES["zh"])
    prompt_path = _project_root() / "prompts" / prompt_name
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()
    return template.replace("{subtitle_text}", subtitle_text or "")


class OpenAICompatibleClientBase:
    """
    OpenAI 兼容接口通用底座。
    - 统一处理鉴权、POST JSON、重试
    - 统一提供 chat / embeddings / rerank 调用
    - 子类只负责默认 URL 与配置校验
    """

    provider_name = "openai_compatible"
    default_chat_completions_url = ""
    default_embeddings_url = ""
    default_rerank_url = ""
    config_section_name = "model_client"

    def __init__(
        self,
        *,
        api_key: str,
        chat_completions_url: str = "",
        embeddings_url: str = "",
        rerank_url: str = "",
        timeout_seconds: int = 120,
    ):
        if not api_key:
            raise ValueError(f"{self.provider_name} api_key 不能为空（请在 config.json 中配置 {self.config_section_name}.api_key）")
        self.api_key = api_key
        self.chat_completions_url = (chat_completions_url or self.default_chat_completions_url or "").strip()
        self.embeddings_url = (embeddings_url or self.default_embeddings_url or "").strip()
        self.rerank_url = (rerank_url or self.default_rerank_url or "").strip()
        self.timeout_seconds = int(timeout_seconds or 120)

    def _build_headers(self) -> Dict[str, str]:
        return self._build_headers_for_api_key(self.api_key)

    @staticmethod
    def _build_headers_for_api_key(api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post_json(self, url: str, payload: Dict[str, Any], headers_override: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if not url:
            raise ValueError(f"{self.provider_name} 请求 URL 不能为空")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            method="POST",
            headers=headers_override or self._build_headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
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

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, http.client.IncompleteRead):
            return True
        msg = str(exc or "")
        retryable_markers = [
            "HTTPError 429",
            "HTTPError 500",
            "HTTPError 502",
            "HTTPError 503",
            "HTTPError 504",
            "Too Many Requests",
            "负载已饱和",
            "rate limit",
            "temporarily unavailable",
            "timed out",
            "timeout",
            "URLError",
            "RemoteDisconnected",
            "Remote end closed connection",
            "Connection reset by peer",
            "Broken pipe",
            "IncompleteRead",
            "[errno 54]",
            "[errno 32]",
        ]
        lower_msg = msg.lower()
        return any(marker.lower() in lower_msg for marker in retryable_markers)

    def _is_chat_json_retryable(self, exc: Exception) -> bool:
        """chat_json 专用：模型偶发非法 JSON / 截断时也应重试整次请求。"""
        if isinstance(exc, json.JSONDecodeError):
            return True
        return self._is_retryable_error(exc)

    @staticmethod
    def _compute_retry_sleep_seconds(base_seconds: float, attempt_index: int) -> float:
        base = max(0.5, float(base_seconds or 1.0))
        capped = min(60.0, base * (2 ** max(0, attempt_index)))
        jitter = random.uniform(0.0, min(1.0, capped * 0.15))
        return capped + jitter

    def _post_json_with_retry(
        self,
        url: str,
        payload: Dict[str, Any],
        *,
        max_retries: int = 0,
        retry_sleep_seconds: float = 1.0,
        headers_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        attempts = max(1, int(max_retries or 0) + 1)
        last_exc: Optional[Exception] = None
        for i in range(attempts):
            try:
                return self._post_json(url, payload, headers_override=headers_override)
            except Exception as e:
                last_exc = e
                if i >= attempts - 1 or not self._is_retryable_error(e):
                    break
                time.sleep(self._compute_retry_sleep_seconds(retry_sleep_seconds, i))
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _image_to_data_url(image_path: str) -> str:
        ext = os.path.splitext(image_path)[1].lower()
        mime = "image/jpeg"
        if ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    @classmethod
    def _image_path_to_vl_data_url(
        cls,
        image_path: str,
        *,
        max_long_edge: int,
        jpeg_quality: int,
    ) -> str:
        """
        将帧图转为 data URL；当 max_long_edge > 0 时按比例缩小长边并统一为 JPEG，减少视觉 token。
        降采样失败时回退为原图直读（与 _image_to_data_url 行为一致）。
        """
        if max_long_edge <= 0:
            return cls._image_to_data_url(image_path)
        q = int(jpeg_quality)
        q = max(1, min(100, q))
        try:
            import cv2

            img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                raise RuntimeError("cv2.imread 返回 None")
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            h, w = img.shape[:2]
            me = max(h, w)
            if me > max_long_edge:
                scale = max_long_edge / float(me)
                nw = max(1, int(round(w * scale)))
                nh = max(1, int(round(h * scale)))
                img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(
                ".jpg",
                img,
                [int(cv2.IMWRITE_JPEG_QUALITY), q],
            )
            if not ok or buf is None:
                raise RuntimeError("cv2.imencode 失败")
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except Exception as e:
            logger.warning("VL 图片降采样失败，使用原图: path=%s err=%s", image_path, e)
            return cls._image_to_data_url(image_path)

    def analyze_shot_frame(
        self,
        *,
        model: str,
        image_paths: List[str],
        subtitle_text: str,
        prompt_language: str = "zh",
        temperature: float = 0.2,
        max_retries: int = 0,
        retry_sleep_seconds: float = 1.0,
        max_image_long_edge: int = 0,
        vl_jpeg_quality: int = 85,
        log_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.chat_completions_url:
            raise ValueError(f"{self.provider_name} 未配置 chat_completions_url，无法进行多模态分析")
        log_context = dict(log_context or {})
        shot_id = log_context.get("shot_id")
        shot_index = log_context.get("shot_index")
        item_prefix = f"[shot_analysis] shot_id={shot_id} shot_index={shot_index}"
        subtitle_preview = (subtitle_text or "").replace("\n", " ").strip()[:120]
        logger.info(
            f"{item_prefix} 开始调用视觉模型 provider={self.provider_name} model={model} image_count={len(image_paths)} subtitle_len={len(subtitle_text or '')} subtitle_preview={subtitle_preview!r} prompt_language={prompt_language} max_image_long_edge={max_image_long_edge} vl_jpeg_quality={vl_jpeg_quality}"
        )
        prompt = _load_frame_analysis_prompt(prompt_language, subtitle_text)

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for p in image_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_path_to_vl_data_url(
                            p,
                            max_long_edge=max_image_long_edge,
                            jpeg_quality=vl_jpeg_quality,
                        )
                    },
                }
            )

        schema = {
            "name": "shot_visual_analysis",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "desc": {"type": "string"},
                    "brief": {"type": "string"},
                    "objects": {"type": "array", "items": {"type": "string"}},
                    "action": {"type": "string"},
                    "scene": {"type": "string"},
                    "emotion": {"type": "string"},
                },
                "required": ["desc", "brief", "objects", "action", "scene", "emotion"],
                "additionalProperties": False,
            },
        }

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "response_format": {"type": "json_schema", "json_schema": schema},
        }

        attempts = max(1, int(max_retries or 0) + 1)
        last_exc: Optional[Exception] = None
        for i in range(attempts):
            try:
                # 注意：这里做“整段流程级重试”，任何异常都会触发重试（包括 JSON 解析失败/结构异常）。
                resp = self._post_json_with_retry(
                    self.chat_completions_url,
                    payload,
                    max_retries=0,
                    retry_sleep_seconds=retry_sleep_seconds,
                )
                logger.info(
                    f"{item_prefix} 视觉模型响应成功 choice_count={len(resp.get('choices', []) or [])}"
                )
                try:
                    content_str = resp["choices"][0]["message"]["content"]
                except Exception:
                    raise RuntimeError(f"{self.provider_name} chat 返回结构异常: {resp}")
                try:
                    parsed = json.loads(content_str)
                except Exception:
                    content_str = (content_str or "").strip()
                    if content_str.startswith("```"):
                        # 兼容模型偶发 ```json ... ``` 包裹
                        lines = content_str.splitlines()
                        if lines and lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        content_str = "\n".join(lines).strip()
                    parsed = json.loads(content_str)
                logger.info(
                    f"{item_prefix} 视觉模型解析完成 action={parsed.get('action', '')!r} scene={parsed.get('scene', '')!r} emotion={parsed.get('emotion', '')!r} objects_count={len(parsed.get('objects', []) or [])}"
                )
                return parsed
            except Exception as e:
                last_exc = e
                if i >= attempts - 1:
                    break
                sleep_s = self._compute_retry_sleep_seconds(retry_sleep_seconds, i)
                logger.warning(
                    "%s 视觉分析失败，将重试 (%s/%s) sleep=%.2fs err=%s",
                    item_prefix,
                    i + 1,
                    attempts,
                    sleep_s,
                    e,
                )
                time.sleep(sleep_s)

        raise last_exc  # type: ignore[misc]

    def embed_text(
        self,
        *,
        model: str,
        text: str,
        max_retries: int = 0,
        retry_sleep_seconds: float = 1.0,
        provider_override: Optional[Tuple[str, Dict[str, Any]]] = None,
    ) -> List[float]:
        embeddings_url = self.embeddings_url
        provider_name = self.provider_name
        api_key = self.api_key
        headers = None

        if provider_override:
            provider, provider_cfg = provider_override
            provider = str(provider or "").strip().lower()
            provider_cfg = provider_cfg or {}
            if provider == "yunwu":
                embeddings_url = provider_cfg.get("embeddings_url") or "https://yunwu.ai/v1/embeddings"
                provider_name = "Yunwu"
                api_key = provider_cfg.get("api_key", api_key)
            elif provider in {"custom", "custom_openai", "openai_compatible"}:
                base_url = str(provider_cfg.get("base_url") or "").strip().strip("`").rstrip("/")
                embeddings_url = provider_cfg.get("embeddings_url") or (f"{base_url}/embeddings" if base_url else self.embeddings_url)
                provider_name = "CustomOpenAI"
                api_key = provider_cfg.get("api_key", api_key)
            headers = self._build_headers_for_api_key(api_key)

        if not embeddings_url:
            raise ValueError(f"{provider_name} 未配置 embeddings_url，无法进行向量化")
        payload = {"model": model, "input": (text or "").replace("\n", " ")}
        resp = self._post_json_with_retry(
            embeddings_url,
            payload,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
            headers_override=headers,
        )
        try:
            return resp["data"][0]["embedding"]
        except Exception:
            raise RuntimeError(f"{self.provider_name} embeddings 返回结构异常: {resp}")

    def _extract_message_content(self, resp: Dict[str, Any]) -> str:
        try:
            choices = resp.get("choices", [])
            if not choices or not isinstance(choices[0], dict):
                raise RuntimeError(f"响应缺少 choices: {resp}")

            message = choices[0].get("message", {}) or {}
            content = message.get("content")

            if isinstance(content, str):
                return content

            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        if isinstance(item.get("text"), str):
                            parts.append(item["text"])
                        elif item.get("type") == "output_text" and isinstance(item.get("text"), str):
                            parts.append(item["text"])
                return "".join(parts)

            output_text = resp.get("output_text")
            if isinstance(output_text, str) and output_text:
                return output_text

            output = resp.get("output")
            if isinstance(output, list):
                parts = []
                for out_item in output:
                    if not isinstance(out_item, dict):
                        continue
                    content_list = out_item.get("content")
                    if not isinstance(content_list, list):
                        continue
                    for content_item in content_list:
                        if isinstance(content_item, dict) and isinstance(content_item.get("text"), str):
                            parts.append(content_item["text"])
                if parts:
                    return "".join(parts)

            if isinstance(message, dict) and message.get("role") == "assistant":
                if isinstance(resp.get("usage"), dict) and any((resp.get("usage") or {}).get(k, 0) for k in ["completion_tokens", "output_tokens", "total_tokens"]):
                    raise RuntimeError(f"{self.provider_name} 流式响应已结束，但未提取到任何文本内容: {resp}")
                return ""

            raise RuntimeError(f"无法从响应中提取 content: {resp}")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"解析 chat content 失败: {e}; 原始响应: {resp}")

    def chat_json(
        self,
        *,
        model: str,
        user_prompt: str,
        json_schema: Dict[str, Any],
        system_prompt: str = "",
        temperature: float = 0.2,
        max_retries: int = 0,
        retry_sleep_seconds: float = 1.0,
    ) -> Any:
        if not self.chat_completions_url:
            raise ValueError(f"{self.provider_name} 未配置 chat_completions_url，无法进行对话生成")
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
            "response_format": {"type": "json_schema", "json_schema": json_schema},
        }
        attempts = max(1, int(max_retries or 0) + 1)
        last_exc: Optional[Exception] = None
        for i in range(attempts):
            try:
                resp = self._post_json_with_retry(
                    self.chat_completions_url,
                    payload,
                    max_retries=max_retries,
                    retry_sleep_seconds=retry_sleep_seconds,
                )
                content_str = self._extract_message_content(resp)

                try:
                    return json.loads(content_str)
                except Exception:
                    s = (content_str or "").strip()
                    if s.startswith("```"):
                        lines = s.splitlines()
                        if lines and lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        s = "\n".join(lines).strip()
                    return json.loads(s)
            except Exception as e:
                last_exc = e
                if i >= attempts - 1 or not self._is_chat_json_retryable(e):
                    break
                if isinstance(e, json.JSONDecodeError):
                    logger.warning(
                        "%s chat_json JSON 解析失败，将重试 (%s/%s): %s",
                        self.provider_name,
                        i + 1,
                        attempts,
                        e,
                    )
                elif self._is_retryable_error(e):
                    logger.warning(
                        "%s chat_json 请求失败，将重试 (%s/%s): %s",
                        self.provider_name,
                        i + 1,
                        attempts,
                        e,
                    )
                time.sleep(self._compute_retry_sleep_seconds(retry_sleep_seconds, i))
        raise last_exc  # type: ignore[misc]

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: List[str],
        top_n: int,
        instruct: str = "",
        max_retries: int = 0,
        retry_sleep_seconds: float = 1.0,
        provider_override: Optional[Tuple[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        rerank_url = self.rerank_url
        provider_name = self.provider_name
        api_key = self.api_key
        headers = None

        if provider_override:
            provider, provider_cfg = provider_override
            provider = str(provider or "").strip().lower()
            provider_cfg = provider_cfg or {}
            if provider == "yunwu":
                rerank_url = provider_cfg.get("rerank_url") or "https://yunwu.ai/v1/rerank"
                provider_name = "Yunwu"
                api_key = provider_cfg.get("api_key", api_key)
            elif provider in {"custom", "custom_openai", "openai_compatible"}:
                base_url = str(provider_cfg.get("base_url") or "").strip().strip("`").rstrip("/")
                rerank_url = provider_cfg.get("rerank_url") or (f"{base_url}/rerank" if base_url else self.rerank_url)
                provider_name = "CustomOpenAI"
                api_key = provider_cfg.get("api_key", api_key)
            headers = self._build_headers_for_api_key(api_key)

        if not rerank_url:
            raise ValueError(f"{provider_name} 未配置 rerank_url，无法进行重排")
        payload: Dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": int(top_n),
        }
        if instruct:
            payload["instruct"] = instruct

        resp = self._post_json_with_retry(
            rerank_url,
            payload,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
            headers_override=headers,
        )
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            if isinstance(resp.get("results"), list):
                return resp["results"]
            if isinstance(resp.get("data"), list):
                return resp["data"]
        raise RuntimeError(f"{provider_name} rerank 返回结构异常: {resp}")
