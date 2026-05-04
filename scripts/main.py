 # /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp"]
# ///
"""
电商价格监控工具 - 优化版
优化策略：
1. API 请求缓存（5 分钟内不重复请求同一商品）
2. 智能存储（只记录价格变化点）
3. 错峰检查（分散请求时间）
4. 自动清理（30 天前的详细数据）
"""
import os
import sys
import json
import asyncio
import aiohttp
import ssl
import argparse
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# 基础目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "price_monitor.db"
CONFIG_FILE = DATA_DIR / "config.json"
CACHE_FILE = DATA_DIR / "api_cache.json"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)

# 买手 API 配置
INVITE_CODE = os.getenv("MAISHOU_INVITE_CODE") or "6110440"
HEADERS = {
    aiohttp.hdrs.ACCEPT: "application/json",
    aiohttp.hdrs.REFERER: "https://hnbc018.kuaizhan.com/",
    aiohttp.hdrs.USER_AGENT: "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

# SSL 配置
SSL_CONTEXT = ssl.create_default_context()

# 缓存配置
CACHE_TTL_SECONDS = 300  # 5 分钟缓存
REQUEST_DELAY_MS = 200   # 请求间隔 200ms，避免触发限流

SESSION: aiohttp.ClientSession | None = None
DB_CONN: sqlite3.Connection | None = None


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
    
    # 迁移：为已有数据库增加 group_name 字段
    try:
        DB_CONN.execute("ALTER TABLE monitors ADD COLUMN group_name TEXT DEFAULT ''")
        DB_CONN.commit()
    except Exception:
        pass  # 字段已存在
    
    # 价格历史表（只记录变化点）
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
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return {**default_config, **config}
    return default_config


def save_config(config):
    """保存配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_api_cache() -> Dict:
    """加载 API 缓存"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_api_cache(cache: Dict):
    """保存 API 缓存"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


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


def send_notification(title: str, message: str):
    """发送通知到 OpenClaw"""
    config = load_config()
    if not config.get("auto_notify", True):
        return  # 用户关闭了自动通知
    
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
                except:
                    notifications = []
        
        notifications.append(notification)
        notifications = notifications[-50:]
        
        with open(notification_file, "w", encoding="utf-8") as f:
            json.dump(notifications, f, ensure_ascii=False, indent=2)
        
        print(f"🔔 通知已记录：{title}")
    except Exception as e:
        print(f"⚠️ 发送通知失败：{e}")


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
        print(f"🧹 已清理 {cursor.rowcount} 条旧记录（>{days}天）")


def add_monitor_sync(goods_id: str, source: int, name: str, target_price: Optional[float] = None, group_name: str = "") -> int:
    """添加监控（同步）"""
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
    """列出所有监控（同步）"""
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
    """记录价格点（只记录变化点）"""
    conn = get_db()
    conn.execute(
        """INSERT INTO price_history (monitor_id, price, original_price, title, url, timestamp, is_change_point)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (monitor_id, price, original_price, title, url, datetime.now().isoformat(), 1 if is_change else 0)
    )
    conn.commit()


