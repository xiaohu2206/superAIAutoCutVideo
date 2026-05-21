# narration_type 新增解说类型改造清单

> 目标：在现有“短剧解说”“电影解说”基础上，扩展“电视剧解说”“漫剧解说”等类型，并避免继续把类型判断散落在前后端和提示词代码里。

## 一、当前结论

当前 `narration_type` 不是一个纯展示字段，它会影响：

1. 创建项目时可选的解说类型。
2. 项目保存的默认类型和后续接口透传。
3. 文案生成使用哪一类提示词 category。
4. 解说脚本生成时使用哪一套输出格式要求。
5. 电影解说专属的“影片信息”“洗稿参考文案”入口和生成上下文。
6. 高级配置中可选提示词列表的分类。

目前代码里主要是二分逻辑：

- `电影解说` -> `movie_narration`
- 其他所有类型 -> `short_drama_narration`

所以如果只在前端下拉里加“电视剧解说”“漫剧解说”，功能能创建项目，但后续基本会按“短剧解说”的提示词和脚本格式走，不会有独立提示词语境。

## 二、全局命中点

### 1. 前端类型定义

文件：`frontend/src/types/project.ts`

相关位置：

- `NarrationType` 枚举：当前只有 `SHORT_DRAMA = "短剧解说"`、`MOVIE = "电影解说"`。
- `Project.narration_type`、`CreateProjectRequest.narration_type`、`UpdateProjectRequest.narration_type`、`GenerateScriptRequest.narration_type`、`GenerateCopywritingRequest.narration_type` 都依赖这个枚举。

改造点：

- 增加：
  - `TV_DRAMA = "电视剧解说"`
  - `COMIC_DRAMA = "漫剧解说"` 或 `ANIMATED_COMIC = "漫剧解说"`，命名按团队习惯定。
- 如果未来类型会频繁扩展，建议从硬编码 enum 迁移到配置数组，例如 `NARRATION_TYPE_OPTIONS`，枚举只作为兼容层。

### 2. 创建项目弹窗

文件：`frontend/src/components/projectManagement/CreateProjectModal.tsx`

相关位置：

- 提交 payload 中传 `narration_type: narrationType`。
- 表单重置默认值为 `NarrationType.SHORT_DRAMA`。
- 下拉选项当前只有“短剧解说”“电影解说”。

改造点：

- 在下拉里增加“电视剧解说”“漫剧解说”。
- 更推荐抽成统一配置：
  - `frontend/src/constants/narrationTypes.ts`
  - `NARRATION_TYPE_OPTIONS = [{ label, value, promptCategory, defaultScriptLength, supportsFilmContext }]`
- 创建、重置、展示全部复用配置，避免多处补选项。

### 3. 项目卡片展示

文件：`frontend/src/components/projectManagement/ProjectCard.tsx`

相关位置：

- 直接展示 `project.narration_type`。

改造点：

- 如果继续存中文值，这里无需改。
- 如果以后存 code，例如 `tv_drama_narration`，这里要通过映射展示中文 label。

### 4. 生成流程透传

文件：`frontend/src/hooks/useProjectEditGenerateStep.ts`

相关位置：

- 生成文案请求传 `narration_type: project.narration_type`。
- 生成脚本请求传 `narration_type: project.narration_type`。

改造点：

- 这里本身不用加分支。
- 但后端不能只依赖请求中的中文字符串，应以后端项目内保存的 `narration_type` 为准，避免前端传错导致提示词分类不一致。

## 三、后端数据模型与接口

### 1. Project 模型和项目存储

文件：`backend/modules/projects_store.py`

相关位置：

- `Project.narration_type` 默认值为“短剧解说”。
- `_get_default_script_length()` 根据类型包含“电影”或“短剧”返回默认长度。
- `create_project()` 默认 `narration_type="短剧解说"`。
- `update_project()` 白名单允许更新 `narration_type`。

改造点：

