# /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp", "PyYAML"]
# ///
import os
import sys
import json
import yaml
import asyncio
import aiohttp
import argparse
from datetime import datetime
from pathlib import Path

# 基础目录
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
MONITORS_FILE = DATA_DIR / "monitors.json"
CONFIG_FILE = DATA_DIR / "config.json"

# 确保目录存在
DATA_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)

# 买手 API 配置
INVITE_CODE = os.getenv("MAISHOU_INVITE_CODE") or "6110440"
HEADERS = {
    aiohttp.hdrs.ACCEPT: "application/json",
    aiohttp.hdrs.REFERER: "https://hnbc018.kuaizhan.com/",
    aiohttp.hdrs.USER_AGENT: "Mozilla/5.0 AppleWebKit/537 Chrome/143 Safari/537",
}

SESSION: aiohttp.ClientSession | None = None


def load_monitors():
    """加载监控列表"""
    if MONITORS_FILE.exists():
        with open(MONITORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_monitors(monitors):
    """保存监控列表"""
    with open(MONITORS_FILE, "w", encoding="utf-8") as f:
        json.dump(monitors, f, ensure_ascii=False, indent=2)


def load_config():
    """加载配置"""
    default_config = {
        "check_interval_minutes": 60,
        "price_change_threshold": 0.05,  # 5% 变化触发通知
        "auto_notify": True,
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


def record_price(monitor_id, price_data):
    """记录价格历史"""
    history_file = HISTORY_DIR / f"{monitor_id}.json"
    if history_file.exists():
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    
    history.append({
        "timestamp": datetime.now().isoformat(),
        **price_data,
    })
    
    # 只保留最近 100 条记录
    history = history[-100:]
    
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


async def search_goods(keyword, source, limit=10):
    """搜索商品（调用买手 API 搜索接口）"""
    global SESSION
    
    try:
        resp = await SESSION.post(
            "https://appapi.maishou88.com/api/v3/goods/search",
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
        result = data.get("data") or {}
        goods_list = result.get("goodsList", [])
        
        if not goods_list:
            return []
        
        results = []
        for goods in goods_list:
            try:
                goods_id = goods.get("goodsId") or goods.get("id")
                if not goods_id:
                    continue
                
                # 获取价格信息
                actual_price = float(goods.get("actualPrice") or goods.get("price") or 0)
                original_price = float(goods.get("originalPrice") or goods.get("marketPrice") or actual_price)
                title = goods.get("title") or goods.get("goodsName") or "未知商品"
                
                # 尝试获取链接
                app_url = goods.get("appUrl") or goods.get("clickUrl") or ""
                if not app_url:
                    # 如果需要链接，再调用一次 getTargetUrl
                    pass
                
                results.append({
                    "goods_id": goods_id,
                    "title": title,
                    "actualPrice": actual_price,
                    "originalPrice": original_price,
                    "appUrl": app_url,
                    "couponPrice": float(goods.get("couponPrice") or 0),
                })
            except Exception as e:
                print(f"解析商品数据失败：{e}")
                continue
        
        return results
    except Exception as e:
        print(f"搜索失败：{e}")
        return []


async def get_goods_detail(goods_id, source):
    """获取商品详情（调用买手 API）"""
    global SESSION
    
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
        
        return {
            "title": detail.get("title", ""),
            "actualPrice": float(detail.get("actualPrice", 0)),
            "originalPrice": float(detail.get("originalPrice", 0)),
            "couponPrice": float(detail.get("couponPrice", 0)),
            "appUrl": info.get("appUrl") or info.get("schemaUrl"),
        }
    except Exception as e:
        print(f"获取商品详情失败：{e}")
        return None


async def add_monitor(args):
    """添加监控商品"""
    monitors = load_monitors()
    
    new_id = len(monitors) + 1
    monitor = {
        "id": new_id,
        "goods_id": args.id,
        "source": int(args.source),
        "name": args.name or f"商品{args.id}",
        "target_price": float(args.target_price) if args.target_price else None,
        "created_at": datetime.now().isoformat(),
        "last_price": None,
        "enabled": True,
    }
    
    monitors.append(monitor)
    save_monitors(monitors)
    
    print(f"✅ 已添加监控 #{new_id}: {monitor['name']}")
    print(f"   商品 ID: {args.id}")
    print(f"   平台：{args.source}")
    if args.target_price:
        print(f"   目标价：¥{args.target_price}")
    
    # 立即检查一次价格
    print("\n正在获取当前价格...")
    await check_single_price(new_id)


async def list_monitors(args):
    """查看监控列表"""
    monitors = load_monitors()
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
        if not m.get("enabled", True):
            continue
        price_str = f"¥{m.get('last_price', 'N/A')}" if m.get('last_price') else "N/A"
        target_str = f"¥{m['target_price']}" if m.get('target_price') else "-"
        status = "✅" if m.get('enabled', True) else "⏸️"
        name = m['name'][:18] + ".." if len(m['name']) > 20 else m['name']
        print(f"{m['id']:<4} {name:<20} {source_names.get(m['source'], '未知'):<8} {price_str:<10} {target_str:<10} {status:<8}")


async def check_single_price(monitor_id):
    """检查单个商品价格"""
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    
    if not monitor:
        print(f"❌ 未找到监控 #{monitor_id}")
        return
    
    if not monitor.get("enabled", True):
        print(f"⏸️ 监控 #{monitor_id} 已暂停")
        return
    
    detail = await get_goods_detail(monitor["goods_id"], monitor["source"])
    
    if not detail:
        print(f"⚠️ 获取商品 #{monitor_id} 价格失败")
        return
    
    current_price = detail["actualPrice"]
    last_price = monitor.get("last_price")
    
    # 记录价格历史
    record_price(monitor_id, {
        "price": current_price,
        "title": detail["title"],
        "url": detail.get("appUrl", ""),
    })
    
    # 更新监控记录
    monitor["last_price"] = current_price
    monitor["last_check"] = datetime.now().isoformat()
    save_monitors(monitors)
    
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
    if target_notify:
        print(f"   🎉 已达到目标价 ¥{monitor['target_price']}!")
    
    return {
        "monitor_id": monitor_id,
        "name": monitor["name"],
        "current_price": current_price,
        "last_price": last_price,
        "change_notify": change_notify,
        "target_notify": target_notify,
    }


async def check_all_prices(args):
    """检查所有商品价格"""
    monitors = load_monitors()
    active_monitors = [m for m in monitors if m.get("enabled", True)]
    
    if not active_monitors:
        print("📭 暂无启用的监控商品")
        return
    
    print(f"🔍 正在检查 {len(active_monitors)} 个商品价格...\n")
    
    results = []
    for monitor in active_monitors:
        result = await check_single_price(monitor["id"])
        if result:
            results.append(result)
        # 避免请求过快
        await asyncio.sleep(0.5)
    
    # 汇总通知
    notify_count = sum(1 for r in results if r.get("change_notify") or r.get("target_notify"))
    if notify_count > 0:
        print(f"\n🔔 共 {notify_count} 个商品需要通知")


async def remove_monitor(args):
    """删除监控"""
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == int(args.id)), None)
    
    if not monitor:
        print(f"❌ 未找到监控 #{args.id}")
        return
    
    monitors = [m for m in monitors if m["id"] != int(args.id)]
    save_monitors(monitors)
    
    # 删除历史记录
    history_file = HISTORY_DIR / f"{args.id}.json"
    if history_file.exists():
        history_file.unlink()
    
    print(f"✅ 已删除监控 #{args.id}: {monitor['name']}")


async def show_history(args):
    """查看价格历史"""
    history_file = HISTORY_DIR / f"{args.id}.json"
    
    if not history_file.exists():
        print(f"📭 暂无监控 #{args.id} 的历史记录")
        return
    
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    
    monitors = load_monitors()
    monitor = next((m for m in monitors if m["id"] == int(args.id)), None)
    name = monitor["name"] if monitor else f"商品{args.id}"
    
    print(f"📈 {name} 价格历史 (最近 {len(history)} 条)\n")
    print(f"{'时间':<20} {'价格':<10} {'标题'}")
    print("-" * 60)
    
    for record in history[-10:]:  # 只显示最近 10 条
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
    
    # 搜索商品
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
    
    # 交互式确认
    print(f"\n是否批量添加监控？")
    print(f"  [a] 添加全部 ({len(results)} 个)")
    print(f"  [s] 选择性添加")
    print(f"  [n] 取消")
    
    choice = input("\n请选择 (a/s/n): ").strip().lower()
    
    if choice == 'n':
        print("已取消")
        return
    
    monitors = load_monitors()
    added_count = 0
    
    if choice == 'a':
        # 添加全部
        for item in results:
            new_id = len(monitors) + 1
            monitor = {
                "id": new_id,
                "goods_id": str(item['goods_id']),
                "source": source,
                "name": item['title'][:50],
                "target_price": target_price,
                "created_at": datetime.now().isoformat(),
                "last_price": None,
                "enabled": True,
            }
            monitors.append(monitor)
            added_count += 1
        
        save_monitors(monitors)
        print(f"\n✅ 已批量添加 {added_count} 个监控商品！")
        
    elif choice == 's':
        # 选择性添加
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
                new_id = len(monitors) + 1
                monitor = {
                    "id": new_id,
                    "goods_id": str(item['goods_id']),
                    "source": source,
                    "name": item['title'][:50],
                    "target_price": target_price,
                    "created_at": datetime.now().isoformat(),
                    "last_price": None,
                    "enabled": True,
                }
                monitors.append(monitor)
                added_count += 1
            
            save_monitors(monitors)
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
        config["price_change_threshold"] = float(args.threshold)
        print(f"✅ 价格变化阈值已设置为 {args.threshold*100:.0f}%")
    
    save_config(config)
    
    print(f"\n当前配置:")
    print(f"   检查间隔：{config['check_interval_minutes']} 分钟")
    print(f"   变化阈值：{config['price_change_threshold']*100:.0f}%")
    print(f"   自动通知：{'开启' if config['auto_notify'] else '关闭'}")


async def main():
    global SESSION
    async with aiohttp.ClientSession(headers=HEADERS) as SESSION:
        parser = argparse.ArgumentParser(description="电商价格监控工具")
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
        config_parser.set_defaults(func=config_monitor)
        
        args = parser.parse_args()
        if hasattr(args, "func"):
            await args.func(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
