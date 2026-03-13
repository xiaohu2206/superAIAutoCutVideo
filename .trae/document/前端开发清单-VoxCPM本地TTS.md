# 前端开发清单：VoxCPM 本地 TTS（含声音复刻）

## 目标

- 新增前端 VoxCPM TTS 功能模块，与后端 API 完全对接
- 复用 Qwen3-TTS 的 UI 组件和交互逻辑，保持一致的用户体验
- 支持模型下载、音色上传、克隆预处理、试听、删除等完整流程
- 集成到 TTS 设置页面，作为独立的 provider 选项

---

## 现有 Qwen3-TTS 前端实现参考

### 目录结构
```
frontend/src/features/qwen3Tts/
├── components/
│   ├── Qwen3VoiceSection.tsx          # 主音色管理区域
│   ├── Qwen3VoiceList.tsx             # 音色列表组件
│   ├── Qwen3VoiceUploadDialog.tsx     # 上传参考音频对话框
│   ├── Qwen3CustomRoleDialog.tsx      # 创建角色音色对话框
│   ├── Qwen3VoiceDesignDialog.tsx     # 设计克隆音色对话框
│   ├── Qwen3ModelOptionsList.tsx      # 模型下载选项列表
│   └── Qwen3CloneProgressItem.tsx     # 克隆进度条组件
├── hooks/
│   ├── useQwen3Voices.ts              # 音色列表和操作 hooks
│   └── useQwen3Models.ts              # 模型列表和下载 hooks
├── services/
│   └── qwen3TtsService.ts            # API 服务封装
└── types.ts                           # 类型定义
```

### 关键特性
- **模型管理**: 支持多个模型（base_0_6b, custom_0_6b 等），显示下载状态、校验状态
- **音色管理**: 支持三种创建模式（clone/custom_role/voice_design）
- **实时进度**: WebSocket 监听下载和克隆进度
- **试听功能**: 集成到通用 TTS 试听接口
- **状态同步**: 自动刷新列表，支持手动刷新

---

## VoxCPM 前端开发总体结构（参考 Qwen3-TTS）

建议新增以下模块：

### 1. 类型定义
- `frontend/src/features/voxcpmTts/types.ts`

### 2. API 服务
- `frontend/src/features/voxcpmTts/services/voxcpmTtsService.ts`

### 3. 自定义 Hooks
- `frontend/src/features/voxcpmTts/hooks/useVoxcpmVoices.ts`
- `frontend/src/features/voxcpmTts/hooks/useVoxcpmModels.ts`

### 4. 组件
- `frontend/src/features/voxcpmTts/components/VoxcpmVoiceSection.tsx`
- `frontend/src/features/voxcpmTts/components/VoxcpmVoiceList.tsx`
- `frontend/src/features/voxcpmTts/components/VoxcpmVoiceUploadDialog.tsx`
- `frontend/src/features/voxcpmTts/components/VoxcpmModelOptionsList.tsx`
- `frontend/src/features/voxcpmTts/components/VoxcpmCloneProgressItem.tsx`

### 5. 集成到设置页面
- 修改 `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`

---

## 开发清单（按阶段）

### A. 类型定义（必须先做）

- [ ] 创建 `frontend/src/features/voxcpmTts/types.ts`
  - 定义 `VoxcpmTtsModelStatus`（参考 Qwen3）
    - `key`, `path`, `exists`, `valid`, `missing`, `model_type`, `size`, `display_names`, `sources`
  - 定义 `VoxcpmTtsVoiceStatus`（参考 Qwen3）
    - `"uploaded" | "cloning" | "ready" | "failed"`
  - 定义 `VoxcpmTtsVoice`（参考 Qwen3）
    - `id`, `name`, `kind`, `model_key`, `language`, `ref_audio_path`, `ref_audio_url`, `ref_text`, `status`, `progress`, `last_error`, `meta`, `created_at`, `updated_at`
  - 定义 `VoxcpmTtsDownloadProvider`（仅 modelscope）
    - `"modelscope"`
  - 定义 `VoxcpmTtsDownloadTask`（参考 Qwen3）
    - `key`, `provider`, `progress`, `message`, `phase`, `status`, `downloaded_bytes`, `total_bytes`
  - 定义 `VoxcpmTtsUploadVoiceInput`（参考 Qwen3）
    - `file`, `name`, `model_key`, `language`, `ref_text`
  - 定义 `VoxcpmTtsPatchVoiceInput`（参考 Qwen3）
    - `Partial<Pick<VoxcpmTtsVoice, "name" | "model_key" | "language" | "ref_text">>`
  - 定义 `VoxcpmTtsRuntimeStatus`（可选，参考 Qwen3）
    - `loaded`, `model_key`, `model_path`, `device`, `precision`, `last_device_error`

