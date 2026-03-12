# 发布说明 v1.0.0

**发布日期：** 2026-03-12

---

## 🎉 初次发布

这是价格监控技能的第一个正式版本！

---

## ✨ 功能特性

### 核心功能
- ✅ 支持 5 个电商平台（淘宝/京东/拼多多/抖音/快手）
- ✅ 添加/删除监控商品
- ✅ 自动价格检查
- ✅ 降价提醒（变化超过 5% 或达到目标价）
- ✅ 价格历史记录
- ✅ 可配置检查频率

### 技术特性
- ✅ 本地数据存储（隐私安全）
- ✅ 异步请求（高效）
- ✅ 错误处理完善
- ✅ 命令行界面友好

---

## 📦 安装方式

### ClawHub（推荐）
```bash
clawhub install price-monitor
```

### Git
```bash
git clone https://github.com/Kumagt/price-monitor.git
mv price-monitor ~/.openclaw/workspace/skills/
```

### 手动
下载本仓库文件到 `~/.openclaw/workspace/skills/price-monitor/`

---

## 🚀 快速开始

```bash
# 添加监控
uv run scripts/main.py add --source=1 --id=12345678 --name="iPhone 16" --target_price=5000

# 查看监控
uv run scripts/main.py list

# 检查价格
uv run scripts/main.py check --all
```

详细文档：[README.md](README.md)

---

## 📝 已知问题

### 1. GitHub 账号限制
ClawHub 发布需要 GitHub 账号满 14 天。目前可通过 Git 安装。

** workaround：** 使用 Git 或手动安装

### 2. 通知推送
目前仅支持命令行输出，后续版本将增加：
- 微信推送
- 钉钉推送
- 邮件通知

### 3. 商品 ID 获取
需要手动从商品链接提取 ID，后续考虑：
- 支持完整链接自动解析
- 浏览器插件一键添加

---

## 🗺️ 后续计划

### v1.1.0（预计 2026-03-20）
- [ ] 支持完整商品链接解析
- [ ] 增加微信推送
- [ ] 优化错误提示

### v1.2.0（预计 2026-03-27）
- [ ] 支持更多电商平台
- [ ] 价格趋势图表
- [ ] 批量导入导出

### v2.0.0（预计 2026-04）
- [ ] Web 界面
- [ ] 多用户支持
- [ ] 价格预测功能

---

## 🙏 致谢

感谢：
- OpenClaw 团队提供优秀的框架
- 买手 API 提供商品价格数据
- 所有测试用户和贡献者

---

## 📞 反馈与支持

- GitHub Issues: https://github.com/Kumagt/price-monitor/issues
- 邮箱：[待填写]
- 讨论区：https://github.com/Kumagt/price-monitor/discussions

---

## 📄 许可证

MIT License

---

**Happy Shopping! 🛒**
