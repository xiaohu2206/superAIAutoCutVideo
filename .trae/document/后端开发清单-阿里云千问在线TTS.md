# 后端开发清单：阿里云千问（Qwen）在线 TTS

目标：在现有后端 TTS 体系中新增一个“在线版”的千问 TTS 引擎，支持：
- 使用系统音色进行语音合成
- 使用声音复刻音色进行语音合成

参考：
- 官方文档：https://help.aliyun.com/zh/model-studio/qwen-tts#9499fdcba8g88
- 本地既有实现（需要对齐其调用方式/返回结构/并发/配置）：  
  - e:\learn\superAutoCutVideoApp\backend\modules\tts_service.py  
  - e:\learn\superAutoCutVideoApp\backend\modules\config\tts_config.py  
  - e:\learn\superAutoCutVideoApp\backend\routes\tts_routes.py  
  - e:\learn\superAutoCutVideoApp\backend\routes\qwen3_tts_routes.py  
  - e:\learn\superAutoCutVideoApp\backend\modules\qwen3_tts_model_manager.py  
  - e:\learn\superAutoCutVideoApp\backend\modules\qwen3_tts_service.py  
  - e:\learn\superAutoCutVideoApp\backend\modules\qwen3_tts_voice_store.py  
  - e:\learn\superAutoCutVideoApp\backend\services\jianying_draft_manager.py（TTS 调用点）  
  - e:\learn\superAutoCutVideoApp\backend\services\video_generation_service.py（并发 TTS 调用点）  

---

## 1. 需求与边界确认（必须先定）

- [ ] 明确“在线千问 TTS”在项目内的 provider 标识（建议：`qwen_online_tts` 或 `dashscope_qwen_tts`），并与现有 `tts_engine_config_manager` 兼容
- [ ] 明确支持的合成输出格式（建议与现有调用点一致：输出到 `out_path`，常用为 `.mp3`）
- [ ] 明确目标模型选型与默认值（建议让用户可选，后端做白名单校验）  
  - 默认模型（推荐）
    - 系统音色：`qwen3-tts-flash`（短文本高频、按字符计费，适合导航/通知、课件配音、批量有声读物）
    - 声音复刻：`qwen3-tts-vc-2026-01-22`（基于音频样本复刻音色，适合品牌声纹/拟人化一致性）
  - 可选模型池（供用户选择）
    - 声音设计（文本描述定制音色）：`qwen3-tts-vd-2026-01-26`（无需音频样本，从零设计品牌专属声音）
    - 指令控制/情感表现（自然语言指令控制语速、情绪、角色性格）：`qwen3-tts-instruct-flash`（适合有声书、广播剧、游戏/动画配音）
- [ ] 明确区域/部署模式与 API Key 使用规则  
  - 中国内地部署：接入点与数据存储在北京地域（使用北京地域 API Key）   
  - 对应 base url：`https://dashscope.aliyuncs.com/api/v1`（北京）

---

## 2. 依赖与运行环境

- [ ] 依赖方案选型（两种选一并固定）
  - [ ] 方案 A：DashScope Python SDK（文档推荐；需满足版本下限：Python SDK ≥ 1.24.6）
- [ ] 更新后端依赖清单（`backend/requirements.txt` 与/或 `requirements.runtime.txt`），并补充启动时依赖缺失的错误提示
- [ ] 约定凭据来源优先级（与现有 `tts_service.py` 一致）
  - [ ] 环境变量（建议：`DASHSCOPE_API_KEY`）优先
  - [ ] 配置文件字段兜底（见第 3 节）
- [ ] 预置 `ffprobe` 可用性要求（用于回填 duration；现有实现已依赖）

---

## 3. 配置体系接入（对齐 tts_config / tts_routes）

目标：让前端“设置页”能像切换 `edge_tts / qwen3_tts / tencent_tts` 一样切换到在线千问 TTS。

