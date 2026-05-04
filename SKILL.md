---
name: price-monitor
description: 电商价格监控技能（优化版）。智能缓存、错峰请求、只记录变化点，大幅节省 API 配额和存储空间。支持淘宝、京东、拼多多、抖音、快手等平台。
author: Kumagt
version: 1.3.0
license: MIT
metadata: {"clawdbot":{"emoji":"💰","requires":{"bins":["python3","uv"]}}}
---

# 价格监控技能（优化版）

监控电商平台商品价格变化，设置降价提醒，自动推送优惠信息。

**v1.3.0 新增功能：**
- 🏆 **多源比价**：同时查询多个平台的同一商品，显示最低价
- 📈 **趋势图表**：ASCII 字符画展示价格历史走势
- 🏅 **历史低价**：排名推荐，找出最值得买的价格
- 📁 **商品分组**：自定义分组管理，分类更清晰

**v1.2.0 优化亮点：**
- ⚡ **API 缓存**：5 分钟内不重复请求同一商品
- 🎯 **错峰检查**：请求间隔 200ms，避免触发限流
- 💾 **智能存储**：使用 SQLite，只记录价格变化点
- 🧹 **自动清理**：30 天前的非关键数据自动清理

## 🎯 使用场景

- 跟踪心仪商品，降价时自动通知
- 大促期间监控历史低价
- 代购/二手卖家监控进货成本
- 比价助手，自动寻找最优价格

## 🔧 命令

### 添加监控商品
```bash
cd skills/price-monitor
uv run scripts/main.py add --source=1 --id=商品 ID --name=商品名称 --target_price=目标价
```

### 查看监控列表
```bash
uv run scripts/main.py list
```

### 立即检查价格
```bash
uv run scripts/main.py check --id=监控 ID
uv run scripts/main.py check --all  # 检查所有（自动错峰）
```

### 查看省钱统计
```bash
uv run scripts/main.py stats
```

### 删除监控
```bash
uv run scripts/main.py remove --id=监控 ID
```

### 查看价格历史
```bash
uv run scripts/main.py history --id=监控 ID
```

### 设置检查频率
```bash
uv run scripts/main.py config --interval=60  # 60 分钟检查一次
```

### 搜索商品并批量添加
```bash
uv run scripts/main.py search --keyword="关键词" --source=1 --target_price=目标价 --limit=10
```

### 清理旧数据
```bash
uv run scripts/main.py cleanup  # 清理 30 天前的数据和过期缓存
```

### 多源比价
```bash
uv run scripts/main.py compare --id=商品ID --sources=1,2,3
``` 同时查询淘宝、京东、拼多多的价格，高亮最低价。

### 查看价格趋势
```bash
uv run scripts/main.py trend --id=监控ID --days=30
``` 展示 ASCII 字符价格趋势图，含升降判断。

### 历史低价排名
```bash
uv run scripts/main.py low-price --top 10 --days=30
``` 找出最近 30 天最值得买的商品，按推荐度排序。

### 商品分组管理
```bash
uv run scripts/main.py group add --name="数码" --id=1  # 添加到分组
uv run scripts/main.py group list                         # 列出所有分组
uv run scripts/main.py group show --name="数码"           # 查看分组
uv run scripts/main.py group delete --name="数码"         # 删除分组
```

### 搜索时指定分组
```bash
uv run scripts/main.py search --keyword="iPhone" --source=1 --group="数码"
``` 搜索结果自动归入"数码"分组

## 📊 参数说明

| 参数 | 说明 | 可选值 |
|------|------|--------|
| source | 电商平台 | 1:淘宝/天猫，2:京东，3:拼多多，7:抖音，8:快手 |
| id | 商品 ID | 平台商品 ID |
| name | 商品名称 | 自定义备注 |
| target_price | 目标价格 | 低于此价格时提醒 |
| interval | 检查间隔 | 分钟数，默认 60 |
| threshold | 价格变化阈值 | 0.05 表示 5% 变化 |
| cache-ttl | API 缓存时间 | 秒数，默认 300（5 分钟） |

## 💡 使用示例

```bash
# 添加一个 iPhone 监控，目标价 5000 元
uv run scripts/main.py add --source=1 --id=12345678 --name="iPhone 16" --target_price=5000

# 查看所有监控
uv run scripts/main.py list

# 查看省钱统计
uv run scripts/main.py stats

# 立即检查某个商品
uv run scripts/main.py check --id=1

# 查看价格历史
uv run scripts/main.py history --id=1

# 搜索商品并批量添加
uv run scripts/main.py search --keyword="iPhone 16" --source=1 --target_price=5000

# 清理旧数据
uv run scripts/main.py cleanup
```

## 🔔 通知方式

- 价格变化超过阈值 → 自动推送通知
- 达到目标价格 → 立即推送通知
- 商品下架 → 通知提醒

通知会记录到 `~/.openclaw/workspace/notifications/price-monitor.json`，OpenClaw 可以读取并推送给用户。

## 📁 数据文件

```
data/
├── price_monitor.db      # SQLite 数据库（监控列表 + 价格历史）
├── config.json           # 全局配置
├── api_cache.json        # API 响应缓存
└── notifications/
    └── price-monitor.json  # 通知记录
```

## ⏰ 自动检查

使用 `scripts/auto-check.py` 脚本配合 OpenClaw cron 定时任务，可以实现自动价格检查：

```bash
# 在 OpenClaw 中设置每小时检查一次
openclaw cron add --name="price-check" --schedule="0 * * * *" \
  --command="cd ~/.openclaw/workspace/skills/price-monitor && uv run scripts/auto-check.py"
```

## ⚙️ 高级配置

编辑 `data/config.json`：

```json
{
  "check_interval_minutes": 60,        // 检查间隔（分钟）
  "price_change_threshold": 0.05,      // 价格变化阈值（5%）
  "auto_notify": true,                  // 自动通知
  "cache_ttl_seconds": 300,             // API 缓存时间（秒）
  "request_delay_ms": 200,              // 请求间隔（毫秒）
  "history_retention_days": 30,         // 历史数据保留天数
  "max_history_per_item": 100           // 每个商品最大历史记录数
}
```

## ⚠️ 注意事项

### API 配额优化
- **缓存策略**：5 分钟内同一商品不重复请求
- **错峰检查**：每个请求间隔 200ms
- **批量检查**：自动分散请求时间

建议配置：
- 监控 10 个商品：检查间隔 ≥ 30 分钟
- 监控 50 个商品：检查间隔 ≥ 60 分钟
- 监控 100+ 商品：检查间隔 ≥ 120 分钟

### 存储优化
- 使用 SQLite 替代 JSON，查询速度提升 10 倍
- 只记录价格变化点（变化≥1%），存储空间节省 80%
- 自动清理 30 天前的非关键数据

### 数据准确性
- 实际价格以购买页面为准
- 优惠券可能有时效性
- 促销活动价格可能瞬时变化

---

**让价格监控自动化，不错过任何优惠！** 💰

**优化版 v1.2.0** - 更智能、更高效、更省资源
