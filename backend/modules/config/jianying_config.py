#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class JianyingPathConfig(BaseModel):
    drafts_dir: Optional[str] = Field(default=None, description="剪映（CapCut/JianyingPro）草稿存放目录")


class JianyingConfigManager:
    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            backend_dir = Path(__file__).parent.parent.parent
            cfg_dir = backend_dir / "config"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            config_file = cfg_dir / "jianying_config.json"
        self.config_file = Path(config_file)
        self.config = JianyingPathConfig()
        self.load()

    def load(self) -> None:
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text("utf-8"))
                if isinstance(data, dict):
                    self.config = JianyingPathConfig(**data)
            else:
                self.save()
        except Exception as e:
            logger.error(f"加载剪映配置失败: {e}")
            self.config = JianyingPathConfig()

    def save(self) -> None:
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps(self.config.dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"保存剪映配置失败: {e}")
            raise

    def get_draft_path(self) -> Optional[Path]:
        p = self.config.drafts_dir
        if not p:
            return None
        try:
            return Path(p)
        except Exception:
            return None

    def set_draft_path(self, path_str: str) -> bool:
        try:
            p = Path(path_str).expanduser()
            self.config.drafts_dir = str(p)
            self.save()
            return True
        except Exception as e:
            logger.error(f"设置剪映草稿路径失败: {e}")
            return False

    def _candidate_paths_windows(self) -> List[Path]:
        items: List[Path] = []
        appdata = Path(os.getenv("APPDATA") or "").expanduser()
        localappdata = Path(os.getenv("LOCALAPPDATA") or "").expanduser()
        home = Path.home()
        documents = home / "Documents"
        # JianyingPro / CapCut 常见项目目录
        for base, brand in [
            (appdata, "JianyingPro"),
            (localappdata, "JianyingPro"),
            (appdata, "CapCut"),
            (localappdata, "CapCut"),
        ]:
            if str(base):
                items.append(base / brand / "User Data" / "Projects")
                items.append(base / brand / "userdata" / "projects")
        # Documents 中的常见目录
        items.append(documents / "JianyingPro" / "Projects")
        items.append(documents / "CapCut" / "Projects")
        items.append(documents / "CapCut Projects")
        # 其他常见目录
        items.append(home / "Videos" / "CapCut")
        items.append(home / "Videos" / "JianyingPro")
        return items

    def _candidate_paths_macos(self) -> List[Path]:
        items: List[Path] = []
        home = Path.home()
        app_support = home / "Library" / "Application Support"
        # JianyingPro / CapCut
        for brand in ["JianyingPro", "CapCut"]:
            items.append(app_support / brand / "User Data" / "Projects")
            items.append(app_support / brand / "userdata" / "projects")
        # Movies / Documents 可能的目录
        items.append(home / "Movies" / "CapCut Projects")
        items.append(home / "Movies" / "CapCut")
        items.append(home / "Documents" / "CapCut")
        items.append(home / "Documents" / "JianyingPro")
        return items

    def auto_detect_draft_paths(self) -> List[str]:
        try:
            is_windows = os.name == "nt"
            candidates = self._candidate_paths_windows() if is_windows else self._candidate_paths_macos()
            found: List[str] = []
            for c in candidates:
                try:
                    if c.exists() and c.is_dir():
                        # 简单有效性检测：如果里面存在较多子目录/文件视为可能的草稿目录
                        try:
                            entries = list(c.iterdir())
                            if len(entries) >= 1:
                                found.append(str(c))
                        except Exception:
                            found.append(str(c))
                except Exception:
                    continue
            # 去重，保持顺序
            seen = set()
            uniq: List[str] = []
            for s in found:
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
            return uniq
        except Exception as e:
            logger.error(f"自动查找剪映草稿路径失败: {e}")
            return []

    def ensure_default_draft_path(self) -> Optional[str]:
        try:
            if self.config.drafts_dir:
                return self.config.drafts_dir
            found = self.auto_detect_draft_paths()
            if found:
                self.config.drafts_dir = found[0]
                self.save()
                logger.info(f"已自动设置剪映草稿默认路径: {self.config.drafts_dir}")
                return self.config.drafts_dir
            return None
        except Exception as e:
            logger.error(f"设置默认剪映草稿路径失败: {e}")
            return None


# 全局实例
jianying_config_manager = JianyingConfigManager()

