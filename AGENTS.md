# LLM-ROUTE 项目指南

本文档为 AI 助手和开发者提供项目上下文，帮助理解代码结构、约定和最佳实践。

## 项目概述

LLM-ROUTE 是一个轻量级 LLM API 路由工具，支持：
- 反向代理（Anthropic 和 OpenAI 协议）
- 智能重试机制
- Responses API 转换
- 系统托盘界面
- 跨平台支持（Windows、Linux、macOS、Docker）

## 目录结构

```
llm-route/
├── src/                    # 源代码
│   ├── main.py            # 入口点，信号处理
│   ├── proxy.py           # HTTP 代理服务器
│   ├── autostart.py       # 跨平台开机自启
│   ├── platform.py        # 平台能力检测
│   ├── tray.py            # 系统托盘界面
│   ├── config.py          # 配置加载
│   └── ...
├── tests/                  # 测试文件
├── docs/
│   ├── plans/             # 实现计划
│   └── solutions/         # 已解决的问题文档
├── presets/               # 配置预设
└── wiki/                  # 项目 Wiki
```

## 解决方案知识库

`docs/solutions/` 目录包含已解决的技术问题和最佳实践文档。在开始实现新功能或调试问题时，先搜索该目录可能有帮助：

- 按 YAML frontmatter 搜索：`module`、`component`、`tags` 字段
- 按目录浏览：`integration-issues/`、`best-practices/` 等
- 问题类型：Docker 信号处理、跨平台自启动、健康检查等

## 代码约定

### 跨平台兼容性

- 使用 `src/platform.py` 中的 `get_platform_level()` 检测平台能力
- 平台级别：Level 1（完整功能）、Level 2（托盘降级）、Level 3（headless）
- 不支持的平台功能应优雅降级，而非抛出异常

### 异步编程

- 使用 `asyncio.Event` 进行线程安全的信号处理
- 避免在信号处理器中调用 `asyncio.get_event_loop()`
- 使用 `asyncio.run_coroutine_threadsafe()` 从回调中调度协程

### 错误处理

- 遵循 Liskov 替换原则：子类方法不应抛出基类不抛出的异常
- 对于不支持的操作，返回 `False` 或使用 Null 对象模式
- 使用上下文管理器管理资源（注册表键、文件句柄）

### 配置文件生成

- XML 文件：使用 `xml.sax.saxutils.escape()` 转义特殊字符
- Desktop Entry 文件：转义 `%` 为 `%%`
- JSON：使用 `json.dumps()` 自动处理转义

## 测试

```bash
pytest                          # 运行所有测试
pytest --cov=src               # 带覆盖率
pytest tests/test_autostart.py # 特定测试文件
```

## 相关文档

- [README.md](README.md) — 用户文档和快速开始
- [docs/plans/](docs/plans/) — 功能实现计划
- [docs/solutions/](docs/solutions/) — 已解决的问题和最佳实践