- 增加统一后端配置模块，例如：
  - `backend/modules/narration_types.py`
  - 字段包括：`value`、`category`、`label`、`default_script_length`、`output_format_kind`、`supports_film_context`、`source_label`
- `_get_default_script_length()` 不再用字符串包含判断，改为查配置。
- 当前 `create_project()` 实际写入 `script_length="auto"`，没有调用 `_get_default_script_length()`。需要确认这个方法是否已废弃；如果保留，应接入配置或删除死代码。

建议配置示例：

```python
NARRATION_TYPE_CONFIG = {
    "短剧解说": {
        "category": "short_drama_narration",
        "default_script_length": "30～50条",
        "output_format": "short_drama",
        "source_label": "原剧",
        "supports_film_context": False,
    },
    "电影解说": {
        "category": "movie_narration",
        "default_script_length": "60～80条",
        "output_format": "movie",
        "source_label": "原片",
        "supports_film_context": True,
    },
    "电视剧解说": {
        "category": "tv_drama_narration",
        "default_script_length": "40～70条",
        "output_format": "short_drama",
        "source_label": "原剧",
        "supports_film_context": True,
    },
    "漫剧解说": {
        "category": "comic_drama_narration",
        "default_script_length": "30～60条",
        "output_format": "short_drama",
        "source_label": "原漫",
        "supports_film_context": False,
    },
}
```

### 2. Project API 请求模型

文件：`backend/routes/project_routes.py`

相关位置：

- `CreateProjectRequest.narration_type` 默认“短剧解说”。
- `UpdateProjectRequest.narration_type` 可选。
- `GenerateScriptRequest.narration_type`、`GenerateCopywritingRequest.narration_type` 为必传字符串。
- 创建项目接口把 `req.narration_type or "短剧解说"` 传给 store。

改造点：

- 增加服务端校验：只允许配置中存在的类型。
- 对旧数据/空值保留默认“短剧解说”。
- 如果接口继续传中文值，校验时要 trim。
- 如果改成 code，需加迁移兼容：接受旧中文值并转换。

### 3. AI 路由

文件：`backend/routes/project_ai_routes.py`

相关位置：

- `generate-script`、`generate-copywriting` 记录并透传 `narration_type`。

改造点：

- 路由层无需知道具体类型。
- 可以在 service 层统一读取项目类型并做校验，路由继续负责日志和任务控制。

## 四、提示词与文案生成

### 1. 文案生成入口

文件：`backend/services/generate_copywriting_service.py`

相关位置：

- `_movie_narration_film_context()` 只有 `narration_type` 包含“电影解说”才启用影片信息。
- `_movie_narration_reference_copywriting()` 只有“电影解说”才启用参考文案洗稿。
- `generate_copywriting()` 将 `film_context`、`reference_copywriting` 传入 `ScriptGenerationService.generate_copywriting_pipeline*()`。

改造点：

- 不建议继续写 `_movie_*` 专属函数。
- 改成通用能力判断：
  - `supports_context(narration_type)`
  - `supports_reference_copywriting(narration_type)`
  - `context_label(narration_type)`，例如电影=影片信息，电视剧=剧集信息，漫剧=作品设定。
- 对“电视剧解说”建议开启背景信息能力；对“漫剧解说”视业务需要决定。
- 元数据字段当前叫 `film_context_included`，如果扩展类型，应改为 `context_included`，保留旧字段兼容也可以。

### 2. 默认 prompt category 解析

文件：`backend/services/script_generation/prompt_resolver.py`

相关位置：

- `_default_prompt_key_for_project()` 当前判断：
  - `narration_type == "电影解说"` -> `movie_narration`
  - 其他 -> `short_drama_narration`

改造点：

- 改为查配置：
  - `category = get_narration_category(p.narration_type)`
  - 返回 `f"{category}:script_generation"`
- 这是文案生成选择提示词的核心位置，必须改。

