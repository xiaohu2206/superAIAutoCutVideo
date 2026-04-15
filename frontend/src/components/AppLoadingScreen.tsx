import React from "react";
import logoSrc from "../assets/logo.png";

interface AppLoadingScreenProps {
  appVersion?: string;
}

const AppLoadingScreen: React.FC<AppLoadingScreenProps> = ({ appVersion }) => {
  return (
    <div className="relative flex min-h-screen select-none overflow-hidden rounded-[18px] bg-white">
      {/* 右侧淡色装饰光斑 */}
      <div className="pointer-events-none absolute -right-20 -top-20 h-[36rem] w-[36rem] rounded-full bg-gradient-to-br from-blue-100/60 via-violet-100/40 to-transparent blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 -right-10 h-[28rem] w-[28rem] rounded-full bg-gradient-to-tl from-sky-100/50 via-indigo-50/30 to-transparent blur-3xl" />

      <div className="relative z-10 flex min-h-screen w-full flex-col px-12">
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="w-full max-w-md flex flex-col items-center">
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
            <div className="mt-10 flex w-full max-w-xs flex-col items-center">
              <div className="h-[3px] w-full overflow-hidden rounded-full bg-[#00ecf3]/15">
                <div className="h-full w-1/2 animate-[loading_1.4s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-[#00ecf3] to-[#00c4d6]" />
              </div>
              <p className="mt-3 text-center text-xs text-slate-400">即将就绪，预计 5 分钟</p>
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

      <style>{`
        @keyframes loading {
          0% { transform: translateX(-100%); }
          50% { transform: translateX(150%); }
          100% { transform: translateX(-100%); }
        }
      `}</style>
    </div>
  );
};

export default AppLoadingScreen;
