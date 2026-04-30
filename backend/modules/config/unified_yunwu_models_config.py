#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聚合模型平台配置：支持多个平台（如 yunwu、rightCodes 等），每个平台有三档（low / medium / high），
每档可独立配置 Key 与分角色模型名。

用户只需选择平台 + 输入 API Key，base_url / 模型名等可由远程接口下发，也可本地配置。

远程同步：每 1 小时从上游 /api/model-platforms 拉取平台与模型组合数据，合并到本地配置。
- FORCE_REMOTE_SYNC=True 时每次 load() 都请求远程。
- 请求失败则沿用本地/缓存配置。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_YUNWU_CHAT_URL = "https://yunwu.ai/v1/chat/completions"

TierKey = Union[str, None]
ALLOWED_TIERS = {"low", "medium", "high"}
DEFAULT_TIER = "high"

FORCE_REMOTE_SYNC: bool = False
_REMOTE_SYNC_PATH: str = "/api/model-platforms"
_REMOTE_SYNC_CACHE_SECONDS: float = 3600.0

_remote_sync_lock = asyncio.Lock()


def _beijing_now() -> datetime:
    """返回北京时间（UTC+8）的当前时间。"""
    return datetime.now(timezone(timedelta(hours=8)))


# ---------- 单档模型配置 ----------

class YunwuTierSettings(BaseModel):
    """单档聚合模型配置（low / medium / high）。"""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    api_key: str = Field("", description="API Key（该档位）")
    base_url: str = Field(DEFAULT_YUNWU_CHAT_URL, description="Chat Completions 地址")
    copywriting_model_name: str = Field(
        "deepseek-v4-flash",
        description="文案生成 / 参考文案清洗等",
    )
    video_analysis_model_name: str = Field(
        "gemini-2.5-flash-lite",
        description="在线视频帧 / 多模态视觉理解",
    )
    llm_rerank_model_name: str = Field(
        "deepseek-v4-flash",
        description="Omni 镜头 LLM 精排",
    )
    script_generation_model_name: str = Field(
        "deepseek-v4-flash",
        description="脚本 JSON / 分镜脚本等",
    )

    @field_validator("base_url")
    @classmethod
    def _strip_base(cls, v: str) -> str:
        s = (v or "").strip().strip("`")
        return s or DEFAULT_YUNWU_CHAT_URL

    @field_validator(
        "copywriting_model_name",
        "video_analysis_model_name",
        "llm_rerank_model_name",
        "script_generation_model_name",
    )
    @classmethod
    def _strip_model(cls, v: str) -> str:
        s = (v or "").strip().strip("`")
        if not s:
            raise ValueError("模型名称不能为空")
        return s


def _default_yunwu_tiers() -> Dict[str, YunwuTierSettings]:
    return {
        "low": YunwuTierSettings(),
        "medium": YunwuTierSettings(),
        "high": YunwuTierSettings(),
    }


# ---------- 单平台配置 ----------

class PlatformSettings(BaseModel):
    """单个聚合平台的配置。"""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    display_name: str = Field("", description="平台显示名称")
    office_web: str = Field("", description="平台官网地址")
    tiers: Dict[str, YunwuTierSettings] = Field(
        default_factory=_default_yunwu_tiers,
        description="low / medium / high 三档配置",
    )

    @field_validator("tiers")
    @classmethod
    def _ensure_tiers(cls, v: Any) -> Dict[str, YunwuTierSettings]:
        """确保 low/medium/high 始终存在。"""
        if not isinstance(v, dict):
            return _default_yunwu_tiers()
        out: Dict[str, YunwuTierSettings] = {}
        for tk in ALLOWED_TIERS:
            raw = v.get(tk)
            try:
                if raw is None:
                    out[tk] = YunwuTierSettings()
                else:
                    out[tk] = YunwuTierSettings.model_validate(raw)
            except Exception:
                out[tk] = YunwuTierSettings()
        return out

    def tier_or_default(self, tier: TierKey) -> YunwuTierSettings:
        """获取指定档位配置；非法或缺少时回退到 high。"""
        t = str(tier or "").strip().lower()
        if t not in ALLOWED_TIERS:
            t = DEFAULT_TIER
        if t not in self.tiers:
            return YunwuTierSettings()
        return self.tiers[t]


# ---------- 默认平台 ----------

