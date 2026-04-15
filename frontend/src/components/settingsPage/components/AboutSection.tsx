import { Download, Info, Loader2, RefreshCw } from "lucide-react";
import React from "react";
import { useAppUpdater } from "../../../hooks/useAppUpdater";
import { useAppVersion } from "../../../hooks/useAppVersion";

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)} ${units[index]}`;
};

const AboutSection: React.FC = () => {
  const { appVersion } = useAppVersion();
  const {
    checking,
    installing,
    updateInfo,
    downloadedBytes,
    totalBytes,
    error,
    checkNow,
    installNow,
  } = useAppUpdater();

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg p-6">
        <div className="flex items-center mb-6">
          <Info className="h-6 w-6 text-blue-600 mr-3" />
          <h2 className="text-2xl font-bold text-gray-900">关于应用</h2>
        </div>

        <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50/80 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-slate-900">桌面端自动更新</h3>
              <p className="text-sm text-slate-600">
                已接入 Tauri updater。发布更新时只需生成并发布更新清单与签名安装包即可。
              </p>
              {updateInfo?.available ? (
                <p className="text-sm text-emerald-600">
                  检测到新版本 {updateInfo.version}
                  {updateInfo.currentVersion ? `，当前版本 ${updateInfo.currentVersion}` : ""}
                </p>
              ) : updateInfo?.available === false ? (
                <p className="text-sm text-slate-500">当前已是最新版本</p>
              ) : (
                <p className="text-sm text-slate-500">尚未检查更新</p>
              )}
              {installing && (
                <p className="text-xs text-slate-500">
                  正在下载更新：{formatBytes(downloadedBytes)}
                  {totalBytes ? ` / ${formatBytes(totalBytes)}` : ""}
                </p>
              )}
              {!!error && <p className="text-sm text-rose-600">{error}</p>}
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void checkNow()}
                disabled={checking || installing}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                检查更新
              </button>
              <button
                type="button"
                onClick={() => void installNow()}
                disabled={!updateInfo?.available || checking || installing}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
              >
                {installing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                下载并安装
              </button>
            </div>
          </div>
          {!!updateInfo?.body && (
            <div className="mt-3 rounded-lg bg-white/80 p-3 text-sm text-slate-600 whitespace-pre-wrap">
              {updateInfo.body}
            </div>
          )}
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
