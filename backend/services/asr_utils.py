import math


def _ms_to_srt_ts(ms: int) -> str:
    s = ms / 1000.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms_part = int(round((s - math.floor(s)) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms_part:03d}"


def convert_asr_to_custom_format(segments: list) -> list:
    result = []
    for seg in segments:
        start_seconds = (seg.get('start_time', 0) or 0) / 1000.0
        end_seconds = (seg.get('end_time', 0) or 0) / 1000.0
        result.append({
            'start': round(start_seconds, 2),
            'end': round(end_seconds, 2),
            'text': seg.get('text', '')
        })
    return result


def utterances_to_srt(utterances: list) -> str:
    lines = []
    idx = 1
    for u in utterances:
        st = int(u.get('start_time', 0) or 0)
        et = int(u.get('end_time', 0) or 0)
        text = (u.get('text') or u.get('transcript') or '').strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{_ms_to_srt_ts(st)} --> {_ms_to_srt_ts(et)}")
        lines.append(text)
        lines.append("")
        idx += 1
    return "\n".join(lines).strip() + ("\n" if lines else "")