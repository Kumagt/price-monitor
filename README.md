# 电商价格监控助手 v2.3.0

> 跟踪商品价格变化，设置降价提醒，自动推送优惠信息  
> 支持 10 个电商平台 · Web UI · REST API · 价格预测

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-green.svg)](https://openclaw.ai)
[![Version](https://img.shields.io/badge/version-2.3.0-red.svg)](https://github.com/Kumagt/price-monitor/releases)

---

## 快速开始

### 1. 安装

```bash
# 通过 ClawHub（推荐）
clawhub install price-monitor

# 或手动克隆
git clone https://github.com/Kumagt/price-monitor.git
cd price-monitor
```

### 2. 配置邀请码（可选）

买手 API 邀请码用于获取商品价格数据：

```bash
cp .env.example .env
# 编辑 .env，填入你的邀请码
MAISHOU_INVITE_CODE=你的邀请码
```

> v2.2.0 起邀请码改为可选，不设置仍可运行（但无法查询价格）。

### 3. 添加监控

```bash
# 添加 iPhone 监控，目标价 5000 元
uv run scripts/main.py add --source=1 --id=12345678 --name="iPhone 16" --target_price=5000
```

### 4. 检查价格

```bash
uv run scripts/main.py check --all    # 检查所有商品
uv run scripts/main.py check --id=1   # 检查指定商品
```

### 5. 启动 Web UI

```bash
uv run scripts/main.py webui          # http://127.0.0.1:8765
```

---

## 支持平台

| 代码 | 平台 | 状态 |
|------|------|------|
| 1 | 淘宝/天猫 | ✅ 已接入 |
| 2 | 京东 | ✅ 已接入 |
| 3 | 拼多多 | ✅ 已接入 |
| 7 | 抖音 | ✅ 已接入 |
| 8 | 快手 | ✅ 已接入 |
| 4 | 小红书 | 🚧 框架已就绪 |
| 5 | 得物 | 🚧 框架已就绪 |
| 6 | 唯品会 | 🚧 框架已就绪 |
| 9 | 美团 | 🚧 框架已就绪 |
| 10 | 饿了么 | 🚧 框架已就绪 |

---

## 全部命令

### 核心命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `add` | 添加监控商品 | `add --source=1 --id=12345 --target_price=100` |
| `list` | 查看监控列表 | `list` |
| `check` | 检查价格 | `check --all` 或 `check --id=1` |
| `remove` | 删除监控 | `remove --id=1` |
| `search` | 搜索并批量添加 | `search --keyword="iPhone" --source=1` |
| `config` | 配置参数 | `config --interval=30` |

### 分析命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `history` | 查看价格历史 | `history --id=1` |
| `trend` | 价格趋势图（ASCII） | `trend --id=1 --days=30` |
| `predict` | 价格预测（线性回归） | `predict --id=1` |
| `compare` | 多源比价 | `compare --id=123 --sources=1,2,3` |
| `low-price` | 历史低价排名 | `low-price --top=10 --days=30` |
| `stats` | 省钱统计 | `stats` |

### 管理命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `group` | 商品分组 | `group list` / `group add --name=手机 --id=1` |
| `export-monitors` | 导出监控列表 | `export-monitors --format=csv` |
| `import-monitors` | 导入监控列表 | `import-monitors --file=monitors.json` |
| `export-history` | 导出价格历史 | `export-history --id=1 --format=xlsx` |
| `cleanup` | 清理旧数据 | `cleanup` |

### 服务器命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `webui` | 启动 Web UI | `webui --port 8765 --host 0.0.0.0` |
| `api-server` | 启动 REST API | `api-server --port 8766 --token MY_SECRET` |

---

## Web UI

零依赖内嵌页面，浏览器直接访问：

```bash
uv run scripts/main.py webui [--port 8765] [--host 0.0.0.0]
```

功能：
- 📊 仪表盘：所有监控商品卡片列表
- 📈 价格趋势图：Chart.js 可视化
- ➕ 添加/删除监控商品
- ⚙️ 配置查看和修改
- 📱 响应式设计，手机友好

---

## REST API

完整的 REST API 服务器，供外部系统集成：

```bash
uv run scripts/main.py api-server [--port 8766] [--token YOUR_TOKEN]
```

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| GET | `/api/v1/monitors` | 获取所有监控 |
| GET | `/api/v1/monitors/<id>` | 获取指定监控 |
| POST | `/api/v1/monitors` | 添加监控 |
| DELETE | `/api/v1/monitors/<id>` | 删除监控 |
| GET | `/api/v1/monitors/<id>/history` | 价格历史 |
| GET | `/api/v1/check/<id>` | 检查指定商品 |
| POST | `/api/v1/check/all` | 检查所有商品 |
| GET | `/api/v1/config` | 获取配置 |
| PUT | `/api/v1/config` | 更新配置 |
| GET | `/api/v1/stats` | 省钱统计 |

### 认证

设置 `--token` 后，所有端点需要 Bearer Token：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://127.0.0.1:8766/api/v1/monitors
```

健康检查端点无需认证。

---

## 配置参数

```bash
# 基础配置
uv run scripts/main.py config --interval=30       # 检查间隔（分钟）
uv run scripts/main.py config --threshold=0.03    # 价格变化阈值（3%）
uv run scripts/main.py config --cache-ttl=600     # API 缓存时间（秒）

# 通知配置
uv run scripts/main.py config --notify-channel=webhook --webhook-url=https://...
uv run scripts/main.py config --notify-channel=email --email-smtp=smtp.qq.com --email-from=xxx@qq.com --email-to=yyy@qq.com --email-password=xxx

# 邀请码
uv run scripts/main.py config --invite-code=你的邀请码

# 查看当前配置
uv run scripts/main.py config
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

## 定时任务

使用 OpenClaw cron 设置自动检查：

```bash
openclaw cron add --name="price-check" --schedule="0 * * * *" \
  --command="cd price-monitor && uv run scripts/auto-check.py"
```

---

## 文件结构

```
price-monitor/
├── README.md             # 本文件
├── FEATURES.md           # 功能清单
├── CONTRIBUTING.md       # 贡献指南
├── SECURITY.md           # 安全政策
├── LICENSE               # MIT 许可证
├── .env.example          # 环境变量示例
├── SKILL.md              # OpenClaw 技能描述
├── scripts/
│   ├── main.py           # 主程序
│   ├── api_server.py     # REST API 服务器
│   ├── database.py       # 共享数据库模块
│   └── auto-check.py     # 定时检查脚本
└── data/                 # 运行时数据（不入库）
    ├── price_monitor.db  # SQLite 数据库
    ├── config.json       # 全局配置
    └── api_cache.json    # API 缓存
```

---

## 更新日志

### v2.3.0 (2026-05-08)
- 新增 Web UI（零依赖内嵌页面）
- 新增 REST API 服务器（支持 Bearer Token 认证）
- 新增平台扩展框架（小红书/得物/唯品会/美团/饿了么）
- 邀请码改为可选配置
- 提取共享数据库模块（database.py）
- 修复 Web UI 阻塞 asyncio 问题
- 修复 Windows GBK 编码 emoji 问题

### v2.2.0 (2026-05-08)
- 新增价格预测（纯 Python 线性回归）
- 新增价格历史导出（CSV / XLSX）

### v2.1.0 (2026-05-08)
- 新增多通知渠道（JSON / Webhook / Email）
- 新增导入/导出监控列表（JSON + CSV）
- 新增价格异常检测（暴涨暴跌告警）

### v2.0.0 (2026-05-08)
- 修复 5 个严重 Bug
- 引入网络重试机制（3 次指数退避）
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

欢迎提交 Issue 和 Pull Request！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全

发现安全问题请联系，详见 [SECURITY.md](SECURITY.md)。

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

<div align="center">

**Made with ❤ by Kumagt | Powered by OpenClaw**

[⭐ Star](https://github.com/Kumagt/price-monitor) · [🐛 Issues](https://github.com/Kumagt/price-monitor/issues)

**v2.3.0 - Web UI · REST API · 10 平台**

</div>
