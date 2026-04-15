import { Download, Info, Layers, Loader2, Package, RefreshCw } from "lucide-react";
import React from "react";
import { useAppUpdater } from "../../../hooks/useAppUpdater";
import { useAppVersion } from "../../../hooks/useAppVersion";
import { useRuntimeUpdater } from "../../../hooks/useRuntimeUpdater";
import { formatBytes } from "../../../services/runtimeUpdaterService";

const AboutSection: React.FC = () => {
  const { appVersion } = useAppVersion();
  const {
    checking: shellChecking,
    installing: shellInstalling,
    updateInfo: shellUpdate,
    downloadedBytes: shellDownloaded,
    totalBytes: shellTotal,
    error: shellError,
    checkNow: shellCheckNow,
    installNow: shellInstallNow,
  } = useAppUpdater();
  const {
    checking: rtChecking,
    installing: rtInstalling,
    updateInfo: rtUpdate,
    installedState: rtInstalled,
    progress: rtProgress,
    error: rtError,
    checkNow: rtCheckNow,
    installNow: rtInstallNow,
  } = useRuntimeUpdater();

  const rtProgressPct =
    rtProgress && rtProgress.total > 0
      ? Math.min(100, Math.round((rtProgress.downloaded / rtProgress.total) * 100))
      : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg p-6">
        <div className="flex items-center mb-6">
          <Info className="h-6 w-6 text-blue-600 mr-3" />
          <h2 className="text-2xl font-bold text-gray-900">关于应用</h2>
        </div>

        {/* ─── 壳更新（Tauri updater）─── */}
        <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50/80 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Package className="h-4 w-4 text-blue-500" />
                <h3 className="text-sm font-semibold text-slate-900">桌面端壳更新</h3>
              </div>
              <p className="text-xs text-slate-500">
                更新前端界面与 Tauri 桥接层，体积小、秒级完成。
              </p>
              {shellUpdate?.available ? (
                <p className="text-sm text-emerald-600">
                  检测到新版本 {shellUpdate.version}
                  {shellUpdate.currentVersion ? `，当前 ${shellUpdate.currentVersion}` : ""}
                </p>
              ) : shellUpdate?.available === false ? (
                <p className="text-xs text-slate-500">当前已是最新壳版本</p>
              ) : null}
              {shellInstalling && (
                <p className="text-xs text-slate-500">
                  正在下载：{formatBytes(shellDownloaded)}
                  {shellTotal ? ` / ${formatBytes(shellTotal)}` : ""}
                </p>
              )}
              {!!shellError && <p className="text-xs text-rose-600">{shellError}</p>}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void shellCheckNow()}
                disabled={shellChecking || shellInstalling}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {shellChecking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                检查
              </button>
              <button
                type="button"
                onClick={() => void shellInstallNow()}
                disabled={!shellUpdate?.available || shellChecking || shellInstalling}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
              >
                {shellInstalling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                安装
              </button>
            </div>
          </div>
          {!!shellUpdate?.body && (
            <div className="mt-2 rounded-lg bg-white/80 p-2 text-xs text-slate-600 whitespace-pre-wrap">
              {shellUpdate.body}
            </div>
          )}
        </div>

        {/* ─── GPU / 后端运行时分块更新 ─── */}
        <div className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-indigo-500" />
                <h3 className="text-sm font-semibold text-slate-900">后端运行时更新</h3>
              </div>
              <p className="text-xs text-slate-500">
                分块更新 GPU/CPU 后端依赖，仅下载变化部分，无需每次重下整包。
              </p>

              {rtInstalled && rtInstalled.runtime_version ? (
                <p className="text-xs text-slate-500">
                  已安装版本：{rtInstalled.runtime_version}
                  {rtInstalled.variant ? ` (${rtInstalled.variant})` : ""}
                  {rtInstalled.chunks
                    ? ` · ${Object.keys(rtInstalled.chunks).length} 个分块`
                    : ""}
                </p>
              ) : (
                <p className="text-xs text-slate-400">尚无已安装运行时状态记录</p>
              )}

              {rtUpdate?.available ? (
                <>
                  <p className="text-sm text-emerald-600">
                    发现运行时 {rtUpdate.remote_version}，需更新{" "}
                    {rtUpdate.chunks_to_update.length} 个分块
                    {rtUpdate.skip_chunks.length > 0
                      ? `，跳过 ${rtUpdate.skip_chunks.length} 个`
                      : ""}
                  </p>
                  <p className="text-xs text-slate-500">
                    本次下载量：{formatBytes(rtUpdate.total_download_size)}
                  </p>
                </>
              ) : rtUpdate?.available === false ? (
                <p className="text-xs text-slate-500">运行时已是最新</p>
              ) : null}

              {rtInstalling && rtProgress && (
                <div className="mt-1 space-y-1">
                  <p className="text-xs text-slate-500">
                    {rtProgress.phase === "downloading"
                      ? `下载中：${rtProgress.chunk_name} — ${formatBytes(rtProgress.downloaded)} / ${formatBytes(rtProgress.total)}`
                      : rtProgress.phase === "extracting"
                        ? `解压中：${rtProgress.chunk_name}`
                        : "完成"}
                  </p>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-[width] duration-200"
                      style={{ width: `${rtProgressPct}%` }}
                    />
                  </div>
                </div>
              )}

              {!!rtError && <p className="text-xs text-rose-600">{rtError}</p>}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void rtCheckNow()}
                disabled={rtChecking || rtInstalling}
                className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {rtChecking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                检查
              </button>
              <button
                type="button"
                onClick={() => void rtInstallNow()}
                disabled={!rtUpdate?.available || rtChecking || rtInstalling}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
              >
                {rtInstalling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                下载并安装
              </button>
            </div>
          </div>
        </div>

        {/* ─── 基本信息 ─── */}
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