验收口径：
- [ ] 类型定义完整，与后端 API 响应结构一致
- [ ] 支持类型推导和 IDE 自动补全

---

### B. API 服务封装

- [ ] 创建 `frontend/src/features/voxcpmTts/services/voxcpmTtsService.ts`
  - `getRuntimeStatus()`: GET `/api/tts/voxcpm/runtime-status`
  - `listModels()`: GET `/api/tts/voxcpm/models`
  - `validateModel(key)`: POST `/api/tts/voxcpm/models/validate`
  - `downloadModel(key, provider)`: POST `/api/tts/voxcpm/models/download`
  - `stopDownload(key)`: POST `/api/tts/voxcpm/models/downloads/{key}/stop`
  - `listDownloadTasks()`: GET `/api/tts/voxcpm/models/downloads`
  - `openModelDirInExplorer(key)`: GET `/api/tts/voxcpm/models/open-path`
  - `listVoices()`: GET `/api/tts/voxcpm/voices`
  - `getVoice(id)`: GET `/api/tts/voxcpm/voices/{id}`
  - `uploadVoice(input)`: POST `/api/tts/voxcpm/voices/upload`（FormData）
  - `patchVoice(id, partial)`: PATCH `/api/tts/voxcpm/voices/{id}`
  - `deleteVoice(id, removeFiles)`: DELETE `/api/tts/voxcpm/voices/{id}?remove_files={bool}`
  - `startClone(id)`: POST `/api/tts/voxcpm/voices/{id}/clone`
  - `getCloneStatus(id)`: GET `/api/tts/voxcpm/voices/{id}/clone-status`

验收口径：
- [ ] 所有 API 方法与后端路由一一对应
- [ ] 正确处理 FormData 上传
- [ ] 正确处理查询参数和路径参数

---

### C. 自定义 Hooks（状态管理）

- [ ] 创建 `frontend/src/features/voxcpmTts/hooks/useVoxcpmModels.ts`
  - `models`: 模型列表（`VoxcpmTtsModelStatus[]`）
  - `modelByKey`: 模型字典（`Record<string, VoxcpmTtsModelStatus>`）
  - `loading`: 加载状态
  - `error`: 错误信息
  - `downloadsByKey`: 下载任务字典（`Record<string, VoxcpmTtsDownloadTask>`）
  - `refresh()`: 刷新模型列表
  - `validate(key)`: 校验模型
  - `downloadModel(key, provider)`: 启动下载
  - `stopDownload(key)`: 停止下载
  - `openModelDirInExplorer(key)`: 打开模型目录
  - 监听 WebSocket 进度（scope: `voxcpm_tts_models`）

- [ ] 创建 `frontend/src/features/voxcpmTts/hooks/useVoxcpmVoices.ts`
  - `voices`: 音色列表（`VoxcpmTtsVoice[]`）
  - `loading`: 加载状态
  - `error`: 错误信息
  - `cloneEventByVoiceId`: 克隆事件字典（`Record<string, { type, phase, message, progress }>`）
  - `refresh()`: 刷新音色列表
  - `upload(input)`: 上传参考音频
  - `patch(id, partial)`: 更新音色
  - `remove(id, removeFiles)`: 删除音色
  - `startClone(id)`: 启动克隆预处理
  - 监听 WebSocket 进度（scope: `voxcpm_tts_voice_clone`）

