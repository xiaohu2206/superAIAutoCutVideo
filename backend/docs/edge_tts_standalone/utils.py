from loguru import logger

PUNCTUATIONS = [
    "?",
    ",",
    ".",
    "、",
    ";",
    ":",
    "!",
    "…",
    "？",
    "，",
    "。",
    "、",
    "；",
    "：",
    "！",
    "...",
]

def split_string_by_punctuations(s):
    result = []
    txt = ""

    previous_char = ""
    next_char = ""
    for i in range(len(s)):
        char = s[i]
        if char == "\n":
            result.append(txt.strip())
            txt = ""
            continue

        if i > 0:
            previous_char = s[i - 1]
        if i < len(s) - 1:
            next_char = s[i + 1]

        if char == "." and previous_char.isdigit() and next_char.isdigit():
            # 取现1万，按2.5%收取手续费, 2.5 中的 . 不能作为换行标记
            txt += char
            continue

        if char not in PUNCTUATIONS:
            txt += char
        else:
            result.append(txt.strip())
            txt = ""
    result.append(txt.strip())
    # filter empty string
    result = list(filter(None, result))
    return result

def time_to_seconds(time_str: str) -> float:
    """
    将不同格式的时间字符串转换为秒数
    支持格式:
    - "HH:MM:SS"
    - "MM:SS"
    - "SS"
    - "SS,mmm" -> 秒,毫秒
    - "SS-mmm" -> 秒-毫秒
    
    Args:
        time_str: 时间字符串
        
    Returns:
        float: 转换后的秒数(包含毫秒)
    """
    try:
        # 处理带有'-'的毫秒格式
        if '-' in time_str:
            time_part, ms_part = time_str.split('-')
            ms = float(ms_part) / 1000
        # 处理带有','的毫秒格式
        elif ',' in time_str:
            time_part, ms_part = time_str.split(',')
            ms = float(ms_part) / 1000
        else:
            time_part = time_str
            ms = 0

        # 分割时间部分
        parts = time_part.split(':')

        if len(parts) == 3:  # HH:MM:SS
            h, m, s = map(float, parts)
            seconds = h * 3600 + m * 60 + s
        elif len(parts) == 2:  # MM:SS
            m, s = map(float, parts)
            seconds = m * 60 + s
        else:  # SS
            seconds = float(parts[0])

        return seconds + ms

    except (ValueError, IndexError) as e:
        logger.error(f"时间格式转换错误 {time_str}: {str(e)}")
        return 0.0

def seconds_to_time(seconds: float) -> str:
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"
