import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from modules.app_paths import uploads_dir, user_data_dir


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_filename(name: str, fallback: str) -> str:
    base = (name or "").strip()
    if not base:
        base = fallback
    base = base.replace("\\", "_").replace("/", "_").replace(":", "_")
    base = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in base)
    base = base.strip("._ ")
    if not base:
        base = fallback
    return base


def _uploads_root() -> Path:
    env = os.environ.get("SACV_UPLOADS_DIR")
    if env:
        return Path(env).expanduser()
    up = uploads_dir()
    return up if isinstance(up, Path) else Path(str(up))


def _to_uploads_web_path(p: Path) -> Optional[str]:
    try:
        root = _uploads_root()
        rel = p.resolve().relative_to(root.resolve())
        return "/uploads/" + str(rel).replace("\\", "/")
    except Exception:
        return None


class VoxCPMTTSVoice(BaseModel):
    id: str
    name: str
    kind: str = Field(default="clone")
    model_key: str = Field(default="voxcpm_0_5b")
    language: str = Field(default="Auto")
    ref_audio_path: Optional[str] = None
    ref_audio_url: Optional[str] = None
    ref_text: Optional[str] = None
    status: str = Field(default="uploaded")
    progress: int = Field(default=0, ge=0, le=100)
    last_error: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class VoxCPMTTSVoiceStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        data_dir = user_data_dir()
        self._db_path = db_path or (data_dir / "voxcpm_tts_voices.json")
        self._lock = RLock()
        self._voices: Dict[str, VoxCPMTTSVoice] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            self._voices = {}
            if not self._db_path.exists():
                self._persist()
                return
            try:
                raw = json.loads(self._db_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for vid, data in raw.items():
                        if not isinstance(data, dict):
                            continue
                        try:
                            if "id" not in data:
                                data["id"] = str(vid)
                            if "kind" not in data:
                                data["kind"] = "clone"
                            if "created_at" not in data:
                                data["created_at"] = _now_iso()
                            if "updated_at" not in data:
                                data["updated_at"] = data.get("created_at") or _now_iso()
                            p = Path(str(data.get("ref_audio_path") or ""))
                            if p and str(data.get("ref_audio_path")):
                                data["ref_audio_url"] = _to_uploads_web_path(p)
                            else:
                                data["ref_audio_url"] = None
                            self._voices[str(vid)] = VoxCPMTTSVoice(**data)
                        except Exception:
                            continue
            except Exception:
                self._persist()

    def _persist(self) -> None:
        with self._lock:
            serializable = {vid: v.model_dump() for vid, v in self._voices.items()}
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> List[VoxCPMTTSVoice]:
        with self._lock:
            return list(self._voices.values())

    def get(self, voice_id: str) -> Optional[VoxCPMTTSVoice]:
        with self._lock:
            return self._voices.get(str(voice_id))

    def create_from_upload(
        self,
        upload_bytes: bytes,
        original_filename: str,
        name: Optional[str] = None,
        model_key: str = "voxcpm_0_5b",
        language: str = "Auto",
        ref_text: Optional[str] = None,
    ) -> VoxCPMTTSVoice:
        voice_id = str(uuid.uuid4())
        root = _uploads_root()
        dir_path = root / "audios" / "voxcpm_tts_voices" / voice_id
        dir_path.mkdir(parents=True, exist_ok=True)

        ext = Path(original_filename or "").suffix.lower()
        if ext not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}:
            ext = ".wav"
        stored_name = _safe_filename(Path(original_filename or "").stem, "ref") + ext
        raw_path = dir_path / stored_name
        raw_path.write_bytes(upload_bytes)

        now = _now_iso()
        display_name = (name or "").strip() or Path(original_filename or "").stem.strip() or f"voice_{voice_id[:8]}"

        v = VoxCPMTTSVoice(
            id=voice_id,
            name=display_name,
            kind="clone",
            model_key=(model_key or "voxcpm_0_5b").strip() or "voxcpm_0_5b",
            language=(language or "Auto").strip() or "Auto",
            ref_audio_path=str(raw_path),
            ref_audio_url=_to_uploads_web_path(raw_path),
            ref_text=(ref_text.strip() if isinstance(ref_text, str) and ref_text.strip() else None),
            status="uploaded",
            progress=0,
            last_error=None,
            meta={"original_filename": original_filename},
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._voices[voice_id] = v
            self._persist()
        return v

    def update(self, voice_id: str, updates: Dict[str, Any]) -> Optional[VoxCPMTTSVoice]:
        with self._lock:
            v = self._voices.get(str(voice_id))
            if not v:
                return None
            data = v.model_dump()
            for key in [
                "name",
                "kind",
                "model_key",
                "language",
                "ref_text",
                "status",
                "progress",
                "last_error",
                "meta",
                "ref_audio_path",
            ]:
                if key in updates and updates[key] is not None:
                    data[key] = updates[key]
            data["updated_at"] = _now_iso()
            p = Path(str(data.get("ref_audio_path") or ""))
            if p and str(data.get("ref_audio_path")):
                data["ref_audio_url"] = _to_uploads_web_path(p)
            else:
                data["ref_audio_url"] = None
            v2 = VoxCPMTTSVoice(**data)
            self._voices[str(voice_id)] = v2
            self._persist()
            return v2

    def delete(self, voice_id: str, remove_files: bool = False) -> bool:
        with self._lock:
            v = self._voices.get(str(voice_id))
            if not v:
                return False
            del self._voices[str(voice_id)]
            self._persist()
        if remove_files:
            try:
                p = Path(v.ref_audio_path) if v.ref_audio_path else None
                root = _uploads_root() / "audios" / "voxcpm_tts_voices" / str(voice_id)
                if root.exists() and root.is_dir():
                    for it in root.iterdir():
                        try:
                            if it.is_file() or it.is_symlink():
                                it.unlink()
                        except Exception:
                            pass
                    try:
                        root.rmdir()
                    except Exception:
                        pass
                else:
                    if p and p.exists() and p.is_file():
                        p.unlink()
            except Exception:
                pass
        return True

    def prepare_clone_paths(self, voice_id: str) -> Tuple[Path, Path]:
        v = self.get(voice_id)
        if not v:
            raise KeyError("voice_not_found")

        if v.ref_audio_path:
            raw_path = Path(v.ref_audio_path)
            root = raw_path.parent
        else:
            root = _uploads_root() / "audios" / "voxcpm_tts_voices" / voice_id
            root.mkdir(parents=True, exist_ok=True)
            raw_path = root / "raw.wav"

        out_wav = root / "ref_16k_mono.wav"
        return raw_path, out_wav

    def set_clone_progress(self, voice_id: str, status: str, progress: int, message: Optional[str] = None) -> Optional[VoxCPMTTSVoice]:
        updates: Dict[str, Any] = {"status": status, "progress": int(progress)}
        if status == "failed":
            updates["last_error"] = message
        if status in {"ready", "cloned"}:
            updates["last_error"] = None
            updates["progress"] = 100
        return self.update(voice_id, updates)


voxcpm_tts_voice_store = VoxCPMTTSVoiceStore()
