# 暗色主题改造规范（方法学版）

> 与 `dark-theme-follow-up-handoff.md`（改造清单）配套使用。
> 本文档定义“怎么改”，清单文档定义“改哪些”。

## 1. 背景

第一轮主题机制改造（`darkMode: "class"`、`sacv_theme`、Navigation 主题按钮、`html.dark` 同步）已经完成。
随后陆续发现大量组件在暗色下仍出现：

- 白色 / 浅色渐变（如 `from-white via-amber-50/25 to-purple-50/40`、`to-fuchsia-50`）
- 浅色 `ring`（如 `ring-1 ring-purple-400/40`、`ring-green-200/80`）
- 浅色背景（如 `bg-blue-50/80`、`bg-slate-50/60`、`bg-amber-50`）
- focus / hover 时变白（`focus-within:bg-white`、`hover:bg-gray-50`）

仅靠在 className 末尾追加 `dark:xxx` 不能解决这些场景，原因：

1. Tailwind 在暗色下仍会把亮色类编译进 CSS。半透明、渐变、ring 不是单纯被 `dark:` 覆盖即可；多色渐变（from/via/to）只能整组覆盖，单独 `dark:to-xxx` 不一定生效。
2. 半透明类在暗背景上不会被“盖住”，反而透出原始浅色，看上去就是“白渐变”。
3. focus / hover 类与 `dark:hover:` 同时存在时优先级和合并行为不直观，容易残留浅色态。

## 2. 两种改造方式

### A. 类附加方式（仅追加 `dark:` 修饰符）

适用场景：

- 单色背景 / 边框 / 文字
- 没有 ring、没有渐变、没有 `bg-*-50/80` 这类浅色半透明
- 状态简单（无 hover 浅底、无 focus 白底）

```tsx
<div className="bg-white border border-slate-200 text-slate-900
                dark:bg-[#1f1f1f] dark:border-white/10 dark:text-zinc-100">
  ...
</div>
```

### B. `useThemeMode` 分支方式（推荐用于复杂状态）

适用场景：

- 渐变背景（`bg-gradient-to-*` + `from/via/to`）
- `ring-*` 颜色描边
- 半透明浅色（`bg-*-50/80`、`bg-white/80`）
- focus / hover 出现浅色（`focus-within:bg-white`、`hover:bg-gray-50`）
- 选中/未选中、active/idle、禁用等多分支条件 class
- 文字渐变 `bg-clip-text text-transparent`

通过 `useThemeMode()` 在 JS 层判定，**直接不渲染亮色类**，从根上消除浅色样式：

```tsx
import { useThemeMode } from "@/hooks/useThemeMode";

const isDark = useThemeMode() === "dark";

<div className={`rounded-lg border p-4 ${
  isDark
    ? "border-[#2a2a2a] bg-[#1f1f1f] text-zinc-200"
    : "border-slate-200 bg-slate-50/80 text-slate-700"
}`}>
  ...
</div>
```

> 经验法则：
> - 一行 className 里 `dark:` 出现 4 次以上，或包含 gradient / ring / 半透明，优先用方式 B。
> - 单色简单覆盖，用方式 A 更轻量。

## 3. `useThemeMode` 钩子

文件：`frontend/src/hooks/useThemeMode.ts`

- 同步读取 `document.documentElement.classList.contains("dark")`。
- 通过 `MutationObserver` 监听 `<html class>` 变化，主题切换时自动重渲染。
- 返回 `"light" | "dark"`。

使用：

```tsx
const isDark = useThemeMode() === "dark";
```

注意：

- 该钩子安全可在任何组件内调用（不依赖 Context）。
- 同一组件多次使用同一变量即可，不要重复调用。
- 不要在循环 / map 内部调用钩子。

## 4. 暗色色板（项目基线）

延续清单文档约定，且与本次实际改造一致：

