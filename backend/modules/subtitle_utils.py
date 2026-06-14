import re
from pathlib import Path
from typing import Any, Dict, List, Optional


SUBTITLE_PARSER_VERSION = 2

def format_ts_srt(seconds: float) -> str:
    """Format seconds to HH:MM:SS,mmm for SRT"""
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    ms = ms_total % 1000
    s_total = ms_total // 1000
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def compress_srt_content(content: str) -> str:
    def normalize_timestamp(raw: str) -> Optional[str]:
        match = re.fullmatch(r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})", raw.strip())
        if not match:
            return None
        hours, minutes, seconds, fraction = match.groups()
        total = (
            int(hours) * 3600
            + int(minutes) * 60
            + int(seconds)
            + int(fraction) / (10 ** len(fraction))
        )
        return format_ts_srt(total)

    text = content.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = [block for block in text.split("\n\n") if block.strip()]
    out_lines: List[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines[:3]) if "-->" in line), None)
        if timing_index is None:
            continue
        parts = lines[timing_index].split("-->")
        if len(parts) < 2:
            continue
        start = normalize_timestamp(parts[0])
        end = normalize_timestamp(parts[1])
        if not start or not end:
            continue
        subtitle_text = " ".join(lines[timing_index + 1 :])
        subtitle_text = re.sub(r"\s+", " ", subtitle_text).strip()
        subtitle_text = re.sub(r"<[^>]+>", "", subtitle_text)
        if subtitle_text:
            out_lines.append(f"[{start}-{end}] {subtitle_text}")
    return "\n".join(out_lines) + ("\n" if out_lines else "")

def parse_srt(srt_path: Path) -> List[Dict[str, Any]]:
    """简易SRT解析，返回包含 start/end/text 的列表"""
    def _parse_ts(ts: str) -> float:
        # format: HH:MM:SS,mmm
        try:
            parts = ts.replace(".", ",").replace(",", ":").split(":")
            if len(parts) == 4:
                h, m, s, ms = parts
                return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / (10 ** len(ms))
            elif len(parts) == 3:
                 # maybe HH:MM:SS.mmm or HH:MM:SS
                 if "." in parts[2]:
                     s, ms = parts[2].split(".")
                     return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(s) + int(ms) / (10**len(ms))
                 else:
                     return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except Exception:
            return 0.0
        return 0.0

    segments: List[Dict[str, Any]] = []
    if not srt_path.exists():
        return segments

    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
        norm = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
        
        # 优先检测压缩后的行格式：[HH:MM:SS,mmm-HH:MM:SS,mmm] text
        timestamp = r"\d+:\d{1,2}:\d{1,2}[,.]\d{1,3}"
        bracket_pattern = re.compile(rf"^\[({timestamp})-({timestamp})\]\s*(.+)$")
        bracket_matches = [bracket_pattern.match(ln) for ln in lines]
        
        if any(bracket_matches):
            idx = 1
            for m in bracket_matches:
                if not m:
                    continue
                start_str, end_str, text = m.groups()
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
                idx += 1
        else:
            # 兼容标准SRT解析
            blocks = [b.strip() for b in norm.split("\n\n") if b.strip()]
            for idx, block in enumerate(blocks, start=1):
                lines_in_block = [line for line in block.splitlines() if line.strip()]
                if len(lines_in_block) < 2:
                    continue
                
                # Try to find timing line
                timing_line_idx = -1
                for i, line in enumerate(lines_in_block[:3]):
                     if "-->" in line:
                         timing_line_idx = i
                         break
                
                if timing_line_idx == -1:
                    continue

                timing_line = lines_in_block[timing_line_idx]
                parts = timing_line.split("-->")
                if len(parts) < 2:
                    continue
                    
                start_str = parts[0].strip()
                end_str = parts[1].strip()
                
                start_t = _parse_ts(start_str)
                end_t = _parse_ts(end_str)
                
                text_lines = lines_in_block[timing_line_idx+1:]
                text = " ".join([ln.strip() for ln in text_lines if ln.strip()])
                
                if not text:
                    text = f"字幕段{idx}"
                    
                segments.append({
                    "id": str(idx),
                    "start_time": float(start_t),
                    "end_time": float(end_t),
                    "text": text,
                    "subtitle": text,
                })
    except Exception:
        # 解析失败返回空
        pass
    return segments
