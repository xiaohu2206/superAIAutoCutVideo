import {
  Github,
  Home,
  Settings,
} from "lucide-react";
import React from "react";
import Logo from "@/assets/logo.png";
import LogConsolePanel from "@/components/settingsPage/components/LogConsolePanel";
import { TauriCommands } from "@/services/clients";

interface NavigationProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  onHomeClick?: () => void;
  className?: string;
}

const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
  onHomeClick,
  className = "",
}) => {
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

  return (
    <aside
      className={`flex h-full w-[40px] shrink-0 flex-col items-center border-r border-slate-200/80 bg-white/90 py-3 shadow-[10px_0_30px_-24px_rgba(15,23,42,0.35)] backdrop-blur-xl ${className}`}
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
                  ? "text-blue-600"
                  : "text-slate-400 hover:bg-slate-100 hover:text-slate-700",
              ].join(" ")}
              title={item.description}
            >
              <Icon className="h-4 w-4" />
            </button>
          );
        })}
      </div>

      <div className="border-t border-slate-200/80 pt-3">
        <div className="flex flex-col items-center gap-2">
          <LogConsolePanel enabled={true} />
          <button
            onClick={() =>
              TauriCommands.openExternalLink("https://github.com/xiaohu2206/superAIAutoCutVideo")
            }
            className="group flex h-9 w-9 items-center justify-center rounded-xl text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700"
            title="查看源代码"
          >
            <Github className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Navigation;