def _default_platforms() -> Dict[str, PlatformSettings]:
    return {
        "yunwu": PlatformSettings(
            display_name="云雾",
            office_web="https://yunwu.apifox.cn",
            tiers=_default_yunwu_tiers(),
        ),
        "rightCodes": PlatformSettings(
            display_name="RightCodes",
            office_web="https://rightcodes.ai",
            tiers={
                "low": YunwuTierSettings(
                    base_url="https://rightcodes.ai/v1/chat/completions",
                    copywriting_model_name="gemini-2.5-flash",
                    video_analysis_model_name="gemini-2.5-flash",
                    llm_rerank_model_name="gemini-2.5-flash",
                    script_generation_model_name="gemini-2.5-flash",
                ),
                "medium": YunwuTierSettings(
                    base_url="https://rightcodes.ai/v1/chat/completions",
                    copywriting_model_name="gemini-2.5-pro",
                    video_analysis_model_name="gemini-2.5-flash",
                    llm_rerank_model_name="gemini-2.5-flash",
                    script_generation_model_name="gemini-2.5-pro",
                ),
                "high": YunwuTierSettings(
                    base_url="https://rightcodes.ai/v1/chat/completions",
                    copywriting_model_name="gemini-3.1-pro-preview",
                    video_analysis_model_name="gemini-2.5-pro",
                    llm_rerank_model_name="gemini-2.5-flash",
                    script_generation_model_name="gpt-5.2-high",
                ),
            },
        ),
    }


# ---------- 根配置 ----------

class UnifiedYunwuModelsRoot(BaseModel):
    """多平台聚合根配置。"""

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    use_custom_models: bool = Field(
        True,
        description="为 True 时文案/视频等仍走原 content_model / video_model；为 False 时走聚合按档位",
    )
    active_platform: str = Field(
        "yunwu",
        description="当前激活的聚合平台标识",
    )
    platforms: Dict[str, PlatformSettings] = Field(
        default_factory=_default_platforms,
        description="所有可用聚合平台",
    )
    last_remote_sync_time: Optional[str] = Field(
        default=None,
        description="上次远程同步时间（ISO 8601 / 北京时间字符串）",
    )

    def get_active_platform(self) -> PlatformSettings:
        """获取当前激活平台的配置；若不存在则回退到第一个可用平台。"""
        key = (self.active_platform or "").strip()
        if key and key in self.platforms:
            return self.platforms[key]
        if self.platforms:
            first_key = next(iter(self.platforms))
            return self.platforms[first_key]
        return PlatformSettings()

    def tier_or_default(self, tier: TierKey) -> YunwuTierSettings:
        """获取激活平台的指定档位配置。"""
        return self.get_active_platform().tier_or_default(tier)

    def needs_remote_sync(self, cache_seconds: float = _REMOTE_SYNC_CACHE_SECONDS) -> bool:
        """基于北京时间判断是否需要再次远程同步。"""
        if FORCE_REMOTE_SYNC:
            return True
        if not self.last_remote_sync_time:
            return True
        try:
            last_sync = datetime.fromisoformat(self.last_remote_sync_time)
            elapsed = (_beijing_now() - last_sync).total_seconds()
            return elapsed >= cache_seconds
        except Exception:
            return True

    def mark_remote_synced(self) -> None:
        """记录本次同步成功时间为当前北京时间。"""
        now = _beijing_now().replace(microsecond=0)
        self.last_remote_sync_time = now.isoformat()

    @field_validator("platforms")
    @classmethod
    def _ensure_platforms(cls, v: Any) -> Dict[str, PlatformSettings]:
        """校验各平台配置合法性；仅在完全没有平台时回退到默认。"""
        if not isinstance(v, dict) or not v:
            return _default_platforms()
        out: Dict[str, PlatformSettings] = {}
        for k, raw in v.items():
            try:
                if isinstance(raw, PlatformSettings):
                    out[k] = raw
                else:
                    out[k] = PlatformSettings.model_validate(raw)
            except Exception:
                out[k] = PlatformSettings()
        return out

    # ---------- 旧版兼容属性 ----------

    @property
    def yunwu(self) -> Dict[str, YunwuTierSettings]:
        """兼容旧代码：返回激活平台的三档配置。"""
        return self.get_active_platform().tiers


# ---------- 远程数据转换 ----------