async def search_goods(keyword: str, source: int, limit: int = 10) -> List[Dict]:
    """搜索商品（带缓存）"""
    global SESSION
    
    cache_key = f"search:{source}:{keyword}:{limit}"
    cache = load_api_cache()
    
    if is_cache_valid(cache, cache_key):
        print(f"⚡ 使用缓存：搜索 \"{keyword}\"")
        return cache[cache_key]["data"]
    
    try:
        resp = await SESSION.post(
            "https://appapi.maishou88.com/api/v3/goods/list",
            json={
                "keyword": keyword,
                "sourceType": str(source),
                "inviteCode": INVITE_CODE,
                "supplierCode": "",
                "activityId": "",
                "usageScene": 5,
                "page": 1,
                "pageSize": limit,
            },
            headers=HEADERS,
        )
        data = await resp.json(encoding="utf-8-sig") or {}
        
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
                
                actual_price = float(goods.get("actualPrice") or goods.get("price") or goods.get("actual_price") or 0)
                original_price = float(goods.get("originalPrice") or goods.get("marketPrice") or goods.get("original_price") or actual_price)
                title = goods.get("title") or goods.get("goodsName") or goods.get("name") or "未知商品"
                app_url = goods.get("appUrl") or goods.get("clickUrl") or goods.get("url") or ""
                
                results.append({
                    "goods_id": goods_id,
                    "title": title,
                    "actualPrice": actual_price,
                    "originalPrice": original_price,
                    "appUrl": app_url,
                    "couponPrice": float(goods.get("couponPrice") or goods.get("coupon_price") or 0),
                })
            except Exception as e:
                print(f"解析商品数据失败：{e}")
                continue
        
        # 缓存结果
        cache[cache_key] = {
            "timestamp": datetime.now().isoformat(),
            "data": results,
        }
        save_api_cache(cache)
        
        return results
    except Exception as e:
        print(f"搜索失败：{e}")
        return []


async def get_goods_detail(goods_id: str, source: int) -> Optional[Dict]:
    """获取商品详情（带缓存和限流）"""
    global SESSION
    
    cache_key = get_cache_key(source, goods_id)
    cache = load_api_cache()
    config = load_config()
    
    # 检查缓存
    if is_cache_valid(cache, cache_key, config.get("cache_ttl_seconds", CACHE_TTL_SECONDS)):
        print(f"⚡ 使用缓存：商品 {goods_id}")
        return cache[cache_key]["data"]
    
    params = {
        "goodsId": str(goods_id),
        "sourceType": str(source),
        "inviteCode": INVITE_CODE,
        "supplierCode": "",
        "activityId": "",
        "isShare": "1",
        "token": "",
    }
    
    try:
        # 延迟请求，避免限流
        await asyncio.sleep(config.get("request_delay_ms", REQUEST_DELAY_MS) / 1000)
        
        resp = await SESSION.post(
            "https://appapi.maishou88.com/api/v3/goods/detail",
            json={
                **params,
                "keyword": "",
                "usageScene": 5,
            },
            headers=HEADERS,
        )
        data = await resp.json(encoding="utf-8-sig") or {}
        detail = data.get("data") or {}
        
        resp = await SESSION.post(
            "https://msapi.maishou88.com/api/v1/share/getTargetUrl",
            json={
                **params,
                "isDirectDetail": 0,
            },
            headers=HEADERS,
        )
        data = await resp.json(encoding="utf-8-sig") or {}
        info = data.get("data") or {}
        
        if not info:
            return None
        
        result = {
            "title": detail.get("title", ""),
            "actualPrice": float(detail.get("actualPrice", 0)),
            "originalPrice": float(detail.get("originalPrice", 0)),
            "couponPrice": float(detail.get("couponPrice", 0)),
            "appUrl": info.get("appUrl") or info.get("schemaUrl"),
        }
        
        # 缓存结果
        cache[cache_key] = {
            "timestamp": datetime.now().isoformat(),
            "data": result,
        }
        save_api_cache(cache)
        
        return result
    except Exception as e:
        print(f"获取商品详情失败：{e}")
        return None


# 平台名称映射
SOURCE_NAMES = {1: "淘宝", 2: "京东", 3: "拼多多", 7: "抖音", 8: "快手"}


async def compare_goods(args):
    """多源比价：同时查询多个平台的同一商品"""
    source_ids = [int(x.strip()) for x in args.sources.split(",")]
    goods_id = args.id
    
    if len(source_ids) < 2:
        print("❌ 多源比价至少需要 2 个平台")
        return
    
    print(f"🔍 正在比价：商品 {goods_id}\n")
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
    print(f"📊 比价结果（共 {len(results)} 个平台）：\n")
    
    # 排序：最低价在前
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
            print(f"   {'':<10} 链接：{r['url'][:60]}...")
    
    print(f"\n💰 价差：¥{max_price - min_price:.0f}（{save_pct:.1f}%）")
    print(f"💡 建议：选择最低价平台可节省 ¥{max_price - min_price:.0f}！")


