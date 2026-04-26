import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { login as apiLogin, getMe, UserInfo } from "./api";

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    isAuthenticated: false,
    isLoading: true,
  });

  const tokenRef = useRef<string | null>(null);

  // 同步 token 到 ref
  useEffect(() => {
    tokenRef.current = state.token;
  }, [state.token]);

  // 初始化：从 localStorage 恢复 token
  useEffect(() => {
    const savedToken = localStorage.getItem(TOKEN_KEY);
    if (savedToken) {
      getMe(savedToken)
        .then((user) => {
          tokenRef.current = savedToken;
          setState({
            token: savedToken,
            user,
            isAuthenticated: true,
            isLoading: false,
          });
        })
        .catch(() => {
          localStorage.removeItem(TOKEN_KEY);
          tokenRef.current = null;
          setState({ token: null, user: null, isAuthenticated: false, isLoading: false });
        });
    } else {
      setState((s) => ({ ...s, isLoading: false }));
    }
  }, []);

  const loginAction = useCallback(async (email: string, password: string) => {
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
    } catch {
      logout();
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
