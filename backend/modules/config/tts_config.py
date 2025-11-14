#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS引擎配置管理模块
支持动态配置TTS引擎参数、音色选择与语速调节，当前内置腾讯云TTS。
"""

import json
from pathlib import Path
from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)


class TtsVoice(BaseModel):
    """TTS音色信息"""
    id: str = Field(..., description="音色ID（如Cherry）")
    name: str = Field(..., description="音色名称（中文展示）")
    description: Optional[str] = Field(None, description="音色描述")
    sample_wav_url: Optional[str] = Field(None, description="试听音频地址（wav）")
    language: Optional[str] = Field(None, description="语言标识，如zh-CN")
    gender: Optional[str] = Field(None, description="性别，如male/female")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签")
    voice_type: Optional[int] = Field(None, description="腾讯云TTS VoiceType")
    category: Optional[str] = Field(None, description="分类名称")


class TtsEngineConfig(BaseModel):
    """TTS引擎配置数据模型"""
    provider: str = Field(..., description="TTS提供商标识，如tencent_tts")
    secret_id: Optional[str] = Field(None, description="腾讯云SecretId")
    secret_key: Optional[str] = Field(None, description="腾讯云SecretKey")
    region: Optional[str] = Field("ap-guangzhou", description="区域标识")
    description: Optional[str] = Field(None, description="配置说明")
    enabled: bool = Field(False, description="是否启用（同一时间仅一个启用）")
    active_voice_id: Optional[str] = Field(None, description="当前激活的音色ID")
    speed_ratio: float = Field(1.0, description="语速倍率", ge=0.5, le=2.0)
    extra_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="扩展参数")

    @validator('provider')
    def validate_provider(cls, v):
        allowed = ['tencent_tts']  # 可扩展其他引擎，如index_tts2
        if v.lower() not in allowed:
            raise ValueError(f'提供商必须是以下之一: {allowed}')
        return v.lower()


class TtsEngineConfigManager:
    """TTS引擎配置管理器"""

    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            backend_dir = Path(__file__).parent.parent.parent
            config_dir = backend_dir / "config"
            config_dir.mkdir(exist_ok=True)
            config_file = config_dir / "tts_config.json"

        self.config_file = Path(config_file)
        self.configs: Dict[str, TtsEngineConfig] = {}

        self._voices_cache: Dict[str, List[TtsVoice]] = {}

        # 预加载配置
        self.load_configs()

    def load_configs(self):
        """从文件加载配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                configs_data = data.get('configs', {})
                for config_id, config_data in configs_data.items():
                    try:
                        self.configs[config_id] = TtsEngineConfig(**config_data)
                    except Exception as e:
                        logger.error(f"加载TTS引擎配置 {config_id} 失败: {e}")

                logger.info(f"成功加载 {len(self.configs)} 个TTS引擎配置")
            else:
                self._create_default_configs()

        except Exception as e:
            logger.error(f"加载TTS引擎配置失败: {e}")
            self._create_default_configs()

    def save_configs(self):
        """保存配置到文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            data = {'configs': {}}
            for config_id, config in self.configs.items():
                data['configs'][config_id] = config.dict(exclude={'secret_id', 'secret_key'})
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("TTS引擎配置保存成功")
        except Exception as e:
            logger.error(f"保存TTS引擎配置失败: {e}")
            raise

    def _create_default_configs(self):
        """创建默认配置：腾讯云TTS（未启用）"""
        default = {
            'id': 'tencent_tts_default',
            'config': TtsEngineConfig(
                provider='tencent_tts',
                secret_id=None,
                secret_key=None,
                region='ap-guangzhou',
                description='腾讯云 TTS 默认配置',
                enabled=False,
                active_voice_id="502007",
                speed_ratio=1.0,
                extra_params={"Volume": 10}
            )
        }
        self.configs[default['id']] = default['config']
        self.save_configs()

    def update_config(self, config_id: str, config: TtsEngineConfig) -> bool:
        """更新配置，确保同时只有一个配置被启用"""
        try:
            if config_id not in self.configs:
                raise ValueError(f"配置ID '{config_id}' 不存在")

            # 若启用该配置，则禁用其他配置
            if config.enabled:
                for other_id, other_config in self.configs.items():
                    if other_id != config_id and other_config.enabled:
                        self.configs[other_id] = other_config.copy(update={'enabled': False})
                        logger.info(f"自动禁用配置: {other_id}")

            self.configs[config_id] = config
            self.save_configs()
            logger.info(f"更新TTS引擎配置成功: {config_id}")
            return True
        except Exception as e:
            logger.error(f"更新TTS引擎配置失败: {e}")
            return False

    def get_config(self, config_id: str) -> Optional[TtsEngineConfig]:
        return self.configs.get(config_id)

    def get_all_configs(self) -> Dict[str, TtsEngineConfig]:
        return self.configs.copy()

    def get_active_config(self) -> Optional[TtsEngineConfig]:
        for config in self.configs.values():
            if config.enabled:
                return config
        return None

    def get_active_config_id(self) -> Optional[str]:
        for config_id, config in self.configs.items():
            if config.enabled:
                return config_id
        return None

    def get_engines_meta(self) -> List[Dict[str, Any]]:
        """返回可用引擎元信息列表"""
        return [
            {
                'provider': 'tencent_tts',
                'display_name': '腾讯云 TTS',
                'description': '支持多种中文方言与风格，需配置SecretId与SecretKey',
                'required_fields': ['secret_id', 'secret_key'],
                'optional_fields': ['region']
            }
        ]

    def get_voices(self, provider: str) -> List[TtsVoice]:
        """获取指定提供商的音色列表"""
        provider = provider.lower()
        if provider != 'tencent_tts':
            return []
        if provider in self._voices_cache:
            return self._voices_cache[provider]
        voices: List[TtsVoice] = []
        try:
            backend_dir = Path(__file__).parent.parent.parent
            data_path = backend_dir / "serviceData" / "tencent_tts_data.json"
            if data_path.exists():
                with open(data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for category in data:
                    category_name = category.get("CategoryName")
                    for item in category.get("VoiceList", []):
                        vt = item.get("VoiceType")
                        vtags = item.get("VoiceTypeTag") or ""
                        tags = [t.strip() for t in vtags.split(",") if t.strip()]
                        if category_name:
                            tags = [category_name] + tags
                        voices.append(
                            TtsVoice(
                                id=str(vt) if vt is not None else (item.get("VoiceName") or ""),
                                name=item.get("VoiceName") or "",
                                description=item.get("VoiceDesc") or None,
                                sample_wav_url=item.get("VoiceAudio") or None,
                                language=None,
                                gender=item.get("VoiceGender") or None,
                                tags=tags,
                                voice_type=vt if isinstance(vt, int) else None,
                                category=category_name,
                            )
                        )
            else:
                voices = []
        except Exception as e:
            logger.error(f"加载腾讯TTS音色列表失败: {e}")
            voices = []
        self._voices_cache[provider] = voices
        return voices

    async def test_connection(self, config_id: str) -> Dict[str, Any]:
        """测试指定配置的连通性：调用腾讯云 TTS TextToVoice 进行鉴权校验"""
        config = self.get_config(config_id)
        if not config:
            return {"success": False, "config_id": config_id, "error": f"配置 '{config_id}' 不存在"}

        import os
        secret_id = (os.getenv("TENCENTCLOUD_SECRET_ID") or (config.secret_id or "")).strip()
        secret_key = (os.getenv("TENCENTCLOUD_SECRET_KEY") or (config.secret_key or "")).strip()
        if not (secret_id and secret_key):
            return {
                "success": False,
                "config_id": config_id,
                "provider": (config.provider if config else "tencent_tts"),
                "message": "缺少SecretId或SecretKey"
            }

        # 动态导入腾讯云 SDK，避免在未安装时模块加载失败
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
            from tencentcloud.tts.v20190823 import tts_client, models
        except Exception as import_err:
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "message": f"未安装腾讯云SDK: {import_err}. 请安装 'tencentcloud-sdk-python'",
                "error": str(import_err)
            }

        # 构造客户端并发起一次最小化的合成请求来校验鉴权
        try:
            cred = credential.Credential(secret_id, secret_key)
            httpProfile = HttpProfile()
            httpProfile.endpoint = "tts.tencentcloudapi.com"

            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile

            region = config.region or ""
            client = tts_client.TtsClient(cred, region, clientProfile)

            req = models.TextToVoiceRequest()
            import json, uuid
            params = {
                "Text": "你好，腾讯云 TTS 连通性测试。",
                "SessionId": f"{uuid.uuid4()}",
                # 选择轻量返回格式，减少响应体体积
                "SampleRate": 16000,
                "Codec": "mp3",
                "EnableSubtitle": False
            }
            req.from_json_string(json.dumps(params))

            # 仅需成功返回即可判定鉴权有效；不向前端返回音频数据
            resp = client.TextToVoice(req)
            # SDK会抛异常处理错误，这里成功即视为鉴权成功
            return {
                "success": True,
                "config_id": config_id,
                "provider": config.provider,
                "message": "凭据有效",
                "request_id": getattr(resp, "RequestId", None)
            }
        except TencentCloudSDKException as err:
            # 腾讯云SDK异常（包括鉴权失败等）
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "message": str(err),
                "error": getattr(err, "message", str(err))
            }
        except Exception as e:
            # 其他未知错误
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "message": "测试请求失败",
                "error": str(e)
            }


# 全局TTS引擎配置管理器实例
tts_engine_config_manager = TtsEngineConfigManager()
