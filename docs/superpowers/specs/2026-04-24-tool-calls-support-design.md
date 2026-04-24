# Responses API Tool Calls 支持设计

## 概述

为 LLM-ROUTE 的 Responses API 转换功能添加完整的工具调用（Tool Calls）支持，包括请求和响应的双向转换，以及流式输出支持。

## 背景

当前 Responses API 转换只支持基本的文本对话，不支持工具调用。需要扩展以支持：

1. 模型调用工具 → 客户端执行
2. 客户端提交工具结果 → 模型继续生成

## 数据模型扩展

### 新增事件类型（`src/responses_models.py`）

```python
# 工具调用参数流式增量
class ToolCallArgumentsDelta:
    type: str = "response.function_call_arguments.delta"
    item_id: str        # 工具调用 ID
    output_index: int   # 输出索引
    delta: str          # 参数片段

# 工具调用参数完成
class ToolCallArgumentsDone:
    type: str = "response.function_call_arguments.done"
    id: str             # 工具调用 ID
    output_index: int   # 输出索引
    arguments: str      # 完整参数 JSON

# 工具调用创建
class ToolCallsCreated:
    type: str = "response.tool_calls.created"
    item_id: str
    output_index: int
    tool_call: dict     # {id, name, arguments}
```

## 请求转换

### 输入类型处理

扩展 `_parse_input` 方法，支持以下输入类型：

#### 1. function_call_output（工具执行结果）

客户端提交工具执行结果：

```json
{
  "type": "function_call_output",
  "call_id": "call_xxx",
  "output": "工具执行结果"
}
```

转换为 Chat Completions 格式：

```json
{
  "role": "tool",
  "tool_call_id": "call_xxx",
  "content": "工具执行结果"
}
```

#### 2. function_call（历史工具调用）

历史对话中的工具调用：

```json
{
  "type": "function_call",
  "id": "call_xxx",
  "name": "get_weather",
  "arguments": "{\"location\": \"Beijing\"}"
}
```

转换为 assistant 消息：

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [{
    "id": "call_xxx",
    "type": "function",
    "function": {
      "name": "get_weather",
      "arguments": "{\"location\": \"Beijing\"}"
    }
  }]
}
```

## 响应转换

### 非流式响应

Chat Completions 响应中的 `tool_calls`：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_xxx",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\": \"Beijing\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

转换为 Responses API 格式：

```json
{
  "output": [{
    "type": "function_call",
    "id": "call_xxx",
    "call_id": "call_xxx",
    "name": "get_weather",
    "arguments": "{\"location\": \"Beijing\"}",
    "status": "completed"
  }]
}
```

### 流式响应

#### 事件顺序

```
1. response.created
2. response.output_item.added (type: function_call)  -- 工具调用开始
3. response.function_call_arguments.delta (多次)     -- 参数流式输出
4. response.function_call_arguments.done             -- 参数完成
5. response.output_item.done                         -- 工具调用结束
6. response.completed
```

#### 处理逻辑

1. **检测 tool_calls 开始**
   - 条件：`delta.tool_calls` 存在且包含 `id` 字段
   - 动作：发送 `response.output_item.added` 事件

2. **处理参数流式输出**
   - 条件：`delta.tool_calls[].function.arguments` 有内容
   - 动作：发送 `response.function_call_arguments.delta` 事件

3. **工具调用完成**
   - 条件：`finish_reason` 为 `tool_calls`
   - 动作：发送 `response.function_call_arguments.done` 和 `response.output_item.done` 事件

#### SSE 事件示例

```
data: {"type": "response.output_item.added", "output_index": 0, "item": {"type": "function_call", "id": "call_xxx", "name": "get_weather", "status": "in_progress"}}

data: {"type": "response.function_call_arguments.delta", "item_id": "call_xxx", "output_index": 0, "delta": "{\"loc"}

data: {"type": "response.function_call_arguments.delta", "item_id": "call_xxx", "output_index": 0, "delta": "ation\": \"Beijing\"}"}

data: {"type": "response.function_call_arguments.done", "id": "call_xxx", "output_index": 0, "arguments": "{\"location\": \"Beijing\"}"}

data: {"type": "response.output_item.done", "output_index": 0, "item": {"type": "function_call", "id": "call_xxx", "name": "get_weather", "arguments": "{\"location\": \"Beijing\"}", "status": "completed"}}
```

## 实现要点

### 1. 状态跟踪

流式转换过程中需要维护工具调用状态：

```python
tool_calls = {}  # {index: {id, name, arguments, item_id, output_index}}
tool_call_counter = 0
```

### 2. 并行工具调用

支持同一响应中的多个并行工具调用，每个工具调用有独立的 `output_index`。

### 3. 会话历史

工具调用消息需要正确保存到会话历史，支持 `previous_response_id` 恢复上下文。

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `src/responses_models.py` | 新增工具调用相关数据类 |
| `src/responses_converter.py` | 扩展请求/响应/流式转换逻辑 |

## 测试要点

1. 单个工具调用的非流式响应
2. 单个工具调用的流式响应
3. 并行多个工具调用
4. 客户端提交工具结果后继续对话
5. 带历史对话的工具调用恢复