| 角色 | 暗色 token | 备注 |
|------|------------|------|
| App 主背景 | `#121212` | 由全局 CSS 提供 |
| 面板 / 卡片底 | `#1f1f1f` | 主要容器 |
| 次级卡片 / 表单底 | `#242424` | 输入框、二级面板 |
| 底栏 / footer / 代码块 | `#181818` | 视觉下沉 |
| 分隔线 / 边框 | `#2a2a2a` 或 `white/10` | 项目里两种都在用，单文件保持一致即可 |
| 主文字 | `text-gray-100` / `text-zinc-100` | |
| 次文字 | `text-gray-300` / `text-zinc-300` | |
| 弱文字 | `text-gray-400` / `text-zinc-400` | |
| disabled / placeholder | `text-gray-500` / `text-zinc-500` | |
| 主品牌色（蓝） | `text-blue-300`、`bg-blue-500/10`、`border-blue-500/40` | 选中 / 激活 |
| 危险色（红） | `text-rose-300`、`bg-rose-500/15` | 错误 / 删除 |
| 成功色（绿） | `text-emerald-300`、`bg-emerald-500/15` | |
| 警告色（琥珀） | `text-amber-200`、`bg-amber-500/10`、`border-amber-700/40` | |
| 强调色（紫） | `text-purple-300`、`bg-purple-950/35`、`border-purple-500` | |

> 偏好半透明（`*-500/10` ~ `/20`）而不是 `*-900/40` 系列，颜色更柔，对比度更可控。

## 5. 常见反模式 / 易踩坑

### 5.1 浅色渐变背景

错误：

```tsx
className="bg-gradient-to-br from-purple-50 via-amber-50/60 to-fuchsia-50
           dark:bg-purple-950/35"
```

`bg-gradient-to-br` 仍会被编译，`to-fuchsia-50` 会透出。
**正确做法**：用 `useThemeMode` 分两套，暗色显式 `bg-none + 纯色` 或干脆完全不渲染渐变类。

```tsx
isDark
  ? "border-purple-500 bg-purple-950/35"
  : "border-purple-500 bg-gradient-to-br from-purple-50 via-amber-50/60 to-fuchsia-50 ring-1 ring-purple-400/40"
```

### 5.2 浅色 `ring`

错误：

```tsx
className="ring-1 ring-purple-400/40 dark:ring-purple-500/30"
```

`ring-purple-400/40` 在暗色下仍是浅色描边。
**正确做法**：暗色去掉 ring 或换 `ring-blue-500/30` 等系列。优先用 `useThemeMode` 分支干掉它。

### 5.3 焦点 / hover 变白

错误：

```tsx
"focus-within:bg-white"          // 暗色下 focus 会闪白
"hover:bg-gray-50"               // hover 闪浅灰
```

**正确做法**：把整个 wrapper 用 `useThemeMode` 拆，暗色 focus 用 `focus-within:bg-[#2a2a2a] focus-within:ring-blue-500/20`。

### 5.4 半透明浅色背景

错误：

```tsx
"bg-blue-50/80"          // 暗色下仍是浅蓝
```

**正确做法**：

```tsx
isDark ? "bg-blue-500/10 ring-1 ring-inset ring-blue-500/30" : "bg-blue-50/80"
```

### 5.5 文字渐变

错误：

```tsx
"bg-gradient-to-r from-purple-700 via-amber-700 to-purple-700
 bg-clip-text text-transparent dark:text-purple-300"
```

`bg-clip-text` + `text-transparent` 仍生效，`dark:text-purple-300` 不会让文字变实色（因为透明已经设置）。
**正确做法**：暗色用纯色：

```tsx
isDark
  ? "text-purple-300"
  : "bg-gradient-to-r from-purple-700 via-amber-700 to-purple-700 bg-clip-text text-transparent"
```

### 5.6 仅外层加 `dark:` 内层文字仍是浅灰

容器 `dark:bg-[#1f1f1f]` 但内部 `<p className="text-slate-500">` 没补 `dark:text-gray-400`。
**统一做法**：处理一个块时，至少同时检查容器、标题、正文、图标、按钮、链接、徽章六个角色。

