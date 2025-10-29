# AI大模型调用框架使用文档

## 概述

本框架是一个工程化的AI大模型调用服务框架，支持多种AI提供商（Qwen、Doubao、DeepSeek等），采用OpenAI标准接口，具有高度的模块化和可扩展性。

## 框架架构

### 核心模块

```
backend/
├── modules/
│   ├── ai/                     # AI模型核心模块
│   │   ├── base.py            # 抽象基类定义
│   │   └── providers/         # 具体提供商实现
│   │       ├── qwen.py        # 通义千问提供商
│   │       ├── doubao.py      # 豆包提供商
│   │       └── deepseek.py    # DeepSeek提供商
│   ├── config/                # 配置管理模块
│   │   └── ai_config.py       # AI配置管理器
│   └── prompts/               # 提示词管理模块
│       └── prompt_manager.py  # 提示词模板管理
├── services/                  # 服务层
│   └── ai_service.py         # AI服务统一调用接口
└── routes/                   # API路由
    ├── ai_routes.py          # AI相关接口
    └── health_routes.py      # 健康检查接口
```

## 主要特性

### 1. 多提供商支持
- **Qwen (通义千问)**: 阿里云大模型服务
- **Doubao (豆包)**: 字节跳动大模型服务  
- **DeepSeek**: DeepSeek大模型服务
- **可扩展**: 易于添加新的AI提供商

### 2. 统一OpenAI接口
- 所有提供商都遵循OpenAI API标准
- 支持流式和非流式响应
- 统一的消息格式和响应结构

### 3. 配置管理
- 动态配置AI模型参数
- 支持多配置管理和切换
- API密钥安全存储
- 配置热更新

### 4. 提示词管理
- 模板化提示词系统
- 支持变量替换
- 分类管理和搜索
- 预定义视频分析模板

### 5. 健康监控
- 实时服务状态监控
- AI连接测试
- 系统资源监控
- 详细的健康检查报告

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. 访问API文档

打开浏览器访问: http://127.0.0.1:8000/docs

## API接口说明

### AI配置管理

#### 获取所有配置
```http
GET /api/ai/configs
```

#### 创建配置
```http
POST /api/ai/configs
Content-Type: application/json

{
  "config_id": "qwen_config",
  "config": {
    "provider": "qwen",
    "api_key": "your_api_key",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-turbo",
    "enabled": true
  }
}
```

#### 激活配置
```http
POST /api/ai/configs/{config_id}/activate
```

### AI聊天接口

#### 普通聊天
```http
POST /api/ai/chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "config_id": "qwen_config",
  "stream": false
}
```

#### 流式聊天
```http
POST /api/ai/chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "config_id": "qwen_config",
  "stream": true
}
```

### 连接测试

#### 测试单个配置
```http
POST /api/ai/test/{config_id}
```

#### 测试所有配置
```http
POST /api/ai/test-all
```

### 健康检查

#### 基础健康检查
```http
GET /api/health/
```

#### 详细健康检查
```http
GET /api/health/detailed
```

#### AI服务健康检查
```http
GET /api/health/ai
```

### 提示词管理

#### 获取所有提示词
```http
GET /api/ai/prompts
```

#### 创建提示词模板
```http
POST /api/ai/prompts
Content-Type: application/json

{
  "id": "video_analysis",
  "name": "视频内容分析",
  "description": "分析视频内容并提取关键信息",
  "category": "video",
  "template": "请分析这个视频的内容：{video_description}",
  "variables": ["video_description"],
  "system_prompt": "你是一个专业的视频内容分析师",
  "enabled": true
}
```

#### 渲染提示词模板
```http
POST /api/ai/prompts/{template_id}/render
Content-Type: application/json

{
  "template_id": "video_analysis",
  "variables": {
    "video_description": "一个关于编程教学的视频"
  }
}
```

## 配置示例

### Qwen配置
```json
{
  "provider": "qwen",
  "api_key": "sk-xxx",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-turbo",
  "enabled": true,
  "max_tokens": 2000,
  "temperature": 0.7
}
```

### Doubao配置
```json
{
  "provider": "doubao",
  "api_key": "your_doubao_key",
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "model": "doubao-lite-4k",
  "enabled": true,
  "max_tokens": 2000,
  "temperature": 0.7
}
```

### DeepSeek配置
```json
{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "enabled": true,
  "max_tokens": 2000,
  "temperature": 0.7
}
```

## 扩展开发

### 添加新的AI提供商

1. 在 `modules/ai/providers/` 目录下创建新的提供商文件
2. 继承 `AIProviderBase` 基类
3. 实现必要的抽象方法
4. 在 `providers/__init__.py` 中注册新提供商

示例：
```python
from ..base import AIProviderBase, AIModelConfig, ChatMessage, ChatResponse

class NewProvider(AIProviderBase):
    def get_headers(self, config: AIModelConfig) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }
    
    def format_messages(self, messages: List[ChatMessage]) -> List[Dict]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]
    
    # 实现其他抽象方法...
```

### 自定义提示词模板

```python
from modules.prompts import prompt_manager, PromptTemplate

# 创建新模板
template = PromptTemplate(
    id="custom_template",
    name="自定义模板",
    description="这是一个自定义模板",
    category="custom",
    template="处理以下内容：{content}",
    variables=["content"],
    system_prompt="你是一个专业助手",
    enabled=True
)

# 添加到管理器
prompt_manager.add_template(template)
```

## 最佳实践

### 1. 配置管理
- 使用环境变量存储敏感信息
- 定期轮换API密钥
- 为不同环境使用不同配置

### 2. 错误处理
- 实现重试机制
- 记录详细的错误日志
- 提供友好的错误信息

### 3. 性能优化
- 使用连接池
- 实现请求缓存
- 监控API调用频率

### 4. 安全考虑
- 验证输入参数
- 限制API调用频率
- 保护敏感配置信息

## 故障排除

### 常见问题

1. **连接超时**
   - 检查网络连接
   - 验证API端点URL
   - 调整超时设置

2. **认证失败**
   - 验证API密钥
   - 检查密钥权限
   - 确认账户余额

3. **模型不可用**
   - 检查模型名称
   - 验证模型权限
   - 查看提供商文档

### 日志查看

```bash
# 查看服务日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log
```

## 更新日志

### v1.0.0
- 初始版本发布
- 支持Qwen、Doubao、DeepSeek提供商
- 实现配置管理和提示词管理
- 添加健康检查功能

## 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 许可证

本项目采用MIT许可证，详见LICENSE文件。