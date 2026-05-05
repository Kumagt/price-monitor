# T2 梯队任务规范

## 任务目标
为 `price-monitor` 实现第 2 梯队功能：
1. **价格预测**：基于历史价格用简单线性回归预测未来价格走势
2. **CSV 导出**：将监控商品的价格历史导出为 CSV 文件
3. **简易 Web UI**：提供浏览器可访问的价格监控仪表板

## 开发要求

### 功能 1: 价格预测 (`predict`)

```bash
uv run scripts/main.py predict --id=监控ID --days=7
```

**实现要点：**
- 使用简单的线性回归（不引入 numpy，用纯 Python 计算）
- 基于最近 N 天（默认 30 天）的价格数据
- 输出：预测价格、置信区间、趋势方向（涨/跌/稳）
- 显示预测公式和 R² 值
- 如果数据不足（<3 个点），提示无法预测
- 函数签名: `async def predict_price(args)`

### 功能 2: CSV 导出 (`export`)

```bash
uv run scripts/main.py export --id=监控ID --format=csv  # 单个商品
uv run scripts/main.py export --all --format=csv         # 全部商品
```

**实现要点：**
- 支持 `--format=csv`（默认）和 `--format=xlsx`
- CSV 输出到 `data/exports/` 目录，文件名含日期
- CSV 列：商品名、价格、原价、标题、URL、时间戳、来源
- xlsx 使用 `openpyxl`（如可用），否则降级为 CSV
- 进度提示和文件大小
- 函数签名: `async def export_data(args)`

### 功能 3: Web UI (`webui`)

```bash
uv run scripts/main.py webui  # 启动 Web 界面
```

**实现要点：**
- 使用 Flask（轻量级，常用）作为 Web 框架
- 如果 Flask 不可用，使用 Python 内置 `http.server` + 嵌入式 HTML
- 页面内容：
  - 仪表盘：所有监控商品的卡片（名称、当前价、目标价、状态）
  - 趋势图：使用 Chart.js（CDN）展示价格趋势
  - 搜索/筛选功能
- 端口默认 8765，可配置
- 响应式设计（手机友好）
- 无外部 CSS 依赖（内联样式）
- 函数签名: `async def start_webui(args)`

## 编码规范

1. **保持现有架构**：所有新函数放在 `main.py` 中
2. **async/await**：保持异步风格（如需要 HTTP 服务器则用同步）
3. **不引入新依赖**：优先使用 Python 标准库
4. **向后兼容**：不破坏现有命令
5. **中文注释**：所有代码添加中文注释和 docstring
6. **错误处理**：完善的 try/except
7. **代码风格**：PEP 8，4 空格缩进

## DB Schema 要求

- `monitors` 表已有 `group_name TEXT DEFAULT ''`（T1 已迁移）
- `price_history` 表已有 `is_change_point` 字段

## 文件结构（新建）

```
price-monitor/
├── data/
│   └── exports/          # CSV 导出目录（自动创建）
├── webui/
│   ├── index.html        # Web 界面（如分离）
│   └── static/
│       └── style.css     # 样式（如分离）
├── scripts/
│   └── main.py           # 新增功能
└── FEATURES.md           # 更新进度
```

## 提交要求

完成后：
1. 语法验证: `python -c "import py_compile; py_compile.compile('scripts/main.py', doraise=True)"`
2. Git commit 并 push 到 `origin/main`
3. 更新 `FEATURES.md` 进度（T1 和 T2 标记完成）
4. 输出完成的命令列表

## 文件路径

- 主文件: `C:\Users\96390\.openclaw\workspace\price-monitor\scripts\main.py`
- 项目根: `C:\Users\96390\.openclaw\workspace\price-monitor`
- FEATURES: `C:\Users\96390\.openclaw\workspace\price-monitor\FEATURES.md`
