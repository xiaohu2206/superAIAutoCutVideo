import { FolderOpen, Info, Layers, Loader2, RefreshCw } from "lucide-react";
import React from "react";
import { exit, relaunch } from "@tauri-apps/plugin-process";
import { TauriCommands } from "../../../services/tauriService";
import { useAppVersion } from "../../../hooks/useAppVersion";
import { useRuntimeUpdater } from "../../../hooks/useRuntimeUpdater";
import {
  formatBytes,
  isTauriRuntime,
  launchLocalShellInstaller,
  resolveOfflineUpdateBundle,
} from "../../../services/runtimeUpdaterService";

const AboutSection: React.FC = () => {
  const { appVersion } = useAppVersion();
  const {
    checking: rtChecking,
    installing: rtInstalling,
    updateInfo: rtUpdate,
    installedState: rtInstalled,
    localManifestPath: rtManifestPath,
    progress: rtProgress,
    error: rtError,
    checkLocal: rtCheckLocal,
    applyLocal: rtApplyLocal,
  } = useRuntimeUpdater();

  const [shellInstallerPath, setShellInstallerPath] = React.useState<string | null>(null);
  const [bundleError, setBundleError] = React.useState("");

  const pickOfflineUpdateBundle = async () => {
    if (!isTauriRuntime()) return;
    const res = await TauriCommands.selectOfflineBundleManifest();
    if (res.cancelled || !res.path) return;
    setShellInstallerPath(null);
    setBundleError("");
    try {
      const resolved = await resolveOfflineUpdateBundle(res.path);
      if (!resolved) return;
      setShellInstallerPath(resolved.shellInstallerPath);
      await rtCheckLocal(resolved.backendManifestPath);
    } catch (e) {
      setShellInstallerPath(null);
      setBundleError(e instanceof Error ? e.message : String(e));
    }
  };

  const installOfflineAndContinue = async () => {
    if (!isTauriRuntime() || !rtManifestPath) return;
    const result = await rtApplyLocal(rtManifestPath);
    if (result == null) return;
    if (shellInstallerPath) {
      await launchLocalShellInstaller(shellInstallerPath);
      await exit(0);
      return;
    }
    if (result.available) {
      await relaunch();
    }
  };

  const canInstall =
    !!rtManifestPath &&
    !rtChecking &&
    !rtInstalling &&
    ((rtUpdate?.available ?? false) || !!shellInstallerPath);

  const rtProgressPct =
    rtProgress && rtProgress.total > 0
      ? Math.min(100, Math.round((rtProgress.downloaded / rtProgress.total) * 100))
      : 0;

  const shellBasename = shellInstallerPath
    ? shellInstallerPath.replace(/^.*[/\\]/, "")
    : null;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg p-6">
        <div className="flex items-center mb-6">
          <Info className="h-6 w-6 text-blue-600 mr-3" />
          <h2 className="text-2xl font-bold text-gray-900">关于应用</h2>
        </div>

        <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50/80 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between md:gap-4">
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-indigo-500" />
                <h3 className="text-sm font-semibold text-slate-900">离线更新（壳 + 后端）</h3>
              </div>
              <p className="text-xs text-slate-500">
                从网盘将 zip、runtime-manifest.json、安装包与总清单放到<strong>同一文件夹</strong>。此处<strong>必须</strong>选择名为{" "}
                <code className="rounded bg-slate-200/80 px-1">offline-bundle-manifest.json</code> 的文件。
              </p>
              {!!rtManifestPath && !bundleError && !rtChecking && (
                <p className="text-xs text-slate-600">已解析总清单并定位后端 runtime-manifest。</p>
              )}
              {shellBasename ? (
                <p className="text-xs text-emerald-700">
                  壳安装包：{shellBasename}
                </p>
              ) : rtManifestPath ? (
                <p className="text-xs text-slate-500">壳安装包：未指定（仅更新后端运行时）</p>
              ) : null}

              {rtInstalled && rtInstalled.runtime_version ? (
                <p className="text-xs text-slate-500">
                  已安装运行时：{rtInstalled.runtime_version}
                  {rtInstalled.variant ? ` (${rtInstalled.variant})` : ""}
                  {rtInstalled.chunks ? ` · ${Object.keys(rtInstalled.chunks).length} 个分块` : ""}
                </p>
              ) : (
                <p className="text-xs text-slate-400">尚无已安装运行时状态记录</p>
              )}

              {rtUpdate?.available ? (
                <>
                  <p className="text-sm text-emerald-600">
                    后端：发现 {rtUpdate.remote_version}，需处理 {rtUpdate.chunks_to_update.length} 个分块
                    {rtUpdate.skip_chunks.length > 0 ? `，跳过 ${rtUpdate.skip_chunks.length} 个` : ""}
                  </p>
                  <p className="text-xs text-slate-500">
                    本次需解压/校验约：{formatBytes(rtUpdate.total_download_size)}
                  </p>
                </>
              ) : rtUpdate?.available === false ? (
                <p className="text-xs text-slate-500">后端运行时已是最新（若仍要重装壳，可保留总清单中的安装包并安装）</p>
              ) : null}

              {rtInstalling && rtProgress && (
                <div className="mt-1 space-y-1">
                  <p className="text-xs text-slate-500">
                    {rtProgress.phase === "verifying"
                      ? `校验 SHA256：${rtProgress.chunk_name} — ${formatBytes(rtProgress.downloaded)} / ${formatBytes(rtProgress.total)}`
                      : rtProgress.phase === "downloading"
                        ? `下载中：${rtProgress.chunk_name} — ${formatBytes(rtProgress.downloaded)} / ${formatBytes(rtProgress.total)}`
                        : rtProgress.phase === "extracting"
                          ? `解压中：${rtProgress.chunk_name}`
                          : rtProgress.phase === "done"
                            ? "完成"
                            : "处理中"}
                  </p>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-[width] duration-200"
                      style={{ width: `${rtProgressPct}%` }}
                    />
                  </div>
                </div>
              )}

              {!!bundleError && <p className="text-xs text-rose-600">{bundleError}</p>}
              {!!rtError && <p className="text-xs text-rose-600">{rtError}</p>}
            </div>

            <div className="flex shrink-0 flex-wrap gap-2 md:justify-end">
              <button
                type="button"
                onClick={() => void pickOfflineUpdateBundle()}
                disabled={rtChecking || rtInstalling}
                className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {rtChecking ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5 shrink-0" />}
                选择总清单
              </button>
              <button
                type="button"
                onClick={() => void installOfflineAndContinue()}
                disabled={!canInstall}
                className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
              >
                {rtInstalling ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 shrink-0" />}
                {shellInstallerPath ? "安装并处理壳" : "安装并重启"}
              </button>
            </div>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
            若总清单包含壳安装包：将先解压后端到用户目录，再启动 NSIS 安装程序，本应用随后退出，请在安装向导中完成桌面壳更新。
            若仅后端：安装完成后将自动重启以加载新运行时。
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-lg font-medium text-gray-900 mb-3">应用信息</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-600">应用名称:</dt>
                <dd className="font-medium">SuperAI智能视频剪辑</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">软件版本:</dt>
                <dd className="font-medium">{appVersion || "未知"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">构建时间:</dt>
                <dd className="font-medium">{new Date().toLocaleDateString("zh-CN")}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">开发者:</dt>
                <dd className="font-medium">xiaohu2206 Team</dd>
              </div>
            </dl>
          </div>

          <div>
            <h3 className="text-lg font-medium text-gray-900 mb-3">技术栈</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center">
                <div className="w-2 h-2 bg-blue-500 rounded-full mr-2" />
                <span>React 18 + TypeScript</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-green-500 rounded-full mr-2" />
                <span>Tauri (Rust)</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-yellow-500 rounded-full mr-2" />
                <span>Python FastAPI</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-purple-500 rounded-full mr-2" />
                <span>TailwindCSS</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-red-500 rounded-full mr-2" />
                <span>OpenCV + FFmpeg</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AboutSection;
