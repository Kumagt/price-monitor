"""
共享数据库模块 - price-monitor v2.3.0
提供数据库初始化、连接管理和配置加载功能。
供 main.py 和 api_server.py 共同使用。
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional

# 基础目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "price_monitor.db"
CONFIG_FILE = DATA_DIR / "config.json"
CACHE_FILE = DATA_DIR / "api_cache.json"


def init_database(db_file: Path = DB_FILE) -> sqlite3.Connection:
    """初始化 SQLite 数据库，返回连接对象。"""
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # 监控表
    conn.execute("""
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
        conn.execute("ALTER TABLE monitors ADD COLUMN group_name TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # 字段已存在

    # 价格历史表（只记录变化点）
    conn.execute("""
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_monitor ON price_history(monitor_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON price_history(timestamp)")

    conn.commit()
    return conn


def load_config(config_file: Path = CONFIG_FILE) -> dict:
    """加载配置文件，返回默认配置 + 用户配置的合并结果。"""
    default_config = {
        "check_interval_minutes": 60,
        "price_change_threshold": 0.05,
        "auto_notify": True,
        "notify_on_rise": False,
        "max_history_per_item": 100,
        "anomaly_threshold": 0.3,
        "anomaly_trend_count": 3,
        "invite_code": "",
        "notify_channel": "json",
        "notify_webhook_url": "",
        "notify_email_smtp": "",
        "notify_email_from": "",
        "notify_email_to": "",
        "notify_email_password": "",
        "cache_ttl_seconds": 300,
        "history_retention_days": 30,
        "request_delay_ms": 1000,
    }

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            default_config.update(user_config)
        except (json.JSONDecodeError, IOError):
            pass

    return default_config


def save_config(config: dict, config_file: Path = CONFIG_FILE) -> None:
    """原子写入配置文件。"""
    DATA_DIR.mkdir(exist_ok=True)
    tmp_file = config_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    tmp_file.replace(config_file)