验收口径：
- [ ] Hooks 提供完整的 CRUD 操作
- [ ] WebSocket 进度实时更新
- [ ] 错误处理和加载状态管理

---

### D. UI 组件开发

#### D.1 模型选项列表组件

- [ ] 创建 `frontend/src/features/voxcpmTts/components/VoxcpmModelOptionsList.tsx`
  - 参考 `Qwen3ModelOptionsList.tsx` 的布局和交互
  - 显示 VoxCPM 模型选项：
    - `voxcpm_0_5b`: VoxCPM-0.5B（约 1.6GB）
    - `voxcpm_1_5b`: VoxCPM1.5（约 1.95GB）
  - 每个选项显示：
    - 模型名称和大小
    - 状态徽章（未发现/可用/缺文件）
    - 下载源选择（仅 modelscope）
    - 下载/停止/校验/打开目录按钮
    - 下载进度条（使用 `VoxcpmCloneProgressItem`）
  - 支持复制模型目录路径

验收口径：
- [ ] UI 布局与 Qwen3 一致
- [ ] 下载进度实时显示
- [ ] 按钮状态正确（下载中禁用等）

#### D.2 音色列表组件

- [ ] 创建 `frontend/src/features/voxcpmTts/components/VoxcpmVoiceList.tsx`
  - 参考 `Qwen3VoiceList.tsx` 的布局和交互
  - 每个音色显示：
    - 试听按钮（播放/暂停/加载中）
    - 音色名称、类型徽章（克隆）
    - 状态徽章（已上传/处理中/可用/失败）
    - 模型和语言信息
    - 克隆进度条（使用 `VoxcpmCloneProgressItem`）
    - 错误信息（失败时）
    - 选择按钮（仅 ready 状态）
    - 编辑按钮
    - 克隆按钮（仅 uploaded/failed 状态）
    - 删除按钮（带确认对话框）
  - 支持删除确认对话框（带"同时删除本地音频文件"选项）
  - 支持按更新时间排序

验收口径：
- [ ] 音色卡片布局与 Qwen3 一致
- [ ] 试听功能正常（调用通用 TTS 试听接口）
- [ ] 克隆进度实时显示
- [ ] 删除确认对话框完整

#### D.3 音色上传对话框

- [ ] 创建 `frontend/src/features/voxcpmTts/components/VoxcpmVoiceUploadDialog.tsx`
  - 参考 `Qwen3VoiceUploadDialog.tsx` 的布局和交互
  - 表单字段：
    - 文件上传（支持 wav/mp3/m4a/flac/ogg/aac）
    - 音色名称（可选，默认使用文件名）
    - 模型选择（voxcpm_0_5b / voxcpm_1_5b）
    - 语言选择（Auto/zh/en）
    - 参考文本（可选）
  - 支持编辑模式（传入 voice 对象）
  - 上传成功后自动开始克隆（可选）

验收口径：
- [ ] 表单验证完整
- [ ] 文件类型限制正确
- [ ] 上传成功后关闭对话框

#### D.4 克隆进度组件

- [ ] 创建 `frontend/src/features/voxcpmTts/components/VoxcpmCloneProgressItem.tsx`
  - 参考 `Qwen3CloneProgressItem.tsx` 的布局
  - 显示进度条、当前阶段、消息
  - 支持不同阶段显示不同颜色

验收口径：
- [ ] 进度条动画流畅
- [ ] 阶段文本清晰

#### D.5 主音色管理区域组件

- [ ] 创建 `frontend/src/features/voxcpmTts/components/VoxcpmVoiceSection.tsx`
  - 参考 `Qwen3VoiceSection.tsx` 的布局和交互
  - 包含两个主要区域：
    1. 模型管理区域
       - 标题和说明
       - 模型选项列表（`VoxcpmModelOptionsList`）
       - 刷新按钮
    2. 音色列表区域
       - 标题和数量
       - 音色列表（`VoxcpmVoiceList`）
  - 集成 `useVoxcpmModels` 和 `useVoxcpmVoices` hooks
  - 处理所有对话框状态（上传/编辑）
  - 处理音色激活回调

