# 买手 (Maishou) API 文档

> **版本:** v3 / v1 &nbsp;|&nbsp; **协议:** HTTPS &nbsp;|&nbsp; **数据格式:** JSON

买手 API 是 price-monitor 项目的核心数据源，用于查询电商平台商品价格、详情及获取跳转链接。

---

## 目录

- [通用说明](#通用说明)
  - [Headers](#headers)
  - [平台代码](#平台代码)
  - [SSL 配置](#ssl-配置)
  - [重试与限流](#重试与限流)
- [API 端点](#api-端点)
  - [1. 搜索商品列表](#1-搜索商品列表)
  - [2. 获取商品详情](#2-获取商品详情)
  - [3. 获取分享跳转链接](#3-获取分享跳转链接)
- [使用示例](#使用示例)
- [注意事项](#注意事项)

---

## 通用说明

### Headers

所有请求必须携带以下 HTTP Headers：

| Header      | 值                                                         |
| ----------- | ---------------------------------------------------------- |
| `Accept`    | `application/json`                                         |
| `Referer`   | `https://hnbc018.kuaizhan.com/`                            |
| `User-Agent`| `Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537`        |

### 平台代码 (`sourceType`)

| 代码 | 平台   | 代码 | 平台   |
| ---- | ------ | ---- | ------ |
| 1    | 淘宝   | 6    | 唯品会 |
| 2    | 京东   | 7    | 抖音   |
| 3    | 拼多多 | 8    | 快手   |
| 4    | 小红书 | 9    | 美团   |
| 5    | 得物   | 10   | 饿了么 |

### SSL 配置

API 使用默认 SSL 验证 (`ssl.create_default_context()`)。

### 重试与限流

| 参数           | 默认值     | 说明                                     |
| -------------- | ---------- | ---------------------------------------- |
| 最大重试次数   | 3          | 指数退避: 1s → 2s → 4s                   |
| 请求间隔       | 200ms      | 避免触发限流                             |
| 缓存 TTL        | 300s (5min)| 同一商品 5 分钟内不重复请求              |

可重试的异常类型：`ClientConnectionError`, `ClientTimeout`, `ConnectionError`, `TimeoutError`, `OSError`。

---

## API 端点

### 1. 搜索商品列表

**POST** `https://appapi.maishou88.com/api/v3/goods/list`

根据关键词搜索商品，返回商品列表。

#### 请求体

| 字段          | 类型   | 必填 | 默认值 | 说明            |
| ------------- | ------ | ---- | ------ | --------------- |
| `keyword`     | string | ✅    | —      | 搜索关键词      |
| `sourceType`  | string | ✅    | —      | 平台代码        |
| `inviteCode`  | string | ❌    | `""`   | 邀请码（可选）  |
| `supplierCode`| string | ❌    | `""`   | 供应商代码      |
| `activityId`  | string | ❌    | `""`   | 活动 ID         |
| `usageScene`  | string | ✅    | `5`    | 使用场景        |
| `page`        | number | ✅    | `1`    | 页码            |
| `pageSize`    | number | ✅    | —      | 每页数量        |

#### 请求示例

```bash
curl -X POST "https://appapi.maishou88.com/api/v3/goods/list" \
  -H "Accept: application/json" \
  -H "Referer: https://hnbc018.kuaizhan.com/" \
  -H "User-Agent: Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537" \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "蓝牙耳机",
    "sourceType": "1",
    "inviteCode": "",
    "supplierCode": "",
    "activityId": "",
    "usageScene": 5,
    "page": 1,
    "pageSize": 10
  }'
```

#### 响应结构

```json
{
  "data": {
    "goodsList": [
      {
        "goodsId": "string",
        "title": "string",
        "actualPrice": "number",
        "originalPrice": "number",
        "couponPrice": "number",
        "appUrl": "string"
      }
    ]
  }
}
```

#### 响应字段说明

| 字段            | 类型   | 说明           |
| --------------- | ------ | -------------- |
| `goodsId`       | string | 商品 ID        |
| `title`         | string | 商品标题       |
| `actualPrice`   | number | 实际成交价（元）|
| `originalPrice` | number | 原价/市场价（元）|
| `couponPrice`   | number | 优惠券金额（元） |
| `appUrl`        | string | 商品跳转链接   |

> **注意：** 响应数据可能位于 `data.result.goodsList`、`data.goodsList`、`data.list`、`data.items` 或直接为 `data` 数组。客户端应做兼容处理。

---

### 2. 获取商品详情

**POST** `https://appapi.maishou88.com/api/v3/goods/detail`

根据商品 ID 获取详细信息，包括价格、优惠券等。

#### 请求体

| 字段          | 类型   | 必填 | 默认值 | 说明           |
| ------------- | ------ | ---- | ------ | -------------- |
| `goodsId`     | string | ✅    | —      | 商品 ID        |
| `sourceType`  | string | ✅    | —      | 平台代码       |
| `inviteCode`  | string | ❌    | `""`   | 邀请码（可选） |
| `keyword`     | string | ✅    | `""`   | 搜索关键词     |
| `usageScene`  | string | ✅    | `5`    | 使用场景       |
| `supplierCode`| string | ❌    | `""`   | 供应商代码     |
| `activityId`  | string | ❌    | `""`   | 活动 ID        |
| `isShare`     | string | ❌    | `"1"`  | 是否分享       |
| `token`       | string | ❌    | `""`   | 令牌           |

#### 请求示例

```bash
curl -X POST "https://appapi.maishou88.com/api/v3/goods/detail" \
  -H "Accept: application/json" \
  -H "Referer: https://hnbc018.kuaizhan.com/" \
  -H "User-Agent: Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537" \
  -H "Content-Type: application/json" \
  -d '{
    "goodsId": "12345678",
    "sourceType": "1",
    "inviteCode": "",
    "keyword": "",
    "usageScene": 5,
    "supplierCode": "",
    "activityId": "",
    "isShare": "1",
    "token": ""
  }'
```

#### 响应结构

```json
{
  "data": {
    "title": "string",
    "actualPrice": "number",
    "originalPrice": "number",
    "couponPrice": "number"
  }
}
```

#### 响应字段说明

| 字段            | 类型   | 说明             |
| --------------- | ------ | ---------------- |
| `title`         | string | 商品标题         |
| `actualPrice`   | number | 实际成交价（元） |
| `originalPrice` | number | 原价/市场价（元）|
| `couponPrice`   | number | 优惠券金额（元） |

---

### 3. 获取分享跳转链接

**POST** `https://msapi.maishou88.com/api/v1/share/getTargetUrl`

获取商品的外部分享链接（`appUrl` / `schemaUrl`），用于跳转到对应电商 App。

#### 请求体

| 字段              | 类型   | 必填 | 默认值 | 说明           |
| ----------------- | ------ | ---- | ------ | -------------- |
| `goodsId`         | string | ✅    | —      | 商品 ID        |
| `sourceType`      | string | ✅    | —      | 平台代码       |
| `inviteCode`      | string | ❌    | `""`   | 邀请码（可选） |
| `isDirectDetail`  | number | ✅    | `0`    | 是否直达详情页 |
| `supplierCode`    | string | ❌    | `""`   | 供应商代码     |
| `activityId`      | string | ❌    | `""`   | 活动 ID        |
| `isShare`         | string | ❌    | `"1"`  | 是否分享       |
| `token`           | string | ❌    | `""`   | 令牌           |

#### 请求示例

```bash
curl -X POST "https://msapi.maishou88.com/api/v1/share/getTargetUrl" \
  -H "Accept: application/json" \
  -H "Referer: https://hnbc018.kuaizhan.com/" \
  -H "User-Agent: Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537" \
  -H "Content-Type: application/json" \
  -d '{
    "goodsId": "12345678",
    "sourceType": "1",
    "inviteCode": "",
    "isDirectDetail": 0
  }'
```

#### 响应结构

```json
{
  "data": {
    "appUrl": "string",
    "schemaUrl": "string"
  }
}
```

#### 响应字段说明

| 字段          | 类型   | 说明                               |
| ------------- | ------ | ---------------------------------- |
| `appUrl`      | string | 通用跳转链接（优先使用）           |
| `schemaUrl`   | string | 应用内协议链接（`appUrl` 缺失时使用）|

---

## 使用示例

### Python 示例（完整流程：搜索 → 详情 → 获取链接）

```python
import aiohttp
import asyncio

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://hnbc018.kuaizhan.com/",
    "User-Agent": "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

INVITE_CODE = ""  # 设置你的邀请码

async def search_and_get_detail(keyword: str, source: int = 1):
    """搜索商品并获取第一个商品的详情和链接"""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # 1. 搜索商品
        async with session.post(
            "https://appapi.maishou88.com/api/v3/goods/list",
            json={
                "keyword": keyword,
                "sourceType": str(source),
                "inviteCode": INVITE_CODE,
                "supplierCode": "",
                "activityId": "",
                "usageScene": 5,
                "page": 1,
                "pageSize": 10,
            },
        ) as resp:
            data = await resp.json(encoding="utf-8-sig")
            goods_list = (data.get("data") or {}).get("goodsList", [])

        if not goods_list:
            print("未找到商品")
            return

        first = goods_list[0]
        goods_id = first["goodsId"]
        print(f"找到: {first['title']}")
        print(f"  现价: ¥{first['actualPrice']}")

        # 2. 获取商品详情
        async with session.post(
            "https://appapi.maishou88.com/api/v3/goods/detail",
            json={
                "goodsId": goods_id,
                "sourceType": str(source),
                "inviteCode": INVITE_CODE,
                "keyword": "",
                "usageScene": 5,
                "supplierCode": "",
                "activityId": "",
                "isShare": "1",
                "token": "",
            },
        ) as resp:
            detail = (await resp.json(encoding="utf-8-sig")).get("data", {})
            print(f"  原价: ¥{detail.get('originalPrice', 0)}")
            print(f"  优惠券: ¥{detail.get('couponPrice', 0)}")

        # 3. 获取分享链接
        async with session.post(
            "https://msapi.maishou88.com/api/v1/share/getTargetUrl",
            json={
                "goodsId": goods_id,
                "sourceType": str(source),
                "inviteCode": INVITE_CODE,
                "isDirectDetail": 0,
                "supplierCode": "",
                "activityId": "",
                "isShare": "1",
                "token": "",
            },
        ) as resp:
            url_info = (await resp.json(encoding="utf-8-sig")).get("data", {})
            app_url = url_info.get("appUrl") or url_info.get("schemaUrl", "")
            print(f"  链接: {app_url}")

if __name__ == "__main__":
    asyncio.run(search_and_get_detail("蓝牙耳机", source=1))  # source=1 为淘宝
```

### 调用顺序

典型的商品查询流程需要**两步调用**：

```
1. POST /api/v3/goods/detail   → 获取价格信息（actualPrice, originalPrice, couponPrice）
2. POST /api/v1/share/getTargetUrl → 获取跳转链接（appUrl）
```

> `goods/detail` 响应中**不包含** `appUrl`，需要通过 `getTargetUrl` 单独获取。

---

## 注意事项

1. **`inviteCode`（邀请码）为可选参数**，可通过环境变量 `MAISHOU_INVITE_CODE` 或配置文件 `data/config.json` 中的 `invite_code` 字段设置。未设置时 API 仍可调用，但部分功能可能受限。

2. **响应编码**：API 响应使用 `utf-8-sig`（带 BOM 的 UTF-8），解析时需指定 `encoding="utf-8-sig"`，否则可能出现乱码。

3. **字段兼容性**：搜索接口返回的商品列表字段名可能有多种变体：
   - 商品 ID：`goodsId` / `id` / `goods_id`
   - 价格：`actualPrice` / `price` / `actual_price`
   - 标题：`title` / `goodsName` / `name`
   
   建议按优先级 fallback 处理。

4. **限流策略**：建议请求间隔不低于 200ms，避免触发 API 限流。

5. **错误处理**：API 无统一错误码规范，网络错误应重试（最多 3 次），业务错误（如商品不存在）应直接处理。

6. **已接入平台**：淘宝(1)、京东(2)、拼多多(3)、抖音(7)、快手(8) 已完全接入；小红书(4)、得物(5)、唯品会(6)、美团(9)、饿了么(10) 适配器已预留，API 待接入。
