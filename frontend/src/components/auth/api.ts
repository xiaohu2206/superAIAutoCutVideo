/**
 * 认证相关 API 服务
 * 封装后端 /api/auth/* 接口调用
 */

const API_BASE = "/api/auth";

interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

interface LoginData {
  token: string;
  user: UserInfo;
}

interface UserInfo {
  id: number;
  email: string;
  status: string;
  createdAt?: string;
  updatedAt?: string;
}

async function request<T>(url: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `请求失败 (${res.status})`);
  }

  return res.json();
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

/** 发送注册验证码 */
export async function sendRegisterCode(email: string): Promise<boolean> {
  const res = await request<boolean>(`${API_BASE}/send-register-code`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  return res.data;
}

/** 注册用户 */
export async function register(
  email: string,
  password: string,
  code: string
): Promise<{ userId: number }> {
  const res = await request<{ userId: number }>(`${API_BASE}/register`, {
    method: "POST",
    body: JSON.stringify({ email, password, code }),
  });
  return res.data;
}

/** 用户登录 */
export async function login(
  email: string,
  password: string
): Promise<LoginData> {
  const res = await request<LoginData>(`${API_BASE}/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return res.data;
}

/** 获取当前用户信息 */
export async function getMe(token: string): Promise<UserInfo & { createdAt: string; updatedAt: string }> {
  const res = await request<UserInfo & { createdAt: string; updatedAt: string }>(`${API_BASE}/me`, {
    headers: {
      ...authHeaders(token),
    },
  });
  return res.data;
}

/** 发送重置密码验证码 */
export async function sendResetCode(email: string): Promise<boolean> {
  const res = await request<boolean>(`${API_BASE}/send-reset-code`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  return res.data;
}

/** 重置密码 */
export async function resetPassword(
  email: string,
  code: string,
  newPassword: string
): Promise<boolean> {
  const res = await request<boolean>(`${API_BASE}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ email, code, newPassword }),
  });
  return res.data;
}

export type { UserInfo, LoginData };
