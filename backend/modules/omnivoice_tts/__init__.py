# OmniVoice 局域网服务集成（独立模块）

from .connection_store import omnivoice_tts_connection_store
from .service import omnivoice_tts_service

__all__ = ["omnivoice_tts_connection_store", "omnivoice_tts_service"]