- [ ] 在 `backend/modules/config/tts_config.py` 中扩展 provider 白名单，新增在线千问 provider
- [ ] 新增默认配置项（如 `qwen_online_tts_default`），并保证旧配置文件可前向兼容自动补齐
- [ ] 配置字段映射设计（建议复用现有字段，避免大范围结构改动）
  - [ ] `secret_key`：存放 DashScope API Key（或仅使用环境变量，配置里可为空）
  - [ ] `region`：可复用为“部署模式/地域”标识（如 `cn`/`intl` 或 `ap-beijing`/`ap-singapore`）
  - [ ] `extra_params`：存放在线 TTS 专用参数（示例）
    - [ ] `BaseUrl`：覆盖 base url（可选）
    - [ ] `Model`：模型名（如 `qwen3-tts-flash`、`qwen3-tts-vc-2026-01-22`）
    - [ ] `Voice`：系统音色名（如 `Cherry`）
    - [ ] `LanguageType`：建议与文本一致（如 `Chinese`）
    - [ ] `Instructions`：指令控制（如走 `qwen3-tts-instruct-flash`）
    - [ ] `Codec`：期望保存格式（mp3/wav）与采样率策略（如 SDK/接口允许）
- [ ] 在 `backend/routes/tts_routes.py` 中：
  - [ ] `GET /api/tts/engines` 增加在线千问的引擎元信息（名称、描述、必填字段）
  - [ ] `GET /api/tts/voices?provider=...` 为在线千问返回系统音色列表（第 4 节定义来源）
  - [ ] `POST /api/tts/voices/preview`（如现有存在试听/测试入口）支持在线千问的合成试听
- [ ] 配置脱敏：确保 API Key 不会在接口返回、日志中明文输出（参考 `safe_tts_config_dict_hide_secret` 的处理方式）

---

## 使用系统音色进行语音合成-代码示例
```
import os
import dashscope

# 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：https://dashscope-intl.aliyuncs.com/api/v1
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

text = "那我来给大家推荐一款T恤，这款呢真的是超级好看，这个颜色呢很显气质，而且呢也是搭配的绝佳单品，大家可以闭眼入，真的是非常好看，对身材的包容性也很好，不管啥身材的宝宝呢，穿上去都是很好看的。推荐宝宝们下单哦。"
# SpeechSynthesizer接口使用方法：dashscope.audio.qwen_tts.SpeechSynthesizer.call(...)
response = dashscope.MultiModalConversation.call(
    # 如需使用指令控制功能，请将model替换为qwen3-tts-instruct-flash
    model="qwen3-tts-flash",
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key = "sk-xxx"
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    text=text,
    voice="Cherry",
    language_type="Chinese", # 建议与文本语种一致，以获得正确的发音和自然的语调。
    # 如需使用指令控制功能，请取消下方注释，并将model替换为qwen3-tts-instruct-flash
    # instructions='语速较快，带有明显的上扬语调，适合介绍时尚产品。',
    # optimize_instructions=True,
    stream=False
)
print(response)
```

## 使用声音复刻音色进行语音合成-代码示例
```
import os
import requests
import base64
import pathlib
import dashscope

# ======= 常量配置 =======
DEFAULT_TARGET_MODEL = "qwen3-tts-vc-2026-01-22"  # 声音复刻、语音合成要使用相同的模型
DEFAULT_PREFERRED_NAME = "guanyu"
DEFAULT_AUDIO_MIME_TYPE = "audio/mpeg"
VOICE_FILE_PATH = "voice.mp3"  # 用于声音复刻的本地音频文件的相对路径


def create_voice(file_path: str,
                 target_model: str = DEFAULT_TARGET_MODEL,
                 preferred_name: str = DEFAULT_PREFERRED_NAME,
                 audio_mime_type: str = DEFAULT_AUDIO_MIME_TYPE) -> str:
    """
    创建音色，并返回 voice 参数
    """
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key = "sk-xxx"
    api_key = os.getenv("DASHSCOPE_API_KEY")

    file_path_obj = pathlib.Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    base64_str = base64.b64encode(file_path_obj.read_bytes()).decode()
    data_uri = f"data:{audio_mime_type};base64,{base64_str}"

    # 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization
    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
    payload = {
        "model": "qwen-voice-enrollment", # 不要修改该值
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "audio": {"data": data_uri}
        }
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"创建 voice 失败: {resp.status_code}, {resp.text}")

    try:
        return resp.json()["output"]["voice"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"解析 voice 响应失败: {e}")


if __name__ == '__main__':
    # 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：https://dashscope-intl.aliyuncs.com/api/v1
    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

    text = "今天天气怎么样？"
    # SpeechSynthesizer接口使用方法：dashscope.audio.qwen_tts.SpeechSynthesizer.call(...)
    response = dashscope.MultiModalConversation.call(
        model=DEFAULT_TARGET_MODEL,
        # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
        # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key = "sk-xxx"
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        text=text,
        voice=create_voice(VOICE_FILE_PATH), # 将voice参数替换为复刻生成的专属音色
        stream=False
    )
    print(response)
```

