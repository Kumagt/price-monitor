# /// script
# requires-python = ">=3.11"
# ///
"""
多数据源抽象层 - Price Monitor

架构设计:
  DataSource (抽象基类)
    ├── MaishouDataSource     — 现有买手 API（真实数据源）
    ├── MockOfficialDataSource — 官方 API 模拟（标注待接入）
    └── FallbackDataSource    — 组合器：按优先级尝试多个数据源，失败自动 fallback

使用方式:
  1. 在 config.json 中配置 data_sources 列表（按优先级排序）
  2. 默认 fallback 模式: ["official", "maishou"]
  3. 可通过配置切换单一数据源或自定义优先级
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import aiohttp

# 基础目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"

logger = logging.getLogger(__name__)

# 买手 API 配置
MAISHOU_API_BASE = "https://appapi.maishou88.com/api/v3"
MAISHOU_SHARE_API = "https://msapi.maishou88.com/api/v1/share/getTargetUrl"
HEADERS = {
    aiohttp.hdrs.ACCEPT: "application/json",
    aiohttp.hdrs.REFERER: "https://hnbc018.kuaizhan.com/",
    aiohttp.hdrs.USER_AGENT: "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

import ssl
SSL_CONTEXT = ssl.create_default_context()

# 重试配置
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1

RETRIABLE_EXCEPTIONS = (
    aiohttp.ClientConnectionError,
    aiohttp.ClientTimeout,
    asyncio.TimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)


# ─────────────────────────────────────────────
# 抽象基类
# ─────────────────────────────────────────────

class DataSource(ABC):
    """数据源抽象基类。

    每个数据源必须实现:
      - name: 数据源名称（用于日志和配置）
      - get_goods_detail: 获取商品详情
      - search_goods: 搜索商品列表
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称标识。"""
        ...

    @abstractmethod
    async def get_goods_detail(
        self, session: aiohttp.ClientSession,
        goods_id: str, source: int,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """获取商品详情。

        Returns:
            成功时返回包含 title, actualPrice, originalPrice, couponPrice, appUrl 的字典
            失败时返回 None
        """
        ...

    @abstractmethod
    async def search_goods(
        self, session: aiohttp.ClientSession,
        keyword: str, source: int,
        limit: int = 10, **kwargs
    ) -> List[Dict[str, Any]]:
        """搜索商品。

        Returns:
            商品列表，每个商品包含 goods_id, title, actualPrice, originalPrice, appUrl, couponPrice
        """
        ...

    def __repr__(self) -> str:
        return f"<DataSource: {self.name}>"


# ─────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────

async def _retry_request(coro_fn, label: str = ""):
    """通用异步网络重试：仅重试网络层异常，业务异常不重试。"""
    last_exc = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return await coro_fn()
        except RETRIABLE_EXCEPTIONS as e:
            last_exc = e
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            prefix = f"[{label}] " if label else ""
            logger.warning("%s%s: %s, %ds 后重试 (%d/%d)", prefix, type(e).__name__, e, delay, attempt, RETRY_MAX_ATTEMPTS)
            await asyncio.sleep(delay)
        except aiohttp.ClientResponseError as e:
            logger.error("[%s] HTTP %d: %s", label or "request", e.status, e.message)
            raise
        except aiohttp.ContentTypeError as e:
            logger.error("[%s] 响应解析失败: %s", label or "request", e)
            raise
    raise last_exc  # type: ignore[misc]


# ─────────────────────────────────────────────
# 买手数据源（现有 API）
# ─────────────────────────────────────────────

class MaishouDataSource(DataSource):
    """买手 API 数据源。

    使用 maishou88.com 第三方 API 获取商品信息和价格。
    需要邀请码 (inviteCode) 才能正常使用。
    """

    @property
    def name(self) -> str:
        return "maishou"

    async def get_goods_detail(
        self, session: aiohttp.ClientSession,
        goods_id: str, source: int,
        invite_code: str = "", **kwargs
    ) -> Optional[Dict[str, Any]]:
        if not invite_code:
            logger.warning("[maishou] 未设置邀请码，API 调用可能失败")

        params = {
            "goodsId": str(goods_id),
            "sourceType": str(source),
            "inviteCode": invite_code,
            "supplierCode": "",
            "activityId": "",
            "isShare": "1",
            "token": "",
        }

        try:
            async def _request_detail():
                resp = await session.post(
                    f"{MAISHOU_API_BASE}/goods/detail",
                    json={**params, "keyword": "", "usageScene": 5},
                    headers=HEADERS,
                )
                return await resp.json(encoding="utf-8-sig") or {}

            data = await _retry_request(_request_detail, label="maishou/detail")
            detail = data.get("data") or {}

            async def _request_url():
                resp = await session.post(
                    MAISHOU_SHARE_API,
                    json={**params, "isDirectDetail": 0},
                    headers=HEADERS,
                )
                return await resp.json(encoding="utf-8-sig") or {}

            url_data = await _retry_request(_request_url, label="maishou/url")
            info = url_data.get("data") or {}

            if not info:
                return None

            return {
                "title": detail.get("title", ""),
                "actualPrice": float(detail.get("actualPrice", 0)),
                "originalPrice": float(detail.get("originalPrice", 0)),
                "couponPrice": float(detail.get("couponPrice", 0)),
                "appUrl": info.get("appUrl") or info.get("schemaUrl"),
                "source": "maishou",
            }
        except Exception as e:
            logger.error("[maishou] 获取商品详情失败: %s", e)
            return None

    async def search_goods(
        self, session: aiohttp.ClientSession,
        keyword: str, source: int,
        limit: int = 10, invite_code: str = "", **kwargs
    ) -> List[Dict[str, Any]]:
        if not invite_code:
            logger.warning("[maishou] 未设置邀请码，搜索可能失败")

        try:
            async def _request():
                resp = await session.post(
                    f"{MAISHOU_API_BASE}/goods/list",
                    json={
                        "keyword": keyword,
                        "sourceType": str(source),
                        "inviteCode": invite_code,
                        "supplierCode": "",
                        "activityId": "",
                        "usageScene": 5,
                        "page": 1,
                        "pageSize": limit,
                    },
                    headers=HEADERS,
                )
                return await resp.json(encoding="utf-8-sig") or {}

            data = await _retry_request(_request, label="maishou/search")

            result = data.get("data") or data.get("result") or {}
            goods_list = result.get("goodsList") or result.get("list") or result.get("items") or []

            if isinstance(result, list):
                goods_list = result

            if not goods_list:
                return []

            results = []
            for goods in goods_list:
                try:
                    goods_id = goods.get("goodsId") or goods.get("id") or goods.get("goods_id")
                    if not goods_id:
                        continue

                    actual_price = float(
                        goods.get("actualPrice") or goods.get("price") or goods.get("actual_price") or 0
                    )
                    original_price = float(
                        goods.get("originalPrice") or goods.get("marketPrice") or goods.get("original_price") or actual_price
                    )
                    title = goods.get("title") or goods.get("goodsName") or goods.get("name") or "未知商品"
                    app_url = goods.get("appUrl") or goods.get("clickUrl") or goods.get("url") or ""

                    results.append({
                        "goods_id": goods_id,
                        "title": title,
                        "actualPrice": actual_price,
                        "originalPrice": original_price,
                        "appUrl": app_url,
                        "couponPrice": float(goods.get("couponPrice") or goods.get("coupon_price") or 0),
                        "source": "maishou",
                    })
                except Exception as e:
                    logger.warning("[maishou] 解析商品数据失败: %s", e)
                    continue

            return results
        except Exception as e:
            logger.error("[maishou] 搜索失败: %s", e)
            return []


# ─────────────────────────────────────────────
# 官方 API 模拟数据源（按平台标注待接入）
# ─────────────────────────────────────────────

class MockOfficialDataSource(DataSource):
    """官方 API 模拟数据源。

    ⚠️ 这是一个占位实现，模拟官方 API 的行为。
    待真实官方 API 接入后，替换此类中的请求逻辑。

    TODO: 接入真实官方 API 时需要修改:
      1. 替换 API URL 和请求参数
      2. 适配返回数据格式
      3. 处理认证/授权逻辑
    """

    @property
    def name(self) -> str:
        return "official"

    async def get_goods_detail(
        self, session: aiohttp.ClientSession,
        goods_id: str, source: int,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """模拟官方 API 商品详情查询。

        当前返回 None 表示官方 API 不可用，触发 fallback。
        待接入后应返回真实数据。
        """
        logger.info(
            "[official] ⚠️ 官方 API 尚未接入，返回不可用状态 "
            "(goods_id=%s, source=%d) — 将触发 fallback",
            goods_id, source
        )
        # 模拟延迟
        await asyncio.sleep(0.1)
        # 返回 None 表示此数据源不可用，应 fallback
        return None

    async def search_goods(
        self, session: aiohttp.ClientSession,
        keyword: str, source: int,
        limit: int = 10, **kwargs
    ) -> List[Dict[str, Any]]:
        """模拟官方 API 商品搜索。

        当前返回空列表表示官方 API 不可用，触发 fallback。
        待接入后应返回真实搜索结果。
        """
        logger.info(
            "[official] ⚠️ 官方 API 尚未接入，返回空结果 "
            "(keyword=%s, source=%d) — 将触发 fallback",
            keyword, source
        )
        await asyncio.sleep(0.1)
        return []


# ─────────────────────────────────────────────
# 平台专属官方 API 占位数据源
# ─────────────────────────────────────────────
# 以下为每个平台提供独立的官方 API 占位实现，
# 包含详细的直接接入指南。接入真实 API 时只需
# 替换对应类中的 get_goods_detail / search_goods 方法。

class XiaohongshuOfficialDataSource(DataSource):
    """小红书官方 API 占位数据源。

    当前返回不可用状态，触发 fallback 到买手 API。

    【小红书开放平台接入指南】
    1. 注册地址：https://open.xiaohongshu.com
    2. 申请「电商」相关 API 权限
    3. 主要 API 端点：
       - 商品详情：GET /api/v1/goods/detail?goodsId={id}
       - 商品搜索：GET /api/v1/goods/search?keyword={kw}
    4. 需要 OAuth 2.0 认证，获取 access_token
    5. 注意：小红书 API 主要面向入驻商家，普通开发者权限有限

    【接入步骤】
    1. 在 open.xiaohongshu.com 注册开发者账号
    2. 创建应用，获取 app_id 和 app_secret
    3. 完成 OAuth 授权流程获取 access_token
    4. 在 get_goods_detail 中替换为真实 API 请求
    5. 在 search_goods 中替换为真实搜索请求
    """

    @property
    def name(self) -> str:
        return "xiaohongshu_official"

    async def get_goods_detail(self, session, goods_id, source, **kwargs):
        logger.info("[xiaohongshu_official] ⚠️ 小红书官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return None

    async def search_goods(self, session, keyword, source, limit=10, **kwargs):
        logger.info("[xiaohongshu_official] ⚠️ 小红书官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return []


class DewuOfficialDataSource(DataSource):
    """得物官方 API 占位数据源。

    当前返回不可用状态，触发 fallback 到买手 API。

    【得物开放平台接入指南】
    1. 注册地址：https://open.dewu.com
    2. 得物 API 主要面向品牌商家/供应链合作方
    3. 需要企业账号入驻，个人开发者权限受限
    4. 主要 API：
       - 商品信息：POST /open-api/goods/detail
       - 价格查询：POST /open-api/goods/price
    5. 使用 AppKey + AppSecret 签名认证

    【接入步骤】
    1. 在 open.dewu.com 注册企业开发者账号
    2. 创建应用，获取 AppKey 和 AppSecret
    3. 实现签名算法（通常为 HMAC-SHA256）
    4. 替换 get_goods_detail 和 search_goods 中的请求逻辑
    """

    @property
    def name(self) -> str:
        return "dewu_official"

    async def get_goods_detail(self, session, goods_id, source, **kwargs):
        logger.info("[dewu_official] ⚠️ 得物官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return None

    async def search_goods(self, session, keyword, source, limit=10, **kwargs):
        logger.info("[dewu_official] ⚠️ 得物官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return []


class VipshopOfficialDataSource(DataSource):
    """唯品会官方 API 占位数据源。

    当前返回不可用状态，触发 fallback 到买手 API。

    【唯品会开放平台接入指南】
    1. 注册地址：https://open.vip.com
    2. API 端点格式：https://open.vip.com/api?service={service_name}
    3. 需要 AppKey + AppSecret，使用签名认证
    4. 主要 API 服务：
       - goods.detail.get — 商品详情
       - goods.price.get — 商品价格
       - goods.search — 商品搜索
    5. 签名公式：sign = MD5(app_key + service + timestamp + app_secret)

    【接入步骤】
    1. 在 open.vip.com 注册开发者账号
    2. 提交企业资质审核
    3. 创建应用，获取 AppKey 和 AppSecret
    4. 实现签名算法和请求封装
    5. 替换 get_goods_detail 和 search_goods

    【替代方案】唯品会 CPS 联盟：https://union.vip.com
    """

    @property
    def name(self) -> str:
        return "vipshop_official"

    async def get_goods_detail(self, session, goods_id, source, **kwargs):
        logger.info("[vipshop_official] ⚠️ 唯品会官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return None

    async def search_goods(self, session, keyword, source, limit=10, **kwargs):
        logger.info("[vipshop_official] ⚠️ 唯品会官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return []


class MeituanOfficialDataSource(DataSource):
    """美团官方 API 占位数据源。

    当前返回不可用状态，触发 fallback 到买手 API。

    【美团开放平台接入指南】
    1. 注册地址：https://developer.meituan.com
    2. 美团 API 主要面向本地生活/外卖服务
    3. 需要企业资质入驻，个人开发者权限极少
    4. 主要 API：
       - 门店信息查询
       - 商品/团购信息（需特定权限）
    5. 认证方式：OAuth 2.0 + AppKey

    【注意事项】
    - 美团核心商品价格 API 不对普通开发者开放
    - 团购/到店业务可通过美团联盟获取推广链接
    - 美团联盟：https://union.meituan.com

    【替代方案】美团联盟 CPS 模式
    """

    @property
    def name(self) -> str:
        return "meituan_official"

    async def get_goods_detail(self, session, goods_id, source, **kwargs):
        logger.info("[meituan_official] ⚠️ 美团官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return None

    async def search_goods(self, session, keyword, source, limit=10, **kwargs):
        logger.info("[meituan_official] ⚠️ 美团官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return []


class ElemeOfficialDataSource(DataSource):
    """饿了么官方 API 占位数据源。

    当前返回不可用状态，触发 fallback 到买手 API。

    【饿了么开放平台接入指南】
    1. 注册地址：https://open.alipay.com / https://open.ele.me
    2. 饿了么 API 属于阿里本地生活体系
    3. 主要 API（需入驻）：
       - 门店商品查询：eleme.product.get
       - 价格查询：通过门店 + 商品 ID 获取
    4. 认证方式：淘宝开放平台 OAuth（TOP SDK）
    5. 需要企业资质，个人开发者基本无法申请

    【注意事项】
    - 饿了么 API 主要面向 ISV/商家/服务商
    - 价格数据通常需要门店授权才能访问
    - 无公开的面向消费者的价格查询 API

    【替代方案】淘宝客/阿里妈妈联盟体系
    """

    @property
    def name(self) -> str:
        return "eleme_official"

    async def get_goods_detail(self, session, goods_id, source, **kwargs):
        logger.info("[eleme_official] ⚠️ 饿了么官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return None

    async def search_goods(self, session, keyword, source, limit=10, **kwargs):
        logger.info("[eleme_official] ⚠️ 饿了么官方 API 尚未接入，触发 fallback")
        await asyncio.sleep(0.1)
        return []


# ─────────────────────────────────────────────
# Fallback 组合器
# ─────────────────────────────────────────────

class FallbackDataSource(DataSource):
    """多数据源 Fallback 组合器。

    按配置的优先级顺序依次尝试每个数据源，
    第一个成功返回的数据源结果将作为最终结果。

    配置示例 (config.json):
    {
      "data_sources": {
        "enabled": ["official", "maishou"],
        "primary": "official"
      }
    }

    行为:
      1. 先尝试 official（MockOfficialDataSource）
      2. official 失败/不可用 → 自动 fallback 到 maishou
      3. maishou 也失败 → 返回 None/[]
    """

    def __init__(self, sources: List[DataSource]):
        """
        Args:
            sources: 按优先级排序的数据源列表（第一个为最高优先级）
        """
        if not sources:
            raise ValueError("至少需要一个数据源")
        self._sources = sources

    @property
    def name(self) -> str:
        names = [s.name for s in self._sources]
        return f"fallback({'>'.join(names)})"

    async def get_goods_detail(
        self, session: aiohttp.ClientSession,
        goods_id: str, source: int,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        last_error = None
        for ds in self._sources:
            try:
                result = await ds.get_goods_detail(session, goods_id, source, **kwargs)
                if result is not None:
                    logger.debug("[fallback] %s 成功返回商品 %s", ds.name, goods_id)
                    return result
                else:
                    logger.debug("[fallback] %s 返回 None，尝试下一个", ds.name)
            except Exception as e:
                last_error = e
                logger.warning("[fallback] %s 异常: %s，尝试下一个", ds.name, e)

        logger.error("[fallback] 所有数据源均失败 (goods_id=%s, source=%d)", goods_id, source)
        return None

    async def search_goods(
        self, session: aiohttp.ClientSession,
        keyword: str, source: int,
        limit: int = 10, **kwargs
    ) -> List[Dict[str, Any]]:
        last_error = None
        for ds in self._sources:
            try:
                result = await ds.search_goods(session, keyword, source, limit, **kwargs)
                if result:  # 非空列表表示成功
                    logger.debug("[fallback] %s 成功返回 %d 个搜索结果", ds.name, len(result))
                    return result
                else:
                    logger.debug("[fallback] %s 返回空结果，尝试下一个", ds.name)
            except Exception as e:
                last_error = e
                logger.warning("[fallback] %s 异常: %s，尝试下一个", ds.name, e)

        logger.error("[fallback] 所有数据源均失败 (keyword=%s, source=%d)", keyword, source)
        return []


# ─────────────────────────────────────────────
# 数据源工厂
# ─────────────────────────────────────────────

# 内置数据源注册表
_REGISTRY: Dict[str, type] = {
    "maishou": MaishouDataSource,
    "official": MockOfficialDataSource,
    "xiaohongshu_official": XiaohongshuOfficialDataSource,
    "dewu_official": DewuOfficialDataSource,
    "vipshop_official": VipshopOfficialDataSource,
    "meituan_official": MeituanOfficialDataSource,
    "eleme_official": ElemeOfficialDataSource,
}


def get_builtin_source(name: str) -> DataSource:
    """根据名称获取内置数据源实例。

    Args:
        name: 数据源名称 ("maishou" 或 "official")

    Returns:
        对应的 DataSource 实例
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知数据源: {name}，可用: {list(_REGISTRY.keys())}")
    return cls()


