# 买手 (MaiShou) API 文档

> 价格监控工具接入买手平台的 API 接口文档。

## 基础信息

| 项目 | 值 |
|------|-----|
| **API 域名** | `appapi.maishou88.com` / `msapi.maishou88.com` |
| **协议** | HTTPS + POST (JSON) |
| **认证** | `inviteCode` 邀请码（可选，但无码可能无法返回数据） |
| **Referer** | `https://hnbc018.kuaizhan.com/` |
| **User-Agent** | `Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537` |

## 平台代码 (sourceType)

| 代码 | 平台 | 状态 |
|------|------|------|
| `0` | 买手官方 | ✅ 已接入 |
| `1` | 淘宝 | ✅ 已接入 |
| `2` | 京东 | ✅ 已接入 |
| `3` | 拼多多 | ✅ 已接入 |
| `4` | 小红书 | 🚧 适配器框架（待接入真实 API） |
| `5` | 得物 | 🚧 适配器框架（待接入真实 API） |
| `6` | 唯品会 | 🚧 适配器框架（待接入真实 API） |
| `7` | 抖音 | ✅ 已接入 |
| `8` | 快手 | ✅ 已接入 |
| `9` | 美团 | 🚧 适配器框架（待接入真实 API） |
| `10` | 饿了么 | 🚧 适配器框架（待接入真实 API） |

---

## API 端点

### 1. 商品搜索 — `POST /api/v3/goods/list`

搜索指定平台上的商品列表。

**URL:** `https://appapi.maishou88.com/api/v3/goods/list`

**请求体:**

```json
{
  "keyword": "关键词",
  "sourceType": "1",
  "inviteCode": "你的邀请码",
  "supplierCode": "",
  "activityId": "",
  "usageScene": 5,
  "page": 1,
  "pageSize": 20
}
```

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | ✅ | 搜索关键词 |
| `sourceType` | string | ✅ | 平台代码（见上方表格） |
| `inviteCode` | string | 可选 | 邀请码（环境变量或 config.json） |
| `supplierCode` | string | — | 供应商代码，通常为空 |
| `activityId` | string | — | 活动 ID，通常为空 |
| `usageScene` | int | ✅ | 使用场景，固定为 `5` |
| `page` | int | ✅ | 页码，从 1 开始 |
| `pageSize` | int | ✅ | 每页数量 |

**响应结构:**

```json
{
  "code": 200,
  "data": {
    "goodsList": [
      {
        "goodsId": "商品ID",
        "title": "商品标题",
        "actualPrice": 99.0,
        "originalPrice": 199.0,
        "couponPrice": 50.0,
        "appUrl": "https://..."
      }
    ]
  }
}
```

**响应字段映射** (代码做兼容处理):

| 标准字段 | 兼容字段 | 说明 |
|----------|----------|------|
| `goodsId` | `id`, `goods_id` | 商品唯一标识 |
| `title` | `goodsName`, `name` | 商品标题 |
| `actualPrice` | `price`, `actual_price` | 实际价格 |
| `originalPrice` | `marketPrice`, `original_price` | 原价/市场价 |
| `couponPrice` | `coupon_price` | 优惠券金额 |
| `appUrl` | `clickUrl`, `url` | 商品跳转链接 |

**使用场景:**
- `search` 命令：搜索并添加到监控
- `list` 命令（部分平台）：列出平台热门商品

---

### 2. 商品详情 — `POST /api/v3/goods/detail`

获取单个商品的详细信息（当前价格、优惠券等）。

**URL:** `https://appapi.maishou88.com/api/v3/goods/detail`

**请求体:**

```json
{
  "goodsId": "658866023929",
  "sourceType": "1",
  "inviteCode": "你的邀请码",
  "supplierCode": "",
  "activityId": "",
  "keyword": "",
  "usageScene": 5,
  "isShare": "1",
  "token": ""
}
```

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `goodsId` | string | ✅ | 商品 ID |
| `sourceType` | string | ✅ | 平台代码 |
| `inviteCode` | string | 可选 | 邀请码 |
| `keyword` | string | ✅ | 搜索关键词（详情请求中传空字符串） |
| `usageScene` | int | ✅ | 使用场景，固定为 `5` |
| `isShare` | string | ✅ | 是否获取分享链接，固定为 `"1"` |
| `token` | string | — | 用户 Token，通常为空 |

