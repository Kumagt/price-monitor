---
name: price-monitor
description: 电商价格监控技能。跟踪指定商品价格变化，设置降价提醒，自动推送优惠信息。支持淘宝、京东、拼多多、抖音、快手等平台。
author: Kumagt
version: 1.0.0
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

## 📊 参数说明

| 参数 | 说明 | 可选值 |
|------|------|--------|
| source | 电商平台 | 1:淘宝/天猫，2:京东，3:拼多多，7:抖音，8:快手 |
| id | 商品 ID | 平台商品 ID |
| name | 商品名称 | 自定义备注 |
| target_price | 目标价格 | 低于此价格时提醒 |
| interval | 检查间隔 | 分钟数，默认 60 |

## 💡 使用示例

```bash
# 添加一个 iPhone 监控，目标价 5000 元
uv run scripts/main.py add --source=1 --id=12345678 --name="iPhone 16" --target_price=5000

# 查看所有监控
uv run scripts/main.py list

# 立即检查某个商品
uv run scripts/main.py check --id=1

# 查看价格历史
uv run scripts/main.py history --id=1
```

## 🔔 通知方式

- 价格变化超过 5% → 自动推送
- 达到目标价格 → 立即推送
- 商品下架 → 通知提醒

## 📁 数据文件

- `data/monitors.json` - 监控列表配置
- `data/history/` - 价格历史记录
- `data/config.json` - 全局配置

## ⚠️ 注意事项

- 默认每 60 分钟检查一次（可配置）
- 检查所有商品会消耗 API 配额，建议分批检查
- 价格数据缓存 10 分钟，避免频繁请求

---

**让价格监控自动化，不错过任何优惠！** 💰
