# License 自助解绑 — 前后端移植文档

面向在**其它电脑 / 其它项目**复现「我的 License」中的**自助解绑**能力。本仓库实现为：**前端 → 本机 FastAPI 后端 → 账号上游服务** 三层透传；业务规则（3 次上限、第 3 次吊销）由**上游**执行，本机只做转发与 UI 展示。

**相关上游接口总览**（绑定、列表等）：见 `.trae/documents/license-user-api.md`（本文仅补充 **self-unbind** 及本仓库落地代码）。

---

## 1. 业务规则（与 UI 文案一致）

| 规则 | 说明 |
|------|------|
| 次数上限 | 每个 License 在**当前用户账号下**累计最多 **3 次**自助解绑 |
| 第 3 次后果 | 第 3 次解绑完成后，上游将该 License **吊销**（`status: revoked`），无法再使用 |
| 列表字段 | 上游若在 `GET /api/licenses` 中返回 `userSelfUnbindCount`、`remainingSelfUnbinds`，前端用于展示剩余次数、隐藏按钮、弹窗预警 |
| 按钮隐藏 | `status === revoked` 或 `remainingSelfUnbinds <= 0` 时不展示「解绑」 |
| 第 3 次预警 | `userSelfUnbindCount >= 2` 或 `remainingSelfUnbinds === 1` 时，确认弹窗显示红色「本次为第 3 次」提示 |

---

## 2. 调用链

```text
UserProfileLicenses.tsx
  └─ selfUnbindLicense(token, licenseId)     [licenseApi.ts]
       └─ POST {本机后端}/api/licenses/{id}/self-unbind
            Body: {}
            Header: Authorization: Bearer <accessToken>
            └─ license_routes.self_unbind_license   [license_routes.py]
                 └─ forward_upstream_post_raw       [auth_upstream.py]
                      └─ POST {上游}/api/licenses/{id}/self-unbind
                           Body: {}
                           Header: Authorization + X-Tenant-Type: jujiancut
```

列表刷新：解绑成功后调用 `fetchMyLicenses`（`GET /api/licenses`）重新拉取，以更新 `remainingSelfUnbinds` 等字段。

---

## 3. 需拷贝 / 注册的文件清单

### 3.1 后端（Python / FastAPI）

| 文件 | 作用 |
|------|------|
| `backend/routes/license_routes.py` | 路由：`POST /{license_id}/self-unbind`（约 87–97 行） |
| `backend/modules/auth/auth_upstream.py` | `forward_upstream_post_raw`、`get_auth_upstream_base`、`merge_auth_upstream_headers` |
| `backend/main.py` | `app.include_router(licenses_router)`（若尚无 License 路由需一并注册） |

**最小新增路由**（已存在 `licenses_router` 时只加 handler）：

```python
@licenses_router.post(
    "/{license_id}/self-unbind",
    summary="自助解绑 License（上游累计 3 次，第 3 次将吊销）",
)
async def self_unbind_license(license_id: int, request: Request):
    return await forward_upstream_post_raw(
        f"/api/licenses/{license_id}/self-unbind",
        b"{}",
        request.headers.get("Authorization"),
        "application/json",
    )
```

**上游基址**：`auth_upstream.py` 中 `get_auth_upstream_base()`（开发 / 打包环境不同）。转发时固定附加请求头 `X-Tenant-Type: jujiancut`。

### 3.2 前端（React + TypeScript）

| 文件 | 作用 |
|------|------|
| `frontend/src/components/auth/licenseApi.ts` | 类型 `SelfUnbindLicenseResult`、`selfUnbindLicense()`；列表类型 `LicenseRecord` 扩展字段 |
| `frontend/src/components/auth/UserProfileLicenses.tsx` | 解绑按钮、确认弹窗、`confirmSelfUnbind`、辅助函数 `canOfferSelfUnbind` / `isNextSelfUnbindTheRevokeOne` |
| `frontend/src/components/auth/UserProfile.tsx` | 挂载 `<UserProfileLicenses accessToken={token} />`（若个人中心尚无 License 区块） |

**依赖（本仓库已有，移植时需等价实现）**：

- `@/services/clients` → `apiClient.getBaseUrl()`（请求本机后端根 URL）
- `@/services/message` → `message.success` / `message.warning`（Toast）
- `lucide-react`：`Link2Off`、`Loader2`、`X` 等图标
- `react-dom` → `createPortal`（确认弹窗挂到 `document.body`）

---

## 4. HTTP 接口约定

### 4.1 本机后端（客户端实际请求）

