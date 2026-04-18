# SuperAI影视剪辑 Tauri 版本清理脚本

独立于项目主工程的一次性清理工具，用于把 Tauri 版本 (`SuperAI影视剪辑`) 在 Windows 上残留的**所有**数据彻底清掉。

## 特性

- **零依赖**：无需安装 Python / Node / Rust，双击 `.bat` 即可运行。
- **先扫描再确认**：第一步只是扫描出命中的条目并打印出来，必须由使用者输入 `y`/`s`/`d`/`n` 后才会动手。
- **自动提权**：`.bat` 检测到非管理员会自动弹出 UAC；缺少管理员权限时仍可以只清理当前用户部分。
- **先停进程再删文件**：避免 Windows 的「文件被占用」错误。
- **优先调官方 uninstaller**：若能找到安装时生成的 `uninstall.exe`，会先以 `/S /P` 静默模式跑一次，再做兜底清理。
- **覆盖全面**：进程 / 安装目录 / Tauri AppData / 后端持久化数据 / 临时目录 / 注册表 Uninstall 键 / Manufacturer 键 / Run 自启项 / 深链接协议 / 桌面与开始菜单快捷方式。
- **带重试与日志**：删除失败会重试 + 回退到 `rd/s/q`，并在结尾输出未成功清理的条目清单。

## 文件清单

| 文件 | 作用 |
|------|------|
| `cleanup_tauri.bat` | 入口。负责切 UTF-8 代码页、自动提权、调用 PS 脚本。**双击它就行。** |
| `cleanup_tauri.ps1` | 核心扫描 / 交互 / 清理逻辑。也可单独用 PowerShell 运行。 |
| `README.md` | 本说明文件。 |

## 使用方法

1. 关闭正在运行的 `SuperAI影视剪辑` 窗口 (如果开着)。
2. 在资源管理器里双击 `tests\tauri_cleanup\cleanup_tauri.bat`。
3. UAC 弹窗选"是"。
4. 看完扫描报告后按提示：
   - `y`：全部清理（先停进程 → 调 uninstaller → 删文件 / 清注册表 / 删快捷方式）。
   - `s`：分类逐项确认是否清理。
   - `d`：只停进程，不动文件/注册表（用于"只想释放端口占用"的场景）。
   - `n`：完全取消，什么都不做。
5. 脚本会在末尾再扫一次，列出未能自动清理的残留 (罕见，通常是文件仍被占用，重启后再跑一次即可)。

## 会清理哪些位置

| 分类 | 位置 |
|------|------|
| 进程 | `super-auto-cut-video.exe`、`superAutoCutVideoBackend.exe`；以及路径命中本应用的 `ffmpeg.exe` / `ffprobe.exe` / `msedgewebview2.exe`（模糊项需二次确认） |
| 端口占用 | 扫描 `8000-8100` 和 `18000-18100`（`backend` 候选区间，来自 `main.rs::choose_backend_port`）：**本应用进程**默认一并杀；**第三方进程**打印 PID / 名称 / 路径后单独询问，默认 `N`，明确选 `y` 才会 `Stop-Process -Force` / `taskkill /F /T` 强杀 |
| 安装目录 | `%ProgramFiles%\SuperAIAutoCutVideo`、`%ProgramFiles(x86)%\SuperAIAutoCutVideo`、`%LOCALAPPDATA%\SuperAIAutoCutVideo` |
| Tauri AppData | `%APPDATA%\com.superautocutvideo.app`、`%LOCALAPPDATA%\com.superautocutvideo.app`（含解压后的 `superAutoCutVideoBackend`、`runtime_chunks_cache`、WebView2 UserData 等） |
| 后端持久化数据 | `%LOCALAPPDATA%\SuperAutoCutVideo`（`uploads/`、`config/app_settings.json`、`data/projects.json` 等） |
| 临时文件 | `%TEMP%\super_auto_cut_backend.log`、`%TEMP%\super_auto_cut_backend_tmp`、`%TEMP%\MicrosoftEdgeWebview2Setup.exe` |
| 注册表 | `HKLM/HKCU\...\Uninstall\SuperAI影视剪辑`、`HKLM/HKCU\SOFTWARE\SuperAI影视剪辑`、`HKCU\...\Run` 自启项、`HKLM/HKCU\SOFTWARE\Classes\com.superautocutvideo.app`、WiX 老版本遗留卸载键 |
| 快捷方式 | 公共/用户桌面、当前用户/All Users 开始菜单下的 `SuperAI影视剪辑.lnk` 及同名文件夹 |

## 不会动的东西

- 项目源码仓库本身（你正在用的 `E:\learn\superAutoCutVideoApp` 下的一切）。
- 系统自带的 WebView2 Runtime（共享组件，卸应用时不删除）。
- 其它进程的 `ffmpeg.exe` / `ffprobe.exe`（路径不命中本应用就不会被杀）。

## 常见问答

**Q: 运行中报"无法删除 …\webview2\EBWebView\…"？**
> 通常是 `msedgewebview2.exe` 还没完全退出。再跑一次脚本，或重启后再跑即可。

**Q: 端口 8000 / 18000 被占用，但被占用的进程不是本应用？**
> 脚本会把它标成 `[第三方]`，并列出 PID / 进程名 / 可执行文件路径。之后会**单独**问一句"是否强杀"，默认 `N`。**只有你明确输入 `y` 才会 `taskkill /F` 这些进程**。如果拿不准就选 N，脚本不会乱动。

**Q: 如果我就想一键释放被占用的端口、但不卸载应用？**
> 在主菜单选 `d` (仅停进程 / 释放端口)，这会执行"杀本应用进程 + 按你确认的范围杀端口占用进程"，但**不**删除任何文件或注册表。

**Q: 我是便携版 / 自定义安装目录用户？**
> 脚本兜底扫描了所有官方默认路径。如果你把 `SuperAIAutoCutVideo/` 装在别处，需要手动删除自定义目录；但注册表/AppData/后端数据仍能被清干净。
