# LLM-ROUTE

轻量级 LLM API 路由工具，支持智能重试、协议转换和跨平台部署。

## 功能特性

- **反向代理** — 支持 Anthropic 和 OpenAI 协议，路径自动路由
- **智能重试** — 400/429/500 错误自动重试，支持流式请求
- **协议转换** — OpenAI Responses API ↔ Chat Completions API
- **预设管理** — 快速切换不同配置模板，支持应用前预览
- **Web 管理** — Docker 环境提供 Web 管理界面
- **系统托盘** — Windows/macOS/Linux 桌面托盘管理
- **日志管理** — 自动滚动、压缩、过期清理

## 快速开始

### 下载安装

从 [Releases](https://github.com/MoreChanger/llm-route/releases) 下载对应平台版本。

### 配置示例

```yaml
# config.yaml
host: 127.0.0.1
port: 8087
log_level: 2
log_retention_days: 7

upstreams:
  anthropic:
    url: https://api.anthropic.com
    protocol: anthropic
  openai:
    url: https://api.openai.com
    protocol: openai
    convert_responses: true  # 启用 Responses API 转换

routes:
  - path: /v1/messages
    upstream: anthropic
  - path: /v1/chat/completions
    upstream: openai
  - path: /v1/responses
    upstream: openai

retry_rules:
  - status: 429
    max_retries: 10
    delay: 2
    jitter: 1
  - status: 500
    max_retries: 5
    delay: 3
    jitter: 1
```

### 运行

```bash
# 桌面模式（托盘）
llm-route

# 无头模式
llm-route --headless

# 指定端口
llm-route --port 9000

# Docker
docker compose up -d
```

## Docker 部署

```bash
# 使用 Docker Compose
docker compose up -d

# 访问 Web 管理界面
http://localhost:8087/_admin
# 默认密码: 123456
```

### 预设管理

在 Web 管理界面中，可以使用预设功能快速切换配置：

1. 点击"预设"标签查看可用预设列表
2. 点击"应用"按钮预览预设内容（上游服务、路由规则、重试规则）
3. 确认后应用预设，配置立即生效
4. 当前激活的预设会在列表中标记显示

> 预设文件位于 `presets/` 目录，可自定义添加新预设

### Docker 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_ROUTE_PORT` | 监听端口 |
| `LLM_ROUTE_LOG_LEVEL` | 日志等级 (1-3) |

## 平台支持

| 功能 | Windows | Linux | macOS | Docker |
|------|---------|-------|-------|--------|
| 核心代理 | ✅ | ✅ | ✅ | ✅ |
| 系统托盘 | ✅ | ⚠️ | ✅ | ❌ |
| Web 管理 | ❌ | ❌ | ❌ | ✅ |

> Linux 托盘需要 `gir1.2-appindicator3-0.1` 和 `xclip`

## 配置 AI 工具

```bash
# Claude Code
export ANTHROPIC_BASE_URL=http://127.0.0.1:8087

# Cursor / 其他 OpenAI 兼容工具
export OPENAI_BASE_URL=http://127.0.0.1:8087
```

## 文档

- [使用指南 (Wiki)](../../wiki) — 详细配置和使用说明
- [预设管理](../../wiki/预设管理) — 预设功能详解
- [Responses API 转换](../../wiki/Responses-API-转换) — 协议转换详解

## 构建

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python -m src.main

# 打包
pip install pyinstaller
pyinstaller build.spec
```

## License

MIT
