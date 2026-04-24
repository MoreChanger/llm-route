# LLM-ROUTE

轻量级 LLM API 路由工具，支持自动重试和系统托盘。

> 本项目旨在解决大模型厂商超售导致请求频繁超时或出错的问题，通过智能重试机制提高 API 调用的稳定性。

## 功能

- **反向代理** — 支持 Anthropic 和 OpenAI 协议，根据路径自动路由
- **智能重试** — 上游返回 400/429/500 等错误时自动重试
- **SSE 流式支持** — 支持流式请求，出错时自动重试
- **格式转换** — 自动转换请求格式，提高服务商兼容性
  - Anthropic Messages API：`content` 数组格式自动转换为字符串格式
  - Responses API：转换为 Chat Completions API，兼容更多模型服务
- **Responses API 转换** — 支持工具调用（Function Calling）、多轮对话
- **系统托盘** — 最小化到托盘，右键菜单控制
- **端口管理** — 自动检测端口占用，支持手动指定或随机分配

## 快速开始

### 1. 配置

编辑 `config.yaml`：

```yaml
host: 127.0.0.1
port: 8087

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
```

### 2. 运行

双击 `llm-route.exe` 启动，服务自动运行。

或在命令行运行：

```bash
llm-route                    # 托盘模式
llm-route --headless         # 无头模式
llm-route --port 9000        # 指定端口
llm-route --config my.yaml   # 指定配置文件
```

### 3. 配置 AI 工具

**Claude Code:**

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8087
```

**Cursor:**

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8087
```

**Cherry Studio:**

在 Cherry Studio 中配置：
- API 地址：`http://127.0.0.1:8087`
- 模型选择：使用 `/v1/responses` 端点
- 工具调用：自动支持

## 托盘菜单

- 复制代理地址
- 日志详情
- 日志等级（基础/详细/完整）
- 启动/停止服务
- 更换端口
- 加载预设
- 开机自启
- 退出

## 日志系统

日志文件存放在 `logs/` 目录，按启动时间命名（如 `2026-04-22_10-30-00.log`）。

**日志等级：**
- **基础信息** — 请求路径、方法、上游服务、响应状态码
- **详细信息** — 基础信息 + 请求耗时、重试次数（默认）
- **完整信息** — 详细信息 + 请求/响应体

**日志窗口：**
- 支持分页浏览（50/100/200/500/1000 行/页）
- 打开时自动跳转到最新日志
- 自动刷新最新日志
- 可跳转指定页码

## 格式转换

LLM-ROUTE 自动转换请求格式，提高与各服务商的兼容性。

### Anthropic Messages API 格式转换

部分服务商（如京东云）不支持 `content` 数组格式，LLM-ROUTE 会自动转换：

```
# 数组格式 → 字符串格式
[{"type": "text", "text": "hello"}] → "hello"

# 多元素数组合并
[{"type": "text", "text": "hello"}, {"type": "text", "text": " world"}] → "hello world"

# 包含图片等非文本内容，保持原格式
[{"type": "text", "text": "hello"}, {"type": "image", ...}] → 保持原格式
```

此功能对 `/v1/messages` 请求自动启用，无需额外配置。

## Responses API 转换

支持将 OpenAI Responses API 请求转换为 Chat Completions API 格式，使不支持 Responses API 的模型服务也能兼容。

### 启用方式

在 upstream 配置中添加 `convert_responses: true`，并添加 `/v1/responses` 路由：

```yaml
upstreams:
  openai:
    url: https://your-api-endpoint
    protocol: openai
    convert_responses: true

routes:
  - path: /v1/responses
    upstream: openai
```

### 支持的功能

| 功能 | 支持状态 |
|-----|---------|
| 文本生成 | ✅ |
| 流式响应 | ✅ |
| 工具调用 (Function Calling) | ✅ |
| 多轮对话 (previous_response_id) | ✅ |
| instructions 系统指令 | ✅ |
| 输入格式 (字符串/Items) | ✅ |

### 转换说明

**请求转换：**
- `input` 字段 → `messages` 数组
- `instructions` 字段 → `system` 消息
- `previous_response_id` → 从会话存储获取历史消息
- 工具定义格式自动转换

**响应转换：**
- Chat Completions 响应 → Responses API Item 格式
- `tool_calls` → `function_call` Items
- 文本内容 → `message` Item
- 流式响应转换为标准 SSE 事件序列

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

**简单请求：**

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "Hello, how are you?"
  }'
```

**带工具调用：**

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
    }]
  }'
```

**多轮对话：**

```bash
# 第一轮
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "My name is Alice"
  }'

# 响应返回 {"id": "resp_xxx", ...}

# 第二轮（引用上一轮）
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "What is my name?",
    "previous_response_id": "resp_xxx"
  }'
```

## 预设

预设文件存放在 `presets/` 目录，切换预设后自动更新配置。

内置预设：
- `openai.yaml` — OpenAI 官方 API
- `anthropic.yaml` — Anthropic 官方 API
- `jdcloud.yaml` — JD Cloud 模型服务

添加新预设只需在 `presets/` 目录创建 `.yaml` 文件即可自动识别。

## 从源码运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python -m src.main
```

## 开发

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest

# 打包
pyinstaller build.spec
```

## License

MIT