async def show_trend(args):
    """展示商品价格历史趋势图（ASCII字符画）"""
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
        print(f"📭 监控 {name} 近 {days} 天内数据不足，需要至少 2 个价格点")
        return
    
    prices = [r["price"] for r in records]
    timestamps = [r["timestamp"] for r in records]
    
    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / len(prices)
    
    # 如果价格范围太小，自动扩展显示范围
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
    
    # 连接相邻点（用竖线和斜线）
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
    
    print(f"📈 {name} 价格趋势（最近 {days} 天）\n")
    
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
    print(f"\n📊 统计：")
    print(f"   📈 最高价：¥{max_price:.0f}（{max(prices)}）")
    print(f"   📉 最低价：¥{min_price:.0f}（{min(prices)}）")
    print(f"   📊 平均价：¥{avg_price:.0f}（{prices}）")
    
    first_change = (prices[-1] - prices[0]) / prices[0] * 100
    print(f"   📈 期间变化：{first_change:+.1f}%")
    
    # 趋势判断
    if len(prices) >= 3:
        # 简单趋势判断：后半段均值 vs 前半段均值
        mid = len(prices) // 2
        first_half_avg = sum(prices[:mid]) / mid
        second_half_avg = sum(prices[mid:]) / (len(prices) - mid)
        trend_pct = (second_half_avg - first_half_avg) / first_half_avg * 100
        
        if trend_pct < -2:
            print(f"   \U0001F4C9 趋势：降价中（-{abs(trend_pct):.1f}%）")
        elif trend_pct > 2:
            print(f"   \U0001F4C8 趋势：涨价中（+{trend_pct:.1f}%）")
        else:
            print(f"   ↔️ 趋势：平稳（±{abs(trend_pct):.1f}%）")


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
        
        # 计算距离最高价的百分比（推荐度）
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
        
        # 推荐度：距离历史低价越近越值得
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
    
    print(f"🏆 历史低价商品排名（最近 {days} 天）\n")
    print(f"{'':<4} {'商品':<20} {'平台':<6} {'当前价':<10} {'历史低价':<10} {'距低':<8} {'推荐度'}")
    print("-" * 75)
    
    for i, r in enumerate(results, 1):
        pct_str = f"{r['pct']:+.1f}%" if r['pct'] > 0 else "✅"
        stars = "⭐" * r["score"] + "☆" * (5 - r["score"])
        name = r["name"][:18] if len(r["name"]) > 18 else r["name"]
        
        print(f"{i:<4} {name:<20} {r['source']:<6} ¥{r['current']:<9.0f} ¥{r['low']:<9.0f} {pct_str:<8} {stars}")
    
    print(f"\n💡 显示 Top {len(results)} 个商品，推荐度越高分值越低越值得买！")


async def add_monitor(args):
    """添加监控商品"""
    monitor_id = add_monitor_sync(args.id, int(args.source), args.name or f"商品{args.id}", 
                                   float(args.target_price) if args.target_price else None, "")
    
    if monitor_id == 0:
        print(f"⚠️ 该商品已在监控中")
        return
    
    print(f"✅ 已添加监控 #{monitor_id}: {args.name or f'商品{args.id}'}")
    print(f"   商品 ID: {args.id}")
    print(f"   平台：{args.source}")
    if args.target_price:
        print(f"   目标价：¥{args.target_price}")
    
    print("\n正在获取当前价格...")
    await check_single_price(monitor_id)


