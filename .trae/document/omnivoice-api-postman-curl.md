# OmniVoice 外部接口（Postman / cURL）

以下接口用于在**外部**（Postman、脚本、服务端）调用 OmniVoice，完成：

- 获取克隆音色列表
- 上传克隆音色
- 选择默认音色
- 修改音色名称
- 删除克隆音色
- 生成语音（异步任务）
- 获取生成结果（查询任务 + 下载音频）
- 访问可交互 Web 页面

## 启动方式

使用统一服务模式启动（同时提供 **Web UI** 和 **HTTP API**）：

```bash
uv run omnivoice-api --model k2-fsa/OmniVoice --host 0.0.0.0 --port 8970
```

如果你已经把项目安装到当前 Python 环境，也可以直接使用：

```bash
omnivoice-api --model k2-fsa/OmniVoice --host 0.0.0.0 --port 8970
```

默认 API 前缀为 `/api`，可用 `--api_prefix` 修改。

默认数据目录为 `.omnivoice_api`，用于保存：

- 上传的克隆音色
- 生成后的音频文件
- 音色元数据

本文示例以：

- Base URL：`http://127.0.0.1:8970`
- API Prefix：`/api`

为准。

---

## 页面入口

### Web UI

- **GET** `${BASE_URL}/`

启动后，浏览器访问首页即可看到完整交互页面，支持：

- 音色上传 / 选择 / 改名 / 删除
- 文本生成语音
- 任务状态查询
- 音频试听

---

## 1) 获取克隆音色列表

### HTTP

- **GET** `${BASE_URL}/api/clone-voices`

### cURL

```bash
curl -sS "http://127.0.0.1:8970/api/clone-voices"
```

### 返回（示例）

- `data.items[]`: 音色条目（`id/name/filename/created_at/is_active`）
- `data.default_id`: 当前默认音色 ID
- `data.active_id`: 当前激活音色 ID

### 返回示例

```json
{
  "ok": true,
  "data": {
    "items": [
      {
        "id": "0e8b4b8d2fd04a6ea8f4a91db1e8d123",
        "name": "我的音色",
        "filename": "0e8b4b8d2fd04a6ea8f4a91db1e8d123.wav",
        "created_at": "2026-04-16T10:30:00.000000+00:00",
        "is_active": true
      }
    ],
    "default_id": "0e8b4b8d2fd04a6ea8f4a91db1e8d123",
    "active_id": "0e8b4b8d2fd04a6ea8f4a91db1e8d123"
  }
}
```

---

## 2) 上传克隆音色

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/upload`
- **Content-Type** `multipart/form-data`
- **表单字段**
  - `file`: 音频文件（必填）
  - `name`: 显示名称（可选）

支持的常见音频格式：

- `.wav`
- `.mp3`
- `.flac`
- `.m4a`
- `.ogg`
- `.aac`
- `.opus`

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/clone-voices/upload" \
  -F "file=@./sample_prompt.wav" \
  -F "name=我的音色"
```

### 返回（示例）

- `item.id`: 上传后生成的音色 ID
- `item.name`: 音色名称
- `path`: 服务器落盘路径（调试用）

### 返回示例

```json
{
  "ok": true,
  "item": {
    "id": "0e8b4b8d2fd04a6ea8f4a91db1e8d123",
    "name": "我的音色",
    "filename": "0e8b4b8d2fd04a6ea8f4a91db1e8d123.wav",
    "created_at": "2026-04-16T10:30:00.000000+00:00"
  },
  "path": "C:/Users/Administrator/Documents/OmniVoice/.omnivoice_api/clone_voices/0e8b4b8d2fd04a6ea8f4a91db1e8d123.wav"
}
```

---

## 3) 选择默认音色

设置默认音色后，不传 `voice_id` 的生成请求会自动使用它。

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/select`
- **JSON Body**
  - `voice_id` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/clone-voices/select" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\"}"
```

### 返回（示例）

- `ok`: 是否成功
- `default_id`: 当前默认音色 ID
- `active_id`: 当前激活音色 ID

---

## 4) 修改音色名称

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/rename`
- **JSON Body**
  - `voice_id` (string, required)
  - `new_name` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/clone-voices/rename" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\",\"new_name\":\"新名称\"}"
```

### 返回（示例）

- `ok`: 是否成功
- `item`: 修改后的音色信息

---

## 5) 删除克隆音色

从列表与磁盘中移除该音色；若删除的是当前默认音色，会自动把 `default_id` 切换到剩余列表中的第一个，若无剩余则为 `null`。

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/delete`
- **JSON Body**
  - `voice_id` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/clone-voices/delete" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\"}"
```

### 返回（示例）

- `ok`: 是否成功
- `default_id`: 删除后的当前默认音色 ID；若没有剩余音色则为 `null`

---

## 6) 生成语音（异步任务）

为了避免长时间推理导致请求超时，生成接口会先返回 `task_id`，后台线程继续执行推理，成功后把音频保存到输出目录。

