# IndexTTS 局域网服务集成（独立模块）

from .connection_store import indextts_connection_store
from .service import indextts_service

__all__ = ["indextts_connection_store", "indextts_service"]
