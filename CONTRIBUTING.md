# 贡献指南

感谢你对本项目的关注！欢迎参与贡献！🎉

## 🤝 如何贡献

### 1. 报告问题

发现问题了？[提交 Issue](https://github.com/Kumagt/price-monitor/issues) 告诉我们！

**提交前请检查：**
- [ ] 是否已有相同 Issue
- [ ] 问题是否可以复现
- [ ] 是否提供了详细信息（平台、商品 ID、错误日志等）

### 2. 提出建议

有新功能想法？[提交 Feature Request](https://github.com/Kumagt/price-monitor/issues)！

**建议格式：**
- 这个功能解决了什么问题
- 你期望的实现方式
- 优先级（低/中/高）

### 3. 提交代码

想直接参与开发？太好了！

**流程：**
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

**代码规范：**
- 遵循 PEP 8 风格指南
- 添加必要的注释
- 确保代码可运行
- 更新相关文档

### 4. 分享使用体验

- 给个 Star ⭐
- 推荐给朋友
- 写使用教程
- 社交媒体分享

---

## 📦 开发环境搭建

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

# 运行测试
uv run scripts/main.py --help
```

---

## 🧪 测试

### 单元测试

```bash
# 运行所有测试
uv run pytest tests/

# 运行特定测试
uv run pytest tests/test_price_check.py
```

### 手动测试

```bash
# 添加测试监控
uv run scripts/main.py add --source=1 --id=测试 ID --name="测试商品"

# 检查价格
uv run scripts/main.py check --id=1

# 查看历史
uv run scripts/main.py history --id=1
```

---

## 📝 文档贡献

文档也可以贡献！

**可以改进的地方：**
- 错别字纠正
- 表达优化
- 补充示例
- 翻译（如有需要）

---

## 💬 讨论

有疑问或想法？欢迎讨论！

- [GitHub Discussions](https://github.com/Kumagt/price-monitor/discussions)
- [Issue 评论区](https://github.com/Kumagt/price-monitor/issues)

---

## 📄 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们承诺：

- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

### 不可接受的行为

- 使用性化的语言或图像
- 人身攻击或侮辱性评论
- 公开或私下骚扰
- 未经许可发布他人信息
- 其他不道德或不专业的行为

---

## 🎯 项目愿景

让每个人都能轻松监控商品价格，不错过任何优惠！

**核心价值：**
- 免费开源
- 隐私优先（本地存储）
- 易于使用
- 持续改进

---

## 📧 联系方式

- GitHub: https://github.com/Kumagt
- 邮箱：[待填写]

---

## 🙏 致谢

感谢所有贡献者！你们让这个项目变得更好！❤️

[![Contributors](https://contrib.rocks/image?repo=Kumagt/price-monitor)](https://github.com/Kumagt/price-monitor/graphs/contributors)

---

**最后更新：** 2026-03-13