async def list_monitors(args):
    """查看监控列表"""
    monitors = list_monitors_sync()
    config = load_config()
    
    if not monitors:
        print("📭 暂无监控商品")
        print("\n添加监控：uv run scripts/main.py add --source=1 --id=商品 ID --name=名称 --target_price=目标价")
        return
    
    print(f"📊 监控列表 (共 {len(monitors)} 个商品，检查间隔：{config['check_interval_minutes']}分钟)\n")
    print(f"{'ID':<4} {'名称':<20} {'平台':<8} {'当前价':<10} {'目标价':<10} {'状态':<8}")
    print("-" * 70)
    
    source_names = {1: "淘宝", 2: "京东", 3: "拼多多", 7: "抖音", 8: "快手"}
    
    for m in monitors:
        price_str = f"¥{m.get('last_price', 'N/A')}" if m.get('last_price') else "N/A"
        target_str = f"¥{m['target_price']}" if m.get('target_price') else "-"
        status = "✅" if m.get('enabled', 1) else "⏸️"
        name = m['name'][:18] + ".." if len(m['name']) > 20 else (m['name'] or "未知")
        print(f"{m['id']:<4} {name:<20} {source_names.get(m['source'], '未知'):<8} {price_str:<10} {target_str:<10} {status:<8}")


async def check_single_price(monitor_id: int):
    """检查单个商品价格"""
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
    
    # 只记录价格变化点（节省存储空间）
    is_change = False
    if last_price and last_price > 0:
        change_ratio = abs(current_price - last_price) / last_price
        config = load_config()
        threshold = config.get("price_change_threshold", 0.01)
        if change_ratio >= threshold:
            is_change = True
            record_price_point(monitor_id, current_price, detail["originalPrice"],
                              detail.get("title", ""), detail.get("appUrl", ""), True)
            print(f"   价格变化点：{change_ratio*100:+.1f}%")
        else:
            print(f"   价格无变化（{change_ratio*100:.1f}% < 阈值 {threshold*100:.0f}%），跳过记录")
    else:
        # 首次监控，无历史价格，记录初始值
        is_change = True
        record_price_point(monitor_id, current_price, detail["originalPrice"],
                          detail.get("title", ""), detail.get("appUrl", ""), True)
    
    # 检查价格变化
    config = load_config()
    change_notify = False
    change_msg = ""
    
    if last_price:
        change_pct = (current_price - last_price) / last_price
        if abs(change_pct) >= config["price_change_threshold"]:
            change_notify = True
            direction = "📈" if change_pct > 0 else "📉"
            change_msg = f"{direction} 价格变化：¥{last_price} → ¥{current_price} ({change_pct:+.1%})"
    
    # 检查目标价
    target_notify = False
    if monitor.get("target_price") and current_price <= monitor["target_price"]:
        target_notify = True
    
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
            f"{change_msg}\n当前价：¥{current_price}\n链接：{detail.get('appUrl', 'N/A')}"
        )
    
    if target_notify:
        print(f"   🎉 已达到目标价 ¥{monitor['target_price']}!")
        send_notification(
            f"🎉 目标价达成：{monitor['name']}",
            f"当前价：¥{current_price} ≤ 目标价：¥{monitor['target_price']}\n链接：{detail.get('appUrl', 'N/A')}"
        )
    
    return {
        "monitor_id": monitor_id,
        "name": monitor["name"],
        "current_price": current_price,
        "last_price": last_price,
        "change_notify": change_notify,
        "target_notify": target_notify,
    }


