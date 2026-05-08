# GitHub 仓库上传规范

> 本地 AI 模型上传项目到 GitHub 时，严格按此规范执行。

---

## 一、仓库文件结构

### 必须存在的文件

```
project/
├── README.md              # 项目首页，最重要
├── LICENSE                # 开源许可证
├── .gitignore             # 排除不必要上传的文件
├── CONTRIBUTING.md        # 贡献指南（可选，建议有）
├── SECURITY.md            # 安全策略（可选，建议有）
├── FEATURES.md            # 功能清单（可选）
├── .env.example           # 环境变量模板（如有配置需求）
├── .github/               # GitHub 配置目录（可选）
│   ├── FUNDING.yml        # 赞助配置
│   ├── ISSUE_TEMPLATE/    # Issue 模板
│   └── PULL_REQUEST_TEMPLATE.md  # PR 模板
└── scripts/               # 项目代码目录
    └── main.py
```

### 绝对不能上传的文件

```
# 数据库和缓存
data/*.db
data/*.json（配置文件）
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

# 锁文件（Python 项目一般不需要）
uv.lock

# IDE 配置
.vscode/
.idea/
*.swp
*.swo

# 系统文件
.DS_Store
Thumbs.db

# 日志文件
*.log

# 环境变量（包含密钥）
.env（只上传 .env.example）
```

---

## 二、README.md 规范

### 必须包含的内容

```markdown
# 项目名称 v版本号

> 一句话描述项目功能

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)]
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]
[![Version](https://img.shields.io/badge/version-x.x.x-blue.svg)]

---

## 快速开始
（3-5 步，让用户能在 1 分钟内跑起来）

## 全部命令
（命令表格，包含示例）

## 配置说明
（需要哪些环境变量/配置文件）

## 更新日志
（从当前版本往前，最多保留 5 个版本）

## 许可证
（MIT / Apache-2.0 等）

## 联系方式
（GitHub 链接）
```

### 不要包含的内容

- ❌ 过时的安装步骤
- ❌ 内部开发笔记
- ❌ 太多 emoji（影响可读性）
- ❌ 重复的说明
- ❌ 过长的更新历史（超过 5 个版本）

---

## 三、.gitignore 规范

### Python 项目标准模板

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
.venv
*.egg-info/
dist/
build/

# uv / pip
.uv/
uv.lock

