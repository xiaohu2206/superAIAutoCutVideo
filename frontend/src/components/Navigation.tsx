import {
  Home,
  Moon,
  Settings,
  Sun,
  User,
} from "lucide-react";
import React, { useState, useEffect } from "react";
import Logo from "@/assets/logo.png";
import LogConsolePanel from "@/components/settingsPage/components/LogConsolePanel";
import { LoginRegisterModal } from "@/components/auth";
import { useAuth } from "@/components/auth";

interface NavigationProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  onHomeClick?: () => void;
  onProfileClick?: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  className?: string;
}

const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
  onHomeClick,
  onProfileClick,
  theme,
  onToggleTheme,
  className = "",
}) => {
  const [showAuthModal, setShowAuthModal] = useState(false);
  const { isAuthenticated, user } = useAuth();

  useEffect(() => {
    const handler = () => setShowAuthModal(true);
    window.addEventListener("sacv:show-login-modal", handler);
    return () => window.removeEventListener("sacv:show-login-modal", handler);
  }, []);

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

  const handlePersonClick = () => {
    if (isAuthenticated) {
      onProfileClick?.();
    } else {
      setShowAuthModal(true);
    }
  };

  return (
    <>
      <aside
        className={`flex h-full w-[40px] shrink-0 flex-col items-center border-r border-slate-200/80 bg-white/90 py-3 shadow-[10px_0_30px_-24px_rgba(15,23,42,0.35)] backdrop-blur-xl dark:border-white/10 dark:bg-[#181818]/90 dark:shadow-[10px_0_30px_-24px_rgba(0,0,0,0.85)] ${className}`}
      >
        <div className="flex items-center justify-center">
          <img src={Logo} alt="SuperAI" className="h-6 w-6 object-contain" />
        </div>

        <div className="mt-5 flex flex-1 flex-col items-center gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;

            return (
              <button
                key={item.id}
                onClick={() => {
                  if (item.id === "home") {
                    onHomeClick?.();
                    return;
                  }
                  onTabChange(item.id);
                }}
                className={[
                  "group flex h-9 w-9 items-center justify-center rounded-xl transition-all duration-200",
                  isActive
                    ? "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300"
                    : "text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100",
                ].join(" ")}
                title={item.description}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
        </div>

        <div className="border-t border-slate-200/80 pt-3 dark:border-white/10">
          <div className="flex flex-col items-center gap-2">
            <button
              onClick={onToggleTheme}
              className="group flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
              title={theme === "dark" ? "切换到亮色主题" : "切换到暗黑主题"}
              aria-label={theme === "dark" ? "切换到亮色主题" : "切换到暗黑主题"}
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              onClick={handlePersonClick}
              className="group flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
              title={isAuthenticated ? `已登录: ${user?.email}` : "登录 / 注册"}
            >
              <User className="h-4 w-4" />
            </button>
            <LogConsolePanel enabled={true} />
            {/* <button
              onClick={() =>
                TauriCommands.openExternalLink("https://github.com/xiaohu2206/superAIAutoCutVideo")
              }
              className="group flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700"
              title="查看源代码"
            >
              <Github className="h-4 w-4" />
            </button> */}
          </div>
        </div>
      </aside>

      {/* 登录/注册弹框 */}
      <LoginRegisterModal
        open={showAuthModal}
        onClose={() => setShowAuthModal(false)}
      />
    </>
  );
};

export default Navigation;
