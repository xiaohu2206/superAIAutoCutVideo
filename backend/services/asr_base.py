import json
import zlib
import logging
from pathlib import Path
from typing import Union, Optional
import os


class BaseASR:
    """
    轻量级 ASR 基类，提供：
    - 音频读取（路径或二进制）
    - CRC32 计算（十六进制）
    - 简单文件级缓存（JSON）

    子类需实现：
    - _run(callback) -> dict  返回规范化的原始结果字典（包含 'utterances' 列表）
    - _get_key() -> str       返回用于缓存键的唯一字符串
    """

    def __init__(self, audio_path: Union[str, bytes], use_cache: bool = False):
        self.use_cache = use_cache
        self.audio_path: Union[str, bytes] = audio_path
        self.file_binary: bytes = b""
        self.crc32_hex: str = ""

        # 读取音频数据
        if isinstance(audio_path, bytes):
            self.file_binary = audio_path
        elif isinstance(audio_path, str):
            p = Path(audio_path)
            if not p.exists():
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")
            self.file_binary = p.read_bytes()
        else:
            raise TypeError("audio_path 需为 str 文件路径或 bytes 数据")

        # 计算 CRC32（十六进制小写）
        self.crc32_hex = format(zlib.crc32(self.file_binary) & 0xFFFFFFFF, '08x')

    # 缓存目录使用项目根下的 uploads/asr_cache
    @property
    def _cache_dir(self) -> Path:
        env = os.environ.get("SACV_UPLOADS_DIR")
        root = Path(env) if env else Path(__file__).resolve().parents[2] / "uploads"
        cache_dir = root / "asr_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _cache_path(self) -> Path:
        key = self._get_key()
        return self._cache_dir / f"{key}.json"

    def _get_key(self) -> str:
        # 子类可覆盖以加入更多维度（例如字级时间戳）
        return f"{self.__class__.__name__}-{self.crc32_hex}"

    def run(self, callback: Optional[callable] = None) -> dict:
        """
        返回规范化的原始数据 dict，至少包含 'utterances': list
        若启用缓存且命中，则直接返回缓存；否则执行 _run 并写入缓存。
        """
        cache_path = self._cache_path()

        if self.use_cache and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding='utf-8'))
                # 简单校验结构
                if isinstance(data, dict) and isinstance(data.get('utterances'), list):
                    logging.info(f"ASR 命中缓存: {cache_path}")
                    return data
            except Exception as e:
                logging.warning(f"读取 ASR 缓存失败，将重新识别: {e}")

        # 执行识别
        data = self._run(callback=callback)
        if not isinstance(data, dict):
            raise ValueError("ASR 返回数据结构异常，期望 dict")

        # 写缓存（尽力而为）
        try:
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logging.warning(f"写入 ASR 缓存失败: {e}")

        return data
