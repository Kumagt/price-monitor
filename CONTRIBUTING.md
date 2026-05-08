# 贡献指南

感谢你对本项目的关注！欢迎参与贡献 🎉

## 如何贡献

### 报告问题

发现了 Bug？[提交 Issue](https://github.com/Kumagt/price-monitor/issues) 告诉我们。

**提交前请确认：**
- 没有重复的 Issue
- 提供了复现步骤和错误日志
- 注明了版本号和平台

### 提出建议

有新功能想法？[提交 Feature Request](https://github.com/Kumagt/price-monitor/issues)！

**建议时请说明：**
- 这个功能解决了什么问题
- 你期望的实现方式

### 提交代码

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'feat: add your feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 开启 Pull Request

**提交规范（Conventional Commits）：**
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `chore:` 构建/工具/配置变更
- `refactor:` 代码重构

**代码规范：**
- Python 3.11+ 兼容
- 使用 aiohttp 异步请求
- 函数/类添加文档字符串
- 确保代码可正常运行

### 分享项目

- 给个 Star ⭐
- 推荐给朋友
- 写使用教程

---

## 开发环境搭建

### 前置要求

- Python 3.11+
- uv（包管理）
- Git

### 安装步骤

```bash
git clone https://github.com/Kumagt/price-monitor.git
cd price-monitor

# 验证安装
uv run scripts/main.py --help
```

### 测试

```bash
# 添加测试监控
uv run scripts/main.py add --source=1 --id=测试ID --name="测试商品"

# 检查价格
uv run scripts/main.py check --id=1

# 启动 Web UI
uv run scripts/main.py webui

# 启动 API Server
uv run scripts/main.py api-server
```

---

## 文档贡献

文档也可以贡献！错别字纠正、表达优化、补充示例都欢迎。

---

## 联系方式

- GitHub: https://github.com/Kumagt

---

感谢所有贡献者！你们让这个项目变得更好 ❤️
