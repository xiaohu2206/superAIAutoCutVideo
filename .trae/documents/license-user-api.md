# 用户侧 License 接口说明

面向其它前端项目接入：用户账号绑定 License、查询已绑定 License，以及客户端用 License Key 校验并换取 `licenseToken`（与 `verify.controller` 一致）。

**Base URL**：部署地址根路径，例如 `http://localhost:3000`（默认端口见服务配置）。下文路径均相对于 Base URL。

**Content-Type**：请求体为 JSON 时请使用 `Content-Type: application/json`。

**CORS**：服务端已允许常见跨域头，需携带用户 JWT 时请确保请求头包含 `Authorization`。

---

## 1. 用户身份（绑定 / 查询 License 必填）

以下接口需要**用户登录态**，使用 **HTTP Bearer Token**（与 `UserJwtAuthGuard` 一致）。

| 请求头 | 说明 |
|--------|------|
| `Authorization` | `Bearer <accessToken>`，`accessToken` 来自用户登录接口 |

登录示例（本仓库 `AuthController`）：

- `POST /api/auth/login`  
  请求体：`{ "email": string, "password": string }`  
  响应中的 `token` 即上述 `accessToken`。

未携带或 Token 无效时，通常返回 **401 Unauthorized**。

---

## 2. 查询当前用户已绑定的 License 列表

用于「我的 License」列表页。

| 项目 | 说明 |
|------|------|
| **Method / Path** | `GET /api/licenses` |
| **鉴权** | 需要用户 JWT |

**成功响应**：`200 OK`，Body 为 **License 对象数组**（按 `id` 降序）。每项为 TypeORM 实体序列化结果，主要字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | number | License 主键，后续详情接口使用 |
| `licenseKey` | string | License 密钥 |
| `userId` | number \| null | 绑定用户 ID；列表场景下一般为当前用户 |
| `planType` | string | 套餐类型，见下方枚举 |
| `status` | string | 状态，见下方枚举 |
| `maxDevices` | number | 允许绑定的设备数上限 |
| `durationDays` | number \| null | 时长型套餐的天数（永久等可能为 null） |
| `activateAt` | string \| null | 首次校验通过激活时间（ISO 8601） |
| `expireAt` | string \| null | 过期时间；永久套餐可能为 null |
| `remark` | string \| null | 备注 |
| `devices` | array | 已绑定设备列表，见「设备对象」 |
| `createdAt` | string | 创建时间 |
| `updatedAt` | string | 更新时间 |

**枚举 `planType`**：`monthly` \| `half_year` \| `permanent`

**枚举 `status`**：`active` \| `expired` \| `revoked`

**设备对象 `devices[]` 主要字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | number | 设备记录主键 |
| `licenseId` | number | 所属 License |
| `deviceId` | string | 客户端设备唯一标识 |
| `deviceName` | string | 设备展示名 |
| `bindCount` | number | 绑定次序等统计 |
| `lastActiveAt` | string \| null | 最近活跃时间 |
| `createdAt` / `updatedAt` | string | 时间戳 |

---

## 3. 查询单条 License 详情（须属于当前用户）

用于 License 详情页；仅能查看**已绑定到当前用户**的 License。

| 项目 | 说明 |
|------|------|
| **Method / Path** | `GET /api/licenses/:licenseId` |
| **鉴权** | 需要用户 JWT |
| **路径参数** | `licenseId`：整数，License 的 `id` |

**成功响应**：`200 OK`，Body 为单个 License 对象（结构同列表项，含 `devices`）。

**常见错误**：

| HTTP | 说明 |
|------|------|
| `404` | License 不存在或不属于当前用户（文案可能为 `License 不存在`） |
| `400` | `licenseId` 非合法整数（例如误把路径写成 `bind`） |

---

## 4. 将 License 绑定到当前用户

用户输入购买得到的 `licenseKey`，绑定到自己的账号。

| 项目 | 说明 |
|------|------|
| **Method / Path** | `POST /api/licenses/bind` |
| **鉴权** | 需要用户 JWT |

**请求体**：

```json
{
  "licenseKey": "string"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `licenseKey` | string | 是 | License 密钥 |

**成功响应**：`201`（若全局未改 `@HttpCode`，Nest 默认 POST 为 `201 Created`）或 `200`，Body 示例：

```json
{
  "licenseId": 1
}
```

**常见错误**：

| HTTP | 场景 |
|------|------|
| `404` | `licenseKey` 在系统中不存在 |
| `400` | License 已绑定到其他用户账号 |
| `400` | 校验失败（请求体缺字段、多余字段等，受全局 `ValidationPipe` 影响） |

说明：若 License 尚未绑定用户，或**已经绑定到当前用户**，再次绑定会写入同一用户（幂等绑定到本人）。

---

## 5. 客户端 License 校验 / 刷新 Token（无需用户 JWT）

以下接口为**公开**（`@Public()`），用于桌面端、插件等用 **License Key + 设备 ID** 换取短期 **`licenseToken`**，与是否已绑定网站账号无关；服务端会校验 License 状态、过期、设备数上限，并记录校验日志。

| 项目 | 说明 |
|------|------|
| **Method / Path** | `POST /api/license/verify` |
| **鉴权** | 不需要用户 JWT |

**请求体**：

```json
{
  "licenseKey": "string",
  "deviceId": "string",
  "deviceName": "string"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `licenseKey` | string | 是 | License 密钥 |
| `deviceId` | string | 是 | 客户端生成的稳定设备唯一标识 |
| `deviceName` | string | 否 | 展示用设备名称 |

**成功响应**：`200 OK`，Body 示例：

```json
{
  "valid": true,
  "deviceValid": true,
  "licenseId": 1,
  "expireAt": "2026-12-31T23:59:59.000Z",
  "licenseToken": "jwt-string"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid` | boolean | 校验通过为 `true` |
| `deviceValid` | boolean | 当前实现下与校验通过一致 |
| `licenseId` | number | License ID |
| `expireAt` | string \| null | 过期时间 ISO 字符串；永久未设置过期可能为 `null` |
| `licenseToken` | string | 使用服务端 `licenseTokenSecret` 签发的 JWT，供客户端后续调用需 License 态的接口 |

**常见错误**：

| HTTP | 场景 |
|------|------|
| `403` | 当前 IP 被风控拉黑 |
| `404` | License 不存在 |
| `400` | License 非 `active`、已过期、设备数已达上限（文案含「不可用」「已过期」「设备绑定数量已达上限」等） |

首次校验成功时可能写入 `activateAt`，并按 `durationDays` 计算 `expireAt`（若适用）。

---

## 6. 刷新 `licenseToken`

与校验逻辑相同，用于在 Token 将过期或客户端需要续期时再次换取 Token。

| 项目 | 说明 |
|------|------|
| **Method / Path** | `POST /api/license/refresh-token` |
| **鉴权** | 不需要用户 JWT |
| **请求体 / 响应** | 与 **第 5 节** `POST /api/license/verify` 完全一致 |

---

## 7. 错误响应格式（NestJS 默认）

业务与校验失败时，Body 多为：

```json
{
  "statusCode": 400,
  "message": "错误说明或校验信息",
  "error": "Bad Request"
}
```

`message` 在部分校验场景下可能为字符串数组。

---

## 8. 与其它文档的关系

同服务还提供 Swagger：`GET {BASE_URL}/docs`（见 `main.ts` 中 `SwaggerModule.setup`），可与本文对照使用。
