# Responses API 转换功能

LLM-ROUTE 支持将 OpenAI Responses API 转换为 Chat Completions API，使不支持 Responses API 的模型服务也能兼容使用。

## 概述

Responses API 是 OpenAI 的新一代 API，相比 Chat Completions API 有以下优势：
- 更简洁的输入格式（`input` 字段代替 `messages`）
- 内置会话状态管理（`previous_response_id`）
- 统一的 Item 类型（`message`、`function_call`、`function_call_output`）
- 更好的推理模型支持（GPT-5 等）

通过 LLM-ROUTE 的转换功能，你可以在任何兼容 OpenAI Chat Completions API 的服务上使用 Responses API。

## 更新日志

### v1.3.0 (2026-04-24)

**新增功能：**
- 完整的流式响应 SSE 事件转换
- 工具调用（Function Calling）支持
- 多轮对话支持（`previous_response_id`）

**流式事件支持：**
- `response.created` / `response.in_progress`
- `response.output_item.added` / `response.output_item.done`
- `response.output_text.delta`
- `response.function_call_arguments.delta` / `response.function_call_arguments.done`
- `response.completed`

**兼容性测试：**
- ✅ Cherry Studio 工具调用测试通过

## 配置

### 启用转换

在 `config.yaml` 中配置：

```yaml
upstreams:
  openai:
    url: https://your-api-endpoint
    protocol: openai
    convert_responses: true  # 启用转换

routes:
  - path: /v1/responses
    upstream: openai
```

### 配置 AI 客户端

**Cherry Studio:**
1. 设置 API 地址为 `http://127.0.0.1:8087`
2. 选择使用 Responses API 格式
3. 工具调用将自动支持

**Cursor / Claude Code:**
```bash
export OPENAI_BASE_URL=http://127.0.0.1:8087
```

## 支持的功能

| 功能 | 状态 | 说明 |
|-----|------|------|
| 文本生成 | ✅ | 完全支持 |
| 流式响应 | ✅ | SSE 格式转换 |
| 工具调用 | ✅ | Function Calling |
| 多轮对话 | ✅ | previous_response_id |
| 系统指令 | ✅ | instructions 字段 |
| 输入格式 | ✅ | 字符串和 Items 格式 |

### 待支持功能

| 功能 | 状态 |
|-----|------|
| Structured Outputs | 🚧 计划中 |
| 内置工具 (web_search 等) | 🚧 计划中 |
| temperature/top_p 参数 | 🚧 计划中 |
| reasoning_effort 参数 | 🚧 计划中 |

## 使用示例

### 基本文本生成

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "Hello!"
  }'
```

响应：
```json
{
  "id": "resp_xxx",
  "object": "response",
  "model": "gpt-4o",
  "output": [{
    "type": "message",
    "id": "msg_xxx",
    "role": "assistant",
    "content": [{"type": "output_text", "text": "Hello! How can I help you?"}],
    "status": "completed"
  }],
  "status": "completed"
}
```

### 工具调用（流式）

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

**流式响应事件序列：**

```
data: {"type":"response.created","response":{...}}

data: {"type":"response.in_progress","response":{...}}

data: {"type":"response.output_item.added","response_id":"resp_xxx","output_index":0,"item":{"type":"function_call","id":"call_xxx","name":"get_weather","status":"in_progress"}}

data: {"type":"response.function_call_arguments.delta","response_id":"resp_xxx","item_id":"call_xxx","output_index":0,"delta":"{\"city\":"}

data: {"type":"response.function_call_arguments.delta","response_id":"resp_xxx","item_id":"call_xxx","output_index":0,"delta":"\"Beijing\"}"}

data: {"type":"response.function_call_arguments.done","response_id":"resp_xxx","item_id":"call_xxx","output_index":0,"arguments":"{\"city\":\"Beijing\"}"}