验收口径：
- [ ] 两个区域布局清晰
- [ ] 所有交互功能正常
- [ ] 对话框状态管理正确

---

### E. 集成到 TTS 设置页面

- [ ] 修改 `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`
  - 在 provider 判断中添加 `voxcpm_tts` 分支：
    ```tsx
    {provider === "voxcpm_tts" ? (
      <VoxcpmVoiceSection
        configId={currentConfigId}
        activeVoiceId={currentConfig?.active_voice_id || ""}
        onSetActive={handleSetActiveVoice}
      />
    ) : /* 其他 provider */}
    ```
  - 导入 `VoxcpmVoiceSection` 组件

验收口径：
- [ ] 切换到 voxcpm_tts provider 时显示 VoxCPM 音色管理区域
- [ ] 切换到其他 provider 时隐藏
- [ ] 音色激活功能正常

---

### F. WebSocket 进度监听

- [ ] 在 `useVoxcpmModels.ts` 中监听 `voxcpm_tts_models` scope
  - 处理事件类型：`progress`, `completed`, `error`, `cancelled`
  - 更新 `downloadsByKey` 状态
  - 下载完成后自动刷新模型列表

- [ ] 在 `useVoxcpmVoices.ts` 中监听 `voxcpm_tts_voice_clone` scope
  - 处理事件类型：`progress`, `completed`, `error`
  - 更新 `cloneEventByVoiceId` 状态
  - 克隆完成后自动刷新音色列表

验收口径：
- [ ] 进度实时更新
- [ ] 下载/克隆完成后自动刷新列表
- [ ] 错误信息正确显示

---

### G. 错误处理和用户体验

- [ ] 统一错误提示（使用 `message` 服务）
  - 下载失败提示
  - 校验失败提示（显示缺失文件）
  - 上传失败提示
  - 克隆失败提示
  - 删除失败提示
  - 试听失败提示

- [ ] 加载状态显示
  - 列表加载中显示骨架屏或加载动画
  - 按钮操作中显示加载状态并禁用

- [ ] 空状态提示
  - 无模型时提示用户下载
  - 无音色时提示用户创建

验收口径：
- [ ] 所有错误都有友好的中文提示
- [ ] 加载状态清晰可见
- [ ] 空状态有引导性提示

---

## 建议的命名和约定（对齐 Qwen3-TTS）

- **目录**: `frontend/src/features/voxcpmTts/`
- **组件前缀**: `Voxcpm`（如 `VoxcpmVoiceSection`）
- **Hook 前缀**: `useVoxcpm`（如 `useVoxcpmVoices`）
- **Service**: `voxcpmTtsService`
- **Type 前缀**: `VoxcpmTts`（如 `VoxcpmTtsVoice`）
- **WS Scope**: `voxcpm_tts_models`, `voxcpm_tts_voice_clone`
- **颜色主题**: 与 Qwen3 保持一致，但可调整主色调（如使用橙色系区分）

---

## 与 Qwen3-TTS 的主要差异

### 后端差异
- VoxCPM 仅支持 voice_clone 模式（无 custom_role/voice_design）
- VoxCPM 仅支持 modelscope 下载源（无 hf）
- VoxCPM 模型校验规则不同（需要 audiovae.pth）
- VoxCPM 无加速状态 API（无 `/acceleration-status`）

### 前端差异
- **创建模式**: VoxCPM 仅支持 "clone" 模式（上传参考音频）
- **模型选项**: 仅两个模型（voxcpm_0_5b, voxcpm_1_5b）
- **下载源**: 仅显示 modelscope（不显示 hf 选项）
- **音色类型**: 仅 "clone"（不显示 custom_role/voice_design 图标和标签）
- **加速状态**: 不显示 GPU 加速检测按钮

