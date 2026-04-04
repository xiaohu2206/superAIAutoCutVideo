import {
  AppWindow,
  Copy,
  Github,
  Home,
  Minus,
  Settings,
  Square,
  X,
} from "lucide-react";
import React from "react";
import Logo from "@/assets/logo.png";
import { useAppVersion } from "@/hooks/useAppVersion";
import { TauriCommands } from "@/services/clients";

interface NavigationProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isTauri?: boolean;
  className?: string;
}

const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
  isTauri = false,
  className = "",
}) => {
  const { appVersion } = useAppVersion();
  const [isMaximized, setIsMaximized] = React.useState(false);

  const navItems = [
    {
      id: "home",
      label: "项目",
      icon: Home,
      description: "项目管理与剪辑流程",
    },
    {
      id: "settings",
      label: "设置",
      icon: Settings,
      description: "应用配置和偏好设置",
    },
  ];

  React.useEffect(() => {
    if (!isTauri) return;

    let mounted = true;

    const syncMaximizedState = async () => {
      const value = await TauriCommands.isWindowMaximized();
      if (mounted) {
        setIsMaximized(value);
      }
    };

    void syncMaximizedState();

    const handleResize = () => {
      void syncMaximizedState();
    };

    window.addEventListener("resize", handleResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", handleResize);
    };
  }, [isTauri]);

  const handleToggleMaximize = async () => {
    const nextState = await TauriCommands.toggleMaximizeWindow();
    setIsMaximized(nextState);
  };

  return (
    <header
      className={`sticky top-0 z-50 border-b border-slate-200/80 bg-white/92 backdrop-blur-xl shadow-[0_12px_40px_-24px_rgba(15,23,42,0.35)] ${className}`}
    >
      <div className="flex h-[72px] items-center px-3 sm:px-4 lg:px-6">
        <div className="titlebar-drag flex min-w-0 flex-1 items-center gap-3" data-tauri-drag-region={isTauri ? true : undefined}>
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl from-blue-500 via-indigo-500 to-violet-500  ring-1 ring-white/70">
              <img src={Logo} alt="SuperAI" className="h-8 w-8 object-contain" />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-[15px] font-semibold tracking-[0.02em] text-slate-900">
                  SuperAI 影视剪辑
                </h1>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                {!!appVersion && <span>v{appVersion}</span>}
              </div>
            </div>
          </div>

          <div className="hidden flex-1 justify-center px-2 md:flex lg:px-4">
            <div className="titlebar-no-drag flex items-center gap-1 rounded-2xl border border-slate-200 bg-slate-50/80 p-1 shadow-inner shadow-slate-200/60">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;

                return (
                  <button
                    key={item.id}
                    onClick={() => onTabChange(item.id)}
                    className={[
                      "titlebar-no-drag group relative inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-all duration-200",
                      isActive
                        ? "bg-white text-blue-700 shadow-sm ring-1 ring-blue-100"
                        : "text-slate-600 hover:bg-white/80 hover:text-slate-900",
                    ].join(" ")}
                    title={item.description}
                  >
                    <Icon
                      className={`h-4 w-4 transition-colors ${
                        isActive ? "text-blue-600" : "text-slate-400 group-hover:text-slate-600"
                      }`}
                    />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="titlebar-no-drag ml-3 flex shrink-0 items-center gap-1">
          <button
            onClick={() =>
              TauriCommands.openExternalLink("https://github.com/xiaohu2206/superAIAutoCutVideo")
            }
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-800"
            title="查看源代码"
          >
            <Github className="h-4.5 w-4.5" />
          </button>

          {isTauri && (
            <div className="titlebar-no-drag flex items-center overflow-hidden rounded-xl border border-slate-200 bg-slate-50/90">
              <button
                onClick={() => void TauriCommands.minimizeWindow()}
                className="titlebar-no-drag inline-flex h-10 w-10 items-center justify-center text-slate-500 transition-colors hover:bg-slate-200/80 hover:text-slate-800 sm:w-11"
                title="最小化"
                aria-label="最小化窗口"
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                onClick={handleToggleMaximize}
                className="titlebar-no-drag inline-flex h-10 w-10 items-center justify-center border-l border-r border-slate-200 text-slate-500 transition-colors hover:bg-slate-200/80 hover:text-slate-800 sm:w-11"
                title={isMaximized ? "还原" : "最大化"}
                aria-label={isMaximized ? "还原窗口" : "最大化窗口"}
              >
                {isMaximized ? (
                  <Copy className="h-3.5 w-3.5" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}
              </button>
              <button
                onClick={() => void TauriCommands.closeWindow()}
                className="titlebar-no-drag inline-flex h-10 w-10 items-center justify-center text-slate-500 transition-colors hover:bg-rose-500 hover:text-white sm:w-11"
                title="关闭"
                aria-label="关闭窗口"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-slate-100/80 px-3 py-2 md:hidden sm:px-4">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={[
                  "inline-flex min-w-fit items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium transition-all duration-200",
                  isActive
                    ? "bg-blue-600 text-white shadow-sm"
                    : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                ].join(" ")}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};

export default Navigation;