async def check_all_prices(args):
    """检查所有商品价格（错峰检查）"""
    monitors = list_monitors_sync()
    
    if not monitors:
        print("📭 暂无启用的监控商品")
        return
    
    print(f"🔍 正在检查 {len(monitors)} 个商品价格...\n")
    
    results = []
    for i, monitor in enumerate(monitors):
        # 错峰：每个请求间隔 200ms
        if i > 0:
            await asyncio.sleep(0.2)
        
        result = await check_single_price(monitor["id"])
        if result:
            results.append(result)
    
    # 汇总通知
    notify_count = sum(1 for r in results if r.get("change_notify") or r.get("target_notify"))
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
    limit = int(args.limit) if args.limit else 10
    
    source_names = {1: "淘宝", 2: "京东", 3: "拼多多", 7: "抖音", 8: "快手"}
    source_name = source_names.get(source, f"平台{source}")
    
    print(f"🔍 正在搜索 \"{keyword}\"（{source_name}）...\n")
    
    results = await search_goods(keyword, source, limit)
    
    if not results:
        print(f"❌ 未找到相关商品")
        return
    
    print(f"✅ 找到 {len(results)} 个商品：\n")
    print(f"{'序号':<4} {'名称':<30} {'当前价':<10} {'目标价':<10}")
    print("-" * 70)
    
    for i, item in enumerate(results, 1):
        name = item['title'][:28] + ".." if len(item['title']) > 30 else item['title']
        target_str = f"¥{target_price}" if target_price else "-"
        print(f"{i:<4} {name:<30} ¥{item['actualPrice']:<9} {target_str:<10}")
    
    print(f"\n是否批量添加监控？")
    print(f"  [a] 添加全部 ({len(results)} 个)")
    print(f"  [s] 选择性添加")
    print(f"  [n] 取消")
    
    choice = input("\n请选择 (a/s/n): ").strip().lower()
    
    if choice == 'n':
        print("已取消")
        return
    
    added_count = 0
    
    if choice == 'a':
        for item in results:
            monitor_id = add_monitor_sync(str(item['goods_id']), source, item['title'][:50], target_price, "")
            if monitor_id:
                added_count += 1
        
        print(f"\n✅ 已批量添加 {added_count} 个监控商品！")
        
    elif choice == 's':
        print(f"\n请输入要添加的序号（用逗号分隔，如：1,3,5）：")
        try:
            indices = input("> ").strip()
            if not indices:
                print("未输入序号，已取消")
                return
            
            selected = [int(x.strip()) - 1 for x in indices.split(",")]
            selected = [i for i in selected if 0 <= i < len(results)]
            
            if not selected:
                print("未选择有效序号，已取消")
                return
            
            for idx in selected:
                item = results[idx]
                add_monitor_sync(str(item['goods_id']), source, item['title'][:50], target_price, "")
                added_count += 1
            
            print(f"\n✅ 已添加 {added_count} 个监控商品！")
            
        except Exception as e:
            print(f"输入错误：{e}")
            return
    
    print(f"\n使用 'uv run scripts/main.py list' 查看监控列表")
    print(f"使用 'uv run scripts/main.py check --all' 检查价格")


async def config_monitor(args):
    """配置监控参数"""
    config = load_config()
    
    if args.interval:
        config["check_interval_minutes"] = int(args.interval)
        print(f"✅ 检查间隔已设置为 {args.interval} 分钟")
    
    if args.threshold:
        new_threshold = float(args.threshold)
        config["price_change_threshold"] = new_threshold
        print(f"✅ 价格变化阈值已设置为 {new_threshold*100:.0f}%")
    
    if args.cache_ttl:
        config["cache_ttl_seconds"] = int(args.cache_ttl)
        print(f"✅ API 缓存时间已设置为 {args.cache_ttl} 秒")
    
    save_config(config)
    
    print(f"\n当前配置:")
    print(f"   检查间隔：{config['check_interval_minutes']} 分钟")
    print(f"   变化阈值：{config['price_change_threshold']*100:.0f}%")
    print(f"   API 缓存：{config.get('cache_ttl_seconds', CACHE_TTL_SECONDS)} 秒")
    print(f"   自动通知：{'开启' if config['auto_notify'] else '关闭'}")


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
    print(f"   监控商品：{len(monitors)} 个")
    print(f"   好价商品：{deals_count} 个")
    if total_saved > 0:
        save_pct = (total_saved / total_original * 100) if total_original > 0 else 0
        print(f"   累计节省：¥{total_saved:.0f} ({save_pct:.0f}%)")
        print(f"\n💡 继续监控，省更多！")
    else:
        print(f"   累计节省：暂无数据（持续监控中...）")


async def group(args):
    """分组管理主函数"""
    if not hasattr(args, 'group_cmd') or not args.group_cmd:
        # 无子命令，显示所有分组
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
    
    source_names = {1: "淘宝", 2: "京东", 3: "拼多多", 7: "抖音", 8: "快手"}
    
    for m in group_monitors:
        price_str = f"¥{m.get('last_price', 'N/A')}" if m.get('last_price') else "N/A"
        target_str = f"¥{m['target_price']}" if m.get('target_price') else "-"
        name = m['name'][:18] + ".." if len(m['name']) > 20 else (m['name'] or "未知")
        print(f"{m['id']:<4} {name:<20} {source_names.get(m['source'], '未知'):<8} {price_str:<10} {target_str:<10}")