## 4. 系统音色：数据来源与接口输出

目标：系统音色可在前端选择并用于合成。

- [ ] 系统音色列表的来源策略（两种选一）
  - [ ] 静态内置：维护一份可用音色清单（可先只做常用音色，后续扩充）
  - [ ] 动态拉取：若官方提供音色列表接口则接入；否则仍需静态兜底
- [ ] 与现有 `TtsVoice` 结构对齐（`id/name/description/language/tags` 等）
- [ ] 统一 voice_id 语义：在线千问的系统音色使用“音色名”作为 `active_voice_id`（例如 `Cherry`）

---

## 5. 声音复刻：资产管理与生命周期（参考 qwen3_tts_voice_store）

目标：用户上传参考音频后，可以在项目中选择该“复刻音色”用于后续合成。

- [ ] 设计“在线复刻音色”的存储模型（建议独立 store，避免与本地 qwen3_tts 混用）
  - [ ] `voice_id`、`name`
  - [ ] `kind=clone`
  - [ ] `ref_audio_path`（上传到本地 uploads 下）
  - [ ] `ref_audio_url`（供前端回放/确认）
  - [ ] `ref_text`（可选，但推荐支持）
  - [ ] `model`（如 `qwen3-tts-vc-2026-01-22`）
  - [ ] 状态字段（uploaded/ready/failed）与错误信息
- [ ] 语音复刻的“调用策略”（两种选一）
  - [ ] 每次合成时都携带参考音频与参考文本（无需在云端持久化音色）
  - [ ] 若平台支持“复刻后生成可复用音色 ID/声纹 ID”，则在 store 中持久化该 ID（需要额外接口与状态机）
- [ ] 上传音频预处理（参考 qwen3 的 `clone` 预处理思路）
  - [ ] 统一采样率/声道（如 16k/mono），降低模型失败率
  - [ ] 限制时长、文件大小、格式白名单

---

## 6. 核心能力封装：在线千问 TTS Service（对齐 tts_service.synthesize 输出）

目标：从业务侧（生成视频/剪映草稿）看，仍然是：
`res = await tts_service.synthesize(text, out_path, voice_id)`，并得到统一的返回结构。

- [ ] 新增模块：`backend/modules/qwen_online_tts_service.py`（命名可调整）
- [ ] 实现最小接口（建议与 `qwen3_tts_service` 的对外风格一致）：
  - [ ] `synthesize_system_voice(text, out_path, voice, language_type, instructions, ...)`
  - [ ] `synthesize_clone_voice(text, out_path, ref_audio_path, ref_text, ...)`
- [ ] 返回结构与现有调用点对齐（至少包含）
  - [ ] `success: bool`
  - [ ] `path: str`（实际落盘的 out_path）
  - [ ] `duration: float`（优先直接拿接口返回；否则用 ffprobe 回填）
  - [ ] `codec/sample_rate`（可选）
  - [ ] `error`（失败原因，尽量可定位）
- [ ] 处理官方“返回 URL、有效期 24 小时”的特点
  - [ ] 自动下载 URL 内容到 `out_path`（业务侧需要本地文件）
  - [ ] 下载失败/超时的重试策略与错误信息
- [ ] 并发与限流
  - [ ] 复用现有 `tts_service.py` 的 `_tts_slot()` 信号量控制（保持全局 TTS 并发可控）
  - [ ] 针对 DashScope 接口增加超时、重试（指数退避）与 429/5xx 处理
- [ ] 日志规范
  - [ ] 可记录：provider、model、text_len、耗时、request_id（若有）
  - [ ] 禁止：记录 API Key、完整文本（如有隐私风险时）

---

## 7. 接入统一入口：modules/tts_service.py

目标：新增 provider 分支，保证业务调用无需改动。

- [ ] 在 `TencentTtsService.synthesize()` 中新增 `provider == "qwen_online_tts"` 分支
- [ ] provider 分支内：
  - [ ] 从 active config 读取 API Key、base url、模型、默认 voice、language_type、instructions 等
  - [ ] 支持 `voice_id` 的优先级：入参 voice_id > 配置 active_voice_id > 默认音色
  - [ ] 若 `voice_id` 命中“复刻音色 store”的 voice_id，则走复刻合成；否则走系统音色合成
