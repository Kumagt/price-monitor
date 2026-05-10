 # /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp"]
# ///
"""
电商价格监控工具 - 优化版
优化策略:
1. API 请求缓存(5 分钟内不重复请求同一商品)
2. 智能存储(只记录价格变化点)
3. 错峰检查(分散请求时间)
4. 自动清理(30 天前的详细数据)
"""
import os
import sys
import json
import csv
import logging
import asyncio
import aiohttp
import ssl
import smtplib
import argparse
import sqlite3
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, TypeVar
from functools import wraps

# 多数据源架构
from datasources import (
    FallbackDataSource,
    create_fallback_from_config,
)

# 基础目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "price_monitor.db"
CONFIG_FILE = DATA_DIR / "config.json"
CACHE_FILE = DATA_DIR / "api_cache.json"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

# 买手 API 配置(可选)
_INVITE_CODE_ENV = os.getenv("MAISHOU_INVITE_CODE", "")
INVITE_CODE = _INVITE_CODE_ENV
HEADERS = {
    aiohttp.hdrs.ACCEPT: "application/json",
    aiohttp.hdrs.REFERER: "https://hnbc018.kuaizhan.com/",
    aiohttp.hdrs.USER_AGENT: "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

# SSL 配置
SSL_CONTEXT = ssl.create_default_context()

logger = logging.getLogger(__name__)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 重试配置
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1  # 指数退避基数(秒)

# 缓存配置
CACHE_TTL_SECONDS = 300  # 5 分钟缓存
REQUEST_DELAY_MS = 200   # 请求间隔 200ms,避免触发限流

SESSION: aiohttp.ClientSession | None = None
DB_CONN: sqlite3.Connection | None = None
DATA_SOURCE: FallbackDataSource | None = None  # 全局数据源实例


def _shutdown():
    """进程退出时清理全局资源(atexit 注册)。

    DB_CONN 是同步 sqlite3 连接,可在 atexit 中安全关闭。
    SESSION 的生命周期由 main() 中的 async with 管理,此处仅在异常情况下兜底关闭。
    """
    global SESSION, DB_CONN
    if DB_CONN is not None:
        try:
            DB_CONN.close()
            logger.debug("数据库连接已关闭")
        except Exception as e:
            logger.warning("关闭数据库连接失败: %s", e)
        DB_CONN = None
    if SESSION is not None:
        try:
            # atexit 是同步上下文,用同步方式标记 session 关闭
            if not SESSION.closed:
                # 创建一个临时事件循环来关闭异步 session
                loop = asyncio.new_event_loop()
                loop.run_until_complete(SESSION.close())
                loop.close()
        except Exception as e:
            logger.warning("关闭 SESSION 失败: %s", e)
        SESSION = None


async def retry_async(coro_fn, max_retries: int = 3, backoff: float = 1.0):
    """通用异步重试:只捕获网络异常(超时、连接错误),不捕获业务异常。

    coro_fn: 一个无参可调用对象,每次调用返回一个新的协程。
    max_retries: 最大重试次数
    backoff: 基础退避秒数(指数退避:backoff * 2^(attempt-1) → 1s, 2s, 4s)
    """
    # 网络异常:重试;HTTP 错误 / 解析错误:不重试
    RETRIABLE = (
        aiohttp.ClientConnectionError,
        aiohttp.ClientTimeout,
        asyncio.TimeoutError,
        ConnectionError,
        TimeoutError,
        OSError,
    )
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except RETRIABLE as e:
            if attempt < max_retries:
                delay = backoff * (2 ** attempt)
                print(f"⚠️ 网络请求失败({type(e).__name__}: {e}),{delay}s 后重试 ({attempt + 1}/{max_retries})...")
                await asyncio.sleep(delay)
            else:
                print(f"❌ 网络请求失败,已重试 {max_retries} 次,放弃({type(e).__name__}: {e})")
                raise

# ---------- 价格预测 ----------


def linear_regression(x, y):
    """纯 Python 线性回归，返回 slope, intercept, r_squared。"""
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)
    sum_y2 = sum(yi ** 2 for yi in y)

    denom = n * sum_x2 - sum_x ** 2
    if denom == 0:
        return 0, sum_y / n, 0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    ss_tot = sum((yi - sum_y / n) ** 2 for yi in y)
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    return slope, intercept, r_squared


async def predict_price(args):
    """价格预测：基于历史数据进行线性回归预测。"""
    monitor_id = int(args.id)
    days = args.days if args.days else 30

    conn = get_db()

    # 获取监控信息
    cursor = conn.execute("SELECT name, goods_id FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    if not row:
        print(f"❌ 未找到监控 #{monitor_id}")
        return
    name = row["name"]

    # 查询最近 N 天的价格历史
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    cursor = conn.execute(
        """SELECT price, timestamp FROM price_history
           WHERE monitor_id = ? AND is_change_point = 1
           AND timestamp > ?
           ORDER BY timestamp ASC""",
        (monitor_id, cutoff)
    )
    records = [dict(r) for r in cursor.fetchall()]

    if len(records) < 3:
        print(f"📭 {name} 最近 {days} 天内仅有 {len(records)} 个数据点，不足以进行预测（至少需要 3 个）。")
        print("💡 建议：添加更多价格历史数据后再试。")
        return

    print(f"📈 价格预测 - {name}")
    print(f"")
    print(f"📊 基于最近 {days} 天的价格历史（共 {len(records)} 个数据点）")
    print("")

    # 打印历史价格
    print("历史价格趋势：")
    for r in records:
        ts = r["timestamp"][:10].replace("T", "")
        print(f"  {ts}  ¥{r['price']:.0f}")
    print("")

    # 构建回归数据：x = 距第一个数据点的天数, y = 价格
    base_time = datetime.fromisoformat(records[0]["timestamp"])
    x_vals = []
    y_vals = []
    for r in records:
        t = datetime.fromisoformat(r["timestamp"])
        day_offset = (t - base_time).total_seconds() / 86400.0
        x_vals.append(day_offset)
        y_vals.append(r["price"])

    slope, intercept, r_squared = linear_regression(x_vals, y_vals)

    # 输出回归结果
    print(f"📈 线性回归结果：")
    print(f"  斜率：{slope:+.2f} 元/天")
    print(f"  R² 值：{r_squared:.2f}")
    print("")

    # 预测未来 7 天
    forecast_days = 7
    last_day_offset = x_vals[-1]

    print(f"📅 未来 {forecast_days} 天预测：")
    predictions = []
    for i in range(1, forecast_days + 1):
        future_x = last_day_offset + i
        predicted_price = slope * future_x + intercept
        predicted_price = max(0, predicted_price)  # 价格不能为负
        predictions.append(predicted_price)
        print(f"  Day {i}: ¥{predicted_price:.0f}")
    print("")

    # 趋势判断
    print("📊 趋势判断：")
    if abs(slope) < 1:
        trend_dir = "↔️ 平稳"
        suggestion = "价格基本稳定，可按需购买"
    elif slope < 0:
        trend_dir = "📉 下降趋势"
        suggestion = f"价格持续下降，建议等待"
    else:
        trend_dir = "📈 上涨趋势"
        suggestion = f"价格持续上涨，建议尽早入手"

    print(f"  方向：{trend_dir}")
    print(f"  建议：{suggestion}")

    # R² 质量提示
    if r_squared < 0.5:
        print(f"")
        print(f"⚠️ 提示：R² = {r_squared:.2f} 较低，预测结果仅供参考（数据波动较大）。")
    elif r_squared < 0.8:
        print(f"")
        print(f"💡 提示：R² = {r_squared:.2f} 中等，预测结果有一定参考价值。")


# ---------- 网络重试工具 ----------
# 仅对网络层异常(连接失败、超时、DNS 等)进行重试
# 业务异常(HTTP 错误响应、JSON 解析失败等)不重试

RETRIABLE_EXCEPTIONS = (
    aiohttp.ClientConnectionError,   # 连接断开、DNS 失败、拒绝连接等
    aiohttp.ClientTimeout,           # aiohttp 超时
    asyncio.TimeoutError,            # asyncio 超时
    ConnectionError,                 # 通用连接错误
    TimeoutError,                    # 通用超时
    OSError,                         # 底层 IO 错误(如网络不可达)
)

F = TypeVar("F", bound=Callable)


def with_retry(label: str = "") -> Callable[[F], F]:
    """
    异步函数重试装饰器。

    - 最多重试 RETRY_MAX_ATTEMPTS 次
    - 指数退避:1s, 2s, 4s
    - 仅对网络层异常重试,业务异常直接抛出
    - 重试失败后打印明确错误信息
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
                try:
                    return await func(*args, **kwargs)
                except RETRIABLE_EXCEPTIONS as e:
                    last_exc = e
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    prefix = f"[{label}] " if label else ""
                    if attempt < RETRY_MAX_ATTEMPTS:
                        print(f"⚠️ {prefix}{type(e).__name__}: {e},{delay}s 后重试(第 {attempt}/{RETRY_MAX_ATTEMPTS} 次)")
                        await asyncio.sleep(delay)
                    else:
                        print(f"❌ {prefix}请求失败(已重试 {RETRY_MAX_ATTEMPTS} 次):{type(e).__name__}: {e}")
                except aiohttp.ClientResponseError as e:
                    # HTTP 4xx/5xx -- 不重试
                    print(f"❌ [{label if label else func.__name__}] HTTP 错误 {e.status}: {e.message}")
                    raise
                except aiohttp.ContentTypeError as e:
                    # 响应体不是合法 JSON -- 不重试
                    print(f"❌ [{label if label else func.__name__}] 响应解析失败:{e}")
                    raise
            # 所有重试耗尽(理论上不会走到这里,因为最后一次异常会走 else 分支 raise)
            # 但为了类型安全,兜底抛出
            raise last_exc
        return wrapper  # type: ignore[return-value]
    return decorator


def init_database():
    """初始化 SQLite 数据库"""
    global DB_CONN
    DB_CONN = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    DB_CONN.row_factory = sqlite3.Row

    # 监控表
    DB_CONN.execute("""
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goods_id TEXT NOT NULL,
            source INTEGER NOT NULL,
            name TEXT,
            target_price REAL,
            group_name TEXT DEFAULT '',
            created_at TEXT,
            last_price REAL,
            last_check TEXT,
            enabled INTEGER DEFAULT 1,
            UNIQUE(goods_id, source)
        )
    """)

    # 迁移:为已有数据库增加 group_name 字段
    try:
        DB_CONN.execute("ALTER TABLE monitors ADD COLUMN group_name TEXT DEFAULT ''")
        DB_CONN.commit()
    except Exception:
        pass  # 字段已存在

    # 价格历史表(只记录变化点)
    DB_CONN.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL,
            price REAL NOT NULL,
            original_price REAL,
            title TEXT,
            url TEXT,
            timestamp TEXT NOT NULL,
            is_change_point INTEGER DEFAULT 1,
            FOREIGN KEY (monitor_id) REFERENCES monitors(id)
        )
    """)

    # 索引优化
    DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_history_monitor ON price_history(monitor_id)")
    DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON price_history(timestamp)")

    DB_CONN.commit()


def get_db():
    """获取数据库连接"""
    global DB_CONN
    if DB_CONN is None:
        init_database()
    return DB_CONN


def load_config():
    """加载配置"""
    default_config = {
        "check_interval_minutes": 60,
        "price_change_threshold": 0.05,  # 5% 变化触发通知
        "auto_notify": True,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "request_delay_ms": REQUEST_DELAY_MS,
        "history_retention_days": 30,
        "max_history_per_item": 100,
        "anomaly_threshold": 0.3,       # 30% 异常波动阈值
        "anomaly_trend_count": 3,       # 连续趋势检测次数
        "invite_code": "",              # 买手 API 邀请码(可选)
        # 多数据源配置
        "data_sources": {
            "enabled": ["official", "maishou"],  # 按优先级排序，默认 fallback 模式
        },
        # 通知渠道配置
        "notify_channel": "json",  # json/webhook/email/all(逗号分隔)
        "notify_webhook_url": "",
        "notify_email_smtp": "",
        "notify_email_from": "",
        "notify_email_to": "",
        "notify_email_password": "",
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return {**default_config, **config}
    return default_config


def save_config(config):
    """保存配置(原子写入)"""
    tmp_file = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_file), str(CONFIG_FILE))


