#!/usr/bin/env python3
import json
import re
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx

def slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_").lower() or "voice"

def get_ext_from_url(u: str) -> str:
    p = urlparse(u)
    name = Path(p.path).name
    if "." in name:
        ext = "." + name.split(".")[-1].lower()
        if ext in {".wav", ".mp3", ".m4a", ".flac"}:
            return ext
    return ".wav"

def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    json_path = project_root / "backend" / "serviceData" / "tencent_tts_data.json"
    base_up = Path(os.environ.get("SACV_UPLOADS_DIR") or (project_root / "uploads"))
    out_dir = base_up / "tts-samples" / "tencent"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    headers = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Range": "bytes=0-",
        "Referer": "https://cloud.tencent.com/",
        "Sec-Fetch-Dest": "audio",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Storage-Access": "active",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    client = httpx.Client(follow_redirects=True, timeout=30)

    total_all = 0
    remote = 0
    downloaded = 0
    failed = 0
    local_ok = 0
    local_missing = 0

    for category in data:
        for item in category.get("VoiceList", []):
            src = item.get("VoiceAudio")
            total_all += 1
            if not src or not isinstance(src, str):
                failed += 1
                continue
            if src.startswith("/uploads/"):
                fname = Path(src).name
                dest = out_dir / fname
                if dest.exists():
                    local_ok += 1
                else:
                    local_missing += 1
                continue
            vt = item.get("VoiceType")
            base_name = str(vt) if vt is not None else slugify(item.get("VoiceName") or "")
            ext = get_ext_from_url(src)
            dest = out_dir / f"{base_name}{ext}"
            remote += 1
            try:
                if not dest.exists():
                    r = client.get(src, headers=headers)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                item["VoiceAudio"] = f"/uploads/tts-samples/tencent/{dest.name}"
                downloaded += 1
            except Exception:
                failed += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(json.dumps({
        "total_all": total_all,
        "remote": remote,
        "downloaded": downloaded,
        "local_ok": local_ok,
        "local_missing": local_missing,
        "failed": failed
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
