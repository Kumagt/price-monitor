# 价格监控技能 (Price Monitor)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-green.svg)](https://openclaw.ai)

> 🛒 电商价格监控助手 - 支持淘宝/京东/拼多多/抖音/快手
> 
> 跟踪商品价格变化，设置降价提醒，自动推送优惠信息

---

## ✨ 功能特性

- 🔍 **多平台支持**：淘宝/天猫、京东、拼多多、抖音、快手
- 📉 **降价提醒**：价格变化超过 5% 或达到目标价时自动通知
- 📊 **价格历史**：记录商品价格变化，查看历史走势
- ⏰ **定时检查**：可配置检查频率，默认 60 分钟
- 💾 **本地存储**：所有数据本地保存，隐私安全
- 🚀 **一键安装**：支持 ClawHub 和手动安装

---

## 🚀 快速开始

### 方式一：ClawHub 安装（推荐）

```bash
# 安装技能
clawhub install price-monitor

# 验证安装
cd ~/.openclaw/workspace/skills/price-monitor
uv run scripts/main.py --help
```

### 方式二：Git 安装

```bash
# 克隆仓库
git clone https://github.com/Kumagt/price-monitor.git

# 移动到 OpenClaw 技能目录
mv price-monitor ~/.openclaw/workspace/skills/

# 验证安装
cd ~/.openclaw/workspace/skills/price-monitor
uv run scripts/main.py --help
```

### 方式三：手动安装

1. 下载本仓库所有文件
2. 放到 `~/.openclaw/workspace/skills/price-monitor/` 目录
3. 运行 `uv run scripts/main.py --help` 验证

---

## 📖 使用指南

### 添加监控商品

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

### 查看监控列表

```bash
uv run scripts/main.py list
```

**输出示例：**
```
📊 监控列表 (共 2 个商品，检查间隔：60 分钟)

ID   名称                 平台     当前价      目标价      状态    
----------------------------------------------------------------------
1    iPhone 16            淘宝     ¥5299      ¥5000      ✅      
2    小米耳机             京东     ¥299       -          ✅      
```

### 检查价格

```bash
# 检查指定商品
uv run scripts/main.py check --id=1

# 检查所有商品
uv run scripts/main.py check --all
```

**输出示例：**
```
🔍 正在检查 2 个商品价格...

📦 iPhone 16
   当前价格：¥5299
   原价：¥5999
   链接：https://item.taobao.com/item.htm?id=12345678...
   📉 价格变化：¥5399 → ¥5299 (-1.9%)

📦 小米耳机
   当前价格：¥299
   链接：https://item.jd.com/100012345678.html...
```

### 查看价格历史

```bash
uv run scripts/main.py history --id=1
```

**输出示例：**
```
📈 iPhone 16 价格历史 (最近 10 条)

时间                 价格       标题
------------------------------------------------------------
2026-03-12 22:00    ¥5299     Apple iPhone 16 128GB
2026-03-12 21:00    ¥5399     Apple iPhone 16 128GB
2026-03-12 20:00    ¥5399     Apple iPhone 16 128GB
2026-03-12 19:00    ¥5499     Apple iPhone 16 128GB
```

### 删除监控

```bash
uv run scripts/main.py remove --id=1
```

### 配置参数

```bash
# 设置检查间隔为 30 分钟
uv run scripts/main.py config --interval=30

# 设置价格变化阈值为 3%
uv run scripts/main.py config --threshold=0.03

# 查看当前配置
uv run scripts/main.py config
```

---

## 💡 使用场景

### 🛒 网购达人
监控心仪商品，大促时自动提醒，不错过优惠。

> "加了 20 个商品监控，双 11 省了 3000 多！"

### 📦 代购/二手卖家
批量监控商品进货成本，价格波动及时知晓。

> "做代购的，这个技能帮我监控 50+ 商品，太实用了！"

### ⚖️ 比价助手
同时监控多个平台，自动寻找最优价格。

> "同一款商品，拼多多比淘宝便宜 200，真香！"

---

## 📁 项目结构

```
price-monitor/
├── SKILL.md              # 技能描述（OpenClaw 格式）
├── README.md             # 本文件
├── scripts/
│   └── main.py          # 主程序
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

1. **API 限制**：频繁查询可能触发平台限流，建议检查间隔不低于 30 分钟
2. **价格准确性**：实际价格以购买页面为准，优惠券可能有时效性
3. **商品下架**：商品下架时会提示获取失败，可手动删除监控
4. **网络要求**：需要能访问互联网

---

## 🛠️ 故障排查

### 问题 1：提示 "获取商品详情失败"

**原因：** 商品 ID 错误或商品已下架

**解决：**
1. 检查商品 ID 是否正确
2. 在电商平台确认商品是否在售
3. 重新添加监控

---

### 问题 2：价格不更新

**原因：** 网络连接问题或 API 限流

**解决：**
1. 检查网络连接
2. 手动运行 `check --id=X` 测试
3. 如频繁出现，增加检查间隔

---

### 问题 3：找不到命令

**原因：** 不在技能目录运行

**解决：**
```bash
cd ~/.openclaw/workspace/skills/price-monitor
uv run scripts/main.py --help
```

---

### 问题 4：依赖安装失败

**原因：** 缺少 uv 或 Python 版本过低

**解决：**
```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install aiohttp PyYAML
```

---

## 📝 更新日志

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

- [爱发电](https://afdian.com/a/your-page)
- 微信打赏：![二维码](docs/qr-wechat.png)

你的支持是我持续更新的动力！❤️

---

## 📞 联系方式

- GitHub: https://github.com/Kumagt
- 邮箱：[待填写]
- 微信：[待填写]

---

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Kumagt/price-monitor&type=Date)](https://star-history.com/#Kumagt/price-monitor&Date)

---

**Made with ❤️ by Kumagt | Powered by OpenClaw**
