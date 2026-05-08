# 贡献指南

感谢你对本项目的关注！欢迎参与贡献 🎉

## 如何贡献

### 报告问题

发现了 Bug？[提交 Issue](https://github.com/Kumagt/price-monitor/issues) 告诉我们。

**提交前请确认：**
- 没有重复的 Issue
- 提供了复现步骤和错误日志

### 提出建议

有新功能想法？[提交 Feature Request](https://github.com/Kumagt/price-monitor/issues)！

**建议时请说明：**
- 这个功能解决了什么问题
- 你期望的实现方式

### 提交代码

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'Add your feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 开启 Pull Request

**代码规范：**
- 遵循 PEP 8 风格
- 添加必要的注释
- 确保代码可正常运行
- 更新相关文档

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
# 克隆仓库
git clone https://github.com/Kumagt/price-monitor.git
cd price-monitor

# 安装依赖
uv sync

# 验证安装
uv run scripts/main.py --help
```

### 手动测试

```bash
# 添加测试监控
uv run scripts/main.py add --source=1 --id=测试ID --name="测试商品"

# 检查价格
uv run scripts/main.py check --id=1

# 查看历史
uv run scripts/main.py history --id=1
```

---

## 文档贡献

文档也可以贡献！错别字纠正、表达优化、补充示例都欢迎。

---

## 讨论

有疑问或想法？欢迎在 [GitHub Discussions](https://github.com/Kumagt/price-monitor/discussions) 或 Issue 评论区交流。

---

## 联系方式

- GitHub: https://github.com/Kumagt

---

感谢所有贡献者！你们让这个项目变得更好 ❤️
