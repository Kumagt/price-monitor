# 🛒 电商价格监控助手

> 跟踪商品价格变化，设置降价提醒，自动推送优惠信息  
> 支持淘宝/京东/拼多多/抖音/快手

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-green.svg)](https://openclaw.ai)

---

## ✨ 功能特性

- 🔍 **多平台支持**：淘宝/天猫、京东、拼多多、抖音、快手
- 📉 **降价提醒**：价格变化超过阈值或达到目标价时自动通知
- 📊 **价格历史**：记录商品价格变化，查看历史走势
- 💰 **省钱统计**：累计计算省了多少钱
- ⏰ **自动检查**：可配置检查频率，支持定时任务
- 💾 **本地存储**：所有数据本地保存，隐私安全
- 🚀 **一键安装**：支持 ClawHub 和手动安装

---

## 📦 安装

### 方式一：通过 ClawHub（推荐）

```bash
clawhub install price-monitor
```

### 方式二：手动安装

```bash
# 克隆仓库
git clone https://github.com/Kumagt/price-monitor.git

# 移动到 OpenClaw 技能目录
mv price-monitor ~/.openclaw/workspace/skills/

# 验证安装
cd ~/.openclaw/workspace/skills/price-monitor
uv run scripts/main.py --help
```

### 方式三：直接下载

1. 下载本仓库所有文件
2. 放到 `~/.openclaw/workspace/skills/price-monitor/` 目录
3. 运行 `uv run scripts/main.py --help` 验证

---

## 🚀 快速开始

### 1️⃣ 添加监控商品

```bash
cd ~/.openclaw/workspace/skills/price-monitor

# 添加一个 iPhone 监控，目标价 5000 元
uv run scripts/main.py add --source=1 --id=12345678 --name="iPhone 16" --target_price=5000
```

**平台代码：**

| 代码 | 平台 |
|------|------|
| 1 | 淘宝/天猫 |
| 2 | 京东 |
| 3 | 拼多多 |
| 7 | 抖音 |
| 8 | 快手 |

**商品 ID 获取方法：**
- **淘宝**：商品链接中的 `id=xxx` 部分
- **京东**：商品链接中的数字 ID
- **拼多多**：商品链接中的 `goods_id=xxx`
- **抖音/快手**：商品链接中的数字 ID

### 2️⃣ 查看监控列表

```bash
uv run scripts/main.py list
```

输出示例：
```
📊 监控列表 (共 2 个商品，检查间隔：60 分钟)

ID   名称                 平台     当前价      目标价      状态    
----------------------------------------------------------------------
1    iPhone 16           淘宝     ¥5299      ¥5000      ✅      
2    小米耳机            京东     ¥299       -          ✅      
```

### 3️⃣ 检查价格

```bash
# 检查指定商品
uv run scripts/main.py check --id=1

# 检查所有商品
uv run scripts/main.py check --all
```

### 4️⃣ 查看省钱统计

```bash
uv run scripts/main.py stats
```

输出示例：
```
📊 省钱统计

商品                      原价       现价       节省       状态    
----------------------------------------------------------------------
iPhone 16                ¥5999      ¥5299      ¥700      ✅      
小米耳机                 ¥399       ¥299       ¥100      ✅      
----------------------------------------------------------------------

📈 总计:
   监控商品：2 个
   好价商品：2 个
   累计节省：¥800 (17%)

💡 继续监控，省更多！
```

### 5️⃣ 查看价格历史

```bash
uv run scripts/main.py history --id=1
```

输出示例：
```
📈 iPhone 16 价格历史 (最近 10 条)

时间                 价格       标题                            
------------------------------------------------------------
2026-03-16 16:00    ¥5299     Apple iPhone 16 128GB
2026-03-16 15:00    ¥5399     Apple iPhone 16 128GB
2026-03-16 14:00    ¥5399     Apple iPhone 16 128GB
2026-03-16 13:00    ¥5499     Apple iPhone 16 128GB
```

---

## 🔧 高级功能

### 🔎 搜索商品并批量添加

```bash
# 搜索 iPhone 并批量添加监控
uv run scripts/main.py search --keyword="iPhone 16" --source=1 --target_price=5000 --limit=10
```

支持交互式选择：
- `[a]` 添加全部
- `[s]` 选择性添加
- `[n]` 取消

### ⚙️ 配置参数

```bash
# 设置检查间隔为 30 分钟
uv run scripts/main.py config --interval=30

# 设置价格变化阈值为 3%
uv run scripts/main.py config --threshold=0.03

# 查看当前配置
uv run scripts/main.py config
```

### 🗑️ 删除监控

```bash
uv run scripts/main.py remove --id=1
```

### ⏰ 设置自动检查（定时任务）

在 OpenClaw 中设置定时任务，每小时自动检查一次：

```bash
# 在 OpenClaw 主会话中运行
openclaw cron add --name="price-check" --schedule="0 * * * *" --command="cd ~/.openclaw/workspace/skills/price-monitor && uv run scripts/auto-check.py"
```

或者使用 OpenClaw 的 cron 工具配置。

---

## 📁 文件结构

```
price-monitor/
├── SKILL.md              # 技能描述（OpenClaw 格式）
├── README.md             # 本文件
├── scripts/
│   ├── main.py           # 主程序
│   └── auto-check.py     # 自动检查脚本
└── data/
    ├── monitors.json     # 监控列表配置
    ├── config.json       # 全局配置
    └── history/          # 价格历史记录
        ├── 1.json
        ├── 2.json
        └── ...
```

---

## ⚠️ 注意事项

### API 限制
- 频繁查询可能触发平台限流
- 建议检查间隔不低于 **30 分钟**
- 大批量检查时建议分批进行

### 价格准确性
- 实际价格以购买页面为准
- 优惠券可能有时效性
- 促销活动价格可能瞬时变化

### 商品状态
- 商品下架时会提示获取失败
- 可手动删除下架商品的监控
- 建议定期清理无效监控

### 网络要求
- 需要能访问互联网
- 需要能访问买手 API

---

## 🐛 常见问题

### Q: 添加监控后显示"获取失败"
**原因**：商品 ID 错误或商品已下架  
**解决**：
1. 检查商品 ID 是否正确
2. 在电商平台确认商品是否在售
3. 重新添加监控

### Q: 检查价格时显示"网络错误"
**原因**：网络连接问题或 API 限流  
**解决**：
1. 检查网络连接
2. 手动运行 `check --id=X` 测试
3. 如频繁出现，增加检查间隔

### Q: 命令运行提示"找不到模块"
**原因**：不在技能目录运行  
**解决**：
```bash
cd ~/.openclaw/workspace/skills/price-monitor
uv run scripts/main.py --help
```

### Q: 提示"缺少 uv"
**原因**：缺少 uv 或 Python 版本过低  
**解决**：
```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip 安装依赖
pip install aiohttp PyYAML
```

---

## 📝 更新日志

### v1.1.0 (2026-03-16)
- ✅ 新增省钱统计功能
- ✅ 新增自动通知推送
- ✅ 新增自动检查脚本
- ✅ 优化文档和示例

### v1.0.0 (2026-03-12)
- ✅ 初始版本发布
- ✅ 支持 5 个电商平台
- ✅ 价格监控与提醒
- ✅ 价格历史记录
- ✅ 可配置检查频率
- ✅ 本地数据存储

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 💖 支持

如果觉得这个技能有用，欢迎打赏支持！

- **GitHub**: [Kumagt](https://github.com/Kumagt)
- **爱发电**: 待添加
- **微信打赏**: 待添加

你的支持是我持续更新的动力！❤️

---

## 📬 联系方式

- **GitHub**: https://github.com/Kumagt
- **Email**: 待填写
- **微信**: 待填写

---

<div align="center">

**Made with ❤️ by Kumagt | Powered by OpenClaw**

[⭐ Star this repo](https://github.com/Kumagt/price-monitor) | [🐛 Report Issue](https://github.com/Kumagt/price-monitor/issues)

</div>
