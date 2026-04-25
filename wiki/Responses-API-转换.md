# Responses API 转换功能

将 OpenAI Responses API 转换为 Chat Completions API，使不支持的模型服务也能兼容使用。

## 功能支持

| 功能 | 状态 | 说明 |
|------|------|------|
| 文本生成 | ✅ | 完全支持 |
| 流式响应 | ✅ | SSE 格式转换 |
| 工具调用 | ✅ | Function Calling |
| 多轮对话 | ✅ | previous_response_id |
| 系统指令 | ✅ | instructions 字段 |
| 输入格式 | ✅ | 字符串和 Items |

## 启用方式

```yaml
upstreams:
  openai:
    url: https://api.example.com
    protocol: openai
    convert_responses: true  # 启用转换

routes:
  - path: /v1/responses
    upstream: openai
```

## 使用示例

### 文本生成

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"model":"gpt-4o","input":"Hello"}'
```

### 流式响应

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"model":"gpt-4o","input":"Hello","stream":true}'
```

### 工具调用

```bash
curl http://127.0.0.1:8087/v1/responses \
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

### 多轮对话

```bash
# 第一轮
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"model":"gpt-4o","input":"My name is Alice"}'
# 返回 {"id": "resp_xxx", ...}

# 第二轮
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": "What is my name?",
    "previous_response_id": "resp_xxx"
  }'
```

### 提交工具结果

```bash
curl http://127.0.0.1:8087/v1/responses \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "gpt-4o",
    "input": [{
      "type": "function_call_output",
      "call_id": "call_xxx",
      "output": "{\"temperature\": 25}"
    }],
    "previous_response_id": "resp_previous"
  }'
```

## 流式事件

```
response.created
response.in_progress
response.output_item.added
response.output_text.delta
response.function_call_arguments.delta
response.output_item.done
response.completed
```

## 转换规则

### 请求转换

| Responses API | Chat Completions |
|---------------|------------------|
| `input` (string) | `messages: [{role: user}]` |
| `input` (Items) | `messages` (展开) |
| `instructions` | `messages: [{role: system}]` |
| `previous_response_id` | 从会话存储加载历史 |
| `tools` (内部标签) | `tools` (外部标签) |

### 响应转换

| Chat Completions | Responses API |
|------------------|---------------|
| `choices[0].message` | `output` Items |
| `message.tool_calls` | `function_call` Items |
| `message.content` | `message` Item |

## 会话存储

- 响应 ID 格式：`resp_xxx`
- 会话历史存储在内存中
- 服务重启后清空

## 兼容客户端

| 客户端 | 文本 | 工具 | 多轮 |
|--------|------|------|------|
| Cherry Studio | ✅ | ✅ | ✅ |
| Cursor | ✅ | - | - |
| Claude Code | ✅ | - | - |

## 故障排除

### 工具调用失败

1. 确认上游支持 Function Calling
2. 日志设为"完整"查看请求/响应
3. 检查 `call_id` 关联是否正确

### 多轮对话丢失上下文

1. 确认 `previous_response_id` 正确
2. 服务重启会清空会话存储

## 相关链接

- [OpenAI Responses API 文档](https://developers.openai.com/api/docs/guides/responses)
