import { useState, useRef, useEffect, useCallback } from "react";
import { X, Mail, Lock, KeyRound, ArrowRight, Loader2 } from "lucide-react";
import {
  sendRegisterCode,
  register,
  sendResetCode,
  resetPassword,
} from "./api";
import { useAuth } from "./AuthContext";

type ModalTab = "login" | "register" | "reset";

interface LoginRegisterModalProps {
  open: boolean;
  onClose: () => void;
}

export default function LoginRegisterModal({ open, onClose }: LoginRegisterModalProps) {
  const { loginAction } = useAuth();
  const [tab, setTab] = useState<ModalTab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [countdown, setCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (countdown > 0) {
      countdownRef.current = setInterval(() => {
        setCountdown((c) => {
          if (c <= 1) {
            if (countdownRef.current) clearInterval(countdownRef.current);
            return 0;
          }
          return c - 1;
        });
      }, 1000);
    }
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [countdown > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const switchTab = useCallback((t: ModalTab) => {
    setTab(t);
    setError("");
    setSuccess("");
  }, []);

  // 弹框关闭时重置状态（含 loading：避免请求未正常结束时再次打开仍显示「处理中」）
  useEffect(() => {
    if (!open) {
      setEmail("");
      setPassword("");
      setCode("");
      setNewPassword("");
      setError("");
      setSuccess("");
      setCountdown(0);
      setTab("login");
      setLoading(false);
    }
  }, [open]);

  const handleSendCode = async (type: "register" | "reset") => {
    if (!email.trim()) {
      setSuccess("");
      setError("请输入邮箱");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      if (type === "register") {
        await sendRegisterCode(email);
      } else {
        await sendResetCode(email);
      }
      setCountdown(60);
      setError("");
      setSuccess("验证码已发送，请查收邮箱");
    } catch (e: any) {
      setSuccess("");
      setError(e.message || "发送验证码失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    if (!email.trim() || !password || !code) {
      setSuccess("");
      setError("请填写完整信息");
      return;
    }
    if (password.length < 6) {
      setSuccess("");
      setError("密码至少6位");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await register(email, password, code);
      setError("");
      setSuccess("注册成功，请登录");
      setTab("login");
      setCode("");
      setPassword("");
    } catch (e: any) {
      setSuccess("");
      setError(e.message || "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      setSuccess("");
      setError("请输入邮箱和密码");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await loginAction(email, password);
      onClose();
    } catch (e: any) {
      setSuccess("");
      setError(e.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (!email.trim() || !code || !newPassword) {
      setSuccess("");
      setError("请填写完整信息");
      return;
    }
    if (newPassword.length < 6) {
      setSuccess("");
      setError("新密码至少6位");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await resetPassword(email, code, newPassword);
      setError("");
      setSuccess("密码重置成功，请登录");
      setTab("login");
      setCode("");
      setNewPassword("");
    } catch (e: any) {
      setSuccess("");
      setError(e.message || "重置密码失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => {
    if (tab === "login") handleLogin();
    else if (tab === "register") handleRegister();
    else handleResetPassword();
  };

  if (!open) return null;

  const tabs: { key: ModalTab; label: string }[] = [
    { key: "login", label: "登录" },
    { key: "register", label: "注册" },
    { key: "reset", label: "忘记密码" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div
        className="relative w-full max-w-[420px] rounded-2xl border border-slate-200/80 bg-white shadow-[0_24px_80px_-12px_rgba(15,23,42,0.25)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 关闭按钮 */}
        <button
          onClick={onClose}
          className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <X className="h-4 w-4" />
        </button>

        {/* 标题 */}
        <div className="px-7 pt-7 pb-2">
          <h2 className="text-lg font-semibold tracking-tight text-slate-900">
            {tab === "login" ? "欢迎回来" : tab === "register" ? "创建账号" : "重置密码"}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {tab === "login"
              ? "登录您的账号以继续使用"
              : tab === "register"
              ? "注册一个新账号"
              : "通过邮箱验证码重置密码"}
          </p>
        </div>

        {/* Tab 栏 */}
        <div className="mx-7 mt-3 flex gap-1 rounded-xl bg-slate-100 p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => switchTab(t.key)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                tab === t.key
                  ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 消息提示 */}
        <div className="px-7 pt-4">
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 ring-1 ring-red-200/80">
              {error}
            </div>
          ) : success ? (
            <div className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700 ring-1 ring-green-200/80">
              {success}
            </div>
          ) : null}
        </div>

        {/* 表单 */}
        <div className="flex flex-col gap-4 px-7 pt-4 pb-7">
          {/* 邮箱 */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-slate-600">邮箱地址</span>
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 ring-inset transition-colors focus-within:border-blue-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100">
              <Mail className="h-4 w-4 shrink-0 text-slate-400" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                placeholder="请输入邮箱"
                disabled={loading}
              />
            </div>
          </label>

          {/* 验证码（注册/重置） */}
          {(tab === "register" || tab === "reset") && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-600">验证码</span>
              <div className="flex items-center gap-2">
                <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 ring-inset transition-colors focus-within:border-blue-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100">
                  <KeyRound className="h-4 w-4 shrink-0 text-slate-400" />
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                    placeholder="6位数字验证码"
                    maxLength={6}
                    disabled={loading}
                  />
                </div>
                <button
                  onClick={() => handleSendCode(tab === "register" ? "register" : "reset")}
                  disabled={countdown > 0 || loading}
                  className={`shrink-0 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-colors ${
                    countdown > 0
                      ? "bg-slate-100 text-slate-400"
                      : "bg-blue-50 text-blue-700 ring-1 ring-blue-200/80 hover:bg-blue-100"
                  }`}
                >
                  {countdown > 0 ? `${countdown}s` : "获取验证码"}
                </button>
              </div>
            </label>
          )}

          {/* 密码（登录/注册） */}
          {(tab === "login" || tab === "register") && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-600">密码</span>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 ring-inset transition-colors focus-within:border-blue-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100">
                <Lock className="h-4 w-4 shrink-0 text-slate-400" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  placeholder={tab === "register" ? "至少6位密码" : "请输入密码"}
                  disabled={loading}
                />
              </div>
            </label>
          )}

          {/* 新密码（重置） */}
          {tab === "reset" && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-slate-600">新密码</span>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 ring-inset transition-colors focus-within:border-blue-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-blue-100">
                <Lock className="h-4 w-4 shrink-0 text-slate-400" />
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  placeholder="至少6位新密码"
                  disabled={loading}
                />
              </div>
            </label>
          )}

          {/* 提交按钮 */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className={`mt-1 flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold transition-all ${
              loading
                ? "bg-blue-100 text-blue-400"
                : "bg-blue-600 text-white shadow-sm hover:bg-blue-700 active:scale-[0.98]"
            }`}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            {loading
              ? "处理中..."
              : tab === "login"
              ? "登 录"
              : tab === "register"
              ? "注 册"
              : "重置密码"}
          </button>
        </div>
      </div>
    </div>
  );
}
