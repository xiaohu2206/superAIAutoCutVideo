/**
 * License API：调用本机后端转发的 /api/licenses*。
 * 上游可能返回统一包装 `{ code, message, data }`（与 auth 一致），也可能为裸 JSON；解包后使用。
 */

import { apiClient } from "@/services/clients";

const REQUEST_TIMEOUT_MS = 45_000;

function backendBase(): string {
  return apiClient.getBaseUrl().replace(/\/$/, "");
}

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
  if (Array.isArray(b.message) && b.message.length) {
    const first = b.message[0];
    if (typeof first === "string") return first;
  }
  if (b.detail != null) {
    if (typeof b.detail === "string") {
      return b.detail;
    }
  }
  return `请求失败 (${status})`;
}

/** 识别 `{ code, message, data }`：code !== 0 抛错；否则返回 `data`；非包装则原样返回 */
function unwrapSuccessBody(body: unknown): unknown {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return body;
  }
  const o = body as Record<string, unknown>;
  if (typeof o.code === "number" && "data" in o) {
    if (o.code !== 0) {
      throw new Error(
        (typeof o.message === "string" && o.message) || `请求失败 (code: ${o.code})`
      );
    }
    return o.data;
  }
  return body;
}

export interface LicenseDevice {
  id: number;
  licenseId: number;
  deviceId: string;
  deviceName: string;
  bindCount?: number;
  lastActiveAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface LicenseRecord {
  id: number;
  licenseKey: string;
  userId: number | null;
  planType: string;
  status: string;
  maxDevices: number;
  durationDays: number | null;
  activateAt: string | null;
  expireAt: string | null;
  remark: string | null;
  devices: LicenseDevice[];
  createdAt: string;
  updatedAt: string;
}

/** GET /api/licenses/client-device：由本机后端按系统信息（mac / Windows 等）生成的设备 ID */
export async function fetchLicenseClientDeviceId(): Promise<string> {
  const raw = await fetchJson<unknown>(`${backendBase()}/api/licenses/client-device`, {
    method: "GET",
    headers: {
      Accept: "application/json, text/plain, */*",
    },
  });
  if (
    raw == null ||
    typeof raw !== "object" ||
    typeof (raw as { deviceId?: unknown }).deviceId !== "string"
  ) {
    throw new Error("本机设备 ID 响应异常");
  }
  const s = (raw as { deviceId: string }).deviceId.trim();
  if (!s) {
    throw new Error("本机设备 ID 为空");
  }
  return s;
}

/** 绑定/展示用设备名（由浏览器环境自动生成，无需用户填写） */
export function getDefaultLicenseClientDeviceName(): string {
  if (typeof window === "undefined") {
    return "SuperAIAutoCut 客户端";
  }
  try {
    const n = window.navigator;
    const uaData = (n as Navigator & { userAgentData?: { platform?: string } }).userAgentData;
    const platform = (uaData?.platform || n.platform || "").trim();
    const base = "网页端";
    const s = platform ? `${base} · ${platform}` : base;
    return s.length > 120 ? `${s.slice(0, 117)}…` : s;
  } catch {
    return "网页端";
  }
}

async function fetchJson<T>(
  url: string,
  init: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...rest } = init;
  const controller = new AbortController();
  const t = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...rest,
      signal: rest.signal ?? controller.signal,
    });
    let body: unknown = null;
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("application/json")) {
      body = await res.json().catch(() => null);
    } else {
      const text = await res.text().catch(() => "");
      body = text.trim() ? text : null;
    }
    if (!res.ok) {
      throw new Error(parseHttpErrorMessage(res.status, body));
    }
    return body as T;
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("请求超时，请检查网络后重试");
    }
    throw e;
  } finally {
    window.clearTimeout(t);
  }
}

/** GET /api/licenses */
export async function fetchMyLicenses(token: string): Promise<LicenseRecord[]> {
  const raw = await fetchJson<unknown>(`${backendBase()}/api/licenses`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  const payload = unwrapSuccessBody(raw);
  if (!Array.isArray(payload)) {
    throw new Error("License 列表格式异常");
  }
  return payload as LicenseRecord[];
}

/** POST /api/licenses/bind：仅传 licenseKey；devices 由本机后端注入，不信任浏览器 */
export async function bindLicense(
  token: string,
  licenseKey: string
): Promise<{ licenseId: number }> {
  const raw = await fetchJson<unknown>(`${backendBase()}/api/licenses/bind`, {
    method: "POST",
    headers: {
      Accept: "application/json, text/plain, */*",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ licenseKey: licenseKey.trim() }),
  });
  const payload = unwrapSuccessBody(raw);
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof (payload as { licenseId?: unknown }).licenseId !== "number"
  ) {
    throw new Error("绑定响应格式异常");
  }
  return payload as { licenseId: number };
}
