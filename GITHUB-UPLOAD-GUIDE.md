# GitHub 仓库上传规范

> 本地 AI 模型上传项目到 GitHub 时，严格按此规范执行。

---

## 一、仓库文件结构

### 必须存在的文件

```
price-monitor/
├── README.md              # 项目首页
├── LICENSE                # MIT 许可证
├── .gitignore             # 排除规则
├── CONTRIBUTING.md        # 贡献指南
├── SECURITY.md            # 安全策略
├── FEATURES.md            # 功能清单
├── .env.example           # 环境变量模板
├── SKILL.md               # OpenClaw 技能描述
├── GITHUB-UPLOAD-GUIDE.md # 本文件
└── scripts/
    ├── main.py            # 主程序
    ├── api_server.py      # REST API 服务器
    ├── database.py        # 共享数据库模块
    └── auto-check.py      # 定时检查脚本
```

### 绝对不能上传的文件

```
# 数据库和缓存
data/*.db
data/*.json
data/api_cache.json
data/exports/

# Python 缓存
__pycache__/
*.pyc
*.pyo
*.pyd
*.so

# 虚拟环境和依赖
venv/
env/
.venv/
*.egg-info/

# 锁文件
uv.lock

# IDE 配置
.vscode/
.idea/
*.swp
*.swo

# 系统文件
.DS_Store
Thumbs.db

# 日志
*.log

# 环境变量（包含密钥）
.env
```

---

## 二、README.md 规范

### 必须包含

- 项目名称和版本号
- 功能描述（1-2 句话）
- 徽章（License / Python / Version）
- 快速开始（3-5 步）
- 全部命令（表格，含示例）
- 平台支持列表
- Web UI 和 REST API 使用方式
- 更新日志（保留最近 5 个版本）

### 不要包含

- ❌ 过时的安装步骤
- ❌ 内部开发笔记
- ❌ 重复的说明
- ❌ 过长的更新历史

---

## 三、提交信息规范

### 格式

```
<type>: <简短描述>
```

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: v2.3.0 - Web UI, REST API` |
| `fix` | Bug 修复 | `fix: 修复 Web UI 阻塞问题` |
| `docs` | 文档 | `docs: 重写 README.md` |
| `chore` | 杂项 | `chore: 版本号更新至 2.3.0` |
| `refactor` | 重构 | `refactor: 提取共享数据库模块` |

---

## 四、上传前检查清单

### 代码检查
- [ ] `python -m py_compile scripts/main.py` 通过
- [ ] 所有子命令 `--help` 正常输出
- [ ] 无硬编码密钥/Token
- [ ] 环境变量通过 `.env.example` 模板配置

### 文件检查
- [ ] `.gitignore` 已正确配置
- [ ] `data/` 目录未暂存
- [ ] `__pycache__/` 未暂存
- [ ] `.env` 文件未暂存

### 文档检查
- [ ] `README.md` 版本号与实际一致
- [ ] `README.md` 更新日志已更新
- [ ] `SKILL.md` 版本已同步更新
- [ ] 无过时文件

### Git 检查
- [ ] `git status` 确认变更
- [ ] 提交信息格式正确
- [ ] 推送前已 `git pull`

---

## 五、上传流程

```bash
git status
git diff --stat
python -m py_compile scripts/main.py
git add -A
git commit -m "type: description"
git push origin main
```

---

## 最终仓库结构示例

```
price-monitor/
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── FEATURES.md
├── GITHUB-UPLOAD-GUIDE.md
├── LICENSE
├── README.md
├── SECURITY.md
├── SKILL.md
└── scripts/
    ├── main.py
    ├── api_server.py
    ├── database.py
    └── auto-check.py
```