# 数据库和缓存
data/*.db
data/*.json
data/api_cache.json
data/exports/

# 日志
*.log

# 系统文件
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# 环境变量（不上传密钥）
.env
```

---

## 四、提交信息规范

### 格式

```
<type>: <简短描述>

<详细描述（可选）>
```

### type 类型

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(v2.3.0): 新增 Web UI` |
| `fix` | Bug 修复 | `fix: 修复 group 命令崩溃问题` |
| `docs` | 文档 | `docs: 重写 README.md` |
| `chore` | 杂项 | `chore: SKILL.md 版本更新` |
| `refactor` | 代码重构 | `refactor: 统一通知接口` |
| `test` | 测试 | `test: 添加价格检查测试` |

### 示例

```bash
# 新功能
git commit -m "feat(v2.3.0): 新增 Web UI"

# Bug 修复
git commit -m "fix: 修复价格导出 CSV 编码问题"

# 文档
git commit -m "docs: 整理 GitHub 页面 - 清理过时文件"

# 混合提交
git commit -m "feat(v2.1.0): 新增 3 项功能

- 多通知渠道（JSON/Webhook/Email）
- 导入/导出监控列表
- 价格异常检测"
```

---

## 五、版本管理

### 版本号规则

```
主版本.次版本.补丁
  |      |      |
  |      |      +-- 小修复，不影响功能
  |      +--------- 新功能，向后兼容
  +---------------- 破坏性变更，不兼容旧版
```

### 更新时机

- **feat(新功能)** → 次版本 +1（v2.2 → v2.3）
- **fix(修复 bug)** → 补丁 +1（v2.2.0 → v2.2.1）
- **破坏性变更** → 主版本 +1（v2.x → v3.0）

### README 中的版本更新

每次发布新版本时，更新 README.md 中的「更新日志」部分：

```markdown
## 更新日志

### v2.3.0 (2026-05-08)
- 新增 Web UI
- 支持浏览器访问

### v2.2.0 (2026-05-07)
- 新增价格预测
- 新增价格历史导出

### v2.1.0 (2026-05-06)
- 新增多通知渠道
- 新增导入/导出

### v2.0.0 (2026-05-05)
- 重大更新：架构优化 + Bug 修复

### v1.3.0 (2026-05-04)
- 新增多源比价、趋势图、分组管理
```

---

## 六、上传前检查清单

### 代码检查

- [ ] `python -m py_compile scripts/main.py` 通过
- [ ] 所有子命令 `--help` 正常输出
- [ ] 无硬编码密钥/Token
- [ ] 环境变量通过 `.env.example` 模板配置

### 文件检查

- [ ] `.gitignore` 已正确配置
- [ ] `data/` 目录下的数据库和缓存未暂存
- [ ] `__pycache__/` 未暂存
- [ ] `.env` 文件未暂存（只保留 `.env.example`）

### 文档检查

- [ ] `README.md` 版本号与实际一致
- [ ] `README.md` 更新日志已更新
- [ ] `SKILL.md` 版本已同步更新（如有）
- [ ] 无过时文件（如旧版 RELEASES.md）

### Git 检查

- [ ] `git status` 确认变更文件
- [ ] 提交信息格式正确
- [ ] `git push` 前已 `git pull`（避免冲突）

---

## 七、本地 AI 模型操作建议

### 上传流程

```bash
# 1. 检查状态
git status

# 2. 确认文件
git diff --stat

# 3. 语法验证
python -m py_compile scripts/main.py

# 4. 添加文件
git add -A

# 5. 提交
git commit -m "type: description"

# 6. 推送
git push origin main
```

### 注意事项

1. **不要在提交中包含数据文件**（数据库、缓存、日志）
2. **不要硬编码任何密钥或 Token**
3. **提交前确保 .gitignore 已正确配置**
4. **大文件（>1MB）考虑使用 git-lfs**
5. **每次提交只做一个事，不要混合同类型变更**

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `rejected` | 远程有更新未拉取 | `git pull --rebase` 后再 push |
| `untracked files` | 新文件未 add | `git add <file>` |
| `detached HEAD` | 不在分支上 | `git checkout main` |
| `merge conflict` | 代码冲突 | 手动解决冲突后提交 |

---

## 八、仓库清理清单

### 定期执行（每版本发布后）

```bash
# 删除本地缓存
git gc --prune=now

# 清理未跟踪文件
git clean -fdn  # 先预览
git clean -fd   # 确认后执行

# 检查大文件
git rev-list --objects --all | git cat-file --batch-check | sort -k3 -rn | head -20
```

### 不需要的文件类型

| 类型 | 示例 | 处理 |
|------|------|------|
| 开发笔记 | `CODE-REVIEW.md` | 删除或移到 `.github/` |
| 临时文件 | `*.tmp`, `*.bak` | 删除 |
| 测试数据 | `test_*.json` | 删除或移到 `tests/` |
| 内部规范 | `T2-TASK.md` | 删除（不公开） |

---

## 九、最终仓库结构示例

整理后的 price-monitor 仓库结构：

```
price-monitor/
├── .env.example              # 环境变量模板
├── .github/
│   ├── FUNDING.yml           # 赞助配置
│   ├── ISSUE_TEMPLATE/
│   │   └── bug-report.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── .gitignore                # 排除规则
├── CONTRIBUTING.md           # 贡献指南
├── FEATURES.md               # 功能清单
├── GITHUB-UPLOAD-GUIDE.md    # 上传规范（本文件）
├── LICENSE                   # MIT 许可证
├── README.md                 # 项目首页
├── SECURITY.md               # 安全策略
├── SKILL.md                  # OpenClaw 技能描述
└── scripts/
    ├── main.py               # 主程序
    └── auto-check.py         # 定时检查脚本
```

**注意：`data/` 目录及其内容不应出现在仓库中（已被 .gitignore 排除）。**
