# 字幕独立 Executor 改造落地方案

## 背景

当前“字幕提取”和“镜头分割”虽然是两个不同业务流程，但在后端执行层面会竞争同一个 `asyncio` 默认线程池，导致两者同时执行时，字幕提取明显变慢。这里的关键点不是 BcutASR 是否为远程服务，而是字幕提取流程中仍然存在需要本地线程承载的阻塞步骤。

当前现状：

- 字幕提取中的 `_run_in_thread(...)` 使用 `loop.run_in_executor(None, ...)`
- 镜头分割中的 `model.predict_video(...)` 也使用 `loop.run_in_executor(None, ...)`
- `None` 表示共用事件循环默认 executor

因此，当镜头分割提交大量重任务后，会挤占默认线程池与本地 CPU / I/O 资源，进而拖慢字幕提取中的：

- `BcutASR.test_connection`
- `BcutASR.run`
- 本地音频准备后的请求发起阶段
- 其他依赖线程调度的同步步骤

## 目标

本次改造的目标是：

1. 将字幕提取改为使用独立 executor，不再占用默认 executor
2. 尽量减少改动范围，优先保证稳定性
3. 保持现有业务流程、接口协议、WebSocket 推送逻辑不变
4. 为后续继续优化镜头并发预留空间

## 改造策略

采用“字幕独立 executor，镜头逻辑暂不大改”的最小可落地方案。

### 方案核心

在 `backend/services/extract_subtitle_service.py` 中：

1. 引入 `ThreadPoolExecutor`
2. 创建模块级单例 `_SUBTITLE_EXECUTOR`
3. 将 `_run_in_thread(...)` 改为使用 `_SUBTITLE_EXECUTOR`
4. 通过环境变量允许后续调整字幕线程池大小

这样可以做到：

- 字幕任务不再和镜头任务争抢默认线程池
- 改动点集中，回归风险低
- 便于灰度验证和快速回退

## 建议参数

### 字幕 executor 默认并发

建议默认值：

- `SUBTITLE_EXECUTOR_MAX_WORKERS=2`

原因：

- `1` 过于保守，多项目并发时容易排队
- `2` 对当前远程 BcutASR 场景较稳妥
- 不建议默认给太大，避免本地线程数膨胀

如果后续压测显示字幕任务并发更多，可以再调整到 `3` 或 `4`。

## 精确修改点

## 1. 修改文件

`backend/services/extract_subtitle_service.py`

## 2. 引入线程池依赖

在文件顶部 imports 区域增加：

```python
from concurrent.futures import ThreadPoolExecutor
```

建议放在标准库 import 区域，与 `asyncio`、`json`、`logging`、`os` 等同级。

## 3. 新增字幕 executor 配置函数与单例

建议在 `logger = logging.getLogger(__name__)` 下方增加以下内容：

```python
def _subtitle_executor_max_workers() -> int:
    raw = str(os.environ.get("SUBTITLE_EXECUTOR_MAX_WORKERS") or "").strip()
    try:
        value = int(raw)
        if value > 0:
            return value
    except Exception:
        pass
    return 2


_SUBTITLE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_subtitle_executor_max_workers(),
    thread_name_prefix="subtitle_worker",
)
```

### 说明

- 使用模块级单例，避免每次请求都新建线程池
- `thread_name_prefix` 便于后续排查线程问题
- 环境变量为空或非法时，回退到默认值 `2`

## 4. 修改 `_run_in_thread(...)`

当前代码：

```python
async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
```

改为：

```python
async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _SUBTITLE_EXECUTOR,
        lambda: func(*args, **kwargs),
    )
```

### 影响范围

该修改会影响当前文件中所有通过 `_run_in_thread(...)` 调用的逻辑，主要包括：

- `BcutASR.test_connection`
- `BcutASR.run`

也就是说，字幕提取相关的同步阻塞步骤将统一切到字幕专用线程池执行。

## 推荐代码示例

以下是可以直接落地的完整示意片段。

```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from modules.projects_store import projects_store, Project
from modules.app_paths import uploads_dir as app_uploads_dir, resolve_uploads_path, to_uploads_web_path
from modules.video_processor import video_processor
from modules.ws_manager import manager
from modules.fun_asr_service import fun_asr_service
from modules.fun_asr_model_manager import FunASRPathManager, validate_model_dir
from services.asr_bcut import BcutASR
from services.asr_utils import utterances_to_srt


logger = logging.getLogger(__name__)


def _subtitle_executor_max_workers() -> int:
    raw = str(os.environ.get("SUBTITLE_EXECUTOR_MAX_WORKERS") or "").strip()
    try:
        value = int(raw)
        if value > 0:
            return value
    except Exception:
        pass
    return 2


_SUBTITLE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_subtitle_executor_max_workers(),
    thread_name_prefix="subtitle_worker",
)


async def _run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _SUBTITLE_EXECUTOR,
        lambda: func(*args, **kwargs),
    )
```