**响应结构:**

```json
{
  "code": 200,
  "data": {
    "title": "商品标题",
    "actualPrice": 99.0,
    "originalPrice": 199.0,
    "couponPrice": 50.0
  }
}
```

> **注意:** 商品详情接口不返回 `appUrl`，需要通过第二个接口获取。

---

### 3. 分享链接 — `POST /api/v1/share/getTargetUrl`

获取商品的跳转链接（Deep Link / App 唤起链接）。

**URL:** `https://msapi.maishou88.com/api/v1/share/getTargetUrl`

> ⚠️ 注意此接口域名是 `msapi.maishou88.com`（非 `appapi`）。

**请求体:**

```json
{
  "goodsId": "658866023929",
  "sourceType": "1",
  "inviteCode": "你的邀请码",
  "supplierCode": "",
  "activityId": "",
  "isShare": "1",
  "token": "",
  "isDirectDetail": 0
}
```

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `goodsId` | string | ✅ | 商品 ID |
| `sourceType` | string | ✅ | 平台代码 |
| `inviteCode` | string | 可选 | 邀请码 |
| `isShare` | string | ✅ | 固定为 `"1"` |
| `isDirectDetail` | int | ✅ | 是否直接详情，固定为 `0` |

**响应结构:**

```json
{
  "code": 200,
  "data": {
    "appUrl": "https://...",
    "schemaUrl": "https://..."
  }
}
```

**字段说明:**
- `appUrl` / `schemaUrl` — 商品跳转链接（两者取其一）

---

## 邀请码配置

邀请码为**可选配置**，有三种来源（优先级从高到低）：

1. **环境变量** `MAISHOU_INVITE_CODE`
2. **配置文件** `data/config.json` 中的 `invite_code` 字段
3. **空字符串**（API 可能返回空数据或报错）

**通过 CLI 设置:**
```bash
uv run scripts/main.py config --invite-code=你的邀请码
```

**通过环境变量:**
```bash
set MAISHOU_INVITE_CODE=你的邀请码   # Windows
export MAISHOU_INVITE_CODE=你的邀请码  # Linux/macOS
```

---

## 请求机制

### 重试策略
- 默认重试 3 次
- 失败间隔递增延迟
- 仅 `GET` 请求使用缓存（详情接口每次重新请求以确保价格实时）

### 缓存机制
- 搜索缓存：5 分钟 TTL（`cache_ttl_seconds`）
- 详情缓存：可配置 TTL
- 缓存存储：`data/api_cache.json`
- 每次价格监控检查时，详情请求不受缓存限制（保证价格实时性）

### 请求限流
- 默认请求间隔：可配置（`request_delay_ms`）
- 每次详情请求前自动延迟

### SSL 配置
- 使用自定义 SSL 上下文（禁用证书验证）
- 兼容企业网络/代理环境

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| 邀请码为空 | 打印警告，仍尝试请求 |
| 网络超时 | 自动重试 3 次 |
| 返回数据为空 | 跳过该商品，继续下一个 |
| 解析失败 | 捕获异常，打印错误，继续 |

---

## 待接入平台

以下平台已创建适配器框架，但尚未接入真实 API：

| 平台 | 适配器文件 | 需实现方法 |
|------|-----------|-----------|
| 小红书 (4) | `PlatformAdapter` 子类 | `get_price()`, `search_goods()` |
| 得物 (5) | `PlatformAdapter` 子类 | `get_price()`, `search_goods()` |
| 唯品会 (6) | `PlatformAdapter` 子类 | `get_price()`, `search_goods()` |
| 美团 (9) | `PlatformAdapter` 子类 | `get_price()`, `search_goods()` |
| 饿了么 (10) | `PlatformAdapter` 子类 | `get_price()`, `search_goods()` |

接入步骤：
1. 获取该平台的 API 文档和密钥
2. 在对应适配器中实现 `get_price()` 方法
3. 实现 `search_goods()` 方法（可选）
4. 更新 `SOURCE_NAMES` 映射
5. 测试并更新本文档

---

## 多数据源架构（规划中）

未来计划支持多数据源优先级：
1. **官方 API**（优先，如果有）
2. **买手 API**（当前主用，作为 fallback）
3. **网页爬取**（最后手段）

此架构将在适配器框架基础上扩展。

---

_最后更新: 2026-05-09_