data: {"type":"response.output_item.done","response_id":"resp_xxx","output_index":0,"item":{"type":"function_call","id":"call_xxx","name":"get_weather","arguments":"{\"city\":\"Beijing\"}","status":"completed"}}

data: {"type":"response.completed","response":{...}}
```

### 多轮对话

```bash
# 第一轮
RESPONSE1=$(curl -s http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"model":"gpt-4o","input":"My name is Alice"}')

RESPONSE_ID=$(echo $RESPONSE1 | jq -r '.id')

# 第二轮（引用上一轮）
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d "{
    \"model\": \"gpt-4o\",
    \"input\": \"What is my name?\",
    \"previous_response_id\": \"$RESPONSE_ID\"
  }"
```

### 提交工具调用结果

当模型返回 `function_call` 后，客户端需要执行工具并将结果提交：

```bash
# 假设上一次响应返回了 function_call，call_id 为 "call_xxx"
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": [{
      "type": "function_call_output",
      "call_id": "call_xxx",
      "output": "{\"temperature\": 25, \"condition\": \"sunny\"}"
    }],
    "previous_response_id": "resp_previous"
  }'
```

### 带 instructions 的请求

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "instructions": "You are a helpful assistant. Always be concise.",
    "input": "Explain quantum computing"
  }'
```

## 技术细节

### 请求转换

| Responses API | Chat Completions API |
|--------------|---------------------|
| `input` (string) | `messages: [{role: user, content: ...}]` |
| `input` (Items) | `messages` (展开) |
| `instructions` | `messages: [{role: system, content: ...}]` (前置) |
| `previous_response_id` | 从会话存储获取历史消息 |
| `tools` (内部标签格式) | `tools` (外部标签格式) |

**工具格式转换示例：**

Responses API 格式：
```json
{
  "type": "function",
  "name": "get_weather",
  "description": "Get weather",
  "parameters": {...}
}
```

Chat Completions 格式：
```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get weather",
    "parameters": {...}
  }
}
```

### 响应转换

| Chat Completions | Responses API |
|-----------------|---------------|
| `choices[0].message` | `output` (Items 数组) |
| `message.tool_calls` | `function_call` Items |
| `message.content` | `message` Item |
| `tool_call_id` | `call_id` (用于关联) |

**输出 Item 顺序：**
1. `function_call` Items（如果有工具调用）
2. `message` Item（如果有文本内容）

### 会话存储

会话历史存储在内存中，重启服务后清空。

特性：
- 每个响应都有唯一 ID（格式：`resp_xxx`）
- 客户端通过 `previous_response_id` 获取历史上下文
- 支持分支对话（同一个 ID 可派生多个后续对话）

## 兼容客户端

以下客户端已测试通过：

| 客户端 | 文本生成 | 工具调用 | 多轮对话 |
|-------|---------|---------|---------|
| Cherry Studio | ✅ | ✅ | ✅ |
| Cursor | ✅ | - | - |
| Claude Code | ✅ | - | - |

## 故障排除

### 工具调用不生效

1. 确认上游服务支持 Function Calling
2. 检查日志等级设置为"完整信息"，查看请求/响应内容
3. 确认工具定义格式正确
4. 检查 `call_id` 是否正确关联

### 流式响应中断

1. 检查上游服务是否支持 SSE
2. 查看日志中的详细错误信息
3. 尝试非流式请求 (`"stream": false`) 确认上游响应正常

### 多轮对话丢失上下文

1. 确认 `previous_response_id` 正确传递
2. 注意服务重启后会话存储会清空
3. 检查响应 ID 格式是否正确

### SSE 事件格式错误

如果客户端报错 `text part xxx not found`：
- 这是 v1.3.0 之前版本的 bug
- 请升级到 v1.3.0 或更高版本

## 相关链接

- [OpenAI Responses API 官方文档](https://developers.openai.com/api/docs/guides/responses)
- [GitHub 仓库](https://github.com/MoreChanger/llm-route)
- [问题反馈](https://github.com/MoreChanger/llm-route/issues)
