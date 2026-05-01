# -*- coding: utf-8 -*-
"""OmniVoice 合成入口（供 modules/tts_service 调用）"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from modules.config.tts_config import TtsEngineConfig
from modules.ffmpeg_utils import ffprobe_get_duration

from .client import (
    download_task_audio,
    poll_task_until_done,
    post_tts_generate,
    wav_to_mp3_with_ffmpeg,
)
from .connection_store import omnivoice_tts_connection_store

logger = logging.getLogger(__name__)


class OmniVoiceTTSService:
    async def synthesize(
        self,
        text: str,
        out_path: str,
        voice_id: Optional[str],
        cfg: Optional[TtsEngineConfig],
    ) -> Dict[str, Any]:
        if not omnivoice_tts_connection_store.is_connected():
            return {"success": False, "error": "omnivoice_tts_not_connected"}

        base = omnivoice_tts_connection_store.base_url()
        prefix = omnivoice_tts_connection_store.api_prefix()

        ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
        gen_params = ep.get("GenerateParams") or ep.get("params")
        gen_params_d: Optional[Dict[str, Any]] = gen_params if isinstance(gen_params, dict) else None
        language = ep.get("Language") if isinstance(ep.get("Language"), str) else None
        language_s = str(language).strip() if language else None
        ref_text = ep.get("RefText")
        ref_text_s = str(ref_text).strip() if isinstance(ref_text, str) and ref_text.strip() else None

        vid = (voice_id or (cfg.active_voice_id if cfg else None) or "").strip() or None

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()
        want_mp3 = suffix in {".mp3", ".m4a"} or suffix == ""

        try:
            task_id = await post_tts_generate(
                base,
                prefix,
                text,
                voice_id=vid,
                language=language_s,
                ref_text=ref_text_s,
                params=gen_params_d,
            )
            await poll_task_until_done(base, prefix, task_id)

            if want_mp3 or suffix == ".mp3":
                with tempfile.TemporaryDirectory(prefix="omnivoice_") as td:
                    wav_tmp = Path(td) / "out.wav"
                    await download_task_audio(base, prefix, task_id, wav_tmp)
                    ok = await wav_to_mp3_with_ffmpeg(wav_tmp, out)
                    if not ok:
                        logger.warning("ffmpeg 不可用，回退为直接输出 wav 数据")
                        out.write_bytes(wav_tmp.read_bytes())
            else:
                await download_task_audio(base, prefix, task_id, out)

            dur = await ffprobe_get_duration(str(out))
            return {
                "success": True,
                "path": str(out),
                "duration": dur,
                "task_id": task_id,
            }
        except Exception as e:
            logger.exception("OmniVoice 合成失败")
            return {"success": False, "error": str(e)}


omnivoice_tts_service = OmniVoiceTTSService()
