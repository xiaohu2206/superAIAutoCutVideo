# 视频剪辑项目管理系统 - 后端 API 开发文档

## 概述

本文档详细描述了视频剪辑项目管理系统的后端 API 接口规范，包括项目管理、文件上传、脚本生成等核心功能。

### 技术栈建议

- **框架**: Python FastAPI / Flask / Django
- **数据库**: PostgreSQL / MySQL / SQLite
- **文件存储**: 本地文件系统 / 云存储（阿里云 OSS/AWS S3）
- **AI 服务**: OpenAI GPT / 本地大模型
- **视频处理**: FFmpeg / OpenCV

### 基础配置

- **Base URL**: `http://localhost:8000`
- **API 前缀**: `/api`
- **认证方式**: JWT Token（可选）
- **编码格式**: UTF-8
- **响应格式**: JSON

---

## 数据模型

### 1. Project（项目）

```json
{
  "id": "string (UUID)",
  "name": "string (项目名称)",
  "description": "string | null (项目描述)",
  "narration_type": "string (解说类型: '短剧解说')",
  "status": "string (项目状态: 'draft' | 'processing' | 'completed' | 'failed')",
  "video_path": "string | null (视频文件路径)",
  "subtitle_path": "string | null (字幕文件路径)",
  "script": "object | null (视频脚本JSON对象)",
  "created_at": "string (ISO 8601格式的创建时间)",
  "updated_at": "string (ISO 8601格式的更新时间)"
}
```

### 2. VideoScript（视频脚本）

```json
{
  "version": "string (脚本版本号)",
  "total_duration": "number (总时长，单位：秒)",
  "segments": [
    {
      "id": "string (段落ID)",
      "start_time": "number (开始时间，单位：秒)",
      "end_time": "number (结束时间，单位：秒)",
      "text": "string (解说文本)",
      "subtitle": "string | null (对应字幕)"
    }
  ],
  "metadata": {
    "video_name": "string | null",
    "created_at": "string | null",
    "updated_at": "string | null"
  }
}
```

---

## API 接口列表

### 1. 项目管理接口

#### 1.1 获取项目列表

**接口**: `GET /api/projects`

**功能**: 获取所有项目列表

**请求参数**: 无

**响应示例**:

```json
{
  "message": "获取项目列表成功",
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "我的第一个项目",
      "description": "这是一个测试项目",
      "narration_type": "短剧解说",
      "status": "draft",
      "video_path": "/uploads/videos/video_123.mp4",
      "subtitle_path": "/uploads/subtitles/subtitle_123.srt",
      "script": null,
      "created_at": "2024-01-01T10:00:00Z",
      "updated_at": "2024-01-01T10:00:00Z"
    }
  ],
  "timestamp": "2024-01-01T10:00:00Z"
}
```

**状态码**:

- `200 OK`: 成功
- `500 Internal Server Error`: 服务器错误

---

#### 1.2 获取单个项目详情

**接口**: `GET /api/projects/{project_id}`

**功能**: 获取指定项目的详细信息

**路径参数**:

- `project_id` (string, required): 项目 ID

**响应示例**:

