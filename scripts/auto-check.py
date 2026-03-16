#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp", "PyYAML"]
# ///
"""
自动价格检查脚本
用于 OpenClaw cron 定时任务，定期检查所有商品价格并发送通知
"""
import asyncio
import sys
from pathlib import Path

# 导入主模块的功能
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from main import check_all_prices, load_monitors


async def main():
    """自动检查所有商品价格"""
    monitors = load_monitors()
    active_monitors = [m for m in monitors if m.get("enabled", True)]
    
    if not active_monitors:
        print("📭 暂无启用的监控商品")
        return
    
    print(f"🔍 [自动检查] 正在检查 {len(active_monitors)} 个商品价格...\n")
    
    # 调用检查函数
    await check_all_prices(type('Args', (), {'all': True})())
    
    print("\n✅ 自动检查完成")


if __name__ == "__main__":
    asyncio.run(main())
