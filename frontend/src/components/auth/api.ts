/**
 * 认证相关 API 服务
 * 封装后端 /api/auth/* 接口调用
 *
 * 必须使用后端 base URL（与 apiClient 一致），不能用相对路径；
 * 否则在 Vite 开发服（如 localhost:1420）上会请求到前端服务器导致 404。
 */

import { apiClient } from "@/services/clients";

function authUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${apiClient.getBaseUrl()}/api/auth${p}`;
}

interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

const AUTH_REQUEST_TIMEOUT_MS = 45_000;

function parseHttpErrorMessage(status: number, body: unknown): string {
  if (body == null) {
    return `请求失败 (${status})`;
  }
  if (typeof body === "string" && body.trim()) {
    return body;
  }
  if (typeof body !== "object" || body === null) {
    return `请求失败 (${status})`;
  }
  const b = body as Record<string, unknown>;
  if (typeof b.message === "string" && b.message) {
    return b.message;
  }
  if (b.detail != null) {
    if (typeof b.detail === "string") {
      return b.detail;
    }
    if (Array.isArray(b.detail) && b.detail[0] && typeof (b.detail[0] as { msg?: string }).msg === "string") {
      return (b.detail[0] as { msg: string }).msg;
    }
  }
  return `请求失败 (${status})`;
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
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), AUTH_REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
      signal: options?.signal ?? controller.signal,
    });

    if (!res.ok) {
      let body: unknown = null;
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (ct.includes("application/json")) {
        body = await res.json().catch(() => null);
      } else {
        const text = await res.text().catch(() => "");
        body = text.trim() ? text : null;
      }
      throw new Error(parseHttpErrorMessage(res.status, body));
    }

    let data: ApiResponse<T>;
    try {
      data = (await res.json()) as ApiResponse<T>;
    } catch {
      throw new Error(`请求失败 (${res.status})`);
    }
    if (typeof data.code === "number" && data.code !== 0) {
      throw new Error(
        (typeof data.message === "string" && data.message) || `请求失败 (code: ${data.code})`
      );
    }
    return data;
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("请求超时，请检查网络后重试");
    }
    throw e;
  } finally {
    window.clearTimeout(timeout);
  }
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

/** 发送注册验证码 */
export async function sendRegisterCode(email: string): Promise<boolean> {
  const res = await request<boolean>(authUrl("/send-register-code"), {
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
  const res = await request<{ userId: number }>(authUrl("/register"), {
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
  const res = await request<LoginData>(authUrl("/login"), {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return res.data;
}

/** 获取当前用户信息 */
export async function getMe(token: string): Promise<UserInfo & { createdAt: string; updatedAt: string }> {
  const res = await request<UserInfo & { createdAt: string; updatedAt: string }>(authUrl("/me"), {
    headers: {
      ...authHeaders(token),
    },
  });
  return res.data;
}

/** 发送重置密码验证码 */
export async function sendResetCode(email: string): Promise<boolean> {
  const res = await request<boolean>(authUrl("/send-reset-code"), {
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
  const res = await request<boolean>(authUrl("/reset-password"), {
    method: "POST",
    body: JSON.stringify({ email, code, newPassword }),
  });
  return res.data;
}

export type { UserInfo, LoginData };