```json
{
  "message": "获取项目详情成功",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "我的第一个项目",
    "description": "这是一个测试项目",
    "narration_type": "短剧解说",
    "status": "completed",
    "video_path": "/uploads/videos/video_123.mp4",
    "subtitle_path": "/uploads/subtitles/subtitle_123.srt",
    "script": {
      "version": "1.0",
      "total_duration": 120.5,
      "segments": [
        {
          "id": "1",
          "start_time": 0.0,
          "end_time": 5.5,
          "text": "欢迎观看本期视频",
          "subtitle": "欢迎观看"
        }
      ],
      "metadata": {
        "video_name": "video_123.mp4",
        "created_at": "2024-01-01T10:00:00Z"
      }
    },
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T12:00:00Z"
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**状态码**:

- `200 OK`: 成功
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器错误

---

#### 1.3 创建项目

**接口**: `POST /api/projects`

**功能**: 创建新的视频剪辑项目

**请求体**:

```json
{
  "name": "string (必填, 项目名称)",
  "description": "string | null (可选, 项目描述)",
  "narration_type": "string (可选, 默认: '短剧解说')"
}
```

**请求示例**:

```json
{
  "name": "我的新项目",
  "description": "这是一个关于美食的短剧解说项目",
  "narration_type": "短剧解说"
}
```

**响应示例**:

```json
{
  "message": "项目创建成功",
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "我的新项目",
    "description": "这是一个关于美食的短剧解说项目",
    "narration_type": "短剧解说",
    "status": "draft",
    "video_path": null,
    "subtitle_path": null,
    "script": null,
    "created_at": "2024-01-02T10:00:00Z",
    "updated_at": "2024-01-02T10:00:00Z"
  },
  "timestamp": "2024-01-02T10:00:00Z"
}
```

**状态码**:

- `201 Created`: 创建成功
- `400 Bad Request`: 请求参数错误
- `500 Internal Server Error`: 服务器错误

---

#### 1.4 更新项目

**接口**: `POST /api/projects/{project_id}`

**功能**: 更新项目信息

**路径参数**:

- `project_id` (string, required): 项目 ID

**请求体**:

```json
{
  "name": "string (可选)",
  "description": "string | null (可选)",
  "narration_type": "string (可选)",
  "status": "string (可选)",
  "video_path": "string | null (可选)",
  "subtitle_path": "string | null (可选)",
  "script": "object | null (可选)"
}
```

**请求示例**:

```json
{
  "name": "更新后的项目名称",
  "status": "processing"
}
```

**响应示例**:

```json
{
  "message": "项目更新成功",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "更新后的项目名称",
    "status": "processing",
    "updated_at": "2024-01-02T11:00:00Z"
  },
  "timestamp": "2024-01-02T11:00:00Z"
}
```

**状态码**:

- `200 OK`: 更新成功
- `400 Bad Request`: 请求参数错误
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器错误

---

#### 1.5 删除项目

**接口**: `POST /api/projects/{project_id}/delete`

**功能**: 删除指定项目及其关联数据

**路径参数**:

- `project_id` (string, required): 项目 ID

**响应示例**:

```json
{
  "message": "项目删除成功",
  "success": true,
  "timestamp": "2024-01-02T12:00:00Z"
}
```

**状态码**:

- `200 OK`: 删除成功
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器错误

**注意事项**:

- 删除项目时应同时删除相关的视频文件和字幕文件
- 可以考虑软删除（标记为已删除）而非物理删除
- 需要进行权限验证，防止误删

---

### 2. 文件上传接口

#### 2.1 上传视频文件

**接口**: `POST /api/projects/{project_id}/upload/video`

**功能**: 上传视频文件到指定项目

**路径参数**:

- `project_id` (string, required): 项目 ID

**请求头**:

```
Content-Type: multipart/form-data
```

**请求参数** (Form Data):

- `file` (File, required): 视频文件
- `project_id` (string, required): 项目 ID

**支持的视频格式**:

- MP4, AVI, MOV, MKV, FLV, WMV, WEBM

**文件大小限制**: 建议最大 2GB

**响应示例**:

```json
{
  "message": "视频上传成功",
  "data": {
    "file_path": "/uploads/videos/550e8400_video_20240102_120000.mp4",
    "file_name": "my_video.mp4",
    "file_size": 52428800,
    "upload_time": "2024-01-02T12:00:00Z"
  },
  "timestamp": "2024-01-02T12:00:00Z"
}
```

**状态码**:

- `200 OK`: 上传成功
- `400 Bad Request`: 文件格式不支持或文件过大
- `404 Not Found`: 项目不存在
- `413 Payload Too Large`: 文件过大
- `500 Internal Server Error`: 服务器错误

**实现建议**:

1. 验证文件类型和大小
2. 使用 UUID 重命名文件，避免文件名冲突
3. 自动更新项目的 `video_path` 字段
4. 返回文件存储路径供前端使用
5. 考虑使用分片上传处理大文件
6. 提取视频元信息（时长、分辨率、帧率等）

---

#### 2.2 上传字幕文件

**接口**: `POST /api/projects/{project_id}/upload/subtitle`

**功能**: 上传字幕文件到指定项目

**路径参数**:

- `project_id` (string, required): 项目 ID

**请求头**:

```
Content-Type: multipart/form-data
```

**请求参数** (Form Data):

- `file` (File, required): 字幕文件（.srt 格式）
- `project_id` (string, required): 项目 ID

**支持的字幕格式**:

- SRT (SubRip Text)

**响应示例**:

```json
{
  "message": "字幕上传成功",
  "data": {
    "file_path": "/uploads/subtitles/550e8400_subtitle_20240102_120500.srt",
    "file_name": "my_subtitle.srt",
    "file_size": 2048,
    "upload_time": "2024-01-02T12:05:00Z"
  },
  "timestamp": "2024-01-02T12:05:00Z"
}
```

**状态码**:

- `200 OK`: 上传成功
- `400 Bad Request`: 文件格式不支持
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器错误

**实现建议**:

1. 验证文件格式为 .srt
2. 验证 SRT 文件格式的正确性
3. 解析字幕内容提取时间戳和文本
4. 自动更新项目的 `subtitle_path` 字段
5. 可以考虑将字幕内容存储到数据库

---

### 3. 脚本生成与管理接口

#### 3.1 生成解说脚本

**接口**: `POST /api/projects/generate-script`

**功能**: 基于上传的视频和字幕，使用 AI 生成解说脚本

**请求体**:

```json
{
  "project_id": "string (必填, 项目ID)",
  "video_path": "string (必填, 视频文件路径)",
  "subtitle_path": "string | null (可选, 字幕文件路径)",
  "narration_type": "string (必填, 解说类型)"
}
```

**请求示例**:

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "video_path": "/uploads/videos/550e8400_video_20240102_120000.mp4",
  "subtitle_path": "/uploads/subtitles/550e8400_subtitle_20240102_120500.srt",
  "narration_type": "短剧解说"
}
```

