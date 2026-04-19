import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str
    
    def to_dict(self):
        return {
            'index': self.index,
            'start': self.start,
            'end': self.end,
            'text': self.text
        }


class SRTParser:
    @staticmethod
    def parse_time(time_str: str) -> float:
        time_str = time_str.strip()
        match = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', time_str)
        if not match:
            raise ValueError(f"无效的时间格式: {time_str}")
        
        hours, minutes, seconds, milliseconds = match.groups()
        total_seconds = (
            int(hours) * 3600 +
            int(minutes) * 60 +
            int(seconds) +
            int(milliseconds) / 1000
        )
        return total_seconds
    
    @staticmethod
    def parse(srt_path: str) -> List[Subtitle]:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        blocks = re.split(r'\n\s*\n', content.strip())
        subtitles = []
        
        for block in blocks:
            if not block.strip():
                continue
            
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            try:
                index = int(lines[0].strip())
            except ValueError:
                continue
            
            time_match = re.match(
                r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})',
                lines[1]
            )
            if not time_match:
                continue
            
            start_time = SRTParser.parse_time(time_match.group(1))
            end_time = SRTParser.parse_time(time_match.group(2))
            
            text = '\n'.join(lines[2:]).strip()
            
            subtitles.append(Subtitle(
                index=index,
                start=start_time,
                end=end_time,
                text=text
            ))
        
        return subtitles
    
    @staticmethod
    def save_to_srt(subtitles: List[Subtitle], output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                start_str = SRTParser._format_time(sub.start)
                end_str = SRTParser._format_time(sub.end)
                f.write(f"{i}\n")
                f.write(f"{start_str} --> {end_str}\n")
                f.write(f"{sub.text}\n")
                f.write("\n")
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