def _transform_remote_data(
    remote_data: Dict[str, Any],
    existing_root: UnifiedYunwuModelsRoot,
) -> UnifiedYunwuModelsRoot:
    """将远程 /api/model-platforms 返回的数据直接覆盖本地配置。

    远程数据作为唯一数据源，完全替换本地平台列表；
    仅保留本地已有的 api_key（用户输入的密钥）。
    """
    data = remote_data.get("data") if isinstance(remote_data, dict) else None
    if isinstance(data, list):
        remote_list: List[Dict[str, Any]] = data
    elif isinstance(data, dict):
        remote_list = data.get("list") or []
    else:
        logger.warning("远程模型平台数据格式异常，跳过覆盖")
        return existing_root

    if not isinstance(remote_list, list):
        return existing_root

    # 提取本地各平台各档位的 api_key，供覆盖后保留
    existing_keys: Dict[str, Dict[str, str]] = {}
    for pk, pv in existing_root.platforms.items():
        existing_keys[pk] = {tk: tv.api_key for tk, tv in pv.tiers.items()}

    new_platforms: Dict[str, PlatformSettings] = {}

    for remote_plat in remote_list:
        if not isinstance(remote_plat, dict):
            continue
        name = (remote_plat.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        base_url = (remote_plat.get("baseUrl") or "").strip().strip("`") or DEFAULT_YUNWU_CHAT_URL
        office_web = (remote_plat.get("officialWebsite") or "").strip()
        display_name = remote_plat.get("displayName") or name

        preserved_keys = existing_keys.get(key, {})

        combinations: List[Dict[str, Any]] = remote_plat.get("combinations") or []
        if not isinstance(combinations, list):
            combinations = []

        # 以 base_url 填充默认档位，后续用远程 combinations 覆盖
        tiers: Dict[str, YunwuTierSettings] = {}
        for tk in ALLOWED_TIERS:
            tiers[tk] = YunwuTierSettings(
                api_key=preserved_keys.get(tk, ""),
                base_url=base_url,
            )

        for combo in combinations:
            if not isinstance(combo, dict):
                continue
            level = (combo.get("level") or "").strip().lower()
            if level not in ALLOWED_TIERS:
                continue
            tiers[level] = YunwuTierSettings(
                api_key=preserved_keys.get(level, ""),
                base_url=base_url,
                copywriting_model_name=(combo.get("copywritingModelName") or "deepseek-v4-flash").strip(),
                video_analysis_model_name=(combo.get("videoAnalysisModelName") or "gemini-2.5-flash-lite").strip(),
                llm_rerank_model_name=(combo.get("llmRerankModelName") or "deepseek-v4-flash").strip(),
                script_generation_model_name=(combo.get("scriptGenerationModelName") or "deepseek-v4-flash").strip(),
            )

        new_platforms[key] = PlatformSettings(
            display_name=display_name,
            office_web=office_web,
            tiers=tiers,
        )

    if not new_platforms:
        logger.warning("远程数据中无有效平台，沿用本地配置")
        return existing_root

    # 若当前激活平台在覆盖后不存在，自动切换到第一个可用平台
    active = existing_root.active_platform
    if active and active not in new_platforms:
        fallback = next(iter(new_platforms))
        logger.info("激活平台 '%s' 在远程数据中不存在，切换到 '%s'", active, fallback)
        active = fallback

    return UnifiedYunwuModelsRoot(
        use_custom_models=existing_root.use_custom_models,
        active_platform=active,
        platforms=new_platforms,
    )


# ---------- 管理器 ----------

class UnifiedYunwuModelsConfigManager:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        if config_file is None:
            from ..app_paths import user_config_dir
            config_file = user_config_dir() / "unified_yunwu_models_config.json"
        self.config_file = Path(config_file)
        self._root: UnifiedYunwuModelsRoot = UnifiedYunwuModelsRoot()
        self._sync_guard: Optional[asyncio.Task] = None
        self.load()

    def load(self) -> None:
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    raw: Dict[str, Any] = json.load(f)
                # ---- 兼容旧版：顶层 yunwu 平面/三档 → 迁移为 platforms.yunwu ----
                y = raw.get("yunwu")
                if isinstance(y, dict) and "platforms" not in raw:
                    has_tiers = any(k in y for k in ALLOWED_TIERS)
                    if has_tiers:
                        raw["platforms"] = {
                            "yunwu": {
                                "display_name": "云雾",
                                "office_web": "https://yunwu.apifox.cn",
                                "tiers": y,
                            }
                        }
                    else:
                        raw["platforms"] = {
                            "yunwu": {
                                "display_name": "云雾",
                                "office_web": "https://yunwu.apifox.cn",
                                "tiers": {"low": {}, "medium": {}, "high": y},
                            }
                        }
                    raw.pop("yunwu", None)
                    if "active_platform" not in raw:
                        raw["active_platform"] = "yunwu"
                self._root = UnifiedYunwuModelsRoot.model_validate(raw)
                logger.info("已加载聚合模型配置（多平台，三层档位）")
            else:
                self._root = UnifiedYunwuModelsRoot()
                self.save()
        except Exception as e:
            logger.error("加载聚合模型配置失败，使用默认: %s", e)
            self._root = UnifiedYunwuModelsRoot()

    async def ensure_remote_synced(self, authorization: Optional[str] = None) -> None:
        """确保远程数据已同步。会在首次调用时触发同步并等待完成。

        路由层在 get_root() 之前调用此方法，避免拿到 fire-and-forget 任务还没完成时的旧数据。
        后续调用受缓存时间控制（FORCE_REMOTE_SYNC=True 时跳过缓存）。
        """
        if self._sync_guard is not None and not self._sync_guard.done():
            await self._sync_guard
            return

        if not self._root.needs_remote_sync():
            return

        async with _remote_sync_lock:
            if not self._root.needs_remote_sync():
                return

            if self._sync_guard is not None and not self._sync_guard.done():
                await self._sync_guard
                return

            async def _do_sync() -> None:
                try:
                    from modules.auth.auth_upstream import fetch_upstream_json

                    remote_data = await fetch_upstream_json(_REMOTE_SYNC_PATH, authorization)
                    if remote_data is None:
                        logger.warning("远程模型平台数据获取失败，沿用本地配置")
                        return

                    code = remote_data.get("code")
                    if code != 0:
                        logger.warning("远程模型平台接口返回 code=%s，沿用本地配置", code)
                        return

                    new_root = _transform_remote_data(remote_data, self._root)
                    new_root.mark_remote_synced()
                    self._root = new_root
                    self.save()
                    active = new_root.active_platform
                    total_platforms = len(new_root.platforms)
                    logger.info(
                        "远程模型平台配置已同步（%d 个平台，当前激活: %s）",
                        total_platforms,
                        active,
                    )
                except Exception as e:
                    logger.error("远程同步模型平台配置失败: %s", e)
                finally:
                    self._sync_guard = None

            self._sync_guard = asyncio.ensure_future(_do_sync())
            await self._sync_guard

    async def force_sync_remote(self, authorization: Optional[str] = None) -> bool:
        """强制跳过缓存，立即执行一次远程同步。返回是否成功。"""
        if self._sync_guard is not None and not self._sync_guard.done():
            await self._sync_guard
        async with _remote_sync_lock:
            if self._sync_guard is not None and not self._sync_guard.done():
                await self._sync_guard
                return True

            async def _do_sync() -> bool:
                ok = False
                try:
                    from modules.auth.auth_upstream import fetch_upstream_json

                    remote_data = await fetch_upstream_json(_REMOTE_SYNC_PATH, authorization)
                    if remote_data is None:
                        logger.warning("远程模型平台数据获取失败，沿用本地配置")
                        return False

                    code = remote_data.get("code")
                    if code != 0:
                        logger.warning("远程模型平台接口返回 code=%s，沿用本地配置", code)
                        return False

                    new_root = _transform_remote_data(remote_data, self._root)
                    new_root.mark_remote_synced()
                    self._root = new_root
                    self.save()
                    ok = True
                    logger.info(
                        "远程模型平台配置已强制同步（%d 个平台，当前激活: %s）",
                        len(new_root.platforms),
                        new_root.active_platform,
                    )
                except Exception as e:
                    logger.error("强制远程同步模型平台配置失败: %s", e)
                finally:
                    self._sync_guard = None
                return ok

            self._sync_guard = asyncio.ensure_future(_do_sync())
            return await self._sync_guard

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._root.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info("聚合模型配置已保存")

    def get_root(self) -> UnifiedYunwuModelsRoot:
        return self._root

    def update_root(self, root: UnifiedYunwuModelsRoot) -> None:
        self._root = root
        self.save()


unified_yunwu_models_config_manager = UnifiedYunwuModelsConfigManager()