### 3. copywriting builder 注册 fallback

文件：`backend/services/script_generation/copywriting_builder.py`

相关位置：

- `_resolve_template_key()` 使用 `_default_prompt_key_for_project()`。
- `_build_template_messages()` 在 KeyError fallback 时只支持：
  - `movie_narration` -> `modules.prompts.movie_narration.register_prompts`
  - 其他 -> `modules.prompts.short_drama_narration.register_prompts`

改造点：

- 改为动态 import：
  - `importlib.import_module(f"modules.prompts.{cat}")`
  - 如果模块存在且有 `register_prompts()`，执行注册。
  - 不存在则回退到 `short_drama_narration` 或抛出清晰错误。
- 新增类型要保证 `backend/modules/prompts/<category>/__init__.py` 提供 `register_prompts()`。

### 4. PromptManager 对用户模板的短剧前置补充

文件：`backend/modules/prompts/prompt_manager.py`

相关位置：

- `render_prompt()` 里 `_preamble(cat)` 只对 `short_drama_narration` 添加字幕、剧情概述和“为短剧《xxx》创作”的补充。

改造点：

- 如果用户自定义模板也要支持电视剧/漫剧，应改成按配置生成 preamble。
- 示例：
  - `short_drama_narration` -> “为短剧《xxx》...”
  - `tv_drama_narration` -> “为电视剧/剧集《xxx》...”
  - `comic_drama_narration` -> “为漫剧《xxx》...”
- 否则新增类型的用户模板可能缺少素材注入说明。

## 五、提示词模块新增

当前已有：

- `backend/modules/prompts/short_drama_narration`
- `backend/modules/prompts/movie_narration`

新增类型有两种方案。

### 方案 A：最低成本复用短剧提示词

适合快速上线“电视剧解说”“漫剧解说”选项。

改造方式：

- 后端配置里将：
  - “电视剧解说” -> `short_drama_narration`
  - “漫剧解说” -> `short_drama_narration`
- 前端下拉增加选项。
- 高级配置仍展示短剧提示词。

风险：

- 文案里会出现“短剧”“原剧”等语境，不够精确。
- 无法为电视剧/漫剧沉淀独立官方模板。

### 方案 B：新增独立 prompt category（推荐）

新增目录：

- `backend/modules/prompts/tv_drama_narration`
- `backend/modules/prompts/comic_drama_narration`

每个目录需要：

- `__init__.py`，实现 `register_prompts()`
- `script_generation.py`，实现对应 `TextPrompt`
- 可选：复制并改写 `movie_narration/script_generation.py` 或 `short_drama_narration/script_generation.py`
- 注册通用风格提示词：
  - `register_common_style_prompts_for_category("tv_drama_narration", "电视剧")`
  - `register_common_style_prompts_for_category("comic_drama_narration", "漫剧")`
- 注册幽默风格：
  - `HumorScriptGenerationPrompt(category="tv_drama_narration", label="电视剧")`
  - `HumorScriptGenerationPrompt(category="comic_drama_narration", label="漫剧")`

注意：

- `register_common_style_prompts_for_category()` 当前只对“短剧”做了大量“电影 -> 短剧”的文本替换。它接收任意 label，但内部替换逻辑并不是完全泛化的。
- 如果 label 是“电视剧”“漫剧”，需要确认 `CommonStyleScriptPrompt` 是否只是替换标题/描述，还是正文仍保留“电影解说”。目前正文主要来自 common markdown，存在大量“电影解说”表达。

## 六、脚本生成 output format 改造

### 1. 字幕脚本生成

文件：`backend/services/script_generation/script_builder.py`

相关位置：

- `_detect_narration_type()` 当前只识别“电影解说”，否则返回 `short_drama_narration`。
- `_generate_script_chunk()` 根据 `narration_type == "movie_narration"` 选择 `output_format_blocks.movie()`，否则 `short_drama()`。

改造点：

