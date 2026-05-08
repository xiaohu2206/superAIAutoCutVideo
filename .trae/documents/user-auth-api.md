# 用户认证 API 接口文档

基础路径：`/api/auth`

所有接口返回统一格式：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

- `code` 为 `0` 表示成功，非 `0` 表示失败
- `message` 为提示信息
- `data` 为业务数据

---

## 1. 发送注册验证码

向指定邮箱发送注册验证码，验证码有效期为 5 分钟。

**请求**

```
POST /api/auth/send-register-code
```

**请求体**

| 字段  | 类型   | 必填 | 说明         |
| ----- | ------ | ---- | ------------ |
| email | string | 是   | 邮箱地址     |

**请求示例**

```json
{
  "email": "user@example.com"
}
```

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": true
}
```

**错误情况**

| 场景             | code | message |
| ---------------- | ---- | ------- |
| 邮箱格式不合法   | -    | 邮箱格式校验失败 |

---

## 2. 注册用户

使用邮箱、密码和验证码完成用户注册。

**请求**

```
POST /api/auth/register
```

**请求体**

| 字段     | 类型   | 必填 | 说明                    |
| -------- | ------ | ---- | ----------------------- |
| email    | string | 是   | 邮箱地址                |
| password | string | 是   | 密码，最少 6 位         |
| code     | string | 是   | 邮箱收到的注册验证码    |

**请求示例**

```json
{
  "email": "user@example.com",
  "password": "123456",
  "code": "836427"
}
```

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "userId": 1
  }
}
```

**错误情况**

| 场景               | code | message        |
| ------------------ | ---- | -------------- |
| 验证码错误或已过期 | -    | 验证码错误或已过期 |
| 邮箱已注册         | -    | 邮箱已注册      |

---

## 3. 用户登录

使用邮箱和密码登录，成功后返回 JWT Token。

**请求**

```
POST /api/auth/login
```

**请求体**

| 字段     | 类型   | 必填 | 说明     |
| -------- | ------ | ---- | -------- |
| email    | string | 是   | 邮箱地址 |
| password | string | 是   | 密码     |

**请求示例**

```json
{
  "email": "user@example.com",
  "password": "123456"
}
```

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": 1,
      "email": "user@example.com",
      "status": "active"
    }
  }
}
```

**响应字段说明**

| 字段         | 类型   | 说明                                      |
| ------------ | ------ | ----------------------------------------- |
| token        | string | JWT Token，后续请求需携带                 |
| user.id      | number | 用户 ID                                   |
| user.email   | string | 用户邮箱                                  |
| user.status  | string | 用户状态，可选值：`active`、`disabled`     |

**错误情况**

| 场景             | code | message        |
| ---------------- | ---- | -------------- |
| 邮箱或密码错误   | 401  | 账号或密码错误  |
| 账号已禁用       | 403  | 账号已禁用      |

---

## 4. 获取登录状态（当前用户信息）

获取当前已登录用户的信息。需要携带 JWT Token。

**请求**

```
GET /api/auth/me
```

**请求头**

| 字段          | 值                    | 必填 | 说明                      |
| ------------- | --------------------- | ---- | ------------------------- |
| Authorization | Bearer {token}        | 是   | 登录接口返回的 JWT Token  |

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "email": "user@example.com",
    "status": "active",
    "createdAt": "2026-04-25T00:00:00.000Z",
    "updatedAt": "2026-04-25T00:00:00.000Z"
  }
}
```

**错误情况**

| 场景               | code | message           |
| ------------------ | ---- | ----------------- |
| 未携带 Token       | 401  | Unauthorized      |
| Token 无效或过期   | 401  | Unauthorized      |

---

## 5. 发送重置密码验证码

向指定邮箱发送重置密码验证码，验证码有效期为 5 分钟。

**请求**

```
POST /api/auth/send-reset-code
```

**请求体**

| 字段  | 类型   | 必填 | 说明     |
| ----- | ------ | ---- | -------- |
| email | string | 是   | 邮箱地址 |

**请求示例**

```json
{
  "email": "user@example.com"
}
```

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": true
}
```

---

## 6. 重置密码

使用验证码重置密码。

**请求**

```
POST /api/auth/reset-password
```

**请求体**

| 字段        | 类型   | 必填 | 说明                        |
| ----------- | ------ | ---- | --------------------------- |
| email       | string | 是   | 邮箱地址                    |
| code        | string | 是   | 邮箱收到的重置验证码        |
| newPassword | string | 是   | 新密码，最少 6 位           |

**请求示例**

```json
{
  "email": "user@example.com",
  "code": "836427",
  "newPassword": "654321"
}
```

**响应示例**

```json
{
  "code": 0,
  "message": "success",
  "data": true
}
```

**错误情况**

| 场景               | code | message            |
| ------------------ | ---- | ------------------ |
| 验证码错误或已过期 | -    | 验证码错误或已过期  |
| 用户不存在         | -    | 用户不存在          |

---

## 接入指南

### 认证方式

登录成功后获取 `token`，后续需要认证的接口在请求头中携带：

```
Authorization: Bearer <token>
```

### Token 存储

建议将 Token 存储在 `localStorage` 中，key 为 `user_token`：

```typescript
// 登录成功后存储
localStorage.setItem('user_token', token);

// 请求时读取
const token = localStorage.getItem('user_token');

// 退出登录时清除
localStorage.removeItem('user_token');
```

### 完整调用流程

```
注册流程：
1. 调用「发送注册验证码」→ 用户收到邮件验证码
2. 调用「注册用户」→ 完成注册

登录流程：
1. 调用「用户登录」→ 获取 token 和用户信息
2. 将 token 存储到 localStorage
3. 后续请求携带 Authorization 头

重置密码流程：
1. 调用「发送重置密码验证码」→ 用户收到邮件验证码
2. 调用「重置密码」→ 完成密码重置

登录状态验证：
1. 从 localStorage 读取 token
2. 调用「获取登录状态」→ 验证 token 是否有效并获取用户信息
```

### 前端请求示例

```typescript
const API_BASE = 'http://127.0.0.1:3000';

// 通用请求函数
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('user_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });
  const result = await response.json();
  if (result.code !== 0) {
    throw new Error(result.message || '请求失败');
  }
  return result.data;
}

// 发送注册验证码
const sendRegisterCode = (email: string) =>
  request<boolean>('/api/auth/send-register-code', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });

// 注册用户
const register = (email: string, password: string, code: string) =>
  request<{ userId: number }>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, code }),
  });

// 用户登录
const login = (email: string, password: string) =>
  request<{ token: string; user: { id: number; email: string; status: string } }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });

// 获取当前用户信息
const me = () => request('/api/auth/me');

// 发送重置密码验证码
const sendResetCode = (email: string) =>
  request<boolean>('/api/auth/send-reset-code', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });

// 重置密码
const resetPassword = (email: string, code: string, newPassword: string) =>
  request<boolean>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ email, code, newPassword }),
  });
```