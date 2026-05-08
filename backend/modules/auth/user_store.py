#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户数据存储（文件型）
使用JSON文件进行轻量级持久化，与项目存储模块风格保持一致。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from threading import RLock

import bcrypt
from pydantic import BaseModel, Field

from modules.app_paths import user_data_dir

import logging

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


class User(BaseModel):
    id: int
    email: str
    password_hash: str
    status: str = Field(default="active")  # active | disabled
    created_at: str
    updated_at: str


class UserStore:
    """基于JSON文件的用户存储管理器"""

    def __init__(self, db_path: Optional[Path] = None):
        data_dir = user_data_dir()
        self.db_path = db_path or (data_dir / "users.json")
        self._lock = RLock()
        self._users: Dict[int, User] = {}
        self._next_id: int = 1
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.db_path.exists():
                try:
                    raw = self.db_path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    self._next_id = data.get("_next_id", 1)
                    for uid_str, u in data.get("users", {}).items():
                        try:
                            user = User(**u)
                            self._users[user.id] = user
                        except Exception as e:
                            logger.warning(f"用户数据解析失败（跳过）: {uid_str} - {e}")
                except Exception as e:
                    logger.error(f"加载用户数据失败: {e}")
            else:
                self._persist()

    def _persist(self) -> None:
        with self._lock:
            try:
                serializable = {
                    "_next_id": self._next_id,
                    "users": {str(uid): u.model_dump() for uid, u in self._users.items()},
                }
                self.db_path.write_text(
                    json.dumps(serializable, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error(f"保存用户数据失败: {e}")

    def get_by_email(self, email: str) -> Optional[User]:
        with self._lock:
            email_lower = email.strip().lower()
            for u in self._users.values():
                if u.email.lower() == email_lower:
                    return u
            return None

    def get_by_id(self, user_id: int) -> Optional[User]:
        with self._lock:
            return self._users.get(user_id)

    def create_user(self, email: str, password: str) -> User:
        with self._lock:
            if self.get_by_email(email):
                raise ValueError("邮箱已注册")
            now = datetime.now().isoformat()
            user = User(
                id=self._next_id,
                email=email.strip().lower(),
                password_hash=_hash_password(password),
                status="active",
                created_at=now,
                updated_at=now,
            )
            self._users[user.id] = user
            self._next_id += 1
            self._persist()
            return user

    def verify_password(self, user: User, password: str) -> bool:
        return _verify_password(password, user.password_hash)

    def update_password(self, user_id: int, new_password: str) -> Optional[User]:
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return None
            user.password_hash = _hash_password(new_password)
            user.updated_at = datetime.now().isoformat()
            self._persist()
            return user


# 单例
user_store = UserStore()