**响应示例**:

```json
{
  "message": "解说脚本生成成功",
  "data": {
    "version": "1.0",
    "total_duration": 120.5,
    "segments": [
      {
        "id": "seg_1",
        "start_time": 0.0,
        "end_time": 5.5,
        "text": "在这个宁静的午后，故事就这样开始了...",
        "subtitle": "午后时光"
      },
      {
        "id": "seg_2",
        "start_time": 5.5,
        "end_time": 12.0,
        "text": "男主角李明正在咖啡厅里等待着某个重要的人",
        "subtitle": "李明在咖啡厅"
      },
      {
        "id": "seg_3",
        "start_time": 12.0,
        "end_time": 18.5,
        "text": "突然，门被推开了，一个熟悉的身影出现在门口",
        "subtitle": "有人进来了"
      }
    ],
    "metadata": {
      "video_name": "550e8400_video_20240102_120000.mp4",
      "created_at": "2024-01-02T12:10:00Z",
      "updated_at": "2024-01-02T12:10:00Z",
      "generation_model": "gpt-4",
      "processing_time": 15.5
    }
  },
  "timestamp": "2024-01-02T12:10:00Z"
}
```

**状态码**:

- `200 OK`: 生成成功
- `400 Bad Request`: 请求参数错误或视频文件不存在
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 生成失败或 AI 服务错误
- `503 Service Unavailable`: AI 服务不可用

**实现逻辑**:

1. **视频分析**:

   - 使用 FFmpeg 提取视频关键帧
   - 使用计算机视觉识别场景变化
   - 提取视频时长和分段信息

2. **字幕处理**（如果有）:

   - 解析 SRT 字幕文件
   - 提取时间戳和文本内容
   - 与视频场景进行对齐

3. **AI 生成解说**:

   - 构建提示词（Prompt）:

     ```
     你是一个专业的短剧解说创作者。请根据以下信息生成解说脚本：

     视频时长：{total_duration}秒
     场景信息：{scene_descriptions}
     字幕内容：{subtitles}

     要求：
     1. 解说要生动有趣，吸引观众
     2. 不要直接复述字幕内容
     3. 重点突出剧情冲突和悬念
     4. 每段解说控制在3-8秒
     5. 保持解说的连贯性和节奏感
     ```

   - 调用 OpenAI GPT API 或本地大模型
   - 解析 AI 返回的结果

4. **脚本结构化**:

   - 将 AI 生成的文本按时间轴分段
   - 生成唯一的段落 ID
   - 与字幕进行匹配和对齐
   - 构建完整的 VideoScript 对象

5. **异步处理建议**:
   - 对于长视频，建议使用异步任务队列（Celery/RQ）
   - 通过 WebSocket 推送生成进度
   - 项目状态更新为 "processing"
   - 完成后更新为 "completed" 或 "failed"

**提示词优化建议**:

```python
# 短剧解说类型的提示词模板
SHORT_DRAMA_PROMPT = """
你是一位经验丰富的短剧解说创作者，擅长用生动的语言吸引观众。

【视频信息】
- 总时长：{duration}秒
- 场景数：{scene_count}个

【场景详情】
{scenes}

【字幕内容】
{subtitles}

【任务要求】
1. 为每个场景生成简洁有力的解说文本
2. 突出剧情的关键转折点和冲突
3. 使用口语化、带有情感的表达方式
4. 设置悬念，引导观众继续观看
5. 每段解说3-8秒，不超过30个字

【输出格式】
请以JSON格式输出，包含以下字段：
{
  "segments": [
    {
      "start_time": 0.0,
      "end_time": 5.5,
      "text": "解说文本"
    }
  ]
}
"""
```

---

#### 3.2 保存脚本