- `_detect_narration_type()` 改为查配置，返回 category 或 output_format。
- `output_format_blocks` 不应只有 movie/short_drama 二选一。
- 最低成本：电视剧/漫剧先复用 `short_drama()`。
- 推荐：将 `movie()`、`short_drama()` 泛化为：
  - `build_output_format_block(language, original_ratio, interleave_mode, source_label="原片")`
  - 电影 source_label=原片，短剧/电视剧=原剧，漫剧=原漫。

### 2. 视觉脚本生成

文件：`backend/services/script_generation/visual_script_builder.py`

相关位置：

- `_detect_narration_type()` 同样只识别“电影解说”。
- `_generate_visual_script_chunk()` 同样 movie/short_drama 二选一。

改造点：

- 与 `script_builder.py` 保持一致，建议抽公共 helper，避免两份逻辑再次分叉。

### 3. output_format_blocks

文件：`backend/modules/prompts/common/output_format_blocks.py`

相关位置：

- `short_drama()`、`movie()` 两个函数内容高度相似，主要差异是示例 narration 文字和“播放原片”表达。

改造点：

- 建议新增通用函数并保留旧函数兼容：

```python
def build_output_format_block(
    language: str = "zh",
    original_ratio: Optional[int] = None,
    interleave_mode: Optional[str] = None,
    original_label: str = "原片",
) -> str:
    ...

def movie(...):
    return build_output_format_block(..., original_label="原片")

def short_drama(...):
    return build_output_format_block(..., original_label="原剧")
```

- 新类型再通过配置传 `original_label`。

## 七、前端高级配置与电影专属能力

### 1. 提示词分类选择

文件：`frontend/src/hooks/usePrompts.ts`

相关位置：

- `NarrationType.MOVIE` -> `movie_narration`
- `NarrationType.SHORT_DRAMA` 或默认 -> `short_drama_narration`

改造点：

- 增加“电视剧解说”“漫剧解说”的映射。
- 推荐前端也使用统一配置：
  - `getPromptCategoryByNarrationType(narrationType)`

### 2. 文案高级配置组件

文件：

- `frontend/src/components/projectEdit/GenerateAdvancedConfigSection.tsx`
- `frontend/src/components/projectEdit/advancedConfig/CopywritingAdvancedConfig.tsx`

相关点：

- 都调用 `usePrompts(projectId, narrationType)`。

改造点：

- 如果 `usePrompts` 已配置化，这两个组件不需要单独改。
- 新增 category 后，高级配置会自动请求对应分类的提示词列表。

### 3. 电影解说专属“影片信息/洗稿”入口

文件：

- `frontend/src/components/projectEdit/ProjectOperations.tsx`
- `frontend/src/components/projectEdit/ProjectEditCopywritingStep.tsx`

相关位置：

- `isMovieNarration = project.narration_type === NarrationType.MOVIE`
- 只有电影解说显示“附加影片信息”“洗稿（推荐）”按钮。
- 复制提示词内容写死“这部电影”“电影整体脉络简介”“人物简介”。

改造点：

- 抽象为能力配置：
  - `supportsExternalContext`
  - `supportsReferenceCopywriting`
  - `contextButtonLabel`
  - `contextModalTitle`
  - `contextPromptBuilder(project)`
- 对“电视剧解说”建议：
  - 按钮文案：“附加剧集信息”
  - 提示词：“提取《xxx》这部电视剧/剧集的整体剧情脉络、主要人物关系、分集/阶段性冲突...”
- 对“漫剧解说”建议：
  - 按钮文案：“附加作品设定”
  - 提示词：“提取《xxx》这部漫剧/漫画改编内容的世界观设定、人物关系、主线冲突...”
- 后端字段目前叫 `narration_film_context`，可继续复用但语义不准。建议新增通用别名：
  - 新字段：`narration_context`
  - 旧字段：`narration_film_context` 保留兼容。

## 八、数据库/持久化兼容

