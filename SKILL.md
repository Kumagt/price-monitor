---
name: price-monitor
description: 电商价格监控技能。跟踪指定商品价格变化，设置降价提醒，自动推送优惠信息。支持淘宝、京东、拼多多、抖音、快手等平台。
author: Kumagt
version: 1.1.0
license: MIT
metadata: {"clawdbot":{"emoji":"💰","requires":{"bins":["python3","uv"]}}}
---

# 价格监控技能

监控电商平台商品价格变化，设置降价提醒，自动推送优惠信息。

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
uv run scripts/main.py check --all  # 检查所有
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

## 📊 参数说明

| 参数 | 说明 | 可选值 |
|------|------|--------|
| source | 电商平台 | 1:淘宝/天猫，2:京东，3:拼多多，7:抖音，8:快手 |
| id | 商品 ID | 平台商品 ID |
| name | 商品名称 | 自定义备注 |
| target_price | 目标价格 | 低于此价格时提醒 |
| interval | 检查间隔 | 分钟数，默认 60 |
| threshold | 价格变化阈值 | 0.05 表示 5% 变化 |

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
```

## 🔔 通知方式

- 价格变化超过阈值 → 自动推送通知
- 达到目标价格 → 立即推送通知
- 商品下架 → 通知提醒

通知会记录到 `~/.openclaw/workspace/notifications/price-monitor.json`，OpenClaw 可以读取并推送给用户。

## 📁 数据文件

- `data/monitors.json` - 监控列表配置
- `data/history/` - 价格历史记录
- `data/config.json` - 全局配置
- `notifications/price-monitor.json` - 通知记录

## ⏰ 自动检查

使用 `scripts/auto-check.py` 脚本配合 OpenClaw cron 定时任务，可以实现自动价格检查：

```bash
# 在 OpenClaw 中设置每小时检查一次
openclaw cron add --name="price-check" --schedule="0 * * * *" \
  --command="cd ~/.openclaw/workspace/skills/price-monitor && uv run scripts/auto-check.py"
```

## ⚠️ 注意事项

- 默认每 60 分钟检查一次（可配置）
- 建议检查间隔不低于 30 分钟，避免触发 API 限流
- 价格数据缓存 10 分钟，避免频繁请求
- 商品下架时会提示获取失败，可手动删除监控

---

**让价格监控自动化，不错过任何优惠！** 💰