**接口**: `POST /api/projects/{project_id}/script`

**功能**: 保存或更新项目的解说脚本

**路径参数**:

- `project_id` (string, required): 项目 ID

**请求体**:

```json
{
  "script": {
    "version": "string",
    "total_duration": "number",
    "segments": [
      {
        "id": "string",
        "start_time": "number",
        "end_time": "number",
        "text": "string",
        "subtitle": "string | null"
      }
    ],
    "metadata": "object"
  }
}
```

**请求示例**:

```json
{
  "script": {
    "version": "1.0",
    "total_duration": 120.5,
    "segments": [
      {
        "id": "seg_1",
        "start_time": 0.0,
        "end_time": 5.5,
        "text": "修改后的解说文本",
        "subtitle": "午后时光"
      }
    ],
    "metadata": {
      "video_name": "my_video.mp4",
      "updated_at": "2024-01-02T13:00:00Z"
    }
  }
}
```

**响应示例**:

```json
{
  "message": "脚本保存成功",
  "data": {
    "version": "1.0",
    "total_duration": 120.5,
    "segments": [
      {
        "id": "seg_1",
        "start_time": 0.0,
        "end_time": 5.5,
        "text": "修改后的解说文本",
        "subtitle": "午后时光"
      }
    ],
    "metadata": {
      "video_name": "my_video.mp4",
      "updated_at": "2024-01-02T13:00:00Z"
    }
  },
  "timestamp": "2024-01-02T13:00:00Z"
}
```

**状态码**:

- `200 OK`: 保存成功
- `400 Bad Request`: 脚本格式错误
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器错误

**实现建议**:

1. 验证脚本 JSON 格式的正确性
2. 验证时间轴的连续性和合理性
3. 自动更新项目的 `updated_at` 字段
4. 可以保存脚本历史版本
5. 将脚本存储为 JSON 格式到数据库

---

## 数据库设计

### 1. projects 表

```sql
CREATE TABLE projects (
    id VARCHAR(36) PRIMARY KEY,  -- UUID
    name VARCHAR(255) NOT NULL,
    description TEXT,
    narration_type VARCHAR(50) NOT NULL DEFAULT '短剧解说',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft, processing, completed, failed
    video_path VARCHAR(500),
    subtitle_path VARCHAR(500),
    script JSON,  -- 存储完整的脚本JSON
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

### 2. script_history 表（可选，用于版本管理）

```sql
CREATE TABLE script_history (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id VARCHAR(36) NOT NULL,
    version VARCHAR(20) NOT NULL,
    script JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    INDEX idx_project_id (project_id)
);
```

---

## 文件存储结构

```
uploads/
├── videos/
│   ├── {project_id}_video_{timestamp}.mp4
│   ├── {project_id}_video_{timestamp}.avi
│   └── ...
├── subtitles/
│   ├── {project_id}_subtitle_{timestamp}.srt
│   └── ...
└── thumbnails/  (可选，用于存储视频缩略图)
    ├── {project_id}_thumb_{timestamp}.jpg
    └── ...