- [ ] 语速处理策略
  - [ ] 若云端支持 speed 参数：优先使用云端
  - [ ] 否则复用现有后处理 `apply_audio_speed()`（保持与其他引擎一致）

---

## 8. API 路由：在线千问 TTS（参考 qwen3_tts_routes）

目标：提供“音色管理 + 复刻音色上传 + 状态查询 + 测试合成”的后端 API，便于前端接入与排障。

- [ ] 新增路由文件：`backend/routes/qwen_online_tts_routes.py`（命名可调整）
- [ ] 路由前缀建议：`/api/tts/qwen-online`
- [ ] 系统音色
  - [ ] `GET /voices/system`：返回系统音色列表（可复用 tts_routes 的 `GET /api/tts/voices`，但建议提供专用接口便于扩展）
- [ ] 复刻音色（存储在本地）
  - [ ] `GET /voices`：列表
  - [ ] `GET /voices/{voice_id}`：详情
  - [ ] `POST /voices/upload`：上传参考音频并创建复刻音色条目（FormData + UploadFile）
  - [ ] `PATCH /voices/{voice_id}`：更新名称/模型/ref_text 等
  - [ ] `DELETE /voices/{voice_id}`：删除条目（可选 remove_files）
- [ ] 测试/试听
  - [ ] `POST /synthesize`：输入 text + voice_id（系统音色名或复刻 voice_id）+ 可选参数，返回落盘结果或 preview_id
- [ ] 将路由注册到 `backend/routes/__init__.py` 或 `backend/main.py` 的路由装配处

---

## 9. 业务链路回归点（必须验证）

这些位置会直接调用 `tts_service.synthesize(...)`，新增 provider 后必须确保行为一致、返回结构稳定：

- [ ] 剪映草稿生成：`backend/services/jianying_draft_manager.py`  
  - [ ] 非原片片段输出 `seg_XXXX.mp3` 可被后续“响度归一化/叠加视频生成”流程识别
  - [ ] `duration` 为空时能被 `_probe_audio_duration` / ffprobe 回填
- [ ] 视频生成并发配音：`backend/services/video_generation_service.py`  
  - [ ] 并发任务下稳定（超时/取消/部分失败能正确汇报错误并停止其他任务）
  - [ ] provider==qwen3_tts 的特殊逻辑不会误伤在线 provider（在线 provider 需要自己的分支处理策略）

---

## 10. 失败场景与错误码（建议整理成表）

- [ ] missing_credentials（未配置 DASHSCOPE_API_KEY 且配置中无 key）
- [ ] invalid_region_or_base_url（区域与 base url 不匹配、或 key 用错地域）
- [ ] request_timeout / network_error
- [ ] rate_limited（429）
- [ ] upstream_error（5xx）
- [ ] empty_audio / download_failed（返回 URL 但下载失败）
- [ ] invalid_ref_audio（复刻参考音频不合规）

---

## 11. 测试与验收

- [ ] 单元测试（建议 mock SDK）
  - [ ] 系统音色合成：能生成文件、能拿到 duration
  - [ ] 复刻音色合成：能读取 ref_audio、能生成文件
  - [ ] 异常：缺 key/超时/429/下载失败
- [ ] 集成测试（需要真实 key，建议在本地/CI 仅手动跑）
- [ ] 兼容性验收
  - [ ] 切换 provider 不影响现有 edge/tencent/qwen3 本地功能
  - [ ] 配置文件升级后，旧用户可无感继续使用（默认 provider 仍为 edge_tts）

---

## 12. 交付物清单（代码层）

- [ ] `backend/modules/qwen_online_tts_service.py`（在线千问 TTS 封装）
- [ ] `backend/modules/qwen_online_tts_voice_store.py`（复刻音色本地存储）
- [ ] `backend/routes/qwen_online_tts_routes.py`（音色管理/试听/测试 API）
- [ ] 更新 `backend/modules/tts_service.py`（新增 provider 分支）
- [ ] 更新 `backend/modules/config/tts_config.py`（新增 provider + 默认配置 + engines meta + voices 列表）
- [ ] 更新 `backend/routes/tts_routes.py`（引擎列表/音色列表/试听接口适配）
- [ ] 更新依赖清单（如采用 DashScope SDK）
