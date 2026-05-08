# 电商价格监控助手 v2.2.0

> **重大更新** - 修复所有严重 Bug，引入重试机制、原子写入、日志框架  
> 跟踪商品价格变化，设置降价提醒，自动推送优惠信息  
> 支持淘宝/京东/拼多多/抖音/快手

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-green.svg)](https://openclaw.ai)
[![Version](https://img.shields.io/badge/version-2.2.0-red.svg)](https://github.com/Kumagt/price-monitor/releases)

---

## 快速开始

### 1. 配置邀请码

首次使用前需要设置买手 API 邀请码：

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填入你的邀请码
MAISHOU_INVITE_CODE=你的邀请码
```

> **注意**：v2.0.0 起不再使用硬编码邀请码，必须设置环境变量才能启动。

### 2. 安装

```bash
# 通过 ClawHub（推荐）
clawhub install price-monitor

# 或手动安装
git clone https://github.com/Kumagt/price-monitor.git
```

### 3. 添加监控

```bash
cd price-monitor

# 添加 iPhone 监控，目标价 5000 元
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

### 4. 检查价格

```bash
# 检查指定商品
uv run scripts/main.py check --id=1

# 检查所有商品（自动错峰，带重试）
uv run scripts/main.py check --all
```

### 5. 查看监控列表

```bash
uv run scripts/main.py list
```

### 6. 设置定时检查

```bash
# OpenClaw cron 定时任务，每小时自动检查
openclaw cron add --name="price-check" --schedule="0 * * * *" \
  --command="cd price-monitor && uv run scripts/auto-check.py"
```

---

## 全部命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `add` | 添加监控商品 | `add --source=1 --id=12345` |
| `list` | 查看监控列表 | `list` |
| `check` | 检查价格 | `check --all` 或 `check --id=1` |
| `remove` | 删除监控 | `remove --id=1` |
| `history` | 查看价格历史 | `history --id=1` |
| `search` | 搜索并批量添加 | `search --keyword="iPhone" --source=1 --group=手机` |
| `config` | 配置参数 | `config --interval=30 --threshold=0.03` |
| `stats` | 省钱统计 | `stats` |
| `cleanup` | 清理旧数据 | `cleanup` |
| `low-price` | 历史低价排名 | `low-price --top=10 --days=30` |
| `compare` | 多源比价 | `compare --id=123 --sources=1,2,3` |
| `trend` | 价格趋势图 | `trend --id=1 --days=30` |
| `group` | 商品分组 | `group list` / `group add --name=手机 --id=1` |

---

## 配置参数

```bash
# 设置检查间隔为 30 分钟
uv run scripts/main.py config --interval=30

# 设置价格变化阈值为 3%
uv run scripts/main.py config --threshold=0.03

# 设置 API 缓存时间为 10 分钟
uv run scripts/main.py config --cache-ttl=600

# 查看当前配置
uv run scripts/main.py config
```

---

## v2.2.0 更新内容

### 严重 Bug 修复
- `auto-check.py` 因 SESSION 未初始化导致运行时崩溃
- `trend` 命令因 max(prices)/min(prices) 导致 TypeError
- `search --group` 参数未实现但文档存在
- `group` 命令因 add_parser 方法不存在而崩溃
- `auto-check.py` UTF-8 BOM 导致 Python 解析失败

### 架构改进
- **重试机制**：网络请求自动重试 3 次（指数退避 1s/2s/4s）
- **原子写入**：配置文件和缓存使用 os.replace() 原子替换，防止损坏
- **阈值统一**：价格变化阈值逻辑统一，消除双重阈值不一致
- **邀请码安全**：移除硬编码回退，强制环境变量配置
- **日志框架**：引入 Python logging 模块，区分 INFO/WARNING/ERROR
- **Session 管理**：使用 async with 确保 SESSION/DB 正确关闭

### 文档
- 新增 `.env.example` 模板
- 统一版本号至 2.0.0

---

## 文件结构

```
price-monitor/
├── SKILL.md              # OpenClaw 技能描述
├── README.md             # 本文件
├── .env.example          # 环境变量示例
├── scripts/
│   ├── main.py           # 主程序（v2.2.0 优化版）
│   └── auto-check.py     # 定时检查脚本
└── data/
    ├── price_monitor.db  # SQLite 数据库
    ├── config.json       # 全局配置
    └── api_cache.json    # API 缓存
```

---

## 推荐配置

| 商品数量 | 检查间隔 | 预计每日请求 |
|---------|---------|-------------|
| 10 个   | 30 分钟  | ~48 次 |
| 20 个   | 60 分钟  | ~48 次 |
| 50 个   | 60 分钟  | ~120 次 |
| 100 个  | 120 分钟 | ~120 次 |

---

## 更新日志

### v2.2.0 (2026-05-08)
- 新增价格预测（纯 Python 线性回归）
- 新增价格历史导出（CSV / XLSX）

### v2.1.0 (2026-05-08)
- 新增多通知渠道（JSON / Webhook / Email）
- 新增导入/导出监控列表（JSON + CSV）
- 新增价格异常检测（暴涨暴跌告警）

### v2.0.0 (2026-05-08)
- 修复 5 个严重 Bug
- 引入网络重试机制（3次指数退避）
- 原子写入保护配置和缓存
- 统一价格阈值逻辑
- 移除硬编码邀请码
- 引入 Python logging 框架
- Session 生命周期管理优化

### v1.3.0 (2026-05-05)
- 新增多源比价、价格趋势图、低价排名
- 新增商品分组管理

### v1.2.0 (2026-03-16)
- 使用 SQLite 数据库
- API 请求缓存
- 错峰检查
- 只记录价格变化点
- 自动清理 30 天前数据

### v1.1.0 (2026-03-16)
- 新增省钱统计
- 新增自动通知
- 新增自动检查脚本

### v1.0.0 (2026-03-12)
- 初始版本发布
- 支持 5 个电商平台

---

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

<div align="center">

**Made with ❤ by Kumagt | Powered by OpenClaw**

[⭐ Star this repo](https://github.com/Kumagt/price-monitor) | [🐛 Report Issue](https://github.com/Kumagt/price-monitor/issues)

**v2.2.0 - 更智能、更高效、更稳定**

</div>