def load_api_cache() -> Dict:
    """加载 API 缓存"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.warning("缓存文件 JSON 解析失败 (%s),将使用空缓存。文件: %s", e, CACHE_FILE)
        except Exception as e:
            logger.warning("加载缓存文件失败 (%s),将使用空缓存。文件: %s", e, CACHE_FILE)
    return {}


def save_api_cache(cache: Dict):
    """保存 API 缓存(原子写入)"""
    tmp_file = CACHE_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_file), str(CACHE_FILE))


def get_cache_key(source: int, goods_id: str) -> str:
    """生成缓存键"""
    return hashlib.md5(f"{source}:{goods_id}".encode()).hexdigest()


def is_cache_valid(cache: Dict, key: str, ttl: int = CACHE_TTL_SECONDS) -> bool:
    """检查缓存是否有效"""
    if key not in cache:
        return False
    try:
        cached_time = datetime.fromisoformat(cache[key]["timestamp"])
        return (datetime.now() - cached_time).total_seconds() < ttl
    except (ValueError, TypeError):
        return False


def send_notification(title: str, message: str, config: Optional[Dict] = None):
    """统一通知接口:根据配置分发到多个通知渠道。

    Args:
        title: 通知标题
        message: 通知内容(纯文本)
        config: 配置字典(None 时自动加载)
    """
    if config is None:
        config = load_config()

    if not config.get("auto_notify", True):
        return  # 用户关闭了自动通知

    channel = config.get("notify_channel", "json")
    if not channel:
        channel = "json"

    channels = [c.strip() for c in channel.split(",")]

    if "all" in channels:
        channels = ["json", "webhook", "email"]

    for ch in channels:
        if ch == "json":
            _notify_json(title, message)
        elif ch == "webhook":
            _notify_webhook(title, message, config)
        elif ch == "email":
            _notify_email(title, message, config)


def _notify_json(title: str, message: str):
    """写入 JSON 文件通知(默认渠道)。"""
    try:
        notification_file = Path.home() / ".openclaw" / "workspace" / "notifications" / "price-monitor.json"
        notification_file.parent.mkdir(exist_ok=True)

        notification = {
            "type": "price_alert",
            "title": title,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        notifications = []
        if notification_file.exists():
            with open(notification_file, "r", encoding="utf-8") as f:
                try:
                    notifications = json.load(f)
                except Exception:
                    notifications = []

        notifications.append(notification)
        notifications = notifications[-50:]

        with open(notification_file, "w", encoding="utf-8") as f:
            json.dump(notifications, f, ensure_ascii=False, indent=2)

        print(f"🔔 通知已记录(JSON):{title}")
    except Exception as e:
        print(f"⚠️ JSON 通知失败:{e}")


def _notify_webhook(title: str, message: str, config: Dict):
    """通过 Webhook 发送通知(POST JSON)。"""
    webhook_url = config.get("notify_webhook_url", "")
    if not webhook_url:
        return

    try:
        payload = {
            "title": title,
            "content": message,
            "timestamp": datetime.now().isoformat(),
        }

        # 使用同步方式发送(通知不阻塞主流程)
        import urllib.request
        import urllib.error

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"🔔 通知已发送(Webhook):{title}")
    except Exception as e:
        print(f"⚠️ Webhook 通知失败:{e}")


def _notify_email(title: str, message: str, config: Dict):
    """通过邮件发送通知(HTML 格式)。"""
    smtp_server = config.get("notify_email_smtp", "")
    email_from = config.get("notify_email_from", "")
    email_to = config.get("notify_email_to", "")
    email_password = config.get("notify_email_password", "")

    if not all([smtp_server, email_from, email_to, email_password]):
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = email_from
        msg["To"] = email_to

        # 纯文本备用
        msg.attach(MIMEText(message, "plain", "utf-8"))

        # HTML 格式
        html_body = _build_email_html(title, message)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_server, timeout=10) as server:
            server.starttls()
            server.login(email_from, email_password)
            server.sendmail(email_from, email_to, msg.as_string())

        print(f"🔔 通知已发送(邮件):{title}")
    except Exception as e:
        print(f"⚠️ 邮件通知失败:{e}")


def _build_email_html(title: str, message: str) -> str:
    """构建 HTML 邮件正文。"""
    # 尝试解析消息中的关键信息
    lines = message.split("\n")
    product_name = ""
    price_info = []
    for line in lines:
        line_stripped = line.strip()
        if "当前价" in line_stripped or "原价" in line_stripped or "链接" in line_stripped or "价格变化" in line_stripped or "目标价" in line_stripped or "已达到" in line_stripped:
            price_info.append(line_stripped)
        elif line_stripped and not product_name:
            product_name = line_stripped

    rows = ""
    for info in price_info:
        rows += f"<tr><td style='padding: 6px 12px; border-bottom: 1px solid #eee;'>{info}</td></tr>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="background: #f8f9fa; border-radius: 8px; padding: 24px; border-left: 4px solid #4a90d9;">
    <h2 style="margin: 0 0 16px; color: #333;">{title}</h2>
    {f'<p style="margin: 0 0 16px; color: #666; font-size: 14px;">商品:{product_name}</p>' if product_name else ''}
    <table style="width: 100%; border-collapse: collapse;">
      {rows}
    </table>
    <p style="margin: 16px 0 0; color: #999; font-size: 12px;">发送时间:{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
  </div>
</body>
</html>"""


def get_price_extremes(monitor_id: int):
    """获取监控商品的历史最高/最低价"""
    conn = get_db()
    cursor = conn.execute(
        "SELECT MIN(price) as min_price, MAX(price) as max_price FROM price_history "
        "WHERE monitor_id = ? AND is_change_point = 1",
        (monitor_id,)
    )
    row = cursor.fetchone()
    if row and row["min_price"] is not None:
        return row["min_price"], row["max_price"]
    return None, None


def get_recent_price_trend(monitor_id: int, count: int = 3) -> Optional[str]:
    """获取最近 N 次价格变化点的趋势方向。
    返回：'up'（连续上涨）、'down'（连续下跌）、None（不连续或不一致）
    """
    conn = get_db()
    cursor = conn.execute(
        "SELECT price FROM price_history "
        "WHERE monitor_id = ? AND is_change_point = 1 "
        "ORDER BY timestamp DESC LIMIT ?",
        (monitor_id, count)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    if len(rows) < count:
        return None
    rows.reverse()  # 旧 → 新
    prices = [r["price"] for r in rows]

    all_up = all(prices[i] < prices[i + 1] for i in range(len(prices) - 1))
    all_down = all(prices[i] > prices[i + 1] for i in range(len(prices) - 1))

    if all_up:
        return "up"
    if all_down:
        return "down"
    return None


def check_price_anomaly(current_price: float, last_price: float, monitor_info: Dict, config: Dict) -> Optional[List[Dict]]:
    """检测价格异常波动（暴涨/暴跌/连续趋势）。

    返回异常信息 dict 列表，无异常时返回 None。
    """
    if not last_price or last_price <= 0:
        return None

    monitor_id = monitor_info["id"]
    name = monitor_info.get("name", "未知商品")
    anomaly_threshold = config.get("anomaly_threshold", 0.3)
    trend_count = config.get("anomaly_trend_count", 3)

    change_pct = (current_price - last_price) / last_price
    alerts = []

    # 1. 暴跌检测（跌幅 >= threshold）
    if change_pct <= -anomaly_threshold:
        hist_min, hist_max = get_price_extremes(monitor_id)
        alerts.append({
            "type": "crash",
            "emoji": "🚨",
            "title": "价格暴跌！",
            "name": name,
            "last_price": last_price,
            "current_price": current_price,
            "change_pct": change_pct,
            "hist_min": hist_min,
            "hist_max": hist_max,
            "suggestion": "可能是商家操作失误或重大促销，立即查看！",
        })

    # 2. 暴涨检测（涨幅 >= threshold）
    if change_pct >= anomaly_threshold:
        hist_min, hist_max = get_price_extremes(monitor_id)
        alerts.append({
            "type": "surge",
            "emoji": "🚨",
            "title": "价格暴涨！",
            "name": name,
            "last_price": last_price,
            "current_price": current_price,
            "change_pct": change_pct,
            "hist_min": hist_min,
            "hist_max": hist_max,
            "suggestion": "可能是商家调价或活动结束，请注意！",
        })

    # 3. 连续趋势检测
    trend = get_recent_price_trend(monitor_id, trend_count)
    if trend:
        conn = get_db()
        cursor = conn.execute(
            "SELECT price FROM price_history "
            "WHERE monitor_id = ? AND is_change_point = 1 "
            "ORDER BY timestamp DESC LIMIT ?",
            (monitor_id, trend_count)
        )
        rows = [dict(r)["price"] for r in cursor.fetchall()]
        rows.reverse()
        first_price = rows[0]
        total_pct = (rows[-1] - first_price) / first_price

        if trend == "up":
            alerts.append({
                "type": "trend_up",
                "emoji": "📈",
                "title": f"连续{trend_count}次涨价！",
                "name": name,
                "current_price": current_price,
                "change_pct": total_pct,
                "suggestion": f"价格已连续上涨 {trend_count} 次，累计涨幅 {total_pct*100:.1f}%，建议关注！",
            })
        elif trend == "down":
            alerts.append({
                "type": "trend_down",
                "emoji": "📉",
                "title": f"连续{trend_count}次降价！",
                "name": name,
                "current_price": current_price,
                "change_pct": total_pct,
                "suggestion": f"价格已连续下降 {trend_count} 次，累计降幅 {abs(total_pct)*100:.1f}%，可能是入手好时机！",
            })

    return alerts if alerts else None


def cleanup_old_history(days: int = 30):
    """清理旧的历史数据"""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    cursor = conn.execute(
        "DELETE FROM price_history WHERE timestamp < ? AND is_change_point = 0",
        (cutoff,)
    )
    conn.commit()
    if cursor.rowcount > 0:
        print(f"🧹 已清理 {cursor.rowcount} 条旧记录(>{days}天)")


def add_monitor_sync(goods_id: str, source: int, name: str, target_price: Optional[float] = None, group_name: str = "") -> int:
    """添加监控(同步)"""
    conn = get_db()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO monitors (goods_id, source, name, target_price, group_name, created_at, enabled)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (goods_id, source, name, target_price, group_name, datetime.now().isoformat())
    )
    conn.commit()

    # 获取刚插入的 ID
    cursor = conn.execute(
        "SELECT id FROM monitors WHERE goods_id = ? AND source = ?",
        (goods_id, source)
    )
    row = cursor.fetchone()
    return row["id"] if row else 0


def list_monitors_sync() -> List[Dict]:
    """列出所有监控(同步)"""
    conn = get_db()
    cursor = conn.execute(
        "SELECT * FROM monitors WHERE enabled = 1 ORDER BY id"
    )
    return [dict(row) for row in cursor.fetchall()]


def update_monitor_price(monitor_id: int, price: float, title: str = "", url: str = ""):
    """更新监控价格"""
    conn = get_db()
    conn.execute(
        "UPDATE monitors SET last_price = ?, last_check = ? WHERE id = ?",
        (price, datetime.now().isoformat(), monitor_id)
    )
    conn.commit()


