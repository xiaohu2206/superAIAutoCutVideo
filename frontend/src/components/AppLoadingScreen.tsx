import React from "react";
import type { BackendResourceStatus } from "../services/clients";
import logoSrc from "../assets/logo.png";

interface AppLoadingScreenProps {
  appVersion?: string;
  updateVersion?: string;
  backendExtractProgress?: BackendExtractProgress | null;
  backendResourceStatus?: BackendResourceStatus | null;
  /** 已等待秒数（用于文案与提示） */
  elapsedSeconds?: number;
  /** 超过该秒数后显示「可能被安全软件拦截」等说明 */
  antivirusHintAfterSec?: number;
  /** 超过该毫秒后显示「跳过等待」按钮（0 表示始终显示） */
  showSkipAfterMs?: number;
  onSkipToMain?: () => void;
}

export interface BackendExtractProgress {
  phase: "start" | "extracting" | "fallback" | "done" | string;
  extracted: number;
  total: number;
  current_file?: string;
  current_index?: number;
  total_files?: number;
}

const AppLoadingScreen: React.FC<AppLoadingScreenProps> = ({
  appVersion,
  updateVersion,
  backendExtractProgress,
  backendResourceStatus,
  elapsedSeconds = 0,
  antivirusHintAfterSec = 25,
  showSkipAfterMs = 45_000,
  onSkipToMain,
}) => {
  const showAntivirusHint = elapsedSeconds >= antivirusHintAfterSec;
  const showSkip =
    typeof onSkipToMain === "function" &&
    (showSkipAfterMs <= 0 || elapsedSeconds * 1000 >= showSkipAfterMs);
  const compactMode = showAntivirusHint || showSkip;
  const isExtracting =
    !!backendExtractProgress &&
    backendExtractProgress.phase !== "done" &&
    (backendExtractProgress.phase === "start" ||
      backendExtractProgress.phase === "extracting" ||
      backendExtractProgress.phase === "fallback");
  const extractTotal = Math.max(0, Number(backendExtractProgress?.total || 0));
  const extractDone = Math.max(0, Number(backendExtractProgress?.extracted || 0));
  const extractPercent =
    extractTotal > 0 ? Math.min(100, Math.max(0, Math.round((extractDone / extractTotal) * 100))) : 0;
  const currentFile = backendExtractProgress?.current_file
    ? backendExtractProgress.current_file.split(/[\\/]/).filter(Boolean).pop()
    : "";
  const backendExeReady =
    !!backendResourceStatus &&
    (backendResourceStatus.backend_exe_exists || backendResourceStatus.nested_backend_exe_exists);

  const fmtTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m <= 0) return `${s}秒`;
    return `${m}分${s.toString().padStart(2, "0")}秒`;
  };

  const fmtBytes = (bytes: number) => {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0B";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return `${value.toFixed(value >= 100 || index === 0 ? 0 : 1)}${units[index]}`;
  };

  const statusLine = (() => {
    const waited = fmtTime(elapsedSeconds);
    if (isExtracting) {
      if (backendExtractProgress?.phase === "fallback") {
        return `解压本地后端（兼容模式）· 已等 ${waited}`;
      }
      const parts = [`解压本地后端 ${extractPercent}%`, `已等 ${waited}`];
      if (extractTotal > 0) {
        parts.push(`${fmtBytes(extractDone)}/${fmtBytes(extractTotal)}`);
      }
      if (backendExtractProgress?.total_files) {
        parts.push(
          `${backendExtractProgress.current_index || 0}/${backendExtractProgress.total_files} 文件`,
        );
      }
      if (currentFile) parts.push(currentFile);
      return parts.join(" · ");
    }
    if (backendResourceStatus && !backendResourceStatus.zip_exists && !backendExeReady) {
      return `后端资源缺失 · 已等 ${waited}`;
    }
    if (backendResourceStatus?.zip_exists && !backendExeReady) {
      return `后端ZIP已复制，等待解压/启动 · 已等 ${waited}`;
    }
    if (backendExeReady) {
      return `后端资源已就绪，正在连接服务 · 已等 ${waited}`;
    }
    return `检查本地后端资源 · 已等 ${waited}`;
  })();

  const resourceItems = backendResourceStatus
    ? [
        {
          label: "ZIP",
          ok: backendResourceStatus.zip_exists,
          text: backendResourceStatus.zip_exists ? `已复制 ${fmtBytes(backendResourceStatus.zip_size)}` : "未找到",
        },
        {
          label: "解压目录",
          ok: backendResourceStatus.extract_dir_exists,
          text: backendResourceStatus.extract_dir_exists ? "已存在" : "未创建",
        },
        {
          label: "后端EXE",
          ok: backendExeReady,
          text: backendExeReady ? "已找到" : "未找到",
        },
      ]
    : [];

  return (
    <div className="relative grid h-screen min-h-0 w-full select-none grid-rows-[1fr_auto] overflow-hidden rounded-[18px] bg-white">
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-gradient-to-br from-blue-100/50 via-violet-100/30 to-transparent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 -right-12 h-56 w-56 rounded-full bg-gradient-to-tl from-sky-100/40 via-indigo-50/25 to-transparent blur-3xl" />

      <div className="relative z-10 flex min-h-0 flex-col items-center justify-center px-5 py-4">
        <div className="flex w-full min-w-0 max-w-md flex-col items-center gap-4">
          <div className="flex shrink-0 items-center gap-3">
            <img src={logoSrc} alt="SuperAI" className="h-11 w-11 shrink-0 rounded-xl object-contain" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">SuperAI</h1>
              <p className="text-xs tracking-wide text-slate-400">智能影视剪辑</p>
            </div>
          </div>

          <div className="flex w-full min-w-0 flex-col gap-2">
            <div className="h-[3px] w-full overflow-hidden rounded-full bg-[#00ecf3]/15">
              <div
                className={`h-full rounded-full bg-gradient-to-r from-[#00ecf3] to-[#00c4d6] ${
                  isExtracting ? "transition-[width] duration-300 ease-out" : "w-1/2 animate-loading-bar"
                }`}
                style={isExtracting ? { width: `${Math.max(3, extractPercent)}%` } : undefined}
              />
            </div>

            <p className="line-clamp-2 text-center text-xs leading-snug text-slate-500" aria-live="polite">
              {statusLine}
            </p>

            {/* {backendResourceStatus && (
              <div
                className={`w-full rounded-lg border px-2.5 py-2 text-[10px] leading-snug ${
                  backendResourceStatus.zip_exists || backendExeReady
                    ? "border-slate-200 bg-slate-50 text-slate-600"
                    : "border-rose-200 bg-rose-50 text-rose-700"
                }`}
                role="status"
                aria-live="polite"
              >
                <div className="grid grid-cols-3 gap-1.5">
                  {resourceItems.map((item) => (
                    <div key={item.label} className="min-w-0 rounded-md bg-white/75 px-2 py-1">
                      <div className="text-[9px] text-slate-400">{item.label}</div>
                      <div className={item.ok ? "truncate font-medium text-emerald-600" : "truncate font-medium text-rose-600"}>
                        {item.text}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-1.5 truncate text-slate-400" title={backendResourceStatus.resource_root}>
                  resources: {backendResourceStatus.resource_root}
                </div>
                <div className={backendResourceStatus.ready ? "mt-0.5 truncate text-emerald-600" : "mt-0.5 truncate text-amber-600"}>
                  {backendResourceStatus.message}
                </div>
              </div>
            )} */}

            {!compactMode && (
              <p className="text-center text-[11px] leading-snug text-slate-400">
                首次启动或 GPU 版本解压可能较慢
              </p>
            )}

            {showAntivirusHint && (
              <p
                className="line-clamp-2 rounded-lg border border-amber-200/80 bg-amber-50/90 px-2.5 py-1.5 text-center text-[10px] leading-snug text-amber-900"
                role="status"
                aria-live="polite"
              >
                若长时间无响应，请将安装目录与{" "}
                <span className="font-mono">AppData\Roaming\com.superautocutvideo.app</span>{" "}
                加入杀软白名单
              </p>
            )}

            {!!updateVersion && (
              <p className="text-center text-[11px] text-emerald-500">可更新至 v{updateVersion}</p>
            )}

            {showSkip && (
              <button
                type="button"
                className="titlebar-no-drag mx-auto rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
                onClick={() => onSkipToMain?.()}
              >
                跳过等待，进入主界面
              </button>
            )}
          </div>
        </div>
      </div>

      {!!appVersion && (
        <p
          className="pointer-events-none shrink-0 pb-4 text-center text-[11px] tabular-nums text-slate-400/90"
          aria-label={`应用版本 ${appVersion}`}
        >
          v{appVersion}
        </p>
      )}
    </div>
  );
};

export default AppLoadingScreen;