### 简化点
- 不需要 `Qwen3CustomRoleDialog` 和 `Qwen3VoiceDesignDialog` 组件
- 不需要 `useQwen3Models` 中的 `refreshAcceleration` 逻辑
- 不需要 `Qwen3VoiceSection` 中的创建模式切换（clone/custom_role/voice_design）

---

## 开发优先级建议

### P0（核心功能）
1. 类型定义
2. API 服务封装
3. `useVoxcpmModels` hook
4. `useVoxcpmVoices` hook
5. `VoxcpmModelOptionsList` 组件
6. `VoxcpmVoiceList` 组件
7. `VoxcpmVoiceUploadDialog` 组件
8. `VoxcpmVoiceSection` 组件
9. 集成到 TtsSettings.tsx

### P1（增强体验）
1. WebSocket 进度监听
2. `VoxcpmCloneProgressItem` 组件
3. 错误处理和加载状态
4. 空状态提示

### P2（优化）
1. 模型大小显示优化（自动转换为 GB/MB）
2. 下载速度计算
3. 音色列表搜索/过滤
4. 批量操作（如批量删除）

---

## 验收标准

### 功能验收
- [ ] 可以成功下载 VoxCPM 模型（0.5B 和 1.5B）
- [ ] 可以上传参考音频并创建音色
- [ ] 可以启动克隆预处理并查看进度
- [ ] 克隆完成后音色状态变为 ready
- [ ] 可以试听 ready 状态的音色
- [ ] 可以选择音色并设为当前音色
- [ ] 可以编辑音色信息
- [ ] 可以删除音色（带文件删除选项）
- [ ] 可以校验模型完整性
- [ ] 可以打开模型目录

### UI/UX 验收
- [ ] 界面布局与 Qwen3-TTS 保持一致
- [ ] 所有按钮状态正确（禁用/加载中）
- [ ] 进度条动画流畅
- [ ] 错误提示清晰友好
- [ ] 加载状态明显可见
- [ ] 空状态有引导提示

### 集成验收
- [ ] 在 TTS 设置中切换到 voxcpm_tts provider 时显示 VoxCPM 音色管理区域
- [ ] 音色激活后可以在视频生成中使用
- [ ] 试听功能正常工作
- [ ] WebSocket 进度实时更新

---

## 注意事项

⚠️ **API 差异**:
- VoxCPM 的模型校验需要检查 `audiovae.pth` 文件
- VoxCPM 的下载进度结构与 Qwen3 略有不同
- VoxCPM 的克隆事件字段与 Qwen3 一致

⚠️ **UI 简化**:
- VoxCPM 不需要 custom_role 和 voice_design 模式
- 不需要 GPU 加速检测
- 下载源仅支持 modelscope

⚠️ **兼容性**:
- 确保与现有 TTS 配置系统兼容
- 确保与通用试听接口兼容
- 确保与 WebSocket 消息系统兼容

⚠️ **性能**:
- 大文件上传时显示进度
- 模型下载时避免频繁刷新
- 音色列表分页或虚拟滚动（如果数量很多）

---

## 参考文件

### 后端 API
- `backend/routes/voxcpm_tts_routes.py`
- `backend/modules/voxcpm_tts_model_manager.py`
- `backend/modules/voxcpm_tts_voice_store.py`
- `backend/modules/voxcpm_tts_service.py`

### 前端参考
- `frontend/src/features/qwen3Tts/components/Qwen3VoiceSection.tsx`
- `frontend/src/features/qwen3Tts/components/Qwen3VoiceList.tsx`
- `frontend/src/features/qwen3Tts/components/Qwen3ModelOptionsList.tsx`
- `frontend/src/features/qwen3Tts/services/qwen3TtsService.ts`
- `frontend/src/features/qwen3Tts/types.ts`
- `frontend/src/features/qwen3Tts/hooks/useQwen3Voices.ts`
- `frontend/src/features/qwen3Tts/hooks/useQwen3Models.ts`
- `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`

### 集成点
- `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx` (L355-395)