```

---

## 错误处理

### 统一错误响应格式

```json
{
  "message": "错误描述",
  "error": {
    "code": "ERROR_CODE",
    "details": "详细错误信息"
  },
  "timestamp": "2024-01-02T13:00:00Z"
}
```

### 错误码定义

| 错误码                     | 描述             | HTTP 状态码 |
| -------------------------- | ---------------- | ----------- |
| `PROJECT_NOT_FOUND`        | 项目不存在       | 404         |
| `INVALID_PROJECT_NAME`     | 项目名称无效     | 400         |
| `FILE_TOO_LARGE`           | 文件过大         | 413         |
| `UNSUPPORTED_FORMAT`       | 不支持的文件格式 | 400         |
| `UPLOAD_FAILED`            | 文件上传失败     | 500         |
| `SCRIPT_GENERATION_FAILED` | 脚本生成失败     | 500         |
| `INVALID_SCRIPT_FORMAT`    | 脚本格式错误     | 400         |
| `AI_SERVICE_UNAVAILABLE`   | AI 服务不可用    | 503         |
| `DATABASE_ERROR`           | 数据库错误       | 500         |

---

## 安全性考虑

### 1. 文件上传安全

- 验证文件类型（MIME type）
- 限制文件大小
- 使用 UUID 重命名文件，避免路径遍历攻击
- 存储到非 Web 根目录
- 定期清理未使用的文件

### 2. API 安全

- 实施请求频率限制（Rate Limiting）
- 添加 JWT 认证（可选）
- 输入验证和参数清理
- SQL 注入防护
- CORS 配置

### 3. 数据安全

- 定期备份数据库
- 敏感信息加密存储
- 实施日志记录和审计

---

## 性能优化建议

### 1. 数据库优化

- 为常用查询字段创建索引
- 使用连接池管理数据库连接
- 实施查询缓存（Redis）

### 2. 文件处理优化

- 使用异步任务处理大文件
- 实施文件分片上传
- 使用 CDN 加速文件访问

### 3. AI 生成优化

- 实施任务队列（Celery/RQ）
- 缓存常见的生成结果
- 批量处理多个请求
- 使用 WebSocket 推送进度

---

## WebSocket 实时通信（可选）

用于推送脚本生成进度。

### 连接

```
ws://localhost:8000/ws
```

### 消息格式

**进度更新消息**:

```json
{
  "type": "progress",
  "task_id": "task_550e8400",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "progress": 45,
  "message": "正在分析视频场景...",
  "timestamp": "2024-01-02T12:10:00Z"
}
```

**完成消息**:

```json
{
  "type": "completed",
  "task_id": "task_550e8400",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "脚本生成完成",
  "data": {
    /* VideoScript对象 */
  },
  "timestamp": "2024-01-02T12:15:00Z"
}
```

**错误消息**:

```json
{
  "type": "error",
  "task_id": "task_550e8400",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "脚本生成失败",
  "error": "AI服务连接超时",
  "timestamp": "2024-01-02T12:10:00Z"
}
```

---

## 测试建议

### 1. 单元测试

- 测试每个 API 接口的正常和异常情况
- 测试数据模型的验证逻辑
- 测试文件上传和存储逻辑

### 2. 集成测试

- 测试完整的项目创建到脚本生成流程
- 测试文件上传和下载
- 测试 AI 生成功能

### 3. 性能测试

- 并发请求测试
- 大文件上传测试
- 长时间运行测试

---

## 部署建议

### 1. 环境配置

```bash
# .env 示例
DATABASE_URL=postgresql://user:password@localhost/videoproject
UPLOAD_DIR=/var/uploads
MAX_FILE_SIZE=2147483648  # 2GB
OPENAI_API_KEY=sk-xxxxx
REDIS_URL=redis://localhost:6379
```

### 2. 依赖安装

```bash
pip install fastapi uvicorn sqlalchemy pymysql
pip install python-multipart  # 文件上传
pip install openai  # AI服务
pip install ffmpeg-python opencv-python  # 视频处理
pip install celery redis  # 异步任务
```

### 3. 启动服务

```bash
# 开发环境
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产环境
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## API 调用示例

### Python 示例

```python
import requests

BASE_URL = "http://localhost:8000/api"

# 创建项目
response = requests.post(f"{BASE_URL}/projects", json={
    "name": "我的新项目",
    "description": "测试项目",
    "narration_type": "短剧解说"
})
project = response.json()["data"]
project_id = project["id"]

# 上传视频
with open("video.mp4", "rb") as f:
    files = {"file": f}
    data = {"project_id": project_id}
    response = requests.post(
        f"{BASE_URL}/projects/{project_id}/upload/video",
        files=files,
        data=data
    )
    print(response.json())

# 生成脚本
response = requests.post(f"{BASE_URL}/projects/generate-script", json={
    "project_id": project_id,
    "video_path": "/uploads/videos/video_123.mp4",
    "subtitle_path": None,
    "narration_type": "短剧解说"
})
script = response.json()["data"]
print(script)

# 保存脚本
response = requests.post(
    f"{BASE_URL}/projects/{project_id}/script",
    json={"script": script}
)
print(response.json())
```

### cURL 示例

```bash
# 创建项目
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "我的新项目", "description": "测试项目"}'

# 上传视频
curl -X POST http://localhost:8000/api/projects/{project_id}/upload/video \
  -F "file=@video.mp4" \
  -F "project_id={project_id}"

# 获取项目列表
curl -X GET http://localhost:8000/api/projects
```

---

## 附录

### A. SRT 字幕格式示例

```srt
1
00:00:00,000 --> 00:00:05,500
午后时光

2
00:00:05,500 --> 00:00:12,000
李明在咖啡厅

3
00:00:12,000 --> 00:00:18,500
有人进来了
```

---

## 更新日志

- **v1.0.0** (2024-01-02): 初始版本发布
  - 项目管理基础功能
  - 文件上传功能
  - AI 脚本生成功能
  - 脚本编辑和保存功能

---

## 联系方式

如有技术问题或建议，请联系：

- 开发团队邮箱: dev@example.com
- 项目仓库: https://github.com/example/video-project

---

**文档结束**