## 为什么这是当前最稳妥的改法

### 1. 改动面最小

只动 `extract_subtitle_service.py`，不需要同步重构镜头服务的大量代码。

### 2. 回归风险最低

- 不改变接口参数
- 不改变返回结构
- 不改变任务状态机
- 不改变 WebSocket 消息协议
- 不改变项目存储结构

### 3. 能直接切断“默认线程池争用”问题

镜头服务当前使用：

- `loop.run_in_executor(None, ...)`

字幕服务改造后使用：

- `loop.run_in_executor(_SUBTITLE_EXECUTOR, ...)`

这样两者在线程池层面就不再直接竞争。

## 这次改造不能完全解决的问题

需要明确，这次改造解决的是“线程池争用”，但不能完全消除以下问题：

### 1. 视频文件 I/O 竞争

如果字幕提取正在做音频提取，而镜头分割同时在高并发解码同一个视频文件，依然会有磁盘读竞争。

### 2. CPU 被镜头分析打满

即使字幕有独立 executor，如果镜头分析本身占满 CPU，字幕提取中的其他本地步骤仍可能受到影响。

### 3. 镜头默认并发过高

当前镜头服务存在如下逻辑：

```python
effective_concurrency = total_chunks if max_chunk_concurrency <= 0 else max_chunk_concurrency
```

这意味着在未配置 `TRANSNETV2_MAX_CONCURRENCY` 时，镜头分割可能按总 chunk 数全并发执行。这个策略非常激进，后续建议单独收敛。

## 建议的后续优化顺序

如果字幕独立 executor 上线后仍然观察到明显变慢，建议按以下顺序继续处理。

### 第一步：先上线字幕独立 executor

验证指标：

- 单独跑字幕的耗时
- 字幕 + 镜头同时跑的耗时
- BcutASR 请求启动延迟是否下降

### 第二步：收紧镜头默认并发

建议把默认逻辑从：

```python
effective_concurrency = total_chunks if max_chunk_concurrency <= 0 else max_chunk_concurrency
```

改为：

```python
effective_concurrency = max_chunk_concurrency if max_chunk_concurrency > 0 else 1
```

或者折中版：

```python
effective_concurrency = max_chunk_concurrency if max_chunk_concurrency > 0 else min(2, total_chunks)
```

### 第三步：必要时再给镜头服务也拆独立 executor

如果后续希望彻底隔离线程池资源，可再将 `extract_scene_service.py` 中的 `predict_video(...)` 改为使用独立 scene executor。

## 回归测试建议

本次改造完成后，至少验证以下场景：

### 场景 1：仅字幕提取

验证：

- Bcut 模式正常提取
- 任务状态正常
- WebSocket 进度正常
- 字幕文件正常落盘

### 场景 2：镜头分割与字幕提取同时启动

验证：

- 字幕仍能正常完成
- 总耗时较改造前有改善
- 无任务卡死、无超时异常

### 场景 3：多项目并发字幕提取

验证：

- 线程池大小为 2 时是否出现异常排队
- 结果是否串项目
- 任务状态是否互相污染

### 场景 4：异常路径

验证：

- Bcut 服务不可用时，错误处理是否正常
- 字幕线程池切换后，异常栈是否仍可正常定位

## 环境变量建议

建议新增以下可选环境变量：

```bash
SUBTITLE_EXECUTOR_MAX_WORKERS=2
```

### 推荐上线策略

- 开发环境先用默认值 `2`
- 如需压测，可分别测试 `1 / 2 / 4`
- 生产环境建议先从 `2` 开始

## 落地结论

本次最稳妥、最小改动、可直接上线的方案是：

1. 在 `extract_subtitle_service.py` 中创建模块级 `_SUBTITLE_EXECUTOR`
2. `_run_in_thread(...)` 改为使用 `_SUBTITLE_EXECUTOR`
3. 默认 `SUBTITLE_EXECUTOR_MAX_WORKERS=2`
4. 镜头服务先不做大改，只作为下一阶段优化项

该方案可以优先解决“字幕与镜头共用默认 executor”带来的互相争抢问题，属于当前阶段最适合先落地的改法。