当前项目数据存储在 JSON 中，`narration_type` 直接存中文字符串。

改造建议：

1. 短期继续存中文值，新增配置做映射，兼容风险最低。
2. 中期考虑存稳定 code：
   - `short_drama_narration`
   - `movie_narration`
   - `tv_drama_narration`
   - `comic_drama_narration`
3. 如改成 code，需迁移旧数据：
   - “短剧解说” -> `short_drama_narration`
   - “电影解说” -> `movie_narration`
4. 前后端 API 返回时可以同时给：
   - `narration_type`
   - `narration_type_label`

## 九、测试清单

### 后端测试

- 创建项目：
  - 短剧解说
  - 电影解说
  - 电视剧解说
  - 漫剧解说
- 非法 `narration_type` 返回 400 或回退默认，行为要明确。
- `_default_prompt_key_for_project()` 对每种类型返回正确 category。
- `generate_copywriting` 对每种类型使用正确 prompt。
- 电影/电视剧上下文能力按配置启用。
- 脚本生成输出格式中“播放原片/原剧/原漫”的表达正确。
- 旧项目数据无 `narration_type` 或空值时仍能运行。

### 前端测试

- 创建项目弹窗展示所有类型。
- 创建后项目卡片展示正确。
- 文案高级配置打开后加载对应 category 的提示词。
- 电影解说仍显示影片信息和洗稿入口。
- 电视剧/漫剧按配置显示或隐藏上下文/洗稿入口。
- 生成文案和生成脚本请求中携带正确 `narration_type`。

### 回归测试

- 短剧解说生成效果不变。
- 电影解说的影片信息、洗稿链路不变。
- 用户自定义提示词 selection 不被新增类型影响。

## 十、建议实施顺序

1. 新增后端 `narration_types` 配置模块，提供：
   - `normalize_narration_type`
   - `get_prompt_category`
   - `get_output_format_kind`
   - `get_original_label`
   - `supports_context`
2. 替换后端所有“电影/短剧”硬编码分支：
   - `prompt_resolver.py`
   - `copywriting_builder.py`
   - `script_builder.py`
   - `visual_script_builder.py`
   - `generate_copywriting_service.py`
3. 新增或复用 prompt category：
   - 快速版：电视剧/漫剧先映射到 `short_drama_narration`
   - 完整版：新增 `tv_drama_narration`、`comic_drama_narration`
4. 前端新增统一配置和枚举选项：
   - `project.ts`
   - `CreateProjectModal.tsx`
   - `usePrompts.ts`
   - 电影专属按钮抽成配置化能力
5. 补测试和手工回归。

## 十一、最小改造版本

如果只想最快把“电视剧解说”“漫剧解说”加进来：

1. 前端 `NarrationType` 加两个值。
2. `CreateProjectModal.tsx` 下拉加两个 `<option>`。
3. `usePrompts.ts` 把新类型映射到 `short_drama_narration`。
4. 后端 `prompt_resolver.py` 暂时不改也能默认落到短剧，但建议显式配置。
5. `script_builder.py`、`visual_script_builder.py` 暂时不改也会走短剧 output format。

这个版本上线快，但“电视剧/漫剧”只是在项目类型展示上不同，核心提示词仍然是短剧语境。

## 十二、推荐改造版本

推荐做成配置驱动：

- 前端：一个 `NARRATION_TYPE_OPTIONS` 管所有展示、prompt category、能力开关。
- 后端：一个 `NARRATION_TYPE_CONFIG` 管所有类型到 prompt/output/context 的映射。
- Prompt：新增独立 category，至少为“电视剧解说”“漫剧解说”准备默认 `script_generation`。
- Output format：抽象“原片/原剧/原漫”文案。

这样后续再加“动漫解说”“纪录片解说”“综艺解说”时，只需要：

1. 增加配置。
2. 增加提示词目录或复用已有 category。
3. 前端选项自动出现。

