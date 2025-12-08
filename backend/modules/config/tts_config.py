# -*- coding: utf-8 -*-
"""
TTS引擎配置管理模块
支持动态配置TTS引擎参数、音色选择与语速调节，当前内置腾讯云TTS。
"""

import json
import os
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
    voice_quality: Optional[str] = Field(None, description="音色质量级别")
    voice_type_tag: Optional[str] = Field(None, description="类型标签原文")
    voice_human_style: Optional[str] = Field(None, description="风格描述原文")


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
        allowed = ['tencent_tts', 'edge_tts']
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

                # 前向兼容：若现有文件缺少默认配置，则补充写入
                missing_defaults = []
                if 'tencent_tts_default' not in self.configs:
                    self.configs['tencent_tts_default'] = TtsEngineConfig(
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
                    missing_defaults.append('tencent_tts_default')

                if 'edge_tts_default' not in self.configs:
                    self.configs['edge_tts_default'] = TtsEngineConfig(
                        provider='edge_tts',
                        secret_id=None,
                        secret_key=None,
                        region=None,
                        description='Edge TTS 默认配置（无需凭据）',
                        enabled=False,
                        active_voice_id=None,
                        speed_ratio=1.0,
                        extra_params={}
                    )
                    missing_defaults.append('edge_tts_default')

                if missing_defaults:
                    self.save_configs()
                    logger.info(f"已补充默认TTS配置: {', '.join(missing_defaults)}")
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
                # 持久化保存所有字段（包括 secret_id 与 secret_key）到配置文件
                # 接口返回时仍通过路由层进行脱敏展示
                data['configs'][config_id] = config.dict()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("TTS引擎配置保存成功")
        except Exception as e:
            logger.error(f"保存TTS引擎配置失败: {e}")
            raise

    def _create_default_configs(self):
        """创建默认配置：腾讯云TTS与Edge TTS（均未启用）"""
        defaults = [
            (
                'tencent_tts_default',
                TtsEngineConfig(
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
            ),
            (
                'edge_tts_default',
                TtsEngineConfig(
                    provider='edge_tts',
                    secret_id=None,
                    secret_key=None,
                    region=None,
                    description='Edge TTS 默认配置（无需凭据）',
                    enabled=False,
                    active_voice_id=None,
                    speed_ratio=1.0,
                    extra_params={}
                )
            )
        ]
        for cid, cfg in defaults:
            self.configs[cid] = cfg
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
            },
            {
                'provider': 'edge_tts',
                'display_name': 'Edge TTS',
                'description': '微软 Edge 在线语音，免凭据，适合中文合成测试与预览',
                'required_fields': [],
                'optional_fields': []
            }
        ]

    def get_voices(self, provider: str) -> List[TtsVoice]:
        """获取指定提供商的音色列表"""
        provider = provider.lower()
        if provider in self._voices_cache:
            cached = self._voices_cache[provider]
            # 仅保留 Edge TTS 的中文音色
            if provider == 'edge_tts':
                filtered = [v for v in cached if isinstance(v.language, str) and v.language.lower().startswith('zh') or (isinstance(v.id, str) and v.id.lower().startswith('zh-'))]
                self._voices_cache[provider] = filtered
                return filtered
            return cached

        voices: List[TtsVoice] = []
        try:
            if provider == 'tencent_tts':
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
                                    voice_quality=(item.get("VoiceQuality") or None),
                                    voice_type_tag=(item.get("VoiceTypeTag") or None),
                                    voice_human_style=(item.get("VoiceHumanStyle") or None),
                                )
                            )
                else:
                    voices = []
            elif provider == 'edge_tts':
                # 避免在事件循环中同步调用异步函数，这里优先读取缓存文件，若无缓存则提供中文音色的回退列表
                backend_dir = Path(__file__).parent.parent.parent
                cache_path = backend_dir / "serviceData" / "tts" / "edge_voices_cache.json"
                raw_list = []
                if cache_path.exists():
                    try:
                        cache_data = json.loads(cache_path.read_text("utf-8"))
                        if isinstance(cache_data, dict) and isinstance(cache_data.get("voices"), list):
                            raw_list = cache_data["voices"]
                    except Exception as e:
                        logger.error(f"读取 Edge TTS 音色缓存失败: {e}")

                # 若缓存为空，提供常用中文音色的回退条目，确保前端可用
                if not raw_list:
                    raw_list = [
                        {
                            "id": "zh-CN-XiaoxiaoNeural",
                            "name": "Xiaoxiao",
                            "description": "Xiaoxiao（zh-CN）",
                            "language": "zh-CN",
                            "gender": "Female",
                            "voice_quality": "Neural",
                            "voice_type_tag": "edge",
                            "voice_human_style": None,
                            "tags": ["general"],
                            "sample_wav_url": None,
                        },
                        {
                            "id": "zh-CN-YunxiNeural",
                            "name": "Yunxi",
                            "description": "Yunxi（zh-CN）",
                            "language": "zh-CN",
                            "gender": "Male",
                            "voice_quality": "Neural",
                            "voice_type_tag": "edge",
                            "voice_human_style": None,
                            "tags": ["general"],
                            "sample_wav_url": None,
                        },
                        {
                            "id": "zh-CN-YunjianNeural",
                            "name": "Yunjian",
                            "description": "Yunjian（zh-CN）",
                            "language": "zh-CN",
                            "gender": "Male",
                            "voice_quality": "Neural",
                            "voice_type_tag": "edge",
                            "voice_human_style": None,
                            "tags": ["narration"],
                            "sample_wav_url": None,
                        },
                        {
                            "id": "zh-CN-XiaohanNeural",
                            "name": "Xiaohan",
                            "description": "Xiaohan（zh-CN）",
                            "language": "zh-CN",
                            "gender": "Female",
                            "voice_quality": "Neural",
                            "voice_type_tag": "edge",
                            "voice_human_style": None,
                            "tags": ["narration"],
                            "sample_wav_url": None,
                        },
                        {
                            "id": "zh-CN-YunzeNeural",
                            "name": "Yunze",
                            "description": "Yunze（zh-CN）",
                            "language": "zh-CN",
                            "gender": "Male",
                            "voice_quality": "Neural",
                            "voice_type_tag": "edge",
                            "voice_human_style": None,
                            "tags": ["chat"],
                            "sample_wav_url": None,
                        },
                    ]

                # 仅保留中文（zh-*）音色
                raw_list = [it for it in raw_list if (str(it.get('language') or '')).lower().startswith('zh') or (str(it.get('id') or '')).lower().startswith('zh-')]
                for item in raw_list:
                    voices.append(TtsVoice(
                        id=str(item.get('id') or ''),
                        name=str(item.get('name') or ''),
                        description=item.get('description') or None,
                        sample_wav_url=item.get('sample_wav_url') or None,
                        language=item.get('language') or None,
                        gender=item.get('gender') or None,
                        tags=item.get('tags') or [],
                        voice_type=None,
                        category=None,
                        voice_quality=item.get('voice_quality') or None,
                        voice_type_tag=item.get('voice_type_tag') or None,
                        voice_human_style=item.get('voice_human_style') or None,
                    ))
            else:
                voices = []
        except Exception as e:
            logger.error(f"加载音色列表失败: {e}")
            voices = []
        self._voices_cache[provider] = voices
        return voices

    async def test_connection(self, config_id: str, proxy_url: Optional[str] = None) -> Dict[str, Any]:
        """测试指定配置的连通性：根据 provider 分支校验"""
        config = self.get_config(config_id)
        if not config:
            return {"success": False, "config_id": config_id, "error": f"配置 '{config_id}' 不存在"}

        if config.provider == 'edge_tts':
            try:
                from modules.edge_tts_service import edge_tts_service
                backend_dir = Path(__file__).parent.parent.parent
                out_path = backend_dir / "serviceData" / "tts" / "previews" / "edge_test_preview.mp3"
                voice_id = config.active_voice_id or "zh-CN-XiaoxiaoNeural"
                res = await edge_tts_service.synthesize(
                    text="你好，Edge TTS 连通性测试。",
                    voice_id=voice_id,
                    speed_ratio=config.speed_ratio,
                    out_path=out_path,
                    proxy_override=(proxy_url if isinstance(proxy_url, str) else None),
                )
                if res.get("success"):
                    return {
                        "success": True,
                        "config_id": config_id,
                        "provider": config.provider,
                        "message": "服务可用（免凭据）",
                        "audio_path": res.get("path"),
                        "duration": res.get("duration")
                    }
                else:
                    return {
                        "success": False,
                        "config_id": config_id,
                        "provider": config.provider,
                        "message": res.get("message") or res.get("error") or "合成失败",
                        "error": res.get("error") or res.get("message"),
                        "requires_proxy": bool(res.get("requires_proxy", False)),
                        "hint": "请设置 EDGE_TTS_PROXY 或在配置 extra_params.ProxyUrl 指定代理地址，例如 http://127.0.0.1:7897 或 socks5://127.0.0.1:7897"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "config_id": config_id,
                    "provider": config.provider,
                    "message": "Edge TTS 测试失败",
                    "error": str(e),
                    "hint": "请设置 EDGE_TTS_PROXY 或在配置 extra_params.ProxyUrl 指定代理地址，例如 http://127.0.0.1:7897 或 socks5://127.0.0.1:7897"
                }

        # 默认走腾讯云 TTS 鉴权校验
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
                "SampleRate": 16000,
                "Codec": "mp3",
                "EnableSubtitle": False
            }
            req.from_json_string(json.dumps(params))

            resp = client.TextToVoice(req)
            return {
                "success": True,
                "config_id": config_id,
                "provider": config.provider,
                "message": "凭据有效",
                "request_id": getattr(resp, "RequestId", None)
            }
        except TencentCloudSDKException as err:
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "message": str(err),
                "error": getattr(err, "message", str(err))
            }
        except Exception as e:
            return {
                "success": False,
                "config_id": config_id,
                "provider": config.provider,
                "message": "测试请求失败",
                "error": str(e)
            }


# 全局TTS引擎配置管理器实例
tts_engine_config_manager = TtsEngineConfigManager()
