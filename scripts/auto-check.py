#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp"]
# ///
"""
自动价格检查脚本（优化版）
用于 OpenClaw cron 定时任务，定期检查所有商品价格并发送通知

优化：
- 错峰检查（避免 API 限流）
- 使用缓存（减少重复请求）
- 只记录价格变化点（节省存储）
"""
import asyncio
import sys
import aiohttp
from pathlib import Path

# 导入主模块的功能
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from main import check_all_prices, list_monitors_sync, init_database, SESSION, HEADERS, SSL_CONTEXT


async def main():
    """自动检查所有商品价格"""
    # 初始化数据库
    init_database()
    
    monitors = list_monitors_sync()
    
    if not monitors:
        print("📭 暂无启用的监控商品")
        return
    
    print(f"🔍 [自动检查] 正在检查 {len(monitors)} 个商品价格...\n")
    
    # 创建 aiohttp session（main.py 的 check_all_prices 依赖全局 SESSION）
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        # 将 session 赋值给主模块的全局变量
        import main
        main.SESSION = session
        
        # 调用检查函数（已内置错峰逻辑）
        await check_all_prices(type('Args', (), {'all': True})())
    
    print("\n✅ 自动检查完成")


if __name__ == "__main__":
    # Windows 下设置 UTF-8 输出
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    asyncio.run(main())