def record_price_point(monitor_id: int, price: float, original_price: float,
                       title: str, url: str, is_change: bool = False):
    """记录价格点(只记录变化点)"""
    conn = get_db()
    conn.execute(
        """INSERT INTO price_history (monitor_id, price, original_price, title, url, timestamp, is_change_point)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (monitor_id, price, original_price, title, url, datetime.now().isoformat(), 1 if is_change else 0)
    )
    conn.commit()


async def search_goods(keyword: str, source: int, limit: int = 10) -> List[Dict]:
    """搜索商品(带缓存 + 多数据源 fallback)。"""
    global SESSION, DATA_SOURCE

    cache_key = f"search:{source}:{keyword}:{limit}"
    cache = load_api_cache()

    if is_cache_valid(cache, cache_key):
        print(f"⚡ 使用缓存:搜索 \"{keyword}\"")
        return cache[cache_key]["data"]

    # 初始化数据源
    config = load_config()
    if DATA_SOURCE is None:
        DATA_SOURCE = create_fallback_from_config(config)

    invite_code = INVITE_CODE or config.get("invite_code", "")

    if not invite_code and "maishou" in (config.get("data_sources", {}).get("enabled", ["maishou"])):
        print("⚠️ 未设置邀请码，买手 API 可能失败。请通过以下方式之一设置：")
        print("   1. 环境变量: MAISHOU_INVITE_CODE=你的邀请码")
        print("   2. 配置文件: uv run scripts/main.py config --invite-code=你的邀请码")

    try:
        results = await DATA_SOURCE.search_goods(
            SESSION, keyword, source, limit, invite_code=invite_code
        )

        if not results:
            return []

        # 缓存结果
        cache[cache_key] = {
            "timestamp": datetime.now().isoformat(),
            "data": results,
        }
        save_api_cache(cache)

        return results
    except Exception as e:
        print(f"搜索失败：{type(e).__name__}: {e}")
        return []


async def get_goods_detail(goods_id: str, source: int) -> Optional[Dict]:
    """获取商品详情(带缓存 + 多数据源 fallback + 限流)。"""
    global SESSION, DATA_SOURCE

    cache_key = get_cache_key(source, goods_id)
    cache = load_api_cache()
    config = load_config()

    # 初始化数据源
    if DATA_SOURCE is None:
        DATA_SOURCE = create_fallback_from_config(config)

    invite_code = INVITE_CODE or config.get("invite_code", "")

    # 检查缓存
    if is_cache_valid(cache, cache_key, config.get("cache_ttl_seconds", CACHE_TTL_SECONDS)):
        print(f"⚡ 使用缓存:商品 {goods_id}")
        return cache[cache_key]["data"]

    if not invite_code and "maishou" in (config.get("data_sources", {}).get("enabled", ["maishou"])):
        print("⚠️ 未设置邀请码，买手 API 可能失败。请通过以下方式之一设置：")
        print("   1. 环境变量: MAISHOU_INVITE_CODE=你的邀请码")
        print("   2. 配置文件: uv run scripts/main.py config --invite-code=你的邀请码")

    try:
        # 延迟请求,避免限流
        await asyncio.sleep(config.get("request_delay_ms", REQUEST_DELAY_MS) / 1000)

        result = await DATA_SOURCE.get_goods_detail(
            SESSION, goods_id, source, invite_code=invite_code
        )

        if result is None:
            return None

        # 缓存结果
        cache[cache_key] = {
            "timestamp": datetime.now().isoformat(),
            "data": result,
        }
        save_api_cache(cache)

        return result
    except Exception as e:
        print(f"获取商品详情失败:{e}")
        return None


# 平台名称映射
SOURCE_NAMES = {
    1: "淘宝", 2: "京东", 3: "拼多多",
    4: "小红书", 5: "得物", 6: "唯品会",
    7: "抖音", 8: "快手",
    9: "美团", 10: "饿了么",
}


# ──────────────── 平台适配器框架 ────────────────

class PlatformAdapter:
    """平台适配器基类"""
    platform_id: int = None
    platform_name: str = None

    async def get_price(self, session: aiohttp.ClientSession, goods_id: str) -> Optional[Dict]:
        """获取商品价格（子类实现）"""
        raise NotImplementedError

    async def search_goods(self, session: aiohttp.ClientSession, keyword: str, **kwargs) -> List[Dict]:
        """搜索商品（子类实现）"""
        raise NotImplementedError


PLATFORM_REGISTRY: Dict[int, PlatformAdapter] = {}


def register_platform(adapter_class):
    """注册平台适配器装饰器"""
    PLATFORM_REGISTRY[adapter_class.platform_id] = adapter_class()
    return adapter_class


@register_platform
class XiaohongshuAdapter(PlatformAdapter):
    """小红书平台适配器

    当前通过买手 API (maishou88) sourceType=4 获取数据。
    如需要直接接入小红书开放平台，参考以下指南：

    【直接接入指南】
    1. 注册小红书开放平台：https://open.xiaohongshu.com
    2. 申请「电商」相关 API 权限
    3. 主要 API 端点：
       - 商品详情：GET /api/v1/goods/detail?goodsId={id}
       - 商品搜索：GET /api/v1/goods/search?keyword={kw}
    4. 需要 OAuth 2.0 认证，获取 access_token
    5. 注意：小红书 API 主要面向入驻商家，普通开发者权限有限

    【替代方案】
    - 通过买手 API 聚合获取（当前方案，推荐）
    - 网页解析（需要处理反爬，不稳定，不推荐生产环境）
    """
    platform_id = 4
    platform_name = "小红书"

    async def get_price(self, session, goods_id):
        """通过买手 API 获取小红书商品价格"""
        try:
            detail = await get_goods_detail(goods_id, self.platform_id)
            if detail:
                return {
                    "status": "ok",
                    "goods_id": goods_id,
                    "title": detail.get("title", ""),
                    "actualPrice": detail["actualPrice"],
                    "originalPrice": detail["originalPrice"],
                    "couponPrice": detail.get("couponPrice", 0),
                    "appUrl": detail.get("appUrl", ""),
                }
            return {
                "status": "error",
                "message": f"{self.platform_name} 商品 {goods_id} 未找到",
                "goods_id": goods_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"{self.platform_name} 价格查询失败: {e}",
                "goods_id": goods_id,
            }

    async def search_goods(self, session, keyword, **kwargs):
        """通过买手 API 搜索小红书商品"""
        limit = kwargs.get("limit", 10)
        try:
            results = await search_goods(keyword, self.platform_id, limit)
            if results:
                return [{"status": "ok", **item} for item in results]
            return [{"status": "no_results", "keyword": keyword, "message": f"{self.platform_name} 未找到相关商品"}]
        except Exception as e:
            return [{"status": "error", "keyword": keyword, "message": f"{self.platform_name} 搜索失败: {e}"}]


@register_platform
class DewuAdapter(PlatformAdapter):
    """得物平台适配器

    当前通过买手 API (maishou88) sourceType=5 获取数据。
    如需要直接接入得物开放平台，参考以下指南：

    【直接接入指南】
    1. 注册得物开放平台：https://open.dewu.com
    2. 申请商品相关 API 权限
    3. 得物 API 主要面向品牌商家/供应链合作方
    4. 需要企业账号入驻，个人开发者权限受限
    5. 主要 API：
       - 商品信息：POST /open-api/goods/detail
       - 价格查询：POST /open-api/goods/price
    6. 使用 AppKey + AppSecret 签名认证

    【替代方案】
    - 通过买手 API 聚合获取（当前方案，推荐）
    - 第三方数据服务（如慢慢买、比价网等）
    - 网页解析（得物有较强的反爬机制，不推荐）
    """
    platform_id = 5
    platform_name = "得物"

    async def get_price(self, session, goods_id):
        """通过买手 API 获取得物商品价格"""
        try:
            detail = await get_goods_detail(goods_id, self.platform_id)
            if detail:
                return {
                    "status": "ok",
                    "goods_id": goods_id,
                    "title": detail.get("title", ""),
                    "actualPrice": detail["actualPrice"],
                    "originalPrice": detail["originalPrice"],
                    "couponPrice": detail.get("couponPrice", 0),
                    "appUrl": detail.get("appUrl", ""),
                }
            return {
                "status": "error",
                "message": f"{self.platform_name} 商品 {goods_id} 未找到",
                "goods_id": goods_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"{self.platform_name} 价格查询失败: {e}",
                "goods_id": goods_id,
            }

    async def search_goods(self, session, keyword, **kwargs):
        """通过买手 API 搜索得物商品"""
        limit = kwargs.get("limit", 10)
        try:
            results = await search_goods(keyword, self.platform_id, limit)
            if results:
                return [{"status": "ok", **item} for item in results]
            return [{"status": "no_results", "keyword": keyword, "message": f"{self.platform_name} 未找到相关商品"}]
        except Exception as e:
            return [{"status": "error", "keyword": keyword, "message": f"{self.platform_name} 搜索失败: {e}"}]


@register_platform
class VipshopAdapter(PlatformAdapter):
    """唯品会平台适配器

    当前通过买手 API (maishou88) sourceType=6 获取数据。
    如需要直接接入唯品会开放平台，参考以下指南：

    【直接接入指南】
    1. 注册唯品会开放平台：https://open.vip.com
    2. 唯品会 API 端点示例：https://open.vip.com/api?service={service_name}
    3. 需要 AppKey + AppSecret，使用签名认证
    4. 主要 API 服务：
       - goods.detail.get — 商品详情
       - goods.price.get — 商品价格
       - goods.search — 商品搜索
    5. 请求参数需包含：app_key、timestamp、sign、format=json
    6. 唯品会对第三方开发者审核严格，需提交企业资质

    【签名示例】
    sign = MD5(app_key + service + timestamp + app_secret)

    【替代方案】
    - 通过买手 API 聚合获取（当前方案，推荐）
    - 唯品会 CPS 联盟（推广佣金模式）：https://union.vip.com
    """
    platform_id = 6
    platform_name = "唯品会"

    async def get_price(self, session, goods_id):
        """通过买手 API 获取唯品会商品价格"""
        try:
            detail = await get_goods_detail(goods_id, self.platform_id)
            if detail:
                return {
                    "status": "ok",
                    "goods_id": goods_id,
                    "title": detail.get("title", ""),
                    "actualPrice": detail["actualPrice"],
                    "originalPrice": detail["originalPrice"],
                    "couponPrice": detail.get("couponPrice", 0),
                    "appUrl": detail.get("appUrl", ""),
                }
            return {
                "status": "error",
                "message": f"{self.platform_name} 商品 {goods_id} 未找到",
                "goods_id": goods_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"{self.platform_name} 价格查询失败: {e}",
                "goods_id": goods_id,
            }

    async def search_goods(self, session, keyword, **kwargs):
        """通过买手 API 搜索唯品会商品"""
        limit = kwargs.get("limit", 10)
        try:
            results = await search_goods(keyword, self.platform_id, limit)
            if results:
                return [{"status": "ok", **item} for item in results]
            return [{"status": "no_results", "keyword": keyword, "message": f"{self.platform_name} 未找到相关商品"}]
        except Exception as e:
            return [{"status": "error", "keyword": keyword, "message": f"{self.platform_name} 搜索失败: {e}"}]


@register_platform
class MeituanAdapter(PlatformAdapter):
    """美团平台适配器

    当前通过买手 API (maishou88) sourceType=9 获取数据。
    如需要直接接入美团开放平台，参考以下指南：

    【直接接入指南】
    1. 注册美团开放平台：https://developer.meituan.com
    2. 美团 API 主要面向本地生活/外卖服务
    3. 商品/价格相关 API 有限，主要为：
       - 门店信息查询
       - 商品/团购信息（需特定权限）
    4. 需要企业资质入驻，个人开发者权限极少
    5. 认证方式：OAuth 2.0 + AppKey

    【注意事项】
    - 美团核心商品价格 API 不对普通开发者开放
    - 团购/到店业务可通过美团联盟获取推广链接
    - 美团联盟：https://union.meituan.com

    【替代方案】
    - 通过买手 API 聚合获取（当前方案，推荐）
    - 美团联盟 CPS 模式
    """
    platform_id = 9
    platform_name = "美团"

    async def get_price(self, session, goods_id):
        """通过买手 API 获取美团商品价格"""
        try:
            detail = await get_goods_detail(goods_id, self.platform_id)
            if detail:
                return {
                    "status": "ok",
                    "goods_id": goods_id,
                    "title": detail.get("title", ""),
                    "actualPrice": detail["actualPrice"],
                    "originalPrice": detail["originalPrice"],
                    "couponPrice": detail.get("couponPrice", 0),
                    "appUrl": detail.get("appUrl", ""),
                }
            return {
                "status": "error",
                "message": f"{self.platform_name} 商品 {goods_id} 未找到",
                "goods_id": goods_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"{self.platform_name} 价格查询失败: {e}",
                "goods_id": goods_id,
            }

    async def search_goods(self, session, keyword, **kwargs):
        """通过买手 API 搜索美团商品"""
        limit = kwargs.get("limit", 10)
        try:
            results = await search_goods(keyword, self.platform_id, limit)
            if results:
                return [{"status": "ok", **item} for item in results]
            return [{"status": "no_results", "keyword": keyword, "message": f"{self.platform_name} 未找到相关商品"}]
        except Exception as e:
            return [{"status": "error", "keyword": keyword, "message": f"{self.platform_name} 搜索失败: {e}"}]


@register_platform
class ElemeAdapter(PlatformAdapter):
    """饿了么平台适配器

    当前通过买手 API (maishou88) sourceType=10 获取数据。
    如需要直接接入饿了么开放平台，参考以下指南：

    【直接接入指南】
    1. 注册阿里开放平台/饿了么开发者中心：https://open.alipay.com / https://open.ele.me
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

    【替代方案】
    - 通过买手 API 聚合获取（当前方案，推荐）
    - 淘宝客/阿里妈妈联盟体系
    """
    platform_id = 10
    platform_name = "饿了么"

    async def get_price(self, session, goods_id):
        """通过买手 API 获取饿了么商品价格"""
        try:
            detail = await get_goods_detail(goods_id, self.platform_id)
            if detail:
                return {
                    "status": "ok",
                    "goods_id": goods_id,
                    "title": detail.get("title", ""),
                    "actualPrice": detail["actualPrice"],
                    "originalPrice": detail["originalPrice"],
                    "couponPrice": detail.get("couponPrice", 0),
                    "appUrl": detail.get("appUrl", ""),
                }
            return {
                "status": "error",
                "message": f"{self.platform_name} 商品 {goods_id} 未找到",
                "goods_id": goods_id,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"{self.platform_name} 价格查询失败: {e}",
                "goods_id": goods_id,
            }

    async def search_goods(self, session, keyword, **kwargs):
        """通过买手 API 搜索饿了么商品"""
        limit = kwargs.get("limit", 10)
        try:
            results = await search_goods(keyword, self.platform_id, limit)
            if results:
                return [{"status": "ok", **item} for item in results]
            return [{"status": "no_results", "keyword": keyword, "message": f"{self.platform_name} 未找到相关商品"}]
        except Exception as e:
            return [{"status": "error", "keyword": keyword, "message": f"{self.platform_name} 搜索失败: {e}"}]


async def compare_goods(args):
    """多源比价:同时查询多个平台的同一商品"""
    source_ids = [int(x.strip()) for x in args.sources.split(",")]
    goods_id = args.id

    if len(source_ids) < 2:
        print("❌ 多源比价至少需要 2 个平台")
        return

    print(f"🔍 正在比价:商品 {goods_id}\n")
    print(f"{'平台':<10} {'当前价':<10} {'原价':<10} {'状态'}")
    print("-" * 70)

    results = []
    for source in source_ids:
        source_name = SOURCE_NAMES.get(source, f"平台{source}")
        print(f"⏳ {source_name}...")
        try:
            detail = await get_goods_detail(goods_id, source)
            if detail:
                results.append({
                    "name": source_name,
                    "source": source,
                    "price": detail["actualPrice"],
                    "original": detail["originalPrice"],
                    "url": detail.get("appUrl", ""),
                    "coupon": detail.get("couponPrice", 0),
                })
        except Exception as e:
            print(f"  ❌ {source_name} 查询失败")

        await asyncio.sleep(0.2)

    if not results:
        print("\n❌ 所有平台查询均失败")
        return

    # 找最低价
    min_price = min(r["price"] for r in results)
    max_price = max(r["price"] for r in results)
    save_pct = (max_price - min_price) / max_price * 100

    print("\n" + "=" * 70)
    print(f"📊 比价结果(共 {len(results)} 个平台):\n")

    # 排序:最低价在前
    results.sort(key=lambda x: x["price"])

    for r in results:
        is_lowest = r["price"] == min_price
        is_highest = r["price"] == max_price and len(results) > 1

        flag = ""
        if is_lowest:
            flag = " 🏆最低"
        elif is_highest:
            flag = " (最高)"

        price_str = f"¥{r['price']:.0f}"
        orig_str = f"¥{r['original']:.0f}"

        # 计算折扣
        if r['coupon'] > 0:
            price_str += f" (券¥{r['coupon']})"

        print(f"{r['name']:<10} {price_str:<12} {orig_str:<10}{flag}")
        if r["url"]:
            print(f"   {'':<10} 链接:{r['url'][:60]}...")

    print(f"\n💰 价差:¥{max_price - min_price:.0f}({save_pct:.1f}%)")
    print(f"💡 建议:选择最低价平台可节省 ¥{max_price - min_price:.0f}!")


async def show_trend(args):
    """展示商品价格历史趋势图(ASCII字符画)"""
    monitor_id = int(args.id)
    days = args.days

    conn = get_db()

    # 获取商品名称
    cursor = conn.execute("SELECT name FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    if not row:
        print(f"❌ 未找到监控 #{monitor_id}")
        return
    name = row["name"]

    # 查询历史数据
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    cursor = conn.execute(
        """SELECT price, original_price, timestamp FROM price_history
           WHERE monitor_id = ? AND is_change_point = 1
           AND timestamp > ?
           ORDER BY timestamp ASC""",
        (monitor_id, cutoff)
    )
    records = [dict(r) for r in cursor.fetchall()]

    if len(records) < 2:
        print(f"📭 监控 {name} 近 {days} 天内数据不足,需要至少 2 个价格点")
        return

    prices = [r["price"] for r in records]
    timestamps = [r["timestamp"] for r in records]

    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / len(prices)

    # 如果价格范围太小,自动扩展显示范围
    price_range = max_price - min_price
    padding = price_range * 0.1 if price_range > 0 else 1.0
    p_min = min_price - padding
    p_max = max_price + padding

    # 图表参数
    chart_height = 15
    chart_width = min(len(records) - 1, 40)

    # 计算每个数据点在图表中的位置
    chart_data = []
    for i, p in enumerate(prices):
        y = int((p - p_min) / (p_max - p_min) * chart_height)
        x = int(i / max(len(prices) - 1, 1) * chart_width)
        chart_data.append((x, min(y, chart_height)))

    # 初始化空白图表
    chart = [[" " for _ in range(chart_width + 1)] for _ in range(chart_height + 1)]

    # 标记数据点
    for i, (x, y) in enumerate(chart_data):
        chart[y][x] = "\u2588"  # █

    # 连接相邻点(用竖线和斜线)
    for i in range(len(chart_data) - 1):
        x1, y1 = chart_data[i]
        x2, y2 = chart_data[i + 1]

        # 垂直线
        step = 1 if y2 > y1 else -1
        for y in range(y1 + step, y2 + 1, step):
            if chart[y][x1] == " ":
                chart[y][x1] = "│"

        # 斜线
        if x1 != x2:
            slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0
            for x in range(x1 + 1, x2 + 1):
                y = int(y1 + slope * (x - x1))
                if 0 <= y <= chart_height:
                    if chart[y][x] == " ":
                        chart[y][x] = "\u2591"  # ░

    print(f"📈 {name} 价格趋势(最近 {days} 天)\n")

    # 打印图表
    step = max(1, len(prices) // chart_height)
    for i in range(chart_height, -1, -1):
        target_price = p_min + (p_max - p_min) * i / chart_height
        line = f"¥{target_price:,.0f} │"
        for x in range(chart_width):
            line += chart[i][x]
        print(line)

    # X轴
    line = " " * 10 + " ├──"
    line += "─" * chart_width
    print(line)

    # X轴标签
    first_date = timestamps[0][:10]
    last_date = timestamps[-1][:10]
    mid_idx = len(timestamps) // 2
    mid_date = timestamps[mid_idx][:10]
    label_line = " " * 10 + "   " + first_date.ljust(15) + mid_date.ljust(15) + last_date
    print(label_line)

    # 统计信息
    print(f"\n📊 统计:")
    print(f"   📈 最高价:¥{max_price:.0f}")
    print(f"   📉 最低价:¥{min_price:.0f}")
    print(f"   📊 平均价:¥{avg_price:.0f}")

    first_change = (prices[-1] - prices[0]) / prices[0] * 100
    print(f"   📈 期间变化:{first_change:+.1f}%")

    # 趋势判断
    if len(prices) >= 3:
        # 简单趋势判断:后半段均值 vs 前半段均值
        mid = len(prices) // 2
        first_half_avg = sum(prices[:mid]) / mid
        second_half_avg = sum(prices[mid:]) / (len(prices) - mid)
        trend_pct = (second_half_avg - first_half_avg) / first_half_avg * 100

        if trend_pct < -2:
            print(f"   \U0001F4C9 趋势:降价中(-{abs(trend_pct):.1f}%)")
        elif trend_pct > 2:
            print(f"   \U0001F4C8 趋势:涨价中(+{trend_pct:.1f}%)")
        else:
            print(f"   ↔️ 趋势:平稳(±{abs(trend_pct):.1f}%)")


async def show_low_price(args):
    """显示历史低价商品排名"""
    top_n = args.top if args.top else 10
    days = args.days if args.days else 30

    monitors = list_monitors_sync()

    if not monitors:
        print("📭 暂无监控商品")
        return

    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    results = []
    for m in monitors:
        if not m.get("enabled", 1):
            continue

        current_price = m.get("last_price", 0)
        if not current_price:
            continue

        # 查询历史最低价
        cursor = conn.execute(
            "SELECT MIN(price) as min_price FROM price_history "
            "WHERE monitor_id = ? AND timestamp > ?",
            (m["id"], cutoff)
        )
        row = cursor.fetchone()
        low_price = row["min_price"] if row and row["min_price"] else current_price

        # 计算距离历史低价的百分比
        if low_price > 0:
            pct = (current_price - low_price) / low_price * 100
        else:
            pct = 0

        # 计算距离最高价的百分比(推荐度)
        cursor = conn.execute(
            "SELECT MAX(price) as max_price FROM price_history "
            "WHERE monitor_id = ? AND timestamp > ?",
            (m["id"], cutoff)
        )
        row = cursor.fetchone()
        high_price = row["max_price"] if row and row["max_price"] else current_price

        save_pct = 0
        if high_price > 0 and current_price < high_price:
            save_pct = (high_price - current_price) / high_price * 100

        # 推荐度:距离历史低价越近越值得
        if pct <= 1:
            score = 5  # 接近历史低价
        elif pct <= 5:
            score = 4
        elif pct <= 10:
            score = 3
        elif pct <= 20:
            score = 2
        else:
            score = 1

        results.append({
            "name": m["name"],
            "current": current_price,
            "low": low_price,
            "high": high_price,
            "pct": pct,
            "score": score,
            "source": SOURCE_NAMES.get(m["source"], "未知"),
        })

    # 按推荐度排序
    results.sort(key=lambda x: x["score"], reverse=True)

    if not results:
        print("📭 暂无可用数据")
        return

    results = results[:top_n]

    print(f"🏆 历史低价商品排名(最近 {days} 天)\n")
    print(f"{'':<4} {'商品':<20} {'平台':<6} {'当前价':<10} {'历史低价':<10} {'距低':<8} {'推荐度'}")
    print("-" * 75)

    for i, r in enumerate(results, 1):
        pct_str = f"{r['pct']:+.1f}%" if r['pct'] > 0 else "✅"
        stars = "⭐" * r["score"] + "☆" * (5 - r["score"])
        name = r["name"][:18] if len(r["name"]) > 18 else r["name"]

        print(f"{i:<4} {name:<20} {r['source']:<6} ¥{r['current']:<9.0f} ¥{r['low']:<9.0f} {pct_str:<8} {stars}")

    print(f"\n💡 显示 Top {len(results)} 个商品,推荐度越高分值越低越值得买!")


async def add_monitor(args):
    """添加监控商品"""
    monitor_id = add_monitor_sync(args.id, int(args.source), args.name or f"商品{args.id}",
                                   float(args.target_price) if args.target_price else None, "")

    if monitor_id == 0:
        print(f"⚠️ 该商品已在监控中")
        return

    print(f"✅ 已添加监控 #{monitor_id}: {args.name or f'商品{args.id}'}")
    print(f"   商品 ID: {args.id}")
    print(f"   平台:{args.source}")
    if args.target_price:
        print(f"   目标价:¥{args.target_price}")

    print("\n正在获取当前价格...")
    await check_single_price(monitor_id)


async def list_monitors(args):
    """查看监控列表"""
    monitors = list_monitors_sync()
    config = load_config()

    if not monitors:
        print("📭 暂无监控商品")
        print("\n添加监控:uv run scripts/main.py add --source=1 --id=商品 ID --name=名称 --target_price=目标价")
        return

    print(f"📊 监控列表 (共 {len(monitors)} 个商品,检查间隔:{config['check_interval_minutes']}分钟)\n")
    print(f"{'ID':<4} {'名称':<20} {'平台':<8} {'当前价':<10} {'目标价':<10} {'状态':<8}")
    print("-" * 70)

    source_names = SOURCE_NAMES

    for m in monitors:
        price_str = f"¥{m.get('last_price', 'N/A')}" if m.get('last_price') else "N/A"
        target_str = f"¥{m['target_price']}" if m.get('target_price') else "-"
        status = "✅" if m.get('enabled', 1) else "⏸️"
        name = m['name'][:18] + ".." if len(m['name']) > 20 else (m['name'] or "未知")
        print(f"{m['id']:<4} {name:<20} {source_names.get(m['source'], '未知'):<8} {price_str:<10} {target_str:<10} {status:<8}")


async def check_single_price(monitor_id: int):
    """检查单个商品价格"""
    config = load_config()
    threshold = config["price_change_threshold"]

    monitors = list_monitors_sync()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)

    if not monitor:
        print(f"❌ 未找到监控 #{monitor_id}")
        return

    if not monitor.get("enabled", 1):
        print(f"⏸️ 监控 #{monitor_id} 已暂停")
        return

    detail = await get_goods_detail(monitor["goods_id"], monitor["source"])

    if not detail:
        print(f"⚠️ 获取商品 #{monitor_id} 价格失败")
        return

    current_price = detail["actualPrice"]
    last_price = monitor.get("last_price")

    # 更新监控记录
    update_monitor_price(monitor_id, current_price, detail.get("title", ""), detail.get("appUrl", ""))

    # 只记录价格变化点(节省存储空间)
    is_change = False
    if last_price and last_price > 0:
        change_ratio = abs(current_price - last_price) / last_price
        if change_ratio >= threshold:
            is_change = True
            record_price_point(monitor_id, current_price, detail["originalPrice"],
                              detail.get("title", ""), detail.get("appUrl", ""), True)
            print(f"   价格变化点:{change_ratio*100:+.1f}%")
        else:
            print(f"   价格无变化({change_ratio*100:.1f}% < 阈值 {threshold*100:.0f}%),跳过记录")
    else:
        # 首次监控,无历史价格,记录初始值
        is_change = True
        record_price_point(monitor_id, current_price, detail["originalPrice"],
                          detail.get("title", ""), detail.get("appUrl", ""), True)

    # 检查价格变化(使用同一个阈值)
    change_notify = False
    change_msg = ""

    if last_price:
        change_pct = (current_price - last_price) / last_price
        if abs(change_pct) >= threshold:
            change_notify = True
            direction = "📈" if change_pct > 0 else "📉"
            change_msg = f"{direction} 价格变化:¥{last_price} → ¥{current_price} ({change_pct:+.1%})"

    # 检查目标价
    target_notify = False
    if monitor.get("target_price") and current_price <= monitor["target_price"]:
        target_notify = True

    # 异常检测
    anomaly_alerts = check_price_anomaly(current_price, last_price, monitor, config)
    anomaly_notify = False
    anomaly_output = ""
    if anomaly_alerts:
        anomaly_notify = True
        for alert in anomaly_alerts:
            emoji = alert["emoji"]
            alert_lines = [f"\n  {emoji} 价格异常检测！"]
            alert_lines.append(f"     商品：{alert['name']}")

            if "last_price" in alert and "current_price" in alert:
                alert_lines.append(
                    f"     当前价：¥{alert['last_price']} → ¥{alert['current_price']} ({alert['change_pct']*100:+.1f}%)"
                )
            elif "current_price" in alert:
                alert_lines.append(f"     当前价：¥{alert['current_price']}")

            if alert.get("type") in ("crash", "surge"):
                if alert.get("hist_min") is not None:
                    alert_lines.append(f"     历史最低：¥{alert['hist_min']:.0f}")
                if alert.get("hist_max") is not None:
                    alert_lines.append(f"     历史最高：¥{alert['hist_max']:.0f}")

            alert_lines.append(f"     建议：{alert['suggestion']}")
            anomaly_output += "\n".join(alert_lines)

        send_notification(
            f"⚠️ 价格异常：{monitor['name']}",
            anomaly_output.strip(),
            config,
        )

    # 输出结果
    print(f"\n📦 {monitor['name']}")
    print(f"   当前价格：¥{current_price}")
    if detail["originalPrice"] != current_price:
        print(f"   原价：¥{detail['originalPrice']}")
    if detail.get("appUrl"):
        print(f"   链接：{detail['appUrl'][:50]}...")

    if change_notify:
        print(f"   {change_msg}")
        send_notification(
            f"价格变动：{monitor['name']}",
            f"{change_msg}\n当前价：¥{current_price}\n链接：{detail.get('appUrl', 'N/A')}",
            config,
        )

    if target_notify:
        print(f"   🎉 已达到目标价 ¥{monitor['target_price']}!")
        send_notification(
            f"🎉 目标价达成：{monitor['name']}",
            f"当前价：¥{current_price} ≤ 目标价：¥{monitor['target_price']}\n链接：{detail.get('appUrl', 'N/A')}",
            config,
        )

    if anomaly_output:
        print(anomaly_output)

    return {
        "monitor_id": monitor_id,
        "name": monitor["name"],
        "current_price": current_price,
        "last_price": last_price,
        "change_notify": change_notify,
        "target_notify": target_notify,
        "anomaly_notify": anomaly_notify,
    }


async def check_all_prices(args):
    """检查所有商品价格(错峰检查)"""
    monitors = list_monitors_sync()

    if not monitors:
        print("📭 暂无启用的监控商品")
        return

    print(f"🔍 正在检查 {len(monitors)} 个商品价格...\n")

    results = []
    for i, monitor in enumerate(monitors):
        # 错峰:每个请求间隔 200ms
        if i > 0:
            await asyncio.sleep(0.2)

        result = await check_single_price(monitor["id"])
        if result:
            results.append(result)

    # 汇总通知
    notify_count = sum(1 for r in results if r.get("change_notify") or r.get("target_notify") or r.get("anomaly_notify"))
    if notify_count > 0:
        print(f"\n🔔 共 {notify_count} 个商品需要通知")


async def remove_monitor(args):
    """删除监控"""
    conn = get_db()

    # 先获取名称
    cursor = conn.execute("SELECT name FROM monitors WHERE id = ?", (int(args.id),))
    row = cursor.fetchone()
    if not row:
        print(f"❌ 未找到监控 #{args.id}")
        return

    name = row["name"]

    # 删除监控和历史
    conn.execute("DELETE FROM monitors WHERE id = ?", (int(args.id),))
    conn.execute("DELETE FROM price_history WHERE monitor_id = ?", (int(args.id),))
    conn.commit()

    print(f"✅ 已删除监控 #{args.id}: {name}")


async def show_history(args):
    """查看价格历史"""
    conn = get_db()
    cursor = conn.execute(
        """SELECT price, title, timestamp FROM price_history
           WHERE monitor_id = ?
           ORDER BY timestamp DESC LIMIT 10""",
        (int(args.id),)
    )
    history = cursor.fetchall()

    if not history:
        print(f"📭 暂无监控 #{args.id} 的历史记录")
        return

    monitors = list_monitors_sync()
    monitor = next((m for m in monitors if m["id"] == int(args.id)), None)
    name = monitor["name"] if monitor else f"商品{args.id}"

    print(f"📈 {name} 价格历史 (最近 {len(history)} 条)\n")
    print(f"{'时间':<20} {'价格':<10} {'标题'}")
    print("-" * 60)

    for record in reversed(history):
        time_str = record["timestamp"][:16].replace("T", " ")
        print(f"{time_str:<20} ¥{record['price']:<9} {record.get('title', '')[:30]}")


async def search_and_monitor(args):
    """搜索商品并批量添加监控"""
    keyword = args.keyword
    source = int(args.source)
    target_price = float(args.target_price) if args.target_price else None
    group_name = args.group or ""
    limit = int(args.limit) if args.limit else 10

    source_name = SOURCE_NAMES.get(source, f"平台{source}")

    print(f"🔍 正在搜索 \"{keyword}\"({source_name})...\n")

    results = await search_goods(keyword, source, limit)

    if not results:
        print(f"❌ 未找到相关商品")
        return

    print(f"✅ 找到 {len(results)} 个商品:\n")
    print(f"{'序号':<4} {'名称':<30} {'当前价':<10} {'目标价':<10}")
    print("-" * 70)

    for i, item in enumerate(results, 1):
        name = item['title'][:28] + ".." if len(item['title']) > 30 else item['title']
        target_str = f"¥{target_price}" if target_price else "-"
        print(f"{i:<4} {name:<30} ¥{item['actualPrice']:<9} {target_str:<10}")

    print(f"\n是否批量添加监控?")
    print(f"  [a] 添加全部 ({len(results)} 个)")
    print(f"  [s] 选择性添加")
    print(f"  [n] 取消")

    loop = asyncio.get_event_loop()
    choice = await loop.run_in_executor(None, lambda: input("\n请选择 (a/s/n): "))
    choice = choice.strip().lower()

    if choice == 'n':
        print("已取消")
        return

    added_count = 0

    if choice == 'a':
        for item in results:
            monitor_id = add_monitor_sync(str(item['goods_id']), source, item['title'][:50], target_price, group_name)
            if monitor_id:
                added_count += 1

        print(f"\n✅ 已批量添加 {added_count} 个监控商品!")

    elif choice == 's':
        print(f"\n请输入要添加的序号(用逗号分隔,如:1,3,5):")
        try:
            loop = asyncio.get_event_loop()
            indices = await loop.run_in_executor(None, lambda: input("> "))
            indices = indices.strip()
            if not indices:
                print("未输入序号,已取消")
                return

            selected = [int(x.strip()) - 1 for x in indices.split(",")]
            selected = [i for i in selected if 0 <= i < len(results)]

            if not selected:
                print("未选择有效序号,已取消")
                return

            for idx in selected:
                item = results[idx]
                add_monitor_sync(str(item['goods_id']), source, item['title'][:50], target_price, group_name)
                added_count += 1

            print(f"\n✅ 已添加 {added_count} 个监控商品!")

        except (ValueError, IndexError) as e:
            print(f"输入错误：{e}")
            return
        except Exception as e:
            print(f"未知错误：{type(e).__name__}: {e}")
            return

    print(f"\n使用 'uv run scripts/main.py list' 查看监控列表")
    print(f"使用 'uv run scripts/main.py check --all' 检查价格")


async def config_monitor(args):
    """配置监控参数。无参数时仅显示当前配置。"""
    config = load_config()

    has_changes = False

    if args.interval:
        config["check_interval_minutes"] = int(args.interval)
        print(f"✅ 检查间隔已设置为 {args.interval} 分钟")
        has_changes = True

    if args.threshold:
        new_threshold = float(args.threshold)
        config["price_change_threshold"] = new_threshold
        print(f"✅ 价格变化阈值已设置为 {new_threshold*100:.0f}%")
        has_changes = True

    if args.cache_ttl:
        config["cache_ttl_seconds"] = int(args.cache_ttl)
        print(f"✅ API 缓存时间已设置为 {args.cache_ttl} 秒")
        has_changes = True

    # 通知渠道配置
    if args.notify_channel:
        config["notify_channel"] = args.notify_channel
        print(f"✅ 通知渠道已设置为:{args.notify_channel}")
        has_changes = True

    if args.notify_webhook_url is not None:
        config["notify_webhook_url"] = args.notify_webhook_url
        if args.notify_webhook_url:
            print(f"✅ Webhook URL 已设置")
        else:
            print(f"✅ Webhook URL 已清除")
        has_changes = True

    if args.notify_email_smtp is not None:
        config["notify_email_smtp"] = args.notify_email_smtp
        print(f"✅ SMTP 服务器已设置" if args.notify_email_smtp else f"✅ SMTP 服务器已清除")
        has_changes = True

    if args.notify_email_from is not None:
        config["notify_email_from"] = args.notify_email_from
        print(f"✅ 发件人邮箱已设置" if args.notify_email_from else f"✅ 发件人邮箱已清除")
        has_changes = True

    if args.notify_email_to is not None:
        config["notify_email_to"] = args.notify_email_to
        print(f"✅ 收件人邮箱已设置" if args.notify_email_to else f"✅ 收件人邮箱已清除")
        has_changes = True

    if args.notify_email_password is not None:
        config["notify_email_password"] = args.notify_email_password
        print(f"✅ 邮箱密码已设置" if args.notify_email_password else f"✅ 邮箱密码已清除")
        has_changes = True

    if args.anomaly_threshold is not None:
        config["anomaly_threshold"] = float(args.anomaly_threshold)
        print(f"✅ 异常检测阈值已设置为 {args.anomaly_threshold*100:.0f}%")
        has_changes = True

    if args.anomaly_trend_count is not None:
        config["anomaly_trend_count"] = int(args.anomaly_trend_count)
        print(f"✅ 连续趋势检测次数已设置为 {args.anomaly_trend_count} 次")
        has_changes = True

    if args.invite_code is not None:
        config["invite_code"] = args.invite_code
        if args.invite_code:
            print(f"✅ 邀请码已设置")
        else:
            print(f"✅ 邀请码已清除")
        has_changes = True

    if has_changes:
        save_config(config)
    else:
        print("💡 使用 --interval/--threshold/--cache-ttl 等参数修改配置")
        print("")

    print(f"\n当前配置:")
    print(f"   检查间隔:{config['check_interval_minutes']} 分钟")
    print(f"   变化阈值:{config['price_change_threshold']*100:.0f}%")
    print(f"   API 缓存:{config.get('cache_ttl_seconds', CACHE_TTL_SECONDS)} 秒")
    print(f"   自动通知:{'开启' if config['auto_notify'] else '关闭'}")
    print(f"   通知渠道:{config.get('notify_channel', 'json')}")
    if config.get('notify_webhook_url'):
        print(f"   Webhook URL:{config['notify_webhook_url']}")
    if config.get('notify_email_smtp'):
        print(f"   SMTP:{config['notify_email_smtp']}")
    if config.get('notify_email_from'):
        print(f"   发件人:{config['notify_email_from']}")
    if config.get('notify_email_to'):
        print(f"   收件人:{config['notify_email_to']}")
    if config.get('notify_email_password'):
        print(f"   邮箱密码：{'*' * 8}")
    print(f"   异常检测阈值：{config.get('anomaly_threshold', 0.3)*100:.0f}%")
    print(f"   连续趋势检测次数：{config.get('anomaly_trend_count', 3)} 次")
    invite = config.get('invite_code', '')
    if invite:
        print(f"   邀请码：{invite[:4]}{'*' * (len(invite) - 4) if len(invite) > 4 else ''}")
    else:
        print(f"   邀请码：未设置")


async def show_stats(args):
    """显示省钱统计"""
    monitors = list_monitors_sync()

    if not monitors:
        print("📭 暂无监控数据")
        return

    conn = get_db()
    total_saved = 0
    total_original = 0
    deals_count = 0

    print("📊 省钱统计\n")
    print(f"{'商品':<25} {'最高价':<10} {'现价':<10} {'节省':<10} {'状态'}")
    print("-" * 70)

    for m in monitors:
        if not m.get("enabled", 1):
            continue

        last_price = m.get("last_price")

        if last_price:
            # 查询最高价
            cursor = conn.execute(
                "SELECT MAX(price) as max_price FROM price_history WHERE monitor_id = ?",
                (m["id"],)
            )
            row = cursor.fetchone()
            max_price = row["max_price"] if row and row["max_price"] else last_price

            saved = max_price - last_price

            if saved > 0:
                deals_count += 1
                total_saved += saved
                total_original += max_price

                name = m['name'][:23] + ".." if len(m['name'] or "") > 25 else (m['name'] or "未知")
                print(f"{name:<25} ¥{max_price:<9.0f} ¥{last_price:<9.0f} ¥{saved:<9.0f} ✅")

    print("-" * 70)
    print(f"\n📈 总计:")
    print(f"   监控商品:{len(monitors)} 个")
    print(f"   好价商品:{deals_count} 个")
    if total_saved > 0:
        save_pct = (total_saved / total_original * 100) if total_original > 0 else 0
        print(f"   累计节省:¥{total_saved:.0f} ({save_pct:.0f}%)")
        print(f"\n💡 继续监控,省更多!")
    else:
        print(f"   累计节省:暂无数据(持续监控中...)")


async def group(args):
    """分组管理主函数"""
    if not hasattr(args, 'group_cmd') or not args.group_cmd:
        # 无子命令,显示所有分组
        await group_list(args)
        return

    group_cmd = args.group_cmd

    if group_cmd == "add":
        await group_add(args)
    elif group_cmd == "remove":
        await group_remove(args)
    elif group_cmd == "list":
        await group_list(args)
    elif group_cmd == "show":
        await group_show(args)
    elif group_cmd == "delete":
        await group_delete(args)
    else:
        print(f"❌ 未知分组命令: {group_cmd}")
        print("可用命令: add, remove, list, show, delete")


async def group_add(args):
    """添加商品到分组"""
    conn = get_db()
    conn.execute(
        "UPDATE monitors SET group_name = ? WHERE id = ?",
        (args.name, int(args.id))
    )
    conn.commit()
    print(f"✅ 已将监控 #{args.id} 添加到分组 '{args.name}'")


async def group_remove(args):
    """将商品从分组中移除"""
    conn = get_db()
    conn.execute(
        "UPDATE monitors SET group_name = '' WHERE id = ?",
        (int(args.id),)
    )
    conn.commit()
    print(f"✅ 已从分组中移除监控 #{args.id}")


async def group_list(args):
    """列出所有分组"""
    monitors = list_monitors_sync()

    if not monitors:
        print("📭 暂无监控数据")
        return

    groups = {}
    for m in monitors:
        group_name = m.get("group_name") or "未分组"
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(m)

    print(f"📦 商品分组 (共 {len(groups)} 个)\n")

    for name, items in groups.items():
        if name == "未分组":
            print(f"  📭 {name}: {len(items)} 个商品")
        else:
            print(f"  📁 {name}: {len(items)} 个商品")
            for item in items:
                print(f"      - #{item['id']} {item['name']} (¥{item.get('last_price', 'N/A')})")
        print()


async def group_show(args):
    """查看指定分组"""
    monitors = list_monitors_sync()

    if not monitors:
        print("📭 暂无监控数据")
        return

    group_monitors = [m for m in monitors if (m.get("group_name") or "") == args.name]

    if not group_monitors:
        print(f"📭 分组 '{args.name}' 为空")
        return

    print(f"📁 分组 '{args.name}' ({len(group_monitors)} 个商品)\n")
    print(f"{'ID':<4} {'名称':<20} {'平台':<8} {'当前价':<10} {'目标价':<10}")
    print("-" * 60)

    source_names = SOURCE_NAMES

    for m in group_monitors:
        price_str = f"¥{m.get('last_price', 'N/A')}" if m.get('last_price') else "N/A"
        target_str = f"¥{m['target_price']}" if m.get('target_price') else "-"
        name = m['name'][:18] + ".." if len(m['name']) > 20 else (m['name'] or "未知")
        print(f"{m['id']:<4} {name:<20} {source_names.get(m['source'], '未知'):<8} {price_str:<10} {target_str:<10}")


async def group_delete(args):
    """删除分组(将组内商品移到未分组)"""
    conn = get_db()
    conn.execute(
        "UPDATE monitors SET group_name = '' WHERE group_name = ?",
        (args.name,)
    )
    conn.commit()
    print(f"✅ 已删除分组 '{args.name}',商品已移到未分组")


async def export_history(args):
    """导出价格历史为 CSV/Excel"""
    monitor_id = getattr(args, "id", None)
    export_all = getattr(args, "all", False)
    fmt = getattr(args, "format", "csv").lower()
    days = getattr(args, "days", 90)
    output_dir = getattr(args, "output", None)

    if monitor_id and export_all:
        print("❌ --id 和 --all 互斥,请使用其中一个")
        return
    if not monitor_id and not export_all:
        print("❌ 请指定 --id=监控ID 或 --all")
        return

    if output_dir:
        out_dir = Path(output_dir)
        if not out_dir.is_absolute():
            out_dir = EXPORTS_DIR / out_dir
    else:
        out_dir = EXPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "xlsx":
        try:
            import openpyxl
            use_xlsx = True
        except ImportError:
            print("⚠️ openpyxl 未安装,降级为 CSV 格式")
            print("   安装方法: pip install openpyxl")
            fmt = "csv"
            use_xlsx = False
    else:
        use_xlsx = False

    if export_all:
        await _export_all_history(fmt, days, out_dir, use_xlsx)
    else:
        await _export_single_history(int(monitor_id), fmt, days, out_dir, use_xlsx)


async def _export_single_history(monitor_id: int, fmt: str, days: int, out_dir: Path, use_xlsx: bool):
    """导出单个商品的价格历史"""
    conn = get_db()

    # 获取商品名称
    cursor = conn.execute("SELECT name, goods_id, source FROM monitors WHERE id = ?", (monitor_id,))
    row = cursor.fetchone()
    if not row:
        print(f"❌ 未找到监控 #{monitor_id}")
        return
    name = row["name"] or f"商品{row['goods_id']}"
    goods_id = row["goods_id"]
    source_name = _source_to_name(row["source"])

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # 查询价格历史
    cursor = conn.execute(
        """SELECT price, original_price, title, url, timestamp, is_change_point
           FROM price_history
           WHERE monitor_id = ? AND timestamp > ?
           ORDER BY timestamp ASC""",
        (monitor_id, cutoff)
    )
    records = [dict(r) for r in cursor.fetchall()]

    # 输出统计
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"📊 导出价格历史 - {name}")
    print(f"📅 时间范围：最近 {days} 天")
    print(f"📄 导出格式：{fmt.upper()}")
    print()

    if not records:
        print(f"📭 {name} 近 {days} 天内无价格记录")
        return

    if use_xlsx:
        ext = "xlsx"
        out_path = out_dir / f"history_{goods_id}_{date_str}.{ext}"
        _write_xlsx_single(out_path, records, source_name)
    else:
        ext = "csv"
        out_path = out_dir / f"history_{goods_id}_{date_str}.{ext}"
        _write_csv_single(out_path, records, source_name)

    file_size = out_path.stat().st_size
    size_str = f"{file_size / 1024:.1f} KB" if file_size >= 1024 else f"{file_size} B"
    change_count = sum(1 for r in records if r.get("is_change_point", 1))
    print(f"✅ 已导出 {len(records)} 条价格记录（含 {change_count} 个变化点）")
    print(f"📁 文件：{out_path}")
    print(f"📦 文件大小：{size_str}")


async def _export_all_history(fmt: str, days: int, out_dir: Path, use_xlsx: bool):
    """导出所有商品的价格历史"""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    monitors = conn.execute("SELECT * FROM monitors WHERE enabled = 1 ORDER BY id").fetchall()
    if not monitors:
        print("📭 暂无启用的监控商品")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"📊 导出全部价格历史")
    print(f"📅 时间范围：最近 {days} 天")
    print(f"📄 导出格式：{fmt.upper()}")
    print(f"📦 共 {len(monitors)} 个商品")
    print()

    summary_rows = []
    total_records = 0

    for m in monitors:
        mid = m["id"]
        goods_id = m["goods_id"]
        name = m["name"] or f"商品{goods_id}"
        source_name = _source_to_name(m["source"])

        cursor = conn.execute(
            """SELECT price, original_price, title, url, timestamp, is_change_point
               FROM price_history
               WHERE monitor_id = ? AND timestamp > ?
               ORDER BY timestamp ASC""",
            (mid, cutoff)
        )
        records = [dict(r) for r in cursor.fetchall()]

        # 汇总信息：最新价格
        if records:
            latest = records[-1]
            summary_rows.append({
                "ID": mid,
                "商品ID": goods_id,
                "名称": name,
                "平台": source_name,
                "最新价格": latest["price"],
                "原价": latest.get("original_price") or "",
                "记录数": len(records),
                "最新时间": latest["timestamp"].replace("T", " ")[:19],
            })
        else:
            summary_rows.append({
                "ID": mid,
                "商品ID": goods_id,
                "名称": name,
                "平台": source_name,
                "最新价格": m.get("last_price") or "",
                "原价": "",
                "记录数": 0,
                "最新时间": "",
            })

        if not records:
            continue

        # 每个商品一个文件
        if use_xlsx:
            ext = "xlsx"
            out_path = out_dir / f"history_{goods_id}_{date_str}.{ext}"
            _write_xlsx_single(out_path, records, source_name)
        else:
            ext = "csv"
            out_path = out_dir / f"history_{goods_id}_{date_str}.{ext}"
            _write_csv_single(out_path, records, source_name)

        total_records += len(records)
        print(f"  ✅ {name}: {len(records)} 条记录")

    # 生成汇总文件（始终用 CSV，简单可靠）
    summary_path = out_dir / f"summary_{date_str}.csv"
    _write_csv_summary(summary_path, summary_rows)

    summary_size = summary_path.stat().st_size
    summary_size_str = f"{summary_size / 1024:.1f} KB" if summary_size >= 1024 else f"{summary_size} B"
    print(f"\n✅ 总计：{total_records} 条价格记录")
    print(f"📁 汇总文件：{summary_path}")
    print(f"📦 汇总文件大小：{summary_size_str}")


def _write_csv_single(out_path: Path, records: List[Dict], source_name: str):
    """写入单个商品的 CSV 文件"""
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日期", "价格", "原价", "商品名", "平台", "URL", "是否变化点"])
        for r in records:
            writer.writerow([
                r["timestamp"].replace("T", " ")[:19],
                r["price"],
                r.get("original_price") or "",
                r.get("title") or "",
                source_name,
                r.get("url") or "",
                "是" if r.get("is_change_point", 1) else "否",
            ])


def _write_xlsx_single(out_path: Path, records: List[Dict], source_name: str):
    """写入单个商品的 Excel 文件"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "价格历史"
    ws.append(["日期", "价格", "原价", "商品名", "平台", "URL", "是否变化点"])
    for r in records:
        ws.append([
            r["timestamp"].replace("T", " ")[:19],
            r["price"],
            r.get("original_price") or "",
            r.get("title") or "",
            source_name,
            r.get("url") or "",
            "是" if r.get("is_change_point", 1) else "否",
        ])
    wb.save(str(out_path))


def _write_csv_summary(out_path: Path, rows: List[Dict]):
    """写入汇总 CSV 文件"""
    summary_cols = ["ID", "商品ID", "名称", "平台", "最新价格", "原价", "记录数", "最新时间"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_cols)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


async def cleanup(args):
    """清理旧数据和缓存"""
    config = load_config()

    print("🧹 开始清理...\n")

    # 清理旧历史
    cleanup_old_history(config.get("history_retention_days", 30))

    # 清理过期缓存
    cache = load_api_cache()
    cache_ttl = config.get("cache_ttl_seconds", CACHE_TTL_SECONDS)
    original_count = len(cache)
    cache = {k: v for k, v in cache.items()
             if (datetime.now() - datetime.fromisoformat(v["timestamp"])).total_seconds() < cache_ttl}
    if len(cache) < original_count:
        save_api_cache(cache)
        print(f"🗑️ 已清理 {original_count - len(cache)} 条过期缓存")

    # 数据库优化
    conn = get_db()
    conn.execute("VACUUM")
    conn.commit()
    print("🗄️ 数据库已优化")

    print("\n✅ 清理完成")


# ──────────────── 导入/导出 ────────────────


CSV_COLUMNS = ["ID", "商品ID", "平台", "名称", "目标价", "分组", "启用状态", "当前价", "创建时间"]


def _source_to_name(source: int) -> str:
    """平台编号 → 中文名称"""
    return SOURCE_NAMES.get(source, f"平台{source}")


def _name_to_source(name: str) -> Optional[int]:
    """中文名称 → 平台编号"""
    for sid, sname in SOURCE_NAMES.items():
        if sname == name:
            return sid
    if name.startswith("平台"):
        try:
            return int(name[2:])
        except ValueError:
            pass
    return None


async def export_monitors(args):
    """导出监控列表到文件"""
    fmt = getattr(args, "format", "json").lower()
    file_path = getattr(args, "file", None)

    if fmt not in ("json", "csv"):
        print(f"❌ 不支持的格式:{fmt},请使用 json 或 csv")
        return

    # 获取全部监控(含禁用的)
    conn = get_db()
    all_rows = conn.execute("SELECT * FROM monitors ORDER BY id").fetchall()
    all_monitors = [dict(r) for r in all_rows]

    if not all_monitors:
        print("📭 暂无监控商品可导出")
        return

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if file_path:
        out_path = Path(file_path)
        if not out_path.is_absolute():
            out_path = EXPORTS_DIR / out_path
    else:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "json" if fmt == "json" else "csv"
        out_path = EXPORTS_DIR / f"monitors_{date_str}.{ext}"

    if fmt == "json":
        export_data = []
        for m in all_monitors:
            export_data.append({
                "id": m["id"],
                "goods_id": m["goods_id"],
                "source": m["source"],
                "source_name": _source_to_name(m["source"]),
                "name": m.get("name", ""),
                "target_price": m.get("target_price"),
                "group_name": m.get("group_name", ""),
                "enabled": bool(m.get("enabled", 1)),
                "created_at": m.get("created_at", ""),
                "last_price": m.get("last_price"),
                "last_check": m.get("last_check"),
            })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"monitors": export_data, "exported_at": datetime.now().isoformat()}, f,
                      ensure_ascii=False, indent=2)
    else:
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            for m in all_monitors:
                writer.writerow([
                    m["id"],
                    m["goods_id"],
                    _source_to_name(m["source"]),
                    m.get("name", ""),
                    m.get("target_price") or "",
                    m.get("group_name", ""),
                    "是" if m.get("enabled", 1) else "否",
                    m.get("last_price") or "",
                    m.get("created_at", ""),
                ])

    file_size = out_path.stat().st_size
    size_str = f"{file_size / 1024:.1f} KB" if file_size >= 1024 else f"{file_size} B"
    print(f"✅ 已导出 {len(all_monitors)} 个监控商品")
    print(f"   格式:{fmt.upper()}")
    print(f"   文件:{out_path}")
    print(f"   大小:{size_str}")


