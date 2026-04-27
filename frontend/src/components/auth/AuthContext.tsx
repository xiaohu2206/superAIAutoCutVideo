import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { login as apiLogin, getMe, UserInfo } from "./api";
import { BACKEND_CONFIGURED_EVENT } from "@/services/clients";

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  loginAction: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "sacv_auth_token";

const isAuthFailureMessage = (msg: string) =>
  /401|403|unauthorized|未授权|无权限|token|登录|过期|expired|invalid|无效/i.test(msg);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    isAuthenticated: false,
    isLoading: true,
  });

  const tokenRef = useRef<string | null>(null);
  const restoreSessionInFlight = useRef(false);

  // 同步 token 到 ref
  useEffect(() => {
    tokenRef.current = state.token;
  }, [state.token]);

  // 初始化：在 apiClient 端口对齐后再用 token 调 /me（避免先于 App 里 configureBackend 时误用默认 8000 而清掉登录态）
  useEffect(() => {
    if (typeof window === "undefined") return;

    if (!localStorage.getItem(TOKEN_KEY)) {
      setState((s) => ({ ...s, isLoading: false }));
      return;
    }

    const restore = async () => {
      if (restoreSessionInFlight.current) return;
      const savedToken = localStorage.getItem(TOKEN_KEY);
      if (!savedToken) {
        setState((s) => ({ ...s, isLoading: false }));
        return;
      }
      restoreSessionInFlight.current = true;
      try {
        const user = await getMe(savedToken);
        tokenRef.current = savedToken;
        setState({
          token: savedToken,
          user,
          isAuthenticated: true,
          isLoading: false,
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (isAuthFailureMessage(msg)) {
          localStorage.removeItem(TOKEN_KEY);
          tokenRef.current = null;
          setState({ token: null, user: null, isAuthenticated: false, isLoading: false });
        } else {
          setState((s) => ({ ...s, isLoading: false }));
        }
      } finally {
        restoreSessionInFlight.current = false;
      }
    };

    let fallbackT: ReturnType<typeof setTimeout> | undefined;

    const onBackendConfigured = () => {
      if (fallbackT) {
        window.clearTimeout(fallbackT);
        fallbackT = undefined;
      }
      void restore();
    };

    window.addEventListener(BACKEND_CONFIGURED_EVENT, onBackendConfigured);
    // 未 emit 事件时（如浏览器仅用默认 8000）在稍后再试，避免与首次 configureBackend 抢跑
    fallbackT = window.setTimeout(() => {
      void restore();
    }, 3000);

    return () => {
      window.removeEventListener(BACKEND_CONFIGURED_EVENT, onBackendConfigured);
      if (fallbackT) window.clearTimeout(fallbackT);
    };
  }, []);

  const loginAction = useCallback(async (email: string, password: string) => {
    // 会话恢复与登录可能并发：用户点登录时结束「恢复中」挡板，避免失败/慢请求后 UI 一直停在加载态
    setState((s) => (s.isLoading ? { ...s, isLoading: false } : s));
    const data = await apiLogin(email, password);
    localStorage.setItem(TOKEN_KEY, data.token);
    tokenRef.current = data.token;
    setState({
      token: data.token,
      user: data.user,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    tokenRef.current = null;
    setState({ token: null, user: null, isAuthenticated: false, isLoading: false });
  }, []);

  const refreshUser = useCallback(async () => {
    const currentToken = tokenRef.current;
    if (!currentToken) return;
    try {
      const user = await getMe(currentToken);
      setState((s) => ({ ...s, user }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (isAuthFailureMessage(msg)) {
        logout();
      }
    }
  }, [logout]);

  return (
    <AuthContext.Provider value={{ ...state, loginAction, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
