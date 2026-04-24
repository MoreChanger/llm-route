# LLM-ROUTE 使用指南

LLM-ROUTE 是一个轻量级 LLM API 路由工具，支持自动重试、预设切换和系统托盘管理。

## 目录

- [安装与运行](#安装与运行)
- [配置说明](#配置说明)
- [Responses API 转换](#responses-api-转换)
- [托盘功能](#托盘功能)
- [日志系统](#日志系统)
- [预设系统](#预设系统)
- [重试机制](#重试机制)
- [命令行参数](#命令行参数)
- [配置 AI 工具](#配置-ai-工具)
- [从源码构建](#从源码构建)
- [常见问题](#常见问题)

---

## 安装与运行

### 便携版

1. 从 [Releases](https://github.com/MoreChanger/llm-route/releases) 下载最新版本的 ZIP 文件
2. 解压到任意目录
3. 编辑 `config.yaml` 配置上游服务
4. 双击 `llm-route.exe` 启动

### 目录结构

```
llm-route/
├── llm-route.exe      # 主程序
├── config.yaml        # 配置文件
├── logs/              # 日志目录
│   └── 2026-04-22_10-30-00.log
└── presets/           # 预设目录
    ├── anthropic.yaml
    ├── jdcloud.yaml
    └── openai.yaml
```

---

## 配置说明

### 基本配置

```yaml
# 监听地址
host: 127.0.0.1

# 端口（数字或 "auto" 随机分配）
port: 8087

# 日志等级（1=基础, 2=详细, 3=完整）
log_level: 2
```

### 上游服务 (upstreams)

定义后端 LLM API 服务：

```yaml
upstreams:
  anthropic:
    url: https://api.anthropic.com
    protocol: anthropic    # 支持 anthropic 或 openai
  openai:
    url: https://api.openai.com
    protocol: openai
```

### 路由规则 (routes)

将请求路径映射到上游服务：

```yaml
routes:
  - path: /v1/messages         # Anthropic Messages API
    upstream: anthropic
  - path: /v1/chat/completions # OpenAI Chat API
    upstream: openai
  - path: /v1/models           # 模型列表
    upstream: openai
```

### 重试规则 (retry_rules)

配置自动重试策略：

```yaml
retry_rules:
  - status: 400
    body_contains: "overloaded"  # 可选：匹配响应体内容
    max_retries: 10
    delay: 2                     # 基础延迟（秒）
    jitter: 1                    # 随机抖动（秒）
  - status: 429                  # 速率限制
    max_retries: 10
    delay: 2
    jitter: 1
  - status: 500                  # 服务器错误
    max_retries: 5
    delay: 3
    jitter: 1
```

重试延迟计算：`delay + attempt × jitter`

---

## Responses API 转换

LLM-ROUTE 支持将 OpenAI Responses API 请求转换为 Chat Completions API 格式，使不支持 Responses API 的模型服务也能兼容。

### 更新日志

**v1.3.0 (2026-04-24)** 新增：
- ✅ 完整的流式响应 SSE 事件转换
- ✅ 工具调用（Function Calling）支持
- ✅ 多轮对话（`previous_response_id`）
- ✅ Cherry Studio 兼容测试通过

### 启用转换

在 upstream 配置中添加 `convert_responses: true`，并添加 `/v1/responses` 路由：

```yaml
upstreams:
  openai:
    url: https://api.openai.com
    protocol: openai
    convert_responses: true  # 启用 Responses API 转换

routes:
  - path: /v1/chat/completions
    upstream: openai
  - path: /v1/responses      # Responses API 路由
    upstream: openai
```

### 支持的功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| 文本生成 | ✅ | 完全支持 |
| 流式响应 | ✅ | SSE 格式转换 |
| 工具调用 | ✅ | Function Calling |
| 多轮对话 | ✅ | previous_response_id |
| 系统指令 | ✅ | instructions 字段 |
| 输入格式 | ✅ | 字符串和 Items 格式 |

### 转换说明

**请求转换：**
- Responses API 的 `input` 字段转换为 Chat Completions 的 `messages`
- `instructions` 字段转换为 `system` 消息
- `previous_response_id` 用于加载历史对话上下文

**响应转换：**
- Chat Completions 流式响应转换为 Responses API SSE 事件格式
- 支持流式和非流式请求

**流式事件序列：**
```
response.created
response.in_progress
response.output_item.added      # 每个 Item 创建时
response.output_text.delta      # 文本增量
response.function_call_arguments.delta  # 工具参数增量
response.output_item.done       # 每个 Item 完成时
response.completed
```

### 使用示例

客户端发送 Responses API 请求：

```json
POST /v1/responses
{
  "model": "gpt-4o",
  "input": [{"role": "user", "content": "Hello"}],
  "stream": true
}
```

LLM-ROUTE 自动转换为 Chat Completions 格式发送到上游：

```json
POST /v1/chat/completions
{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true
}
```

### 工具调用示例

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "What is the weather in Beijing?",
    "tools": [{
      "type": "function",
      "name": "get_weather",
      "description": "Get weather for a city",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {"type": "string"}
        },
        "required": ["city"]
      }
    }],
    "stream": true
  }'
```

### 适用场景

- 使用只支持 Chat Completions API 的模型服务
- 兼容使用 Responses API 的客户端工具（如 Cherry Studio）
- 支持京东云、Ollama 等 OpenAI 兼容服务

### 详细文档

更多使用示例和技术细节，请参阅 [Responses-API-转换](Responses-API-转换) 页面。

---

## 托盘功能

运行后程序会最小化到系统托盘，右键菜单提供以下功能：

| 功能 | 说明 |
|------|------|
| 复制代理地址 | 将 `http://127.0.0.1:端口` 复制到剪贴板 |
| 日志详情 | 打开日志窗口查看请求记录 |
| 日志等级 | 切换日志详细程度（基础/详细/完整） |
| 启动/停止服务 | 切换代理服务运行状态 |
| 更换端口 | 动态修改监听端口 |
| 加载预设 | 切换不同的上游服务配置 |
| 开机自启 | 设置 Windows 开机自动启动 |
| 退出 | 关闭程序 |

### 托盘图标颜色

- 🟢 绿色：服务运行中
- 🔴 红色：服务已停止

---

## 日志系统

### 日志文件

日志文件存放在 `logs/` 目录，每次启动创建新文件：

```
logs/
├── 2026-04-22_10-30-00.log
├── 2026-04-22_14-15-30.log
└── ...
```

### 日志等级

| 等级 | 名称 | 显示内容 |
|------|------|----------|
| 1 | 基础信息 | 请求路径、方法、上游服务、响应状态码 |
| 2 | 详细信息 | 基础信息 + 请求耗时、重试次数（默认） |
| 3 | 完整信息 | 详细信息 + 请求/响应体 |

切换日志等级：托盘菜单 → 日志等级 → 选择等级

### 日志窗口

- **分页浏览** — 支持 50/100/200/500/1000 行每页
- **自动跳转** — 打开窗口时自动跳转到最新日志
- **自动刷新** — 在最后一页时自动显示新日志
- **跳转功能** — 可跳转到指定页码
- **滚动到底部** — 点击按钮快速跳转到最新日志

### 日志示例

```
[2026-04-22 10:30:05] INFO  服务启动，监听 127.0.0.1:8087
[2026-04-22 10:30:15] INFO  POST /v1/messages -> anthropic [200] 2765ms
[2026-04-22 10:30:20] INFO  GET /v1/models -> anthropic [200] 150ms
```

---

## 预设系统

预设文件存放在 `presets/` 目录，可以快速切换不同的上游服务配置。

### 内置预设

| 预设 | 说明 |
|------|------|
| `anthropic.yaml` | Anthropic 官方 API |
| `openai.yaml` | OpenAI 官方 API |
| `jdcloud.yaml` | JD Cloud 模型服务 |

### 创建自定义预设

1. 在 `presets/` 目录创建新的 `.yaml` 文件
2. 定义 `upstreams`、`routes` 和 `retry_rules`
3. 重启程序后，托盘菜单会自动显示新预设

示例预设文件：

```yaml
# presets/my-provider.yaml
upstreams:
  myapi:
    url: https://api.example.com
    protocol: openai

routes:
  - path: /v1/chat/completions
    upstream: myapi
  - path: /v1/models
    upstream: myapi

retry_rules:
  - status: 429
    max_retries: 5
    delay: 1
    jitter: 0.5
```

### 预设切换行为

切换预设时：
- `upstreams`、`routes`、`retry_rules` 会更新为新预设的值
- `host` 和 `port` 保持不变
- `config.yaml` 文件会被更新

---

## 重试机制

### 触发条件

当上游服务返回以下错误时自动重试：
- `400` Bad Request（需匹配 `body_contains`）
- `429` Too Many Requests
- `500` Internal Server Error

### 重试延迟

采用线性退避策略：

```
delay_1 = delay + 1 × jitter
delay_2 = delay + 2 × jitter
delay_3 = delay + 3 × jitter
...
```

示例：`delay: 2, jitter: 1`

| 重试次数 | 延迟 |
|---------|------|
| 1 | 3 秒 |
| 2 | 4 秒 |
| 3 | 5 秒 |
| ... | ... |

### 流式请求

SSE 流式请求同样支持重试，重试时会重新发起完整请求。

---

## 命令行参数

```bash
llm-route [选项]

选项:
  --headless          无头模式运行（不显示托盘）
  --config <path>     指定配置文件路径
  --port <port>       指定端口（数字或 "auto"）
```

### 示例

```bash
# 托盘模式（默认）
llm-route

# 无头模式（适合服务器部署）
llm-route --headless

# 指定端口
llm-route --port 9000

# 随机端口
llm-route --port auto

# 使用自定义配置文件
llm-route --config /path/to/config.yaml
```

### 环境变量

- `LLM_ROUTE_PORT`：覆盖端口配置（优先级最高）

```bash
export LLM_ROUTE_PORT=9000
llm-route
```

---

## 配置 AI 工具

### Claude Code

```bash
# Linux/macOS
export ANTHROPIC_BASE_URL=http://127.0.0.1:8087

# Windows PowerShell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8087"
```

### Cursor

```bash
# Linux/macOS
export OPENAI_BASE_URL=http://127.0.0.1:8087

# Windows PowerShell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8087"
```

### Cherry Studio

1. 设置 API 地址为 `http://127.0.0.1:8087`
2. 选择使用 Responses API 格式
3. 工具调用将自动支持

### 其他 OpenAI 兼容工具

任何支持自定义 `base_url` 的工具都可以使用 LLM-ROUTE：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8087/v1",
    api_key="your-api-key"
)
```

---

## 从源码构建

### 环境要求

- Python 3.11+
- pip

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/MoreChanger/llm-route.git
cd llm-route

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖
```

### 运行

```bash
python -m src.main
```

### 测试

```bash
pytest
```

### 打包

```bash
pip install pyinstaller
pyinstaller build.spec
```

打包后的可执行文件位于 `dist/` 目录。

---

## 常见问题

### Q: 端口被占用怎么办？

A: 程序启动时会自动检测端口占用，如果指定端口被占用，会自动寻找下一个可用端口。也可以在托盘菜单中选择"更换端口"或使用 `--port auto` 随机分配。

### Q: 如何查看请求日志？

A: 点击托盘菜单中的"日志详情"可以打开日志窗口，实时查看所有请求记录。

### Q: 支持哪些 API 协议？

A: 目前支持：
- Anthropic Messages API (`/v1/messages`)
- OpenAI Chat Completions API (`/v1/chat/completions`)
- OpenAI Responses API (`/v1/responses`) — 需启用转换
- 模型列表 API (`/v1/models`, `/models`)

### Q: 如何添加新的上游服务？

A: 有两种方式：
1. 编辑 `config.yaml` 添加新的 `upstreams` 和 `routes`
2. 创建预设文件到 `presets/` 目录

### Q: 重试会消耗额外的 API 配额吗？

A: 是的，每次重试都会发起新的 API 请求。建议合理配置 `max_retries` 和匹配条件 `body_contains`。

### Q: 支持 HTTPS 吗？

A: 目前仅支持 HTTP 代理。如需 HTTPS，建议配合反向代理工具（如 nginx）使用。

### Q: 如何关闭开机自启？

A: 取消勾选托盘菜单中的"开机自启"选项即可。

### Q: 工具调用不生效怎么办？

A: 
1. 确认上游服务支持 Function Calling
2. 检查日志等级设置为"完整信息"，查看请求/响应内容
3. 确认工具定义格式正确
4. 升级到 v1.3.0 或更高版本

---

## 反馈与贡献

- 问题反馈：[GitHub Issues](https://github.com/MoreChanger/llm-route/issues)
- 源代码：[GitHub Repository](https://github.com/MoreChanger/llm-route)
