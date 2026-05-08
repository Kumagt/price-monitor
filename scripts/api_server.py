"""
REST API Server for price-monitor v2.3
独立 REST API 服务器，供外部系统调用。

使用 Python 内置 http.server 模块。
"""
import json
import os
import sys
import asyncio
import sqlite3
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

# 共享数据库模块
from database import init_database, load_config, save_config, DB_FILE, DATA_DIR, CONFIG_FILE

# SSL 配置
import ssl
SSL_CONTEXT = ssl.create_default_context()

VERSION = "2.3.0"

# ---------- 价格检查 API（需要 aiohttp，延迟导入） ----------

# ---------- 异步价格查询（独立 session，每次请求新建） ----------

SOURCE_NAMES = {1: "淘宝", 2: "京东", 3: "拼多多", 7: "抖音", 8: "快手"}

MAISHOU_API = "https://appapi.maishou88.com/api/v3/goods/detail"
MAISHOU_URL_API = "https://msapi.maishou88.com/api/v1/share/getTargetUrl"

HEADERS = {
    "Accept": "application/json",
    "Referer": "https://hnbc018.kuaizhan.com/",
    "User-Agent": "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1


async def _retry_async(coro_fn, max_retries: int = RETRY_MAX_ATTEMPTS, backoff: float = RETRY_BASE_DELAY):
    """通用异步重试"""
    import aiohttp
    retriable = (
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
        except retriable as e:
            if attempt < max_retries:
                delay = backoff * (2 ** attempt)
                await asyncio.sleep(delay)
            else:
                raise


async def _fetch_goods_detail(goods_id: str, source: int, invite_code: str = "") -> Optional[Dict]:
    """获取商品详情"""
    import aiohttp

    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        params = {
            "goodsId": str(goods_id),
            "sourceType": str(source),
            "inviteCode": invite_code,
            "supplierCode": "",
            "activityId": "",
            "isShare": "1",
            "token": "",
        }

        async def _request_detail():
            resp = await session.post(
                MAISHOU_API,
                json={**params, "keyword": "", "usageScene": 5},
                headers=HEADERS,
            )
            return await resp.json(encoding="utf-8-sig") or {}

        data = await _retry_async(_request_detail)
        detail = data.get("data") or {}

        async def _request_url():
            resp = await session.post(
                MAISHOU_URL_API,
                json={**params, "isDirectDetail": 0},
                headers=HEADERS,
            )
            return await resp.json(encoding="utf-8-sig") or {}

        data = await _retry_async(_request_url)
        info = data.get("data") or {}

        if not info:
            return None

        return {
            "title": detail.get("title", ""),
            "actualPrice": float(detail.get("actualPrice", 0)),
            "originalPrice": float(detail.get("originalPrice", 0)),
            "couponPrice": float(detail.get("couponPrice", 0)),
            "appUrl": info.get("appUrl") or info.get("schemaUrl"),
        }


def check_single_price_api(monitor_id: int) -> Optional[Dict]:
    """同步检查单个商品价格（供 API server 使用）"""
    config = load_config()
    threshold = config.get("price_change_threshold", 0.05)
    invite_code = os.getenv("MAISHOU_INVITE_CODE") or config.get("invite_code", "")

    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,))
    monitor = cursor.fetchone()
    if not monitor:
        conn.close()
        return None

    monitor_dict = dict(monitor)
    conn.close()

    if not monitor_dict.get("enabled", 1):
        return None

    try:
        loop = asyncio.new_event_loop()
        detail = loop.run_until_complete(
            _fetch_goods_detail(monitor_dict["goods_id"], monitor_dict["source"], invite_code)
        )
        loop.close()
    except Exception:
        return None

    if not detail:
        return None

    current_price = detail["actualPrice"]
    last_price = monitor_dict.get("last_price")

    # 更新监控记录
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.execute(
        "UPDATE monitors SET last_price = ?, last_check = ? WHERE id = ?",
        (current_price, datetime.now().isoformat(), monitor_id)
    )

    # 记录价格变化点
    is_change = False
    if last_price and last_price > 0:
        change_ratio = abs(current_price - last_price) / last_price
        if change_ratio >= threshold:
            is_change = True
            conn.execute(
                """INSERT INTO price_history (monitor_id, price, original_price, title, url, timestamp, is_change_point)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (monitor_id, current_price, detail["originalPrice"],
                 detail.get("title", ""), detail.get("appUrl", ""),
                 datetime.now().isoformat(), 1)
            )

    conn.commit()
    conn.close()

    return {
        "monitor_id": monitor_id,
        "name": monitor_dict.get("name", ""),
        "current_price": current_price,
        "last_price": last_price,
        "original_price": detail.get("originalPrice", current_price),
        "title": detail.get("title", ""),
        "url": detail.get("appUrl", ""),
        "changed": is_change,
    }


# ---------- HTTP Request Handler ----------


class PriceMonitorAPIHandler(BaseHTTPRequestHandler):
    """价格监控 REST API 请求处理器"""

    def __init__(self, *args, **kwargs):
        self.api_token: Optional[str] = kwargs.pop("api_token", None)
        super().__init__(*args, **kwargs)

    # ---- 工具方法 ----

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error(self, message: str, code: int = 400):
        self._send_json({"error": message, "code": code}, code)

    def _check_auth(self) -> bool:
        if not self.api_token:
            return True
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_error("未授权：请提供 Bearer Token", 401)
            return False
        token = auth[7:]
        if token != self.api_token:
            self._send_error("Token 无效", 401)
            return False
        return True

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length) if content_length > 0 else b""

    def _parse_json_body(self) -> Optional[Dict]:
        body = self._read_body()
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    # ---- HTTP 方法路由 ----

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/api/v1/health":
            self._handle_health()
        elif path == "/api/v1/monitors":
            if not self._check_auth():
                return
            self._handle_get_monitors()
        elif path == "/api/v1/config":
            if not self._check_auth():
                return
            self._handle_get_config()
        elif path == "/api/v1/stats":
            if not self._check_auth():
                return
            self._handle_get_stats()
        elif path == "/api/v1/check/all":
            if not self._check_auth():
                return
            self._handle_check_all()
        else:
            # /api/v1/monitors/<id> 或 /api/v1/monitors/<id>/history 或 /api/v1/check/<id>
            parts = path.split("/")
            if len(parts) == 5 and parts[1] == "api" and parts[2] == "v1" and parts[3] == "monitors":
                if not self._check_auth():
                    return
                monitor_id = parts[4]
                if monitor_id.isdigit():
                    if len(parts) == 6 and parts[5] == "history":
                        self._handle_get_history(int(monitor_id))
                    else:
                        self._handle_get_monitor(int(monitor_id))
                else:
                    self._send_error("无效的监控 ID", 400)
            elif len(parts) == 5 and parts[1] == "api" and parts[2] == "v1" and parts[3] == "check":
                if not self._check_auth():
                    return
                check_id = parts[4]
                if check_id.isdigit():
                    self._handle_check_single(int(check_id))
                else:
                    self._send_error("无效的 ID", 400)
            else:
                self._send_error("端点不存在", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/v1/check/all":
            if not self._check_auth():
                return
            self._handle_check_all()
        elif path == "/api/v1/monitors":
            if not self._check_auth():
                return
            self._handle_add_monitor()
        else:
            self._send_error("端点不存在", 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/v1/config":
            if not self._check_auth():
                return
            self._handle_update_config()
        else:
            self._send_error("端点不存在", 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        parts = path.split("/")
        if len(parts) == 5 and parts[1] == "api" and parts[2] == "v1" and parts[3] == "monitors":
            if not self._check_auth():
                return
            monitor_id = parts[4]
            if monitor_id.isdigit():
                self._handle_delete_monitor(int(monitor_id))
            else:
                self._send_error("无效的监控 ID", 400)
        else:
            self._send_error("端点不存在", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format, *args):
        """覆盖默认日志格式"""
        sys.stderr.write(f"[API] {self.address_string()} - {format % args}\n")

    # ---- 端点处理 ----

    def _handle_health(self):
        self._send_json({
            "status": "ok",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
        })

    def _handle_get_monitors(self):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM monitors WHERE enabled = 1 ORDER BY id").fetchall()
        conn.close()

        monitors = []
        for r in rows:
            monitors.append({
                "id": r["id"],
                "goods_id": r["goods_id"],
                "source": r["source"],
                "source_name": SOURCE_NAMES.get(r["source"], f"平台{r['source']}"),
                "name": r.get("name", ""),
                "target_price": r.get("target_price"),
                "group_name": r.get("group_name", ""),
                "last_price": r.get("last_price"),
                "last_check": r.get("last_check"),
                "enabled": bool(r.get("enabled", 1)),
                "created_at": r.get("created_at"),
            })

        self._send_json({"data": monitors, "total": len(monitors)})

    def _handle_get_monitor(self, monitor_id: int):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        conn.close()

        if not row:
            self._send_error("监控不存在", 404)
            return

        self._send_json({
            "data": {
                "id": row["id"],
                "goods_id": row["goods_id"],
                "source": row["source"],
                "source_name": SOURCE_NAMES.get(row["source"], f"平台{row['source']}"),
                "name": row.get("name", ""),
                "target_price": row.get("target_price"),
                "group_name": row.get("group_name", ""),
                "last_price": row.get("last_price"),
                "last_check": row.get("last_check"),
                "enabled": bool(row.get("enabled", 1)),
                "created_at": row.get("created_at"),
            }
        })

    def _handle_get_history(self, monitor_id: int):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        monitor = conn.execute("SELECT id, name FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        if not monitor:
            conn.close()
            self._send_error("监控不存在", 404)
            return

        rows = conn.execute(
            "SELECT price, original_price, title, url, timestamp, is_change_point "
            "FROM price_history WHERE monitor_id = ? ORDER BY timestamp DESC",
            (monitor_id,)
        ).fetchall()
        conn.close()

        history = []
        for r in rows:
            history.append({
                "price": r["price"],
                "original_price": r.get("original_price"),
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "timestamp": r["timestamp"],
                "is_change_point": bool(r.get("is_change_point", 1)),
            })

        self._send_json({"data": history, "total": len(history), "monitor_name": monitor.get("name", "")})

    def _handle_add_monitor(self):
        data = self._parse_json_body()
        if data is None:
            self._send_error("无效的 JSON 请求体", 400)
            return

        source = data.get("source")
        goods_id = data.get("goods_id") or data.get("id")
        name = data.get("name", "")
        target_price = data.get("target_price")
        group_name = data.get("group_name", "")

        if not source or not goods_id:
            self._send_error("缺少必要参数: source, goods_id", 400)
            return

        source = int(source)
        if target_price is not None:
            target_price = float(target_price)

        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """INSERT INTO monitors (goods_id, source, name, target_price, group_name, created_at, enabled)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (str(goods_id), source, name, target_price, group_name, datetime.now().isoformat())
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT * FROM monitors WHERE goods_id = ? AND source = ?",
                (str(goods_id), source)
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                self._send_json({"data": {
                    "id": row["id"],
                    "goods_id": row["goods_id"],
                    "source": row["source"],
                    "name": row.get("name", ""),
                    "target_price": row.get("target_price"),
                    "group_name": row.get("group_name", ""),
                    "created_at": row.get("created_at"),
                }}, 201)
            else:
                self._send_error("该商品已在监控中", 409)
        except sqlite3.IntegrityError:
            conn.close()
            self._send_error("该商品已在监控中", 409)

    def _handle_delete_monitor(self, monitor_id: int):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        monitor = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        if not monitor:
            conn.close()
            self._send_error("监控不存在", 404)
            return

        monitor_info = {
            "id": monitor["id"],
            "name": monitor.get("name", ""),
            "goods_id": monitor["goods_id"],
        }

        conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
        conn.execute("DELETE FROM price_history WHERE monitor_id = ?", (monitor_id,))
        conn.commit()
        conn.close()

        self._send_json({"data": monitor_info, "message": "已删除"})

    def _handle_get_config(self):
        config = load_config()
        self._send_json({"data": config})

    def _handle_update_config(self):
        data = self._parse_json_body()
        if data is None:
            self._send_error("无效的 JSON 请求体", 400)
            return

        config = load_config()
        config.update(data)
        save_config(config)
        self._send_json({"data": config, "message": "配置已更新"})

    def _handle_get_stats(self):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        monitors = conn.execute("SELECT * FROM monitors WHERE enabled = 1").fetchall()

        total_saved = 0.0
        total_original = 0.0
        deals_count = 0
        items = []

        for m in monitors:
            last_price = m.get("last_price")
            if not last_price:
                continue

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

            items.append({
                "id": m["id"],
                "name": m.get("name", ""),
                "current_price": last_price,
                "highest_price": max_price,
                "saved": round(saved, 2),
            })

        conn.close()

        save_pct = (total_saved / total_original * 100) if total_original > 0 else 0
        self._send_json({
            "data": {
                "total_monitors": len(monitors),
                "deals_count": deals_count,
                "total_saved": round(total_saved, 2),
                "save_percentage": round(save_pct, 1),
                "items": items,
            }
        })

    def _handle_check_single(self, monitor_id: int):
        result = check_single_price_api(monitor_id)
        if result is None:
            self._send_error("监控不存在或已禁用", 404)
            return
        self._send_json({"data": result})

    def _handle_check_all(self):
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        monitors = conn.execute("SELECT id, name FROM monitors WHERE enabled = 1").fetchall()
        conn.close()

        results = []
        for m in monitors:
            result = check_single_price_api(m["id"])
            if result:
                results.append(result)

        self._send_json({
            "data": results,
            "total": len(results),
            "message": f"已检查 {len(results)} 个商品",
        })


# ---------- 服务器启动 ----------


def start_api_server(host: str = "127.0.0.1", port: int = 8766, token: Optional[str] = None):
    """启动 REST API 服务器"""
    # 初始化数据库
    init_database()

    def handler_factory(*args, **kwargs):
        return PriceMonitorAPIHandler(*args, api_token=token, **kwargs)

    server = HTTPServer((host, port), handler_factory)
    server.request_queue_size = 5

    auth_status = "已启用" if token else "未启用"
    print(f"API Server 已启动")
    print(f"地址：http://{host}:{port}")
    print(f"认证：{auth_status}")
    print(f"按 Ctrl+C 停止")
    print(f"")
    print(f"可用端点：")
    print(f"  GET  /api/v1/health          - 健康检查")
    print(f"  GET  /api/v1/monitors        - 获取所有监控")
    print(f"  GET  /api/v1/monitors/<id>   - 获取指定监控")
    print(f"  POST /api/v1/monitors        - 添加监控")
    print(f"  DELETE /api/v1/monitors/<id> - 删除监控")
    print(f"  GET  /api/v1/monitors/<id>/history - 价格历史")
    print(f"  GET  /api/v1/check/<id>      - 检查指定商品")
    print(f"  POST /api/v1/check/all       - 检查所有商品")
    print(f"  GET  /api/v1/config          - 获取配置")
    print(f"  PUT  /api/v1/config          - 更新配置")
    print(f"  GET  /api/v1/stats           - 省钱统计")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n服务器已停止")
        server.server_close()