async def group_delete(args):
    """删除分组（将组内商品移到未分组）"""
    conn = get_db()
    conn.execute(
        "UPDATE monitors SET group_name = '' WHERE group_name = ?",
        (args.name,)
    )
    conn.commit()
    print(f"✅ 已删除分组 '{args.name}'，商品已移到未分组")


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


async def main():
    global SESSION
    
    # 初始化数据库
    init_database()
    
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as SESSION:
        parser = argparse.ArgumentParser(description="电商价格监控工具（优化版）")
        parsers = parser.add_subparsers()
        
        # add 命令
        add_parser = parsers.add_parser("add", help="添加监控商品")
        add_parser.add_argument("--source", required=True, help="平台 1:淘宝 2:京东 3:拼多多 7:抖音 8:快手")
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
        search_parser.add_argument("--source", required=True, help="平台 1:淘宝 2:京东 3:拼多多 7:抖音 8:快手")
        search_parser.add_argument("--target_price", help="目标价格")
        search_parser.add_argument("--limit", type=int, default=10, help="返回结果数量（默认 10）")
        search_parser.set_defaults(func=search_and_monitor)
        
        # config 命令
        config_parser = parsers.add_parser("config", help="配置参数")
        config_parser.add_argument("--interval", type=int, help="检查间隔 (分钟)")
        config_parser.add_argument("--threshold", type=float, help="价格变化阈值 (0.05 表示 5%%)")
        config_parser.add_argument("--cache-ttl", type=int, help="API 缓存时间 (秒)")
        config_parser.set_defaults(func=config_monitor)
        
        # stats 命令
        stats_parser = parsers.add_parser("stats", help="查看省钱统计")
        stats_parser.set_defaults(func=show_stats)
        
        # cleanup 命令
        cleanup_parser = parsers.add_parser("cleanup", help="清理旧数据和缓存")
        cleanup_parser.set_defaults(func=cleanup)
        
        # low-price 命令
        lowprice_parser = parsers.add_parser("low-price", help="查看历史低价商品排名")
        lowprice_parser.add_argument("--top", type=int, default=10, help="显示数量（默认 10）")
        lowprice_parser.add_argument("--days", type=int, default=30, help="查询天数（默认 30）")
        lowprice_parser.set_defaults(func=show_low_price)
        
        # compare 命令
        compare_parser = parsers.add_parser("compare", help="多源比价")
        compare_parser.add_argument("--id", required=True, help="商品 ID")
        compare_parser.add_argument("--sources", required=True, help="平台列表，逗号分隔 (如 1,2,3)")
        compare_parser.set_defaults(func=compare_goods)
        
        # trend 命令
        trend_parser = parsers.add_parser("trend", help="查看价格趋势图")
        trend_parser.add_argument("--id", required=True, help="监控 ID")
        trend_parser.add_argument("--days", type=int, default=30, help="查询天数（默认 30）")
        trend_parser.set_defaults(func=show_trend)
        
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
        
        # 让 group 主命令也可以调用 list
        group_list_only_parser = group_parser.add_parser("list", help="列出所有分组")
        group_list_only_parser.set_defaults(func=group_list)
        
        # 将 group 子命令标记到 args
        group_parser.set_defaults(group_cmd=None)
        group_add_parser.set_defaults(group_cmd="add")
        group_remove_parser.set_defaults(group_cmd="remove")
        group_list_parser.set_defaults(group_cmd="list")
        group_show_parser.set_defaults(group_cmd="show")
        group_delete_parser.set_defaults(group_cmd="delete")
        
        args = parser.parse_args()
        if hasattr(args, "func"):
            await args.func(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    # Windows 下设置 UTF-8 输出
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    asyncio.run(main())
