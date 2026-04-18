# -*- coding: utf-8 -*-
"""IndexTTS 连接状态持久化（与 TTS 引擎配置解耦，由「连接成功」接口写入）"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from modules.app_paths import user_config_dir

logger = logging.getLogger(__name__)


@dataclass
class IndexTTSConnectionState:
    connected: bool = False
    base_url: str = ""  # 如 http://192.168.1.10:7860
    api_prefix: str = "/api"
    host: str = ""
    port: int = 7860
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndexTTSConnectionState":
        return cls(
            connected=bool(d.get("connected")),
            base_url=str(d.get("base_url") or ""),
            api_prefix=str(d.get("api_prefix") or "/api"),
            host=str(d.get("host") or ""),
            port=int(d.get("port") or 7860),
            last_error=d.get("last_error"),
        )


class IndexTTSConnectionStore:
    def __init__(self) -> None:
        self._path: Path = user_config_dir() / "indextts_connection.json"
        self._state = IndexTTSConnectionState()
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._state = IndexTTSConnectionState.from_dict(raw if isinstance(raw, dict) else {})
        except Exception as e:
            logger.warning("IndexTTS 连接状态加载失败: %s", e)
            self._state = IndexTTSConnectionState()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("IndexTTS 连接状态保存失败: %s", e)

    def get_state(self) -> IndexTTSConnectionState:
        return self._state

    def is_connected(self) -> bool:
        return bool(self._state.connected and self._state.base_url)

    def base_url(self) -> str:
        return (self._state.base_url or "").rstrip("/")

    def api_prefix(self) -> str:
        p = (self._state.api_prefix or "/api").strip()
        if not p.startswith("/"):
            p = "/" + p
        return p.rstrip("/") or "/api"

    def set_connected(
        self,
        *,
        base_url: str,
        api_prefix: str,
        host: str,
        port: int,
    ) -> None:
        self._state.connected = True
        self._state.base_url = base_url.rstrip("/")
        self._state.api_prefix = api_prefix
        self._state.host = host
        self._state.port = int(port)
        self._state.last_error = None
        self._save()

    def set_failed(self, message: str) -> None:
        self._state.connected = False
        self._state.last_error = message
        self._save()

    def disconnect(self) -> None:
        self._state = IndexTTSConnectionState()
        self._save()


indextts_connection_store = IndexTTSConnectionStore()