### 5.7 输入框 disabled 在暗色下太暗看不出

错误：`disabled:opacity-50` 在 `#242424` 上几乎不可见。
**正确做法**：暗色禁用用更明确的 token，例如 `disabled:bg-indigo-500/30 disabled:text-indigo-200/60`。

## 6. 改造范式（复制粘贴模板）

### 6.1 标准面板 / 卡片

```tsx
<div
  className={`rounded-xl border p-4 ${
    isDark
      ? "border-[#2a2a2a] bg-[#1f1f1f]"
      : "border-slate-200 bg-slate-50/80"
  }`}
>
  ...
</div>
```

### 6.2 表单输入 wrapper

```tsx
const fieldWrapperClass = isDark
  ? "border-[#2a2a2a] bg-[#242424] focus-within:border-blue-500/50 focus-within:bg-[#2a2a2a] focus-within:ring-2 focus-within:ring-blue-500/20"
  : "border-slate-200 bg-slate-50/60 focus-within:border-blue-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100";

const fieldInputClass = isDark
  ? "text-gray-100 placeholder:text-gray-500"
  : "text-slate-900 placeholder:text-slate-400";

<div className={`flex items-center gap-2 rounded-xl border px-3 py-2.5 ring-inset transition-colors ${fieldWrapperClass}`}>
  <input className={`min-w-0 flex-1 bg-transparent text-sm outline-none ${fieldInputClass}`} />
</div>
```

### 6.3 次要按钮

```tsx
className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${
  isDark
    ? "border-[#2a2a2a] bg-[#242424] text-gray-200 hover:bg-[#2d2d2d]"
    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
}`}
```

### 6.4 主按钮（带禁用）

```tsx
className={`rounded-lg px-3 py-1.5 text-xs font-medium text-white transition disabled:cursor-not-allowed ${
  isDark
    ? "bg-indigo-500 hover:bg-indigo-400 disabled:bg-indigo-500/30 disabled:text-indigo-200/60"
    : "bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300"
}`}
```

### 6.5 列表选中态

```tsx
className={`flex items-center gap-2 px-3 py-2 text-sm ${
  active
    ? isDark
      ? "bg-blue-500/10 ring-1 ring-inset ring-blue-500/30"
      : "bg-blue-50/80"
    : ""
}`}
```

### 6.6 状态徽章（带 ring）

```tsx
className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
  isActive
    ? isDark
      ? "bg-green-900/20 text-green-300"
      : "bg-green-50 text-green-700 ring-1 ring-green-200/80"
    : isDark
      ? "bg-red-900/20 text-red-300"
      : "bg-red-50 text-red-700 ring-1 ring-red-200/80"
}`}
```

### 6.7 模态框

```tsx
<div className={`relative w-full max-w-md rounded-lg border shadow-xl ${
  isDark ? "border-[#2a2a2a] bg-[#1f1f1f]" : "border-gray-200 bg-white"
}`}>
  <div className={`border-b p-5 ${isDark ? "border-[#2a2a2a]" : "border-gray-200"}`}>
    {/* header */}
  </div>

  <div className={`p-5 text-sm ${isDark ? "text-gray-300" : "text-gray-700"}`}>
    {/* body */}
  </div>

  <div className={`flex justify-end gap-2 border-t px-5 py-4 ${
    isDark ? "border-[#2a2a2a] bg-[#181818]" : "border-gray-200 bg-gray-50"
  }`}>
    {/* footer */}
  </div>
</div>
```

### 6.8 信息提示（蓝色 Info Box）

```tsx
<div className={`rounded-lg border p-3 text-sm flex gap-2 ${
  isDark
    ? "border-blue-500/30 bg-blue-500/10 text-blue-300"
    : "border-blue-200 bg-blue-50 text-blue-800"
}`}>
  <Info className={`w-5 h-5 ${isDark ? "text-blue-300" : "text-blue-600"}`} />
  ...
</div>
```

### 6.9 警示提示（琥珀色 Warning Box）

