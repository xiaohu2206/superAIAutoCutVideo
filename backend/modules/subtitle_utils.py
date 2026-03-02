import re
from pathlib import Path
from typing import List, Dict, Any

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

def parse_srt(srt_path: Path) -> List[Dict[str, Any]]:
    """简易SRT解析，返回包含 start/end/text 的列表"""
    def _parse_ts(ts: str) -> float:
        # format: HH:MM:SS,mmm
        try:
            parts = ts.replace(",", ":").split(":")
            if len(parts) == 4:
                h, m, s, ms = parts
                return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
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
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
        norm = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [ln.strip() for ln in norm.splitlines() if ln.strip()]
        
        # 优先检测压缩后的行格式：[HH:MM:SS,mmm-HH:MM:SS,mmm] text
        bracket_pattern = re.compile(r"^\[(\d{2}:\d{2}:\d{2},\d{3})-(\d{2}:\d{2}:\d{2},\d{3})\]\s*(.+)$")
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