def create_fallback_from_config(config: Dict[str, Any]) -> FallbackDataSource:
    """从配置创建 FallbackDataSource。

    配置格式:
    {
      "data_sources": {
        "enabled": ["official", "maishou"],  # 按优先级排序
        "primary": "official"                 # 主要数据源（可选）
      }
    }

    如果没有 data_sources 配置，默认返回 ["maishou"]（向后兼容）。

    Args:
        config: 完整配置字典

    Returns:
        FallbackDataSource 实例
    """
    ds_config = config.get("data_sources", {})

    if not ds_config:
        # 向后兼容：没有 data_sources 配置时默认只用 maishou
        return FallbackDataSource([MaishouDataSource()])

    enabled = ds_config.get("enabled", ["maishou"])
    if not enabled:
        enabled = ["maishou"]

    sources = []
    for name in enabled:
        try:
            sources.append(get_builtin_source(name))
        except ValueError as e:
            logger.warning("跳过未知数据源配置: %s", e)

    if not sources:
        sources = [MaishouDataSource()]

    return FallbackDataSource(sources)


def create_single_source(name: str) -> DataSource:
    """创建单个数据源（用于直接使用，不走 fallback）。

    Args:
        name: 数据源名称

    Returns:
        DataSource 实例
    """
    return get_builtin_source(name)
