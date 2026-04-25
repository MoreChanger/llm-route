# LLM-ROUTE 使用指南

轻量级 LLM API 路由工具，支持智能重试、协议转换和跨平台部署。

## 目录

- [安装](#安装)
- [配置](#配置)
- [运行方式](#运行方式)
- [Responses API 转换](#responses-api-转换)
- [日志系统](#日志系统)
- [预设管理](#预设管理)
- [重试机制](#重试机制)
- [配置 AI 工具](#配置-ai-工具)
- [常见问题](#常见问题)

---

## 安装

### 便携版

1. 从 [Releases](https://github.com/MoreChanger/llm-route/releases) 下载
2. 解压到任意目录
3. 编辑 `config.yaml`
4. 运行 `llm-route`

### 目录结构

```
llm-route/
├── llm-route.exe      # 主程序
├── config.yaml        # 配置文件
├── logs/              # 日志目录
│   ├── 2026-04-25.log
│   └── 2026-04-25.log.gz  # 自动压缩
└── presets/           # 预设目录
    ├── anthropic.yaml
    └── openai.yaml
```

---

## 配置

### 基本配置

```yaml
host: 127.0.0.1        # 监听地址
port: 8087             # 端口（或 "auto"）
log_level: 2           # 1=基础, 2=详细, 3=完整
log_retention_days: 7  # 日志保留天数
log_structured: false  # JSON 格式日志
```

### 上游服务

```yaml
upstreams:
  anthropic:
    url: https://api.anthropic.com
    protocol: anthropic
  openai:
    url: https://api.openai.com
    protocol: openai
    convert_responses: true  # 启用 Responses API 转换
```

### 路由规则

```yaml
routes:
  - path: /v1/messages
    upstream: anthropic
  - path: /v1/chat/completions
    upstream: openai
  - path: /v1/responses
    upstream: openai
  - path: /v1/models
    upstream: openai
```

### 重试规则

```yaml
retry_rules:
  - status: 400
    body_contains: "overloaded"
    max_retries: 10
    delay: 2
    jitter: 1
  - status: 429
    max_retries: 10
    delay: 2
    jitter: 1
  - status: 500
    max_retries: 5
    delay: 3
    jitter: 1
```

重试延迟：`delay + attempt × jitter`

---

## 运行方式

### 桌面模式

双击运行，系统托盘管理：

| 菜单 | 功能 |
|------|------|
| 复制代理地址 | 复制 `http://127.0.0.1:端口` |
| 日志详情 | 打开日志窗口 |
| 日志等级 | 基础/详细/完整 |
| 启动/停止 | 切换服务状态 |
| 更换端口 | 动态修改端口 |
| 加载预设 | 切换配置 |
| 开机自启 | Windows 自动启动 |

### 命令行

```bash
llm-route                    # 托盘模式
llm-route --headless         # 无头模式
llm-route --port 9000        # 指定端口
llm-route --port auto        # 随机端口
llm-route --config my.yaml   # 自定义配置
```

### Docker

```bash
# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# Web 管理界面
http://localhost:8087/_admin
# 默认密码: 123456（首次登录后请修改）
```

**修改密码权限问题：**

如果密码保存失败，在宿主机执行：
```bash
chmod 666 config.yaml
```

---

## Responses API 转换

将 OpenAI Responses API 转换为 Chat Completions API，使不支持的模型服务也能兼容。

### 启用

```yaml
upstreams:
  openai:
    url: https://api.example.com
    protocol: openai
    convert_responses: true

routes:
  - path: /v1/responses
    upstream: openai
```

### 支持功能

| 功能 | 状态 |
|------|------|
| 文本生成 | ✅ |
| 流式响应 | ✅ |
| 工具调用 (Function Calling) | ✅ |
| 多轮对话 (previous_response_id) | ✅ |
| 系统指令 (instructions) | ✅ |

### 示例

```bash
# 文本生成
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"model":"gpt-4o","input":"Hello"}'

# 工具调用
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model":"gpt-4o",
    "input":"What is the weather?",
    "tools":[{"type":"function","name":"get_weather","parameters":{...}}]
  }'
```

详见 [Responses-API-转换](Responses-API-转换) 页面。

---

## 日志系统

### 特性

- **自动滚动** — 单文件最大 10MB，自动创建新文件
- **自动压缩** — 超过 1 天的日志自动 gzip 压缩
- **自动清理** — 超过保留天数的日志自动删除
- **高效分页** — seek 定位，大文件低内存占用
- **异步写入** — 后台线程批量写入，不阻塞请求

### 日志等级

| 等级 | 内容 |
|------|------|
| 1 基础 | 路径、方法、状态码 |
| 2 详细 | + 耗时、重试次数 |
| 3 完整 | + 请求/响应体 |

### WebUI 日志统计

Docker 部署可在 Web 管理界面查看：
- 当前日志文件、大小、行数
- 日志文件总数
- 压缩文件数
- 总日志大小

---

## 预设管理

预设文件放在 `presets/` 目录，用于快速切换上游配置。

### 内置预设

| 文件 | 说明 |
|------|------|
| `anthropic.yaml` | Anthropic 官方 API |
| `openai.yaml` | OpenAI 官方 API |

### 自定义预设

```yaml
# presets/my-provider.yaml
upstreams:
  myapi:
    url: https://api.example.com
    protocol: openai

routes:
  - path: /v1/chat/completions
    upstream: myapi

retry_rules:
  - status: 429
    max_retries: 5
    delay: 1
    jitter: 0.5
```

---

## 重试机制

### 触发条件

- `400` + `body_contains` 匹配
- `429` 速率限制
- `500` 服务器错误

### 流式请求

SSE 流式请求同样支持重试，重试时重新发起完整请求。

---

## 配置 AI 工具

### Claude Code

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8087
```

### Cursor

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8087
```

### Cherry Studio

1. API 地址：`http://127.0.0.1:8087`
2. 选择 Responses API 格式
3. 工具调用自动支持

### Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8087/v1",
    api_key="your-key"
)
```

---

## 常见问题

### 端口被占用？

启动时自动检测，找到下一个可用端口。或使用 `--port auto`。

### Docker 密码保存失败？

```bash
chmod 666 config.yaml
```

### 工具调用不生效？

1. 确认上游支持 Function Calling
2. 设置日志等级为"完整"查看详情
3. 检查工具定义格式

### 支持哪些 API？

- Anthropic Messages API (`/v1/messages`)
- OpenAI Chat Completions (`/v1/chat/completions`)
- OpenAI Responses API (`/v1/responses`) — 需启用转换
- 模型列表 (`/v1/models`, `/models`)

### 支持 HTTPS？

仅 HTTP 代理。需要 HTTPS 请配合 nginx 等反向代理使用。

---

## 反馈

- [GitHub Issues](https://github.com/MoreChanger/llm-route/issues)
- [GitHub Repository](https://github.com/MoreChanger/llm-route)
