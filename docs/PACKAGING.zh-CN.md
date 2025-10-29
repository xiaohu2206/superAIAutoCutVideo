**打包说明（Windows / Tauri + PyInstaller）**

- 本文档说明如何在 Windows 上将本项目打包为可分发的桌面应用（便携版 EXE），并包含后端可执行文件。
- 默认采用前端 Vite 构建、后端 PyInstaller onefile 打包、Tauri 桌面封装的组合。

**环境要求**
- 系统：Windows 10/11（建议 x64）
- 必备工具：
  - `Node.js`（建议 LTS）与 `npm`
  - `Python 3.9+` 与 `pip`
  - `Rust` 稳定版（MSVC 工具链）与 `cargo`
  - `Visual Studio Build Tools`（含 C++ 构建工具）
  - `PyInstaller`（脚本会自动安装）
  - `cargo-tauri`（如未安装：`cargo install tauri-cli --locked`）
- 可选/网络：国内环境建议配置 npm/pip 镜像或代理，以提升下载速度。

**一键打包（推荐）**
- 在项目根目录执行 PowerShell（建议以用户权限即可）：
  - 标准打包（使用精简依赖 requirements.runtime.txt）：
    - `powershell -ExecutionPolicy Bypass -File scripts\build.ps1`
  - 完整依赖打包（使用 requirements.txt）：
    - `powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -FullBackend`
- 脚本流程（自动）：
  - 清理旧产物：`backend\dist`、`backend\build`、`src-tauri\target\release`、`src-tauri\resources\superAutoCutVideoBackend.exe`
  - 前端：进入 `frontend` 执行 `npm ci`（首次）和 `npm run build`
  - 后端：进入 `backend`，安装依赖并执行 `pyinstaller --onefile --name superAutoCutVideoBackend --distpath dist main.py`
  - 复制后端：拷贝 `backend\dist\superAutoCutVideoBackend.exe` → `src-tauri\resources\`
  - 桌面应用：进入 `src-tauri` 执行 `cargo tauri build`

**产物位置**
- 应用程序：`src-tauri\target\release\super-auto-cut-video.exe`
- 后端（随应用打包）：`src-tauri\target\release\resources\superAutoCutVideoBackend.exe`
- 前端静态资源（供 Tauri 使用）：`frontend\dist\`

**运行与验证**
- 直接双击运行：`src-tauri\target\release\super-auto-cut-video.exe`
- 应用会在启动时从资源目录自动启动后端：
  - 优先路径：`app_handle.path().resource_dir()`（即 `target\release\resources`）
  - 已设置后端进程 `current_dir` 为资源目录
  - 启动等待时间已放宽至约 20 秒（涵盖 onefile 冷启动解压场景）
- 端口占用：若默认端口占用，应用会尝试切换到可用端口并与前端联动，无需手动干预。

**开发环境（可选）**
- 快速启动开发模式（会拉起前端 Dev、后端、Tauri Dev）：
  - `scripts\dev.bat`
- 首次可能会自动安装依赖并进行 Rust 构建，耗时较长属正常现象。

**常见问题与排查**
- 执行策略受限（PowerShell 提示 ExecutionPolicy）：
  - 使用命令：`powershell -ExecutionPolicy Bypass -File scripts\build.ps1`
- 依赖下载缓慢/失败：
  - 为 npm/pip 配置国内镜像或代理；必要时重复执行脚本。
- 前端构建失败：
  - 检查 `frontend` 目录存在且能 `npm ci && npm run build`；清理 `node_modules` 后重试。
- 后端打包失败：
  - 优先使用 `requirements.runtime.txt`；如仍失败，尝试 `-FullBackend` 使用完整依赖。
  - 手动执行到 `backend` 目录运行：`pyinstaller --onefile --name superAutoCutVideoBackend --distpath dist main.py` 查看详细日志。
- 运行后无法连接后端：
  - 打开任务管理器检查是否残留 `superAutoCutVideoBackend.exe`；可在 PowerShell 执行：
    - `Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force`
  - 确认 `src-tauri\target\release\resources\superAutoCutVideoBackend.exe` 存在且可手动运行。
  - 某些杀毒/防护软件可能误报，需加入信任列表。
- 缺少 WebView2 Runtime：
  - Windows 一般自带或自动安装；若启动白屏，可安装 Microsoft WebView2 Runtime（Evergreen）。
- BAT 脚本异常：
  - `scripts\build.bat` 受编码/环境影响易解析失败，推荐使用 PowerShell 版本 `scripts\build.ps1`。

**自定义与扩展**
- 应用名称/图标/标识：
  - 编辑 `src-tauri\tauri.conf.json` 与 `src-tauri\icons\`。
- 后端打包策略：
  - 体积小（默认）：`requirements.runtime.txt` + `--onefile`，首次运行可能更慢（解压）。
  - 兼容强：`-FullBackend` 使用 `requirements.txt`，体积更大但更稳。
- 启动时限与端口：
  - 已将后端就绪等待上限延长至约 20 秒；端口自动寻找空闲。
- 生成安装包（NSIS/MSI）：
  - 可在 `tauri.conf.json` 配置 `bundle`，并使用 `cargo tauri build --bundles nsis,msi` 生成安装包。

**清理与重建**
- 快速清理：删除如下目录/文件后重新执行脚本：
  - `backend\dist`、`backend\build`
  - `src-tauri\target`、`src-tauri\resources\superAutoCutVideoBackend.exe`
  - 也可使用脚本内置的清理步骤（已默认执行）。

**手动打包（进阶/排障）**
- 前端：
  - `cd frontend && npm ci && npm run build && cd ..`
- 后端（PyInstaller）：
  - `cd backend`
  - `pip install -r requirements.runtime.txt`（或 `requirements.txt`）
  - `pyinstaller --onefile --name superAutoCutVideoBackend --distpath dist main.py`
  - `cd ..`
- 复制后端到资源目录：
  - `mkdir src-tauri\resources`（如不存在）
  - `copy backend\dist\superAutoCutVideoBackend.exe src-tauri\resources\`
- Tauri 打包：
  - `cd src-tauri && cargo tauri build && cd ..`

**目录参考**
- 打包成功后关键目录：
  - `src-tauri\target\release\super-auto-cut-video.exe`
  - `src-tauri\target\release\resources\superAutoCutVideoBackend.exe`
  - `frontend\dist\`（前端静态资源）

**备注**
- 若你需要 Mac/Linux 平台产物，请单独联系或在对应平台安装依赖后执行等价流程（当前项目主要针对 Windows）。
- 如需进一步集成 CI/CD、符号表、自动更新或官方 sidecar 机制，可在后续迭代中加入。