| 项目 | 值 |
|------|-----|
| Method / Path | `POST /api/licenses/{licenseId}/self-unbind` |
| 鉴权 | `Authorization: Bearer <用户 accessToken>` |
| Content-Type | `application/json` |
| 请求体 | `{}`（空对象，必须为 JSON） |

### 4.2 成功响应（解包后 `data` 或裸 JSON）

上游可能包一层 `{ code, message, data }`（`code === 0` 时取 `data`）。前端 `unwrapSuccessBody` 后校验下列字段：

```json
{
  "ok": true,
  "licenseId": 1,
  "userSelfUnbindCount": 1,
  "licenseRevoked": false,
  "remainingSelfUnbinds": 2
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | boolean | 固定为 `true` 表示成功 |
| `licenseId` | number | 被解绑的 License ID |
| `userSelfUnbindCount` | number | 该密钥在当前用户下**累计**自助解绑次数 |
| `licenseRevoked` | boolean | 本次是否为第 3 次导致吊销 |
| `remainingSelfUnbinds` | number | 剩余可自助解绑次数 |

### 4.3 列表接口扩展字段（可选，用于 UI）

`GET /api/licenses` 单项可增加：

| 字段 | 类型 | 说明 |
|------|------|------|
| `userSelfUnbindCount` | number | 已用次数 |
| `remainingSelfUnbinds` | number | 剩余次数；为 0 时前端不展示解绑按钮 |

### 4.4 常见错误

| 场景 | 典型 HTTP | 前端处理 |
|------|-----------|----------|
| 未登录 / Token 无效 | 401 | `parseHttpErrorMessage` 展示 `message` / `detail` |
| 次数用尽、已吊销等 | 400 | 同上，写入组件 `error` 状态 |
| 上游不可达 | 502 | 后端 `{"detail":"认证服务暂时不可用，请稍后重试"}` |

---

## 5. 后端完整代码摘录

### 5.1 `license_routes.py`（解绑路由 + 模块说明）

```python
"""
License 路由：请求体与 Authorization 原样转发至上游账号服务，响应原样返回。
POST /api/licenses/{id}/self-unbind 将空 JSON 体与 Authorization 原样转发上游。
"""

from fastapi import APIRouter, Request
from modules.auth.auth_upstream import forward_upstream_post_raw

licenses_router = APIRouter(prefix="/api/licenses", tags=["Licenses"])

@licenses_router.post(
    "/{license_id}/self-unbind",
    summary="自助解绑 License（上游累计 3 次，第 3 次将吊销）",
)
async def self_unbind_license(license_id: int, request: Request):
    return await forward_upstream_post_raw(
        f"/api/licenses/{license_id}/self-unbind",
        b"{}",
        request.headers.get("Authorization"),
        "application/json",
    )
```

### 5.2 `auth_upstream.py`（转发要点）

- `forward_upstream_post_raw(path, content: bytes, authorization, content_type)`：POST 字节流原样转发，避免 JSON 二次序列化差异。
- 合并头：`X-Tenant-Type: jujiancut`。
- 连接失败 → `502` + `detail` 文案；成功 → 上游状态码与 JSON **原样**返回（`JSONResponse`）。

### 5.3 `main.py` 注册

```python
from routes.license_routes import licenses_router
app.include_router(licenses_router)
```

---

## 6. 前端完整代码摘录

### 6.1 `licenseApi.ts` — 类型与 API

```typescript
export interface LicenseRecord {
  // ... 其它字段 ...
  userSelfUnbindCount?: number;
  remainingSelfUnbinds?: number;
}

export interface SelfUnbindLicenseResult {
  ok: boolean;
  licenseId: number;
  userSelfUnbindCount: number;
  licenseRevoked: boolean;
  remainingSelfUnbinds: number;
}

function isSelfUnbindPayload(v: unknown): v is SelfUnbindLicenseResult {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    o.ok === true &&
    typeof o.licenseId === "number" &&
    typeof o.userSelfUnbindCount === "number" &&
    typeof o.licenseRevoked === "boolean" &&
    typeof o.remainingSelfUnbinds === "number"
  );
}

/** POST /api/licenses/:id/self-unbind */
export async function selfUnbindLicense(
  token: string,
  licenseId: number
): Promise<SelfUnbindLicenseResult> {
  const raw = await fetchJson<unknown>(
    `${backendBase()}/api/licenses/${licenseId}/self-unbind`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({}),
    }
  );
  const payload = unwrapSuccessBody(raw);
  if (!isSelfUnbindPayload(payload)) {
    throw new Error("解绑响应格式异常");
  }
  return payload;
}
```

`unwrapSuccessBody`：若 body 为 `{ code, message, data }` 且 `code !== 0` 则 `throw`；否则返回 `data`。

### 6.2 `UserProfileLicenses.tsx` — 展示与交互逻辑

**是否显示解绑按钮：**

```typescript
function canOfferSelfUnbind(lic: LicenseRecord): boolean {
  if (lic.status === "revoked") return false;
  if (getEffectiveStatus(lic) === "revoked") return false;
  if (typeof lic.remainingSelfUnbinds === "number" && lic.remainingSelfUnbinds <= 0) {
    return false;
  }
  return true;
}
```

**是否第 3 次（弹窗红色警告）：**

```typescript
function isNextSelfUnbindTheRevokeOne(lic: LicenseRecord): boolean {
  if (typeof lic.userSelfUnbindCount === "number" && lic.userSelfUnbindCount >= 2) {
    return true;
  }
  if (typeof lic.remainingSelfUnbinds === "number" && lic.remainingSelfUnbinds === 1) {
    return true;
  }
  return false;
}
```

**确认解绑：**

```typescript
const confirmSelfUnbind = async () => {
  const lic = unbindDialog;
  if (!lic || !accessToken.trim()) return;
  setUnbindingId(lic.id);
  setError(null);
  try {
    const res = await selfUnbindLicense(accessToken, lic.id);
    setUnbindDialog(null);
    await load(); // 重新 GET /api/licenses
    if (res.licenseRevoked) {
      message.warning(
        "本次为第 3 次自助解绑，该 License 已被吊销，无法再使用。",
        5
      );
    } else {
      message.success(
        `解绑成功。该密钥在您账号下已累计自助解绑 ${res.userSelfUnbindCount} 次（上限 3 次），剩余可自助解绑次数：${res.remainingSelfUnbinds}。`,
        4
      );
    }
  } catch (e) {
    setError(e instanceof Error ? e.message : String(e));
  } finally {
    setUnbindingId(null);
  }
};
```

**UI 结构摘要：**

- 列表项：条件渲染「解绑」按钮 → `setUnbindDialog(lic)`。
- `createPortal` 全屏遮罩 + 确认弹窗（规则说明、累计次数、第 3 次红色提示、License Key、`确认解绑` / `取消`）。
- 列表副标题：`· 自助解绑还可 {remainingSelfUnbinds} 次`（字段存在时）。

### 6.3 挂载入口

`UserProfile.tsx`：

```tsx
{token ? <UserProfileLicenses accessToken={token} /> : null}
```

---

## 7. 调试：cURL 示例

将 `BASE` 换成本机后端（如 Tauri 内嵌 Python 端口），`TOKEN` 换为登录后的 accessToken，`LICENSE_ID` 换为整数 ID。

**解绑：**

```bash
curl -sS -X POST "${BASE}/api/licenses/${LICENSE_ID}/self-unbind" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "{}"
```

**解绑后查列表（看 remainingSelfUnbinds）：**

```bash
curl -sS "${BASE}/api/licenses" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${TOKEN}"
```

直连上游调试时，在 URL 上使用 `get_auth_upstream_base()` 对应地址，并增加：

`-H "X-Tenant-Type: jujiancut"`

---

## 8. 移植检查清单

- [ ] 上游已实现 `POST /api/licenses/:id/self-unbind` 及列表中的次数统计字段
- [ ] 本机 `licenses_router` 已注册且 `self_unbind_license` 路由顺序不与 `GET /{license_id}` 冲突（静态路径 `bind`、`client-device` 已在动态 `{license_id}` 之前定义）
- [ ] `auth_upstream` 基址与 `X-Tenant-Type` 与目标环境一致
- [ ] 前端 `apiClient.getBaseUrl()` 指向本机后端而非上游
- [ ] `licenseApi` 中 `unwrapSuccessBody` 与账号服务包装格式一致
- [ ] 个人中心已挂载 `UserProfileLicenses` 并传入有效 `accessToken`
- [ ] 用 cURL 或 Postman 验证：成功 JSON 五项字段、第 3 次 `licenseRevoked: true`、用尽后 400

---

## 9. 仓库内源文件路径（便于 git / 拷贝）

| 层级 | 路径 |
|------|------|
| 后端路由 | `backend/routes/license_routes.py` |
| 上游转发 | `backend/modules/auth/auth_upstream.py` |
| 路由注册 | `backend/main.py` |
| 前端 API | `frontend/src/components/auth/licenseApi.ts` |
| 前端 UI | `frontend/src/components/auth/UserProfileLicenses.tsx` |
| 挂载 | `frontend/src/components/auth/UserProfile.tsx` |

**文档版本**：与仓库 2026-05 实现一致；若上游字段或路径变更，以账号服务 Swagger / `license-user-api.md` 为准并同步本文第 4 节。
