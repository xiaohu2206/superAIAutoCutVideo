import {
  User,
  Mail,
  Shield,
  Calendar,
  Clock,
  LogOut,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { useAuth } from "./AuthContext";

interface UserProfileProps {
  onBack: () => void;
}

export default function UserProfile({ onBack }: UserProfileProps) {
  const { user, logout, isLoading } = useAuth();

  const handleLogout = () => {
    logout();
    onBack();
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-sm text-slate-400">加载中...</div>
      </div>
    );
  }

  if (!user) return null;

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  const infoItems = [
    {
      icon: User,
      label: "用户 ID",
      value: String(user.id),
    },
    {
      icon: Mail,
      label: "邮箱地址",
      value: user.email,
    },
    {
      icon: Shield,
      label: "账号状态",
      value: user.status === "active" ? "正常" : "已禁用",
      badge: true,
      active: user.status === "active",
    },
    {
      icon: Calendar,
      label: "注册时间",
      value: formatDate((user as any).createdAt),
    },
    {
      icon: Clock,
      label: "更新时间",
      value: formatDate((user as any).updatedAt),
    },
  ];

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-3xl flex-1 flex-col gap-6 py-2">
      {/* 头像区域 */}
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-slate-200/80 bg-gradient-to-b from-blue-50/60 to-white px-6 py-8">
        <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 shadow-lg shadow-blue-200/50">
          <span className="text-3xl font-bold text-white">
            {user.email.charAt(0).toUpperCase()}
          </span>
        </div>
        <div className="text-center">
          <h2 className="text-lg font-semibold text-slate-900">{user.email}</h2>
          <div className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ring-1">
            {user.status === "active" ? (
              <>
                <CheckCircle className="h-3 w-3 text-green-500" />
                <span className="bg-green-50 text-green-700 ring-green-200/80">账号正常</span>
              </>
            ) : (
              <>
                <XCircle className="h-3 w-3 text-red-500" />
                <span className="bg-red-50 text-red-700 ring-red-200/80">账号已禁用</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 信息列表 */}
      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm">
        <div className="border-b border-slate-100 px-5 py-3">
          <h3 className="text-sm font-semibold text-slate-900">账号信息</h3>
        </div>
        <div className="divide-y divide-slate-100">
          {infoItems.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.label}
                className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-slate-50/50"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
                  <Icon className="h-4 w-4" />
                </div>
                <span className="w-24 shrink-0 text-sm text-slate-500">{item.label}</span>
                {item.badge ? (
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      item.active
                        ? "bg-green-50 text-green-700 ring-1 ring-green-200/80"
                        : "bg-red-50 text-red-700 ring-1 ring-red-200/80"
                    }`}
                  >
                    {item.value}
                  </span>
                ) : (
                  <span className="text-sm font-medium text-slate-900">{item.value}</span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 退出登录 */}
      <button
        onClick={handleLogout}
        className="flex items-center justify-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-3 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 hover:text-red-700"
      >
        <LogOut className="h-4 w-4" />
        退出登录
      </button>
    </div>
  );
}