async def import_monitors(args):
    """从文件导入监控列表"""
    file_path = getattr(args, "file", None)
    overwrite = getattr(args, "overwrite", False)

    if not file_path:
        print("❌ 请指定导入文件:--file=路径")
        return

    in_path = Path(file_path)
    if not in_path.is_absolute():
        in_path = EXPORTS_DIR / in_path

    if not in_path.exists():
        print(f"❌ 文件不存在:{in_path}")
        return

    ext = in_path.suffix.lower()
    monitors_to_import: List[Dict] = []

    if ext == ".json":
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "monitors" in data:
            monitors_to_import = data["monitors"]
        elif isinstance(data, list):
            monitors_to_import = data
        else:
            print("❌ JSON 格式错误:需要包含 monitors 数组或直接的监控列表数组")
            return
    elif ext == ".csv":
        with open(in_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                source_val = row.get("平台", "").strip()
                source = _name_to_source(source_val)
                if source is None:
                    try:
                        source = int(source_val)
                    except (ValueError, TypeError):
                        print(f"⚠️ 跳过无法识别的平台:{source_val}")
                        continue
                enabled_str = row.get("启用状态", "是").strip()
                enabled = 1 if enabled_str in ("是", "1", "true", "yes", "True", "Yes") else 0
                monitors_to_import.append({
                    "goods_id": row.get("商品ID", "").strip(),
                    "source": source,
                    "name": row.get("名称", "").strip(),
                    "target_price": float(row["目标价"]) if row.get("目标价") and row["目标价"].strip() else None,
                    "group_name": row.get("分组", "").strip(),
                    "enabled": enabled,
                    "created_at": row.get("创建时间", datetime.now().isoformat()).strip(),
                })
    else:
        print(f"❌ 不支持的文件格式:{ext},请使用 .json 或 .csv")
        return

    if not monitors_to_import:
        print("📭 文件中没有可导入的监控数据")
        return

    conn = get_db()
    success = 0
    skipped = 0
    errors = 0

    for m in monitors_to_import:
        goods_id = str(m.get("goods_id", "")).strip()
        source = m.get("source")
        if not goods_id or source is None:
            errors += 1
            continue

        name = m.get("name") or f"商品{goods_id}"
        target_price = m.get("target_price")
        group_name = m.get("group_name", "")
        enabled = m.get("enabled", 1)
        created_at = m.get("created_at", datetime.now().isoformat())
        last_price = m.get("last_price")

        if overwrite:
            # 先查询是否已存在
            cursor = conn.execute(
                "SELECT id FROM monitors WHERE goods_id = ? AND source = ?",
                (goods_id, source)
            )
            existing = cursor.fetchone()

            if existing:
                conn.execute(
                    """UPDATE monitors SET name=?, target_price=?, group_name=?, enabled=?, last_price=?
                       WHERE goods_id = ? AND source = ?""",
                    (name, target_price, group_name, enabled, last_price, goods_id, source)
                )
                success += 1
            else:
                conn.execute(
                    """INSERT INTO monitors (goods_id, source, name, target_price, group_name, created_at, last_price, enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (goods_id, source, name, target_price, group_name, created_at, last_price, enabled)
                )
                success += 1
        else:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO monitors
                   (goods_id, source, name, target_price, group_name, created_at, last_price, enabled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (goods_id, source, name, target_price, group_name, created_at, last_price, enabled)
            )
            if cursor.rowcount > 0:
                success += 1
            else:
                skipped += 1

    conn.commit()

    print(f"✅ 导入完成")
    print(f"   新增:{success} 个")
    if skipped > 0:
        print(f"   跳过(已存在):{skipped} 个")
    if errors > 0:
        print(f"   错误:{errors} 个")
    print(f"   来源:{in_path}")


# ──────────────── Web UI ────────────────


def _build_webui_html() -> str:
    """生成 Web UI 主页面 HTML。"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Price Monitor - Web UI</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;min-height:100vh}
.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.header h1{font-size:1.4rem;font-weight:600}
.header .stats{margin-left:auto;font-size:.85rem;opacity:.9}
.container{max-width:1200px;margin:0 auto;padding:16px}
.filters{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.filters select,.filters input{padding:8px 12px;border:1px solid #ddd;border-radius:8px;background:#fff;font-size:.9rem}
.filters input{width:180px}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.card{background:#fff;border-radius:12px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.08);transition:transform .15s}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.12)}
.card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px}
.card-title{font-weight:600;font-size:1rem;line-height:1.3;flex:1;margin-right:8px}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;font-weight:500}
.badge-normal{background:#e6f7ed;color:#27ae60}
.badge-down{background:#fde8e8;color:#e74c3c}
.badge-up{background:#fff3cd;color:#f39c12}
.card-price{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.current-price{font-size:1.5rem;font-weight:700;color:#333}
.original-price{font-size:.85rem;color:#999;text-decoration:line-through}
.card-meta{display:flex;gap:8px;font-size:.8rem;color:#666;flex-wrap:wrap}
.card-meta span{display:flex;align-items:center;gap:4px}
.card-actions{margin-top:12px;display:flex;gap:8px}
.btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:.8rem;font-weight:500;transition:background .15s}
.btn-sm{padding:4px 10px;font-size:.75rem}
.btn-primary{background:#667eea;color:#fff}
.btn-primary:hover{background:#5568d3}
.btn-danger{background:#e74c3c;color:#fff}
.btn-danger:hover{background:#c0392b}
.btn-secondary{background:#e0e0e0;color:#333}
.btn-secondary:hover{background:#ccc}
.btn-success{background:#27ae60;color:#fff}
.btn-success:hover{background:#219a52}
.modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.5);z-index:100;align-items:center;justify-content:center}
.modal.active{display:flex}
.modal-content{background:#fff;border-radius:12px;padding:24px;max-width:500px;width:90%;max-height:90vh;overflow-y:auto}
.modal-content h2{margin-bottom:16px;font-size:1.2rem}
.form-group{margin-bottom:12px}
.form-group label{display:block;margin-bottom:4px;font-size:.85rem;font-weight:500;color:#555}
.form-group input,.form-group select{width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:.9rem}
.form-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
.chart-container{position:relative;height:300px;margin:16px 0}
.empty-state{text-align:center;padding:60px 20px;color:#999}
.empty-state h2{margin-bottom:8px;color:#666}
.config-section{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.config-section h3{margin-bottom:12px;font-size:1rem}
.config-row{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.config-row label{min-width:180px;font-size:.85rem;color:#555}
.config-row input{flex:1;max-width:300px;padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:.85rem}
.toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:8px;color:#fff;font-size:.9rem;z-index:200;transform:translateY(100px);opacity:0;transition:all .3s}
.toast.show{transform:translateY(0);opacity:1}
.toast-success{background:#27ae60}
.toast-error{background:#e74c3c}
.tab-bar{display:flex;gap:4px;margin-bottom:16px;border-bottom:2px solid #eee}
.tab{padding:10px 20px;cursor:pointer;font-size:.9rem;font-weight:500;color:#666;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .15s}
.tab.active{color:#667eea;border-bottom-color:#667eea}
.tab:hover{color:#333}
.tab-content{display:none}
.tab-content.active{display:block}
@media(max-width:600px){.card-grid{grid-template-columns:1fr}.header{padding:16px}.header h1{font-size:1.1rem}.filters{flex-direction:column}.filters input,.filters select{width:100%}}
</style>
</head>
<body>
<div class="header">
<h1>📊 Price Monitor</h1>
<div class="stats" id="headerStats">加载中...</div>
</div>
<div class="container">
<div class="tab-bar">
<div class="tab active" data-tab="dashboard">仪表盘</div>
<div class="tab" data-tab="add">添加商品</div>
<div class="tab" data-tab="config">配置</div>
</div>

<div class="tab-content active" id="tab-dashboard">
<div class="filters">
<select id="filterPlatform" onchange="applyFilters()">
<option value="">全部平台</option>
<option value="1">淘宝</option>
<option value="2">京东</option>
<option value="3">拼多多</option>
<option value="4">小红书</option>
<option value="5">得物</option>
<option value="6">唯品会</option>
<option value="7">抖音</option>
<option value="8">快手</option>
<option value="9">美团</option>
<option value="10">饿了么</option>
</select>
<select id="filterGroup" onchange="applyFilters()">
<option value="">全部分组</option>
</select>
<input type="text" id="filterSearch" placeholder="🔍 搜索商品..." oninput="applyFilters()">
<button class="btn btn-primary btn-sm" onclick="refreshMonitors()">🔄 刷新</button>
</div>
<div class="card-grid" id="cardGrid"></div>
</div>

<div class="tab-content" id="tab-add">
<div class="config-section">
<h2>添加监控商品</h2>
<div class="form-group">
<label>平台</label>
<select id="addSource">
<option value="1">淘宝</option>
<option value="2">京东</option>
<option value="3">拼多多</option>
<option value="4">小红书</option>
<option value="5">得物</option>
<option value="6">唯品会</option>
<option value="7">抖音</option>
<option value="8">快手</option>
<option value="9">美团</option>
<option value="10">饿了么</option>
</select>
</div>
<div class="form-group">
<label>商品 ID</label>
<input type="text" id="addGoodsId" placeholder="输入商品 ID">
</div>
<div class="form-group">
<label>商品名称</label>
<input type="text" id="addName" placeholder="输入商品名称">
</div>
<div class="form-group">
<label>目标价格（可选）</label>
<input type="number" id="addTargetPrice" placeholder="如：99.9">
</div>
<div class="form-group">
<label>分组（可选）</label>
<input type="text" id="addGroup" placeholder="如：电子产品">
</div>
<div class="form-actions">
<button class="btn btn-secondary" onclick="clearAddForm()">清空</button>
<button class="btn btn-success" onclick="addMonitor()">✅ 添加监控</button>
</div>
</div>
</div>

<div class="tab-content" id="tab-config">
<div class="config-section" id="configForm"></div>
</div>
</div>

<!-- 图表模态框 -->
<div class="modal" id="chartModal">
<div class="modal-content">
<h2 id="chartTitle">价格趋势</h2>
<div class="chart-container"><canvas id="priceChart"></canvas></div>
<div class="form-actions">
<button class="btn btn-secondary" onclick="closeChartModal()">关闭</button>
</div>
</div>
</div>

<div class="toast" id="toast"></div>

<script>
const PLATFORM_NAMES={1:'淘宝',2:'京东',3:'拼多多',4:'小红书',5:'得物',6:'唯品会',7:'抖音',8:'快手',9:'美团',10:'饿了么'};
let allMonitors=[];
let priceChart=null;

// Tab 切换
document.querySelectorAll('.tab').forEach(tab=>{
  tab.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-'+tab.dataset.tab).classList.add('active');
  });
});

async function api(url,method='GET',body=null){
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  const res=await fetch(url,opts);
  if(!res.ok)throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function showToast(msg,type='success'){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='toast toast-'+type+' show';
  setTimeout(()=>t.classList.remove('show'),3000);
}

function getStatus(m){
  if(!m.last_price)return{label:'未知',cls:'badge-normal'};
  if(m.target_price&&m.last_price<=m.target_price)return{label:'🎉 达标',cls:'badge-down'};
  const history=m.history||[];
  if(history.length>=2){
    const last=history[history.length-2]?.price||m.last_price;
    if(m.last_price<last)return{label:'📉 降价',cls:'badge-down'};
    if(m.last_price>last)return{label:'📈 涨价',cls:'badge-up'};
  }
  return{label:'✅ 正常',cls:'badge-normal'};
}

function renderCards(monitors){
  const grid=document.getElementById('cardGrid');
  if(!monitors.length){
    grid.innerHTML='<div class="empty-state"><h2>暂无监控商品</h2><p>点击「添加商品」开始监控</p></div>';
    return;
  }
  grid.innerHTML=monitors.map(m=>{
    const status=getStatus(m);
    const platform=PLATFORM_NAMES[m.source]||'未知';
    const group=m.group_name?`<span>📁 ${m.group_name}</span>`:'';
    const targetStr=m.target_price?`目标:¥${m.target_price}`:'';
    return `<div class="card">
      <div class="card-header">
        <div class="card-title">${m.name||'商品'+m.goods_id}</div>
        <span class="badge ${status.cls}">${status.label}</span>
      </div>
      <div class="card-price">
        <span class="current-price">¥${m.last_price!=null?m.last_price.toFixed(0):'--'}</span>
        ${targetStr?`<span style="font-size:.8rem;color:#667eea">${targetStr}</span>`:''}
      </div>
      <div class="card-meta">
        <span>🏷️ ${platform}</span>
        ${group}
        <span>🕐 ${m.last_check?m.last_check.slice(0,16).replace('T',' '):'未检查'}</span>
      </div>
      <div class="card-actions">
        <button class="btn btn-primary btn-sm" onclick="showChart(${m.id})">📈 趋势</button>
        <button class="btn btn-danger btn-sm" onclick="removeMonitor(${m.id},'${(m.name||'').replace(/'/g,"\\'")}')">🗑️ 删除</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('headerStats').textContent=`共 ${monitors.length} 个商品`;
}

function applyFilters(){
  const platform=document.getElementById('filterPlatform').value;
  const group=document.getElementById('filterGroup').value;
  const search=document.getElementById('filterSearch').value.toLowerCase();
  let filtered=allMonitors;
  if(platform)filtered=filtered.filter(m=>m.source==platform);
  if(group)filtered=filtered.filter(m=>m.group_name===group);
  if(search)filtered=filtered.filter(m=>(m.name||'').toLowerCase().includes(search));
  renderCards(filtered);
}

async function refreshMonitors(){
  try{
    const data=await api('/api/monitors');
    allMonitors=data.monitors||[];
    // 更新分组筛选
    const groups=new Set();
    allMonitors.forEach(m=>{if(m.group_name)groups.add(m.group_name)});
    const groupSel=document.getElementById('filterGroup');
    groupSel.innerHTML='<option value="">全部分组</option>'+Array.from(groups).map(g=>`<option value="${g}">${g}</option>`).join('');
    applyFilters();
  }catch(e){showToast('刷新失败: '+e.message,'error')}
}

async function showChart(id){
  const m=allMonitors.find(x=>x.id===id);
  if(!m)return;
  document.getElementById('chartTitle').textContent=m.name||'商品'+m.goods_id;
  try{
    const data=await api('/api/history/'+id);
    const records=data.history||[];
    const labels=records.map(r=>r.timestamp.slice(0,16).replace('T',' '));
    const prices=records.map(r=>r.price);
    const modal=document.getElementById('chartModal');
    modal.classList.add('active');
    if(priceChart)priceChart.destroy();
    const ctx=document.getElementById('priceChart').getContext('2d');
    priceChart=new Chart(ctx,{
      type:'line',
      data:{labels,datasets:[{label:'价格(¥)',data:prices,borderColor:'#667eea',backgroundColor:'rgba(102,126,234,0.1)',fill:true,tension:.3,pointRadius:3}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true}},scales:{y:{beginAtZero:false,title:{display:true,text:'价格(¥)'}}}}
    });
  }catch(e){showToast('加载趋势失败','error')}
}

function closeChartModal(){document.getElementById('chartModal').classList.remove('active')}

async function addMonitor(){
  const source=document.getElementById('addSource').value;
  const goods_id=document.getElementById('addGoodsId').value.trim();
  const name=document.getElementById('addName').value.trim();
  const target_price=document.getElementById('addTargetPrice').value;
  const group_name=document.getElementById('addGroup').value.trim();
  if(!goods_id){showToast('请输入商品ID','error');return}
  try{
    await api('/api/add','POST',{source:+source,goods_id,name,target_price:target_price?+target_price:null,group_name});
    showToast('添加成功!');
    clearAddForm();
    refreshMonitors();
  }catch(e){showToast('添加失败: '+e.message,'error')}
}

function clearAddForm(){
  ['addGoodsId','addName','addTargetPrice','addGroup'].forEach(id=>document.getElementById(id).value='');
}

async function removeMonitor(id,name){
  if(!confirm(`确定删除「${name}」?`))return;
  try{
    await api('/api/remove/'+id,'DELETE');
    showToast('已删除');
    refreshMonitors();
  }catch(e){showToast('删除失败','error')}
}

async function loadConfig(){
  try{
    const config=await api('/api/config');
    const rows=[
      ['检查间隔(分钟)','check_interval_minutes',config.check_interval_minutes,'number'],
      ['价格变化阈值(%)','price_change_threshold',config.price_change_threshold*100,'number'],
      ['自动通知','auto_notify',config.auto_notify?'开启':'关闭','text'],
      ['API缓存(秒)','cache_ttl_seconds',config.cache_ttl_seconds,'number'],
      ['通知渠道','notify_channel',config.notify_channel,'text'],
      ['历史保留(天)','history_retention_days',config.history_retention_days,'number'],
    ];
    let html='<h3>⚙️ 当前配置</h3>';
    rows.forEach(([label,key,val,type])=>{
      if(type==='text')html+=`<div class="config-row"><label>${label}</label><span>${val}</span></div>`;
      else html+=`<div class="config-row"><label>${label}</label><input type="${type}" id="cfg_${key}" value="${val}"></div>`;
    });
    html+='<div class="form-actions"><button class="btn btn-primary" onclick="saveConfig()">💾 保存配置</button></div>';
    document.getElementById('configForm').innerHTML=html;
  }catch(e){showToast('加载配置失败','error')}
}

async function saveConfig(){
  const updates={
    check_interval_minutes:+document.getElementById('cfg_check_interval_minutes').value,
    price_change_threshold:+document.getElementById('cfg_price_change_threshold').value/100,
    cache_ttl_seconds:+document.getElementById('cfg_cache_ttl_seconds').value,
    history_retention_days:+document.getElementById('cfg_history_retention_days').value,
  };
  try{
    await api('/api/config','POST',updates);
    showToast('配置已保存');
    loadConfig();
  }catch(e){showToast('保存失败: '+e.message,'error')}
}

// 初始化
refreshMonitors();
loadConfig();
document.getElementById('chartModal').addEventListener('click',e=>{if(e.target.id==='chartModal')closeChartModal()});
</script>
</body>
</html>"""


async def start_webui(args):
    """启动 Web UI 服务器。"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)

    html_page = _build_webui_html()

    class WebUIHandler(BaseHTTPRequestHandler):
        """Web UI HTTP 请求处理器。"""

        def log_message(self, format, *args):
            # 抑制默认日志输出
            pass

        def _send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            return {}

        def do_GET(self):
            path = self.path.split("?")[0]  # 忽略 query params

            if path == "/" or path == "":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_page.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(html_page.encode("utf-8"))
                return

            if path == "/api/monitors":
                try:
                    monitors = list_monitors_sync()
                    # 附加简单历史摘要
                    conn = get_db()
                    result = []
                    for m in monitors:
                        cursor = conn.execute(
                            "SELECT price, timestamp FROM price_history "
                            "WHERE monitor_id = ? ORDER BY timestamp ASC LIMIT 100",
                            (m["id"],)
                        )
                        history = [dict(r) for r in cursor.fetchall()]
                        m["history"] = history
                        result.append(m)
                    self._send_json({"monitors": result, "count": len(result)})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            if path.startswith("/api/history/"):
                try:
                    mid = int(path.split("/")[-1])
                    conn = get_db()
                    cursor = conn.execute(
                        "SELECT price, original_price, timestamp, is_change_point "
                        "FROM price_history WHERE monitor_id = ? ORDER BY timestamp ASC",
                        (mid,)
                    )
                    history = [dict(r) for r in cursor.fetchall()]
                    self._send_json({"monitor_id": mid, "history": history, "count": len(history)})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            if path == "/api/config":
                try:
                    config = load_config()
                    self._send_json(config)
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            # 404
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

        def do_POST(self):
            path = self.path.split("?")[0]

            if path == "/api/add":
                try:
                    body = self._read_body()
                    goods_id = str(body.get("goods_id", "")).strip()
                    source = int(body.get("source", 1))
                    name = body.get("name", f"商品{goods_id}")
                    target_price = body.get("target_price")
                    group_name = body.get("group_name", "")

                    if not goods_id:
                        self._send_json({"error": "商品 ID 不能为空"}, 400)
                        return

                    mid = add_monitor_sync(goods_id, source, name, target_price, group_name)
                    if mid == 0:
                        self._send_json({"error": "该商品已在监控中"}, 409)
                    else:
                        self._send_json({"ok": True, "monitor_id": mid, "name": name})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            if path == "/api/config":
                try:
                    body = self._read_body()
                    config = load_config()
                    for key in ("check_interval_minutes", "price_change_threshold",
                                "cache_ttl_seconds", "history_retention_days",
                                "request_delay_ms", "anomaly_threshold", "anomaly_trend_count",
                                "notify_channel", "notify_webhook_url"):
                        if key in body:
                            config[key] = body[key]
                    save_config(config)
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            self.send_response(405)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Method Not Allowed")

        def do_DELETE(self):
            path = self.path.split("?")[0]

            if path.startswith("/api/remove/"):
                try:
                    mid = int(path.split("/")[-1])
                    conn = get_db()
                    cursor = conn.execute("SELECT name FROM monitors WHERE id = ?", (mid,))
                    row = cursor.fetchone()
                    if not row:
                        self._send_json({"error": f"未找到监控 #{mid}"}, 404)
                        return
                    name = row["name"]
                    conn.execute("DELETE FROM monitors WHERE id = ?", (mid,))
                    conn.execute("DELETE FROM price_history WHERE monitor_id = ?", (mid,))
                    conn.commit()
                    self._send_json({"ok": True, "name": name})
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                return

            self.send_response(405)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Method Not Allowed")

    # 使用 ThreadingHTTPServer 支持并发请求
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer((host, port), WebUIHandler)
    print(f"\nWeb UI 已启动")
    print(f"地址：http://{host}:{port}")
    print(f"按 Ctrl+C 停止\n")

    # 在线程中运行，避免阻塞 asyncio event loop
    import threading
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        while server_thread.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nWeb UI 已停止")
        server.shutdown()


async def run_api_server(args):
    """启动 REST API 服务器"""
    import threading
    from api_server import start_api_server

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8766)
    token = getattr(args, "token", None)

    # 在线程中运行 API 服务器
    server_thread = threading.Thread(target=start_api_server, kwargs={"host": host, "port": port, "token": token}, daemon=True)
    server_thread.start()

    # 保持主线程运行
    try:
        while server_thread.is_alive():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n服务器已停止")


async def main():
    global SESSION

    import atexit

    # 注册 atexit 清理:当进程因 sys.exit、未捕获异常等退出时兜底关闭资源
    atexit.register(_shutdown)

    # 初始化数据库
    init_database()

    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15, sock_connect=5)
    try:
        async with aiohttp.ClientSession(headers=HEADERS, connector=connector, timeout=timeout) as SESSION:
            parser = argparse.ArgumentParser(description="电商价格监控工具(优化版)")
            parsers = parser.add_subparsers()

            # add 命令
            add_parser = parsers.add_parser("add", help="添加监控商品")
            add_parser.add_argument("--source", required=True, help="平台 1:淘宝 2:京东 3:拼多多 4:小红书 5:得物 6:唯品会 7:抖音 8:快手 9:美团 10:饿了么")
            add_parser.add_argument("--id", required=True, help="商品 ID")
            add_parser.add_argument("--name", help="商品名称/备注")
            add_parser.add_argument("--target_price", help="目标价格")
            add_parser.set_defaults(func=add_monitor)

            # list 命令
            list_parser = parsers.add_parser("list", help="查看监控列表")
            list_parser.set_defaults(func=list_monitors)

            # check 命令
            check_parser = parsers.add_parser("check", help="检查价格")
            check_parser.add_argument("--id", type=int, help="监控 ID")
            check_parser.add_argument("--all", action="store_true", help="检查所有")
            check_parser.set_defaults(func=check_all_prices)

            # remove 命令
            remove_parser = parsers.add_parser("remove", help="删除监控")
            remove_parser.add_argument("--id", required=True, help="监控 ID")
            remove_parser.set_defaults(func=remove_monitor)

            # history 命令
            history_parser = parsers.add_parser("history", help="查看价格历史")
            history_parser.add_argument("--id", required=True, help="监控 ID")
            history_parser.set_defaults(func=show_history)

            # search 命令
            search_parser = parsers.add_parser("search", help="搜索商品并批量添加监控")
            search_parser.add_argument("--keyword", required=True, help="搜索关键词")
            search_parser.add_argument("--source", required=True, help="平台 1:淘宝 2:京东 3:拼多多 4:小红书 5:得物 6:唯品会 7:抖音 8:快手 9:美团 10:饿了么")
            search_parser.add_argument("--target_price", help="目标价格")
            search_parser.add_argument("--group", help="分组名称")
            search_parser.add_argument("--limit", type=int, default=10, help="返回结果数量(默认 10)")
            search_parser.set_defaults(func=search_and_monitor)

            # config 命令
            config_parser = parsers.add_parser("config", help="配置参数")
            config_parser.add_argument("--interval", type=int, help="检查间隔 (分钟)")
            config_parser.add_argument("--threshold", type=float, help="价格变化阈值 (0.05 表示 5%%)")
            config_parser.add_argument("--cache-ttl", type=int, help="API 缓存时间 (秒)")
            config_parser.add_argument("--notify-channel", help="通知渠道: json/webhook/email/all(逗号分隔可多选)")
            config_parser.add_argument("--notify-webhook-url", help="Webhook URL")
            config_parser.add_argument("--notify-email-smtp", help="SMTP 服务器地址")
            config_parser.add_argument("--notify-email-from", help="发件人邮箱")
            config_parser.add_argument("--notify-email-to", help="收件人邮箱")
            config_parser.add_argument("--notify-email-password", help="邮箱密码/授权码")
            config_parser.add_argument("--anomaly-threshold", type=float, help="异常检测阈值 (0.3 表示 30%%)")
            config_parser.add_argument("--anomaly-trend-count", type=int, help="连续趋势检测次数 (默认 3)")
            config_parser.add_argument("--invite-code", help="买手 API 邀请码(可选)")
            config_parser.set_defaults(func=config_monitor)

            # stats 命令
            stats_parser = parsers.add_parser("stats", help="查看省钱统计")
            stats_parser.set_defaults(func=show_stats)

            # cleanup 命令
            cleanup_parser = parsers.add_parser("cleanup", help="清理旧数据和缓存")
            cleanup_parser.set_defaults(func=cleanup)

            # low-price 命令
            lowprice_parser = parsers.add_parser("low-price", help="查看历史低价商品排名")
            lowprice_parser.add_argument("--top", type=int, default=10, help="显示数量(默认 10)")
            lowprice_parser.add_argument("--days", type=int, default=30, help="查询天数(默认 30)")
            lowprice_parser.set_defaults(func=show_low_price)

            # compare 命令
            compare_parser = parsers.add_parser("compare", help="多源比价")
            compare_parser.add_argument("--id", required=True, help="商品 ID")
            compare_parser.add_argument("--sources", required=True, help="平台列表,逗号分隔 (如 1,2,3)")
            compare_parser.set_defaults(func=compare_goods)

            # trend 命令
            trend_parser = parsers.add_parser("trend", help="查看价格趋势图")
            trend_parser.add_argument("--id", required=True, help="监控 ID")
            trend_parser.add_argument("--days", type=int, default=30, help="查询天数(默认 30)")
            trend_parser.set_defaults(func=show_trend)

            # predict 命令
            predict_parser = parsers.add_parser("predict", help="价格预测（线性回归）")
            predict_parser.add_argument("--id", required=True, type=int, help="监控 ID")
            predict_parser.add_argument("--days", type=int, default=30, help="使用最近 N 天数据(默认 30)")
            predict_parser.set_defaults(func=predict_price)

            # group 命令
            group_parser = parsers.add_parser("group", help="商品分组管理")
            group_subparsers = group_parser.add_subparsers()

            group_add_parser = group_subparsers.add_parser("add", help="添加商品到分组")
            group_add_parser.add_argument("--name", required=True, help="分组名称")
            group_add_parser.add_argument("--id", required=True, help="监控 ID")
            group_add_parser.set_defaults(func=group_add)

            group_remove_parser = group_subparsers.add_parser("remove", help="从分组中移除商品")
            group_remove_parser.add_argument("--id", required=True, help="监控 ID")
            group_remove_parser.set_defaults(func=group_remove)

            group_list_parser = group_subparsers.add_parser("list", help="列出所有分组")
            group_list_parser.set_defaults(func=group_list)

            group_show_parser = group_subparsers.add_parser("show", help="查看指定分组")
            group_show_parser.add_argument("--name", required=True, help="分组名称")
            group_show_parser.set_defaults(func=group_show)

            group_delete_parser = group_subparsers.add_parser("delete", help="删除分组")
            group_delete_parser.add_argument("--name", required=True, help="分组名称")
            group_delete_parser.set_defaults(func=group_delete)

            # 让 group 主命令(无子命令时)默认调用 list
            group_parser.set_defaults(func=group_list)

            # 将 group 子命令标记到 args
            group_parser.set_defaults(group_cmd=None)
            group_add_parser.set_defaults(group_cmd="add")
            group_remove_parser.set_defaults(group_cmd="remove")
            group_list_parser.set_defaults(group_cmd="list")
            group_show_parser.set_defaults(group_cmd="show")
            group_delete_parser.set_defaults(group_cmd="delete")

            # export-monitors 命令
            export_parser = parsers.add_parser("export-monitors", help="导出监控列表")
            export_parser.add_argument("--format", default="json", choices=["json", "csv"],
                                       help="导出格式:json 或 csv(默认 json)")
            export_parser.add_argument("--file", help="输出文件路径(默认输出到 data/exports/)")
            export_parser.set_defaults(func=export_monitors)

            # import-monitors 命令
            import_parser = parsers.add_parser("import-monitors", help="导入监控列表")
            import_parser.add_argument("--file", required=True, help="导入文件路径(.json 或 .csv)")
            import_parser.add_argument("--overwrite", action="store_true",
                                       help="覆盖已存在的商品(默认跳过已有)")
            import_parser.set_defaults(func=import_monitors)

            # export-history 命令
            export_history_parser = parsers.add_parser("export-history", help="导出价格历史")
            export_history_parser.add_argument("--id", help="监控 ID（与 --all 互斥）")
            export_history_parser.add_argument("--all", action="store_true", dest="all",
                                               help="导出所有商品")
            export_history_parser.add_argument("--format", default="csv", choices=["csv", "xlsx"],
                                               help="导出格式:csv 或 xlsx（默认 csv）")
            export_history_parser.add_argument("--days", type=int, default=90,
                                               help="导出最近 N 天的数据（默认 90）")
            export_history_parser.add_argument("--output", help="指定输出目录（默认 data/exports/）")
            export_history_parser.set_defaults(func=export_history)

            # webui 命令
            webui_parser = parsers.add_parser("webui", help="启动 Web UI")
            webui_parser.add_argument("--port", type=int, default=8765, help="端口号（默认 8765）")
            webui_parser.add_argument("--host", default="127.0.0.1", help="绑定地址（默认 127.0.0.1）")
            webui_parser.set_defaults(func=start_webui)

            # api-server 命令
            api_server_parser = parsers.add_parser("api-server", help="启动 REST API 服务器")
            api_server_parser.add_argument("--port", type=int, default=8766, help="端口号（默认 8766）")
            api_server_parser.add_argument("--host", default="127.0.0.1", help="绑定地址（默认 127.0.0.1）")
            api_server_parser.add_argument("--token", default=None, help="API 认证 Token（可选）")
            api_server_parser.set_defaults(func=run_api_server)

            args = parser.parse_args()
            if hasattr(args, "func"):
                await args.func(args)
            else:
                parser.print_help()
    finally:
        # 确保退出时 DB_CONN 始终关闭(sync 连接不受 async with 管理)
        if DB_CONN is not None:
            try:
                DB_CONN.close()
            except Exception as e:
                logger.warning("关闭数据库连接失败: %s", e)


if __name__ == "__main__":
    # Windows 下设置 UTF-8 输出
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    asyncio.run(main())
