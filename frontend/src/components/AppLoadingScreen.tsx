import React from "react";
import logoSrc from "../assets/logo.png";

interface AppLoadingScreenProps {
  appVersion?: string;
  updateVersion?: string;
  /** 已等待秒数（用于文案与提示） */
  elapsedSeconds?: number;
  /** 超过该秒数后显示「可能被安全软件拦截」等说明 */
  antivirusHintAfterSec?: number;
  /** 超过该毫秒后显示「跳过等待」按钮（0 表示始终显示） */
  showSkipAfterMs?: number;
  onSkipToMain?: () => void;
}

const AppLoadingScreen: React.FC<AppLoadingScreenProps> = ({
  appVersion,
  updateVersion,
  elapsedSeconds = 0,
  antivirusHintAfterSec = 25,
  showSkipAfterMs = 45_000,
  onSkipToMain,
}) => {
  const showAntivirusHint = elapsedSeconds >= antivirusHintAfterSec;
  const showSkip =
    typeof onSkipToMain === "function" &&
    (showSkipAfterMs <= 0 || elapsedSeconds * 1000 >= showSkipAfterMs);

  const fmtTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m <= 0) return `${s} 秒`;
    return `${m} 分 ${s.toString().padStart(2, "0")} 秒`;
  };

  return (
    <div className="relative flex min-h-screen select-none overflow-hidden rounded-[18px] bg-white">
      {/* 右侧淡色装饰光斑 */}
      <div className="pointer-events-none absolute -right-20 -top-20 h-[36rem] w-[36rem] rounded-full bg-gradient-to-br from-blue-100/60 via-violet-100/40 to-transparent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -right-10 h-[28rem] w-[28rem] rounded-full bg-gradient-to-tl from-sky-100/50 via-indigo-50/30 to-transparent blur-3xl" />

      <div className="relative z-10 flex min-h-screen w-full flex-col px-6 sm:px-12">
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="w-full max-w-lg flex flex-col items-center">
            {/* 品牌区域 */}
            <div className="flex items-center justify-center gap-4">
              <img src={logoSrc} alt="SuperAI" className="h-14 w-14 rounded-2xl object-contain" />
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-slate-900">
                  SuperAI
                </h1>
                <p className="mt-0.5 text-sm tracking-wide text-slate-400">
                  智能影视剪辑
                </p>
              </div>
            </div>

            {/* 加载指示 + 文案 */}
            <div className="mt-10 flex w-full max-w-md flex-col items-center">
              <div className="h-[3px] w-full overflow-hidden rounded-full bg-[#00ecf3]/15">
                <div className="h-full w-1/2 animate-loading-bar rounded-full bg-gradient-to-r from-[#00ecf3] to-[#00c4d6]" />
              </div>
              <p
                className="mt-3 text-center text-xs text-slate-500"
                aria-live="polite"
              >
                正在连接本地后端… 已等待 {fmtTime(elapsedSeconds)}
              </p>
              <p className="mt-1 text-center text-[11px] leading-relaxed text-slate-400">
                首次启动或 GPU 版本解压较大资源时可能较慢，请稍候。
              </p>
              {showAntivirusHint && (
                <div
                  className="mt-4 w-full rounded-xl border border-amber-200/90 bg-amber-50/95 px-3 py-2.5 text-left shadow-sm"
                  role="status"
                  aria-live="polite"
                >
                  <p className="text-[11px] font-medium text-amber-900">
                    若长时间无响应，可能被安全软件拦截
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-amber-800/95">
                    请将本程序安装目录、以及用户目录下{" "}
                    <span className="font-mono text-[10px]">AppData\Roaming\com.superautocutvideo.app</span>{" "}
                    加入杀毒软件「信任/白名单」，保存后可在主界面内再次重试连接。
                  </p>
                </div>
              )}
              {!!updateVersion && (
                <p className="mt-3 text-center text-[11px] text-emerald-500">
                  检测到可更新版本 v{updateVersion}
                </p>
              )}
              {showSkip && (
                <div className="mt-6 flex w-full flex-col items-center gap-2">
                  <button
                    type="button"
                    className="titlebar-no-drag rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
                    onClick={() => onSkipToMain?.()}
                  >
                    跳过等待，进入主界面
                  </button>
                  <p className="max-w-sm text-center text-[10px] text-slate-400">
                    进入后部分功能需后端就绪才可使用；您可在设置或提示条中稍后重试。
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
        {!!appVersion && (
          <div className="mx-auto w-full max-w-md pb-8">
            <p
              className="pointer-events-none text-center text-[11px] tabular-nums tracking-wide text-slate-400/90"
              aria-label={`应用版本 ${appVersion}`}
            >
              v{appVersion}
            </p>
          </div>
        )}
      </div>

    </div>
  );
};

export default AppLoadingScreen;