### HTTP

- **POST** `${BASE_URL}/api/tts/generate`
- **JSON Body**
  - `text` (string, required): 要合成的文本
  - `voice_id` (string, optional): 指定音色；不传则使用当前默认音色
  - `language` (string, optional): 指定语言
  - `ref_text` (string, optional): 参考音频对应文本；不传则自动识别
  - `params` (object, optional): 高级生成参数

### `params` 可用参数

目前支持的常见参数包括：

- `num_step`
- `guidance_scale`
- `denoise`
- `preprocess_prompt`
- `postprocess_output`
- `audio_chunk_duration`
- `audio_chunk_threshold`
- 以及透传给 `OmniVoice.generate()` 的额外参数，例如：
  - `speed`
  - `duration`

### cURL（最简）

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/tts/generate" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"你好，这是一段测试文本。\",\"voice_id\":\"YOUR_VOICE_ID\"}"
```

### cURL（带高级参数示例）

```bash
curl -sS -X POST "http://127.0.0.1:8970/api/tts/generate" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"你好，这是一段测试文本。\",\"voice_id\":\"YOUR_VOICE_ID\",\"language\":\"Chinese\",\"params\":{\"num_step\":32,\"guidance_scale\":2.0,\"speed\":1.0,\"denoise\":true,\"preprocess_prompt\":true,\"postprocess_output\":true}}"
```

### 返回（示例）

- `ok`: 是否成功
- `task_id`: 任务 ID
- `status`: 初始状态，一般为 `queued`

### 返回示例

```json
{
  "ok": true,
  "task_id": "64b8cf9905cd483282a07a9c7a6a31ff",
  "status": "queued"
}
```

---

## 7) 获取生成结果（查询任务）

### HTTP

- **GET** `${BASE_URL}/api/tts/tasks/{task_id}`

### cURL

```bash
curl -sS "http://127.0.0.1:8970/api/tts/tasks/YOUR_TASK_ID"
```

### 状态说明

- `queued`: 已入队
- `running`: 推理中
- `succeeded`: 已完成，可下载音频
- `failed`: 失败，`error` 字段包含原因

### 返回字段说明

- `task.id`: 任务 ID
- `task.status`: 当前状态
- `task.text`: 提交的文本
- `task.voice_id`: 使用的音色 ID
- `task.audio_path`: 服务端输出文件路径
- `task.audio_url`: 下载音频的接口路径
- `task.error`: 失败原因

### 返回示例

```json
{
  "ok": true,
  "task": {
    "id": "64b8cf9905cd483282a07a9c7a6a31ff",
    "status": "succeeded",
    "text": "你好，这是一段测试文本。",
    "voice_id": "0e8b4b8d2fd04a6ea8f4a91db1e8d123",
    "created_at": "2026-04-16T10:40:00.000000+00:00",
    "updated_at": "2026-04-16T10:40:08.000000+00:00",
    "audio_path": "C:/Users/Administrator/Documents/OmniVoice/.omnivoice_api/tts_outputs/64b8cf9905cd483282a07a9c7a6a31ff.wav",
    "error": null,
    "audio_url": "/api/tts/tasks/64b8cf9905cd483282a07a9c7a6a31ff/audio"
  }
}
```

---

## 8) 下载生成音频

### HTTP

- **GET** `${BASE_URL}/api/tts/tasks/{task_id}/audio`

### cURL（保存到本地文件）

```bash
curl -L -o out.wav "http://127.0.0.1:8970/api/tts/tasks/YOUR_TASK_ID/audio"
```

### 返回说明

- 成功时直接返回 `audio/wav`
- 若任务未完成，返回错误信息
- 若任务不存在或音频文件缺失，也会返回错误信息

---

## Postman 使用建议

- `上传克隆音色`：Body 选择 `form-data`，字段名必须是 `file`
- `生成语音`：建议先调用生成接口拿到 `task_id`，再轮询查询接口直到 `succeeded`
- `下载音频`：可以直接请求下载接口，或在 Postman 中使用 “Send and Download”
- `页面调试`：浏览器直接访问首页即可，不需要额外调用接口就能测试完整流程

---

## 常见问题

### 1. 不传 `voice_id` 能生成吗？

可以。

如果已经设置了默认音色，则会直接使用默认音色；如果还没有任何音色，生成会走模型自身能力，但是否满足你的业务效果，取决于你的使用方式和模型输入。

### 2. `ref_text` 有什么作用？

`ref_text` 是参考音频对应的文本。

- 传了：直接使用你提供的文本
- 不传：服务会尝试自动识别参考音频内容

### 3. 页面和 API 是分开启动的吗？

不是。

当前实现中，启动一次服务即可同时获得：

- Web 页面：`/`
- HTTP API：`/api/*`

### 4. 音频和音色文件保存在哪里？

默认保存在项目目录下：

- `.omnivoice_api/clone_voices/`
- `.omnivoice_api/tts_outputs/`

也可以通过 `--storage_dir` 修改。