```tsx
<p className={`rounded-md border px-3 py-2 ${
  isDark
    ? "border-amber-700/40 bg-amber-900/15 text-amber-200"
    : "border-amber-200 bg-amber-50 text-amber-900"
}`}>
  ...
</p>
```

## 7. 改造流程（建议）

针对一个待改组件，按下面顺序处理：

1. 检索：`bg-white | bg-(gray|slate)- | text-(gray|slate)- | border-(gray|slate)- | ring-*-200 | from- | via- | to- | hover:bg-(gray|slate)- | focus-within:bg-white | bg-clip-text`
2. 评估：浅色出现在多少处？是不是已有大量 `dark:`？
3. 选策略：单色多 → 方式 A；渐变 / ring / 半透明 / 多分支 → 方式 B（`useThemeMode`）
4. 改造：
   - 用方式 B 时不要保留旧的 `dark:` 类，统一收敛到一个三元分支
   - 始终保留亮色分支原样，只补暗色
5. 自检：手动切到 dark，按下面 9 个角色逐项确认
   - 容器背景 / 边框
   - 标题文字
   - 正文 / 次级文字
   - 图标
   - 主按钮 / 次按钮 / 禁用态
   - 输入框 placeholder / focus / disabled
   - 选中 / hover
   - 提示框 / 徽章 / ring
   - 外链 `<a>` / 下划线文本
6. 运行 `npm run build`，确认无新增报错（`type-check` 见清单文档说明）。

## 8. 不要做的事

- 不要回退主题机制（`darkMode: "class"`、`sacv_theme`、Navigation 主题按钮、`html.dark` 同步）。
- 不要把暗色主背景改回 `gray-900` 系列，保持 `#121212`。
- 不要在 `index.css` 全局兜底里写组件级颜色（会让组件层失控）。
- 不要在改一个浅色类时把它直接删掉。永远保留亮色分支。
- 不要在循环里调用 `useThemeMode`。
- 不要把 `useThemeMode` 嵌入到 utility 函数里再以纯字符串形式拼 className（一旦字符串里有动态分支，建议直接在 JSX 里写）。

## 9. 与 handoff 清单的关系

- 本文档：方法、token、范式。
- `dark-theme-follow-up-handoff.md`：还差哪些文件、按优先级排序。
- 修一个清单条目时，第一选择是参考本规范的范式而不是发明新写法，避免每个组件长出一套自己的暗色色板。

## 10. 已应用本规范的样例（可参考）

可作为复制起点的真实文件（截至本次改造批次）：

- `frontend/src/components/projectManagement/CreateProjectModal.tsx`
  - 卡片选中 / 文字渐变 / ring 分支处理
- `frontend/src/components/auth/UserProfile.tsx`
  - 头像卡片渐变、状态徽章 ring 分支
- `frontend/src/components/auth/UserProfileLicenses.tsx`
  - 容器去 ring/边框策略
- `frontend/src/components/auth/LoginRegisterModal.tsx`
  - 输入框 wrapper / focus 暗色态
- `frontend/src/components/projectEdit/omni/BulkTtsChoiceModal.tsx`
  - 模态框整套（容器 / header / body / footer / 三按钮）
- `frontend/src/components/projectEdit/omni/SegmentTypeToggle.tsx`
  - 双色按钮 amber / blue + 阴影暗色裁剪
- `frontend/src/features/omnivoiceTts/components/OmniVoiceTtsSection.tsx`
  - 列表行选中态 + “使用中” 按钮三分支
- `frontend/src/features/subtitleAsr/components/FunAsrModelOptionsList.tsx`
  - Info Box 暗色重写
- `frontend/src/features/visionModel/components/MoondreamLocalModelPanel.tsx`
  - Info Box 简单 `dark:` 类追加版（方式 A）
- `frontend/src/components/settingsPage/components/AboutSection.tsx`
  - 大块（标题/正文/code/进度条/按钮/链接）全分支化

新组件改造遇到拿不准的写法时，先看上面这些样例对应位置。
