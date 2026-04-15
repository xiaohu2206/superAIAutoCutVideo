# -*- coding: utf-8 -*-
"""IndexTTS 合成入口（供 modules/tts_service 调用）"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from modules.config.tts_config import TtsEngineConfig

from .client import (
    download_task_audio,
    poll_task_until_done,
    post_tts_generate,
    wav_to_mp3_with_ffmpeg,
)
from .connection_store import indextts_connection_store

logger = logging.getLogger(__name__)


async def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        if proc.returncode == 0:
            return float(out.decode().strip())
    except Exception:
        pass
    return None


class IndexTTSService:
    async def synthesize(
        self,
        text: str,
        out_path: str,
        voice_id: Optional[str],
        cfg: Optional[TtsEngineConfig],
    ) -> Dict[str, Any]:
        if not indextts_connection_store.is_connected():
            return {"success": False, "error": "indextts_not_connected"}

        base = indextts_connection_store.base_url()
        prefix = indextts_connection_store.api_prefix()

        ep = (getattr(cfg, "extra_params", None) or {}) if cfg else {}
        gen_params = ep.get("GenerateParams")
        gen_params_d: Optional[Dict[str, Any]] = gen_params if isinstance(gen_params, dict) else None

        vid = (voice_id or (cfg.active_voice_id if cfg else None) or "").strip() or None

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()
        want_mp3 = suffix in {".mp3", ".m4a"} or suffix == ""

        try:
            task_id = await post_tts_generate(base, prefix, text, voice_id=vid, params=gen_params_d)
            await poll_task_until_done(base, prefix, task_id)

            if want_mp3 or suffix == ".mp3":
                with tempfile.TemporaryDirectory(prefix="indextts_") as td:
                    wav_tmp = Path(td) / "out.wav"
                    await download_task_audio(base, prefix, task_id, wav_tmp)
                    ok = await wav_to_mp3_with_ffmpeg(wav_tmp, out)
                    if not ok:
                        return {"success": False, "error": "indextts_wav_to_mp3_failed"}
            else:
                await download_task_audio(base, prefix, task_id, out)

            dur = await _ffprobe_duration(str(out))
            return {
                "success": True,
                "path": str(out),
                "duration": dur,
                "task_id": task_id,
            }
        except Exception as e:
            logger.exception("IndexTTS 合成失败")
            return {"success": False, "error": str(e)}


indextts_service = IndexTTSService()
