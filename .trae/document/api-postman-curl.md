# IndexTTS 外部接口（Postman / cURL）

以下接口用于在**外部**（Postman、脚本、服务端）调用 IndexTTS，完成：

- 获取克隆音色列表
- 上传克隆音色
- 选择使用克隆音色
- 修改音色名称
- 删除克隆音色
- 生成语音（异步任务）
- 获取生成结果（查询任务 + 下载音频）

## 启动方式

使用 API 模式启动（保留 WebUI，同时开放 HTTP 接口）：

```bash
python webui.py --enable_api --host 0.0.0.0 --port 7860
```

默认 API 前缀为 `/api`，可用 `--api_prefix` 修改。

API 模式会**优先启动 HTTP 接口**，并在首次调用“生成语音”时才加载大模型（避免启动时卡很久）。
如需 WebUI，请不要加 `--enable_api`，单独启动 WebUI 模式即可。

本文示例以：

- Base URL：`http://127.0.0.1:7860`
- API Prefix：`/api`

为准。

---

## 1) 获取克隆音色列表

### HTTP

- **GET** `${BASE_URL}/api/clone-voices`

### cURL

```bash
curl -sS "http://127.0.0.1:7860/api/clone-voices"
```

### 返回（示例）

- `data.items[]`: 音色条目（`id/name/filename/created_at`）
- `data.default_id`: 当前默认音色（用于生成时的默认选择）
- `data.active_id`: 当前激活音色（与 `default_id` 相同，便于语义理解）
- `data.items[].is_active`: 该条目是否为当前激活音色

---

## 2) 上传克隆音色

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/upload`
- **Content-Type** `multipart/form-data`
- **表单字段**
  - `file`: 音频文件（必填）
  - `name`: 显示名称（可选）

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/clone-voices/upload" \
  -F "file=@./sample_prompt.wav" \
  -F "name=我的音色"
```

### 返回（示例）

- `item.id`: 上传后生成的音色ID（后续选择/改名/生成都用它）
- `path`: 服务器落盘路径（仅用于调试）

---

## 3) 选择使用克隆音色

设置默认音色（不传 `voice_id` 的生成请求会使用它）。

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/select`
- **JSON Body**
  - `voice_id` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/clone-voices/select" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\"}"
```

---

## 4) 修改音色名称

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/rename`
- **JSON Body**
  - `voice_id` (string, required)
  - `new_name` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/clone-voices/rename" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\",\"new_name\":\"新名称\"}"
```

---

## 5) 删除克隆音色

从列表与磁盘移除该音色；若删除的是当前默认音色，会自动将 `default_id` 设为剩余列表中的第一个（若无剩余则为 `null`）。

### HTTP

- **POST** `${BASE_URL}/api/clone-voices/delete`
- **JSON Body**
  - `voice_id` (string, required)

### cURL

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/clone-voices/delete" \
  -H "Content-Type: application/json" \
  -d "{\"voice_id\":\"YOUR_VOICE_ID\"}"
```

### 返回（示例）

- `ok`: 是否成功
- `default_id`: 删除后的当前默认音色 ID（与 `GET /api/clone-voices` 中 `default_id` 一致；若无剩余音色则为 `null`）

---

## 6) 生成语音（异步任务）

为了避免 Postman 超时，生成接口返回 `task_id`，后台线程完成推理并保存 `out.wav`。

### HTTP

- **POST** `${BASE_URL}/api/tts/generate`
- **JSON Body**
  - `text` (string, required): 要合成的文本
  - `voice_id` (string, optional): 使用指定音色；不传则用 `default_id`
  - `params` (object, optional): 透传给 `IndexTTS2.infer()` 的生成参数（高级用法）

### cURL（最简）

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/tts/generate" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"你好，这是一段测试文本。\",\"voice_id\":\"YOUR_VOICE_ID\"}"
```

### cURL（带可选生成参数示例）

```bash
curl -sS -X POST "http://127.0.0.1:7860/api/tts/generate" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"你好，这是一段测试文本。\",\"voice_id\":\"YOUR_VOICE_ID\",\"params\":{\"top_p\":0.8,\"temperature\":0.8,\"num_beams\":3,\"repetition_penalty\":10.0,\"max_mel_tokens\":1500}}"
```

返回包含 `task_id`。

---

## 7) 获取生成结果（查询任务）

### HTTP

- **GET** `${BASE_URL}/api/tts/tasks/{task_id}`

### cURL

```bash
curl -sS "http://127.0.0.1:7860/api/tts/tasks/YOUR_TASK_ID"
```

### 状态说明

- `queued`: 已入队（接口返回时的状态）
- `running`: 推理中
- `succeeded`: 完成，可下载音频
- `failed`: 失败，`error` 字段会给出原因

当 `succeeded` 时，响应里会包含：

- `task.audio_url`: 下载音频的相对路径

---

## 8) 下载生成音频

### HTTP

- **GET** `${BASE_URL}/api/tts/tasks/{task_id}/audio`

### cURL（保存到本地文件）

```bash
curl -L -o out.wav "http://127.0.0.1:7860/api/tts/tasks/YOUR_TASK_ID/audio"
```

---

## Postman 使用建议

- `上传克隆音色`：Body 选择 `form-data`，字段名必须是 `file`
- `生成语音`：建议先调用生成接口拿到 `task_id`，再轮询查询接口直到 `succeeded`
- 下载接口直接返回 `audio/wav`，Postman 里可用 “Send and Download”

