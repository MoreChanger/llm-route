# LLM-Route Responses API 支持设计文档

在 llm-route 基础上添加 `/responses` 端点支持，将 Responses API 请求转换为 Chat Completions API，使 Codex CLI 等工具能与 Ollama、vLLM 等不支持 Responses API 的后端配合使用。

## 目标

1. **Responses API → Chat Completions 转换**：客户端请求 `/responses` 时，自动转换为 `/v1/chat/completions` 发送到上游
2. **会话历史管理**：通过 `previous_response_id` 维护多轮对话上下文
3. **配置化开关**：每个上游可独立配置是否启用转换
4. **流式支持**：支持 SSE 流式响应的转换

## 配置变更

### Upstream 配置扩展

```yaml
upstreams:
  ollama:
    url: http://localhost:11434/v1
    protocol: openai
    convert_responses: true   # 启用转换：/responses → /v1/chat/completions

  openai:
    url: https://api.openai.com
    protocol: openai
    convert_responses: false  # 禁用转换（默认值），直接透传
```

### 路由配置示例

```yaml
routes:
  - path: /responses
    upstream: ollama           # 使用支持转换的上游
  - path: /v1/chat/completions
    upstream: ollama
  - path: /v1/messages
    upstream: openai
```

### 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `convert_responses` | bool | false | 是否将 `/responses` 转换为 `/v1/chat/completions` |

## 新增模块

### 1. responses_models.py — 数据模型

Responses API 的请求/响应数据结构定义。

```python
from dataclasses import dataclass, field
from typing import Optional, Union

@dataclass
class ResponseInput:
    """Responses API 输入项"""
    type: str  # "message"
    role: str  # "user" | "assistant"
    content: Union[str, list[dict]]

@dataclass
class ResponsesRequest:
    """Responses API 请求"""
    model: str
    input: Union[list[ResponseInput], str]
    instructions: Optional[str] = None
    previous_response_id: Optional[str] = None
    tools: Optional[list[dict]] = None
    stream: bool = False

@dataclass
class ResponseContent:
    """Responses API 内容项"""
    type: str  # "output_text" | "refusal" 等
    text: str

@dataclass
class ResponsesOutput:
    """Responses API 输出"""
    type: str = "message"
    id: Optional[str] = None
    role: str = "assistant"
    content: list[ResponseContent] = field(default_factory=list)
    status: str = "completed"

@dataclass
class ResponsesResponse:
    """Responses API 响应"""
    id: str
    model: str
    output: ResponsesOutput
    previous_response_id: Optional[str] = None
```

### 2. session_manager.py — 会话管理

管理多轮对话的会话历史，通过 `previous_response_id` 关联。

```python
from dataclasses import dataclass
from typing import Optional
import time
import uuid

@dataclass
class Session:
    """会话数据"""
    response_id: str
    messages: list[dict]  # Chat Completions 格式消息
    created_at: float

class SessionManager:
    """会话管理器"""

    def __init__(
        self,
        max_sessions: int = 1000,
        ttl_seconds: int = 3600
    ):
        """
        Args:
            max_sessions: 最大会话数，超出时清理最旧
            ttl_seconds: 会话过期时间（秒）
        """
        self._sessions: dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds

    def get_messages(self, previous_response_id: Optional[str]) -> list[dict]:
        """获取历史消息

        Args:
            previous_response_id: 前一个响应的 ID

        Returns:
            消息列表，如果不存在或已过期返回空列表
        """
        if not previous_response_id:
            return []

        session = self._sessions.get(previous_response_id)
        if session is None:
            return []

        # 检查是否过期
        if time.time() - session.created_at > self._ttl_seconds:
            del self._sessions[previous_response_id]
            return []

        return session.messages.copy()

    def save_session(
        self,
        response_id: str,
        messages: list[dict]
    ) -> None:
        """保存会话

        超出上限时清理最旧的会话。
        """
        # 清理过期会话
        if len(self._sessions) >= self._max_sessions:
            self._cleanup_oldest()

        self._sessions[response_id] = Session(
            response_id=response_id,
            messages=messages,
            created_at=time.time()
        )

    def generate_response_id(self) -> str:
        """生成唯一 response_id

        格式：resp_{uuid}
        """
        return f"resp_{uuid.uuid4().hex[:24]}"

    def _cleanup_oldest(self) -> None:
        """清理最旧的会话"""
        if not self._sessions:
            return

        oldest_id = min(
            self._sessions.keys(),
            key=lambda k: self._sessions[k].created_at
        )
        del self._sessions[oldest_id]

    def cleanup_expired(self) -> int:
        """清理所有过期会话

        Returns:
            清理的会话数量
        """
        now = time.time()
        expired = [
            k for k, v in self._sessions.items()
            if now - v.created_at > self._ttl_seconds
        ]
        for k in expired:
            del self._sessions[k]
        return len(expired)
```

### 3. responses_converter.py — 转换逻辑

Responses API 与 Chat Completions API 的双向转换。

```python
import json
from typing import AsyncIterator, Optional
from dataclasses import dataclass

from src.responses_models import (
    ResponsesRequest, ResponsesResponse, ResponsesOutput,
    ResponseContent, ResponseInput
)
from src.session_manager import SessionManager

class ResponsesConverter:
    """Responses API 与 Chat Completions API 双向转换"""

    def __init__(self, session_manager: SessionManager):
        self.sessions = session_manager

    # ========== 请求转换 ==========

    def convert_request(self, req: ResponsesRequest) -> dict:
        """将 Responses 请求转换为 Chat Completions 请求体

        Args:
            req: Responses API 请求

        Returns:
            Chat Completions API 请求体（字典）
        """
        messages = []

        # 1. 获取历史消息（如果有 previous_response_id）
        if req.previous_response_id:
            messages.extend(self.sessions.get_messages(req.previous_response_id))

        # 2. 添加 system 指令
        if req.instructions:
            messages.append({
                "role": "system",
                "content": req.instructions
            })

        # 3. 添加当前输入
        messages.extend(self._parse_input(req.input))

        # 4. 构建请求体
        body = {
            "model": req.model,
            "messages": messages,
            "stream": req.stream
        }

        # 5. 转换工具（如果有）
        if req.tools:
            body["tools"] = self._convert_tools(req.tools)

        return body

    def _parse_input(
        self,
        input_data: Union[list[ResponseInput], str]
    ) -> list[dict]:
        """解析 Responses input 字段

        input 可能是：
        - 字符串：单轮用户输入
        - ResponseInput 列表：多轮对话
        """
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        messages = []
        for item in input_data:
            if item.type == "message":
                content = item.content
                if isinstance(content, list):
                    # 多模态内容，转换为 Chat Completions 格式
                    content = self._convert_content_input(content)
                messages.append({
                    "role": item.role,
                    "content": content
                })
        return messages

    def _convert_content_input(self, content: list[dict]) -> list[dict]:
        """转换 Responses 内容格式到 Chat Completions 格式"""
        # 内容格式基本兼容，直接返回
        return content

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """转换工具格式

        Responses API 和 Chat Completions API 的工具格式略有差异，
        需要进行转换。
        """
        converted = []
        for tool in tools:
            if tool.get("type") == "function":
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })
            else:
                converted.append(tool)
        return converted

    # ========== 响应转换 ==========

    def convert_response(
        self,
        chat_resp: dict,
        req: ResponsesRequest
    ) -> dict:
        """将 Chat Completions 响应转换为 Responses 响应

        Args:
            chat_resp: Chat Completions API 响应
            req: 原始 Responses API 请求

        Returns:
            Responses API 响应（字典）
        """
        response_id = self.sessions.generate_response_id()

        # 提取助手消息
        assistant_message = chat_resp["choices"][0]["message"]

        # 保存会话历史
        messages = self.sessions.get_messages(req.previous_response_id)
        if req.instructions:
            messages = [{"role": "system", "content": req.instructions}] + messages
        messages.extend(self._parse_input(req.input))
        messages.append(assistant_message)
        self.sessions.save_session(response_id, messages)

        # 构建响应
        return {
            "id": response_id,
            "model": chat_resp.get("model", req.model),
            "output": {
                "type": "message",
                "id": f"msg_{response_id}",
                "role": "assistant",
                "content": self._convert_output_content(assistant_message),
                "status": "completed"
            },
            "previous_response_id": req.previous_response_id
        }

    def _convert_output_content(self, message: dict) -> list[dict]:
        """转换 Chat Completions 消息内容到 Responses 格式"""
        content = message.get("content", "")

        # 处理工具调用
        if message.get("tool_calls"):
            # TODO: 转换工具调用格式
            pass

        return [{"type": "output_text", "text": content}]

    # ========== 流式转换 ==========

    async def convert_stream(
        self,
        chat_stream: AsyncIterator[bytes],
        req: ResponsesRequest
    ) -> AsyncIterator[bytes]:
        """将 Chat Completions SSE 流转换为 Responses SSE 流

        Args:
            chat_stream: Chat Completions SSE 字节流
            req: 原始 Responses API 请求

        Yields:
            Responses API SSE 事件字节
        """
        response_id = self.sessions.generate_response_id()

        # 1. 发送 response.created 事件
        yield self._format_sse("response.created", {
            "id": response_id,
            "model": req.model,
            "previous_response_id": req.previous_response_id,
            "status": "in_progress"
        })

        # 2. 发送 output_item.added 事件
        yield self._format_sse("response.output_item.added", {
            "output_index": 0,
            "item": {
                "type": "message",
                "id": f"msg_{response_id}",
                "role": "assistant",
                "status": "in_progress"
            }
        })

        # 3. 处理流式块
        full_content = ""
        async for chunk in chat_stream:
            events = self._parse_chat_chunk(chunk)
            for event in events:
                yield self._format_sse(event.get("event", "response.text.delta"), event)

        # 4. 发送 output_item.done 事件
        yield self._format_sse("response.output_item.done", {
            "output_index": 0,
            "item": {
                "type": "message",
                "id": f"msg_{response_id}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_content}],
                "status": "completed"
            }
        })

        # 5. 发送 response.completed 事件
        yield self._format_sse("response.completed", {
            "id": response_id,
            "status": "completed"
        })

        # 6. 保存会话
        messages = self.sessions.get_messages(req.previous_response_id)
        if req.instructions:
            messages = [{"role": "system", "content": req.instructions}] + messages
        messages.extend(self._parse_input(req.input))
        messages.append({"role": "assistant", "content": full_content})
        self.sessions.save_session(response_id, messages)

    def _parse_chat_chunk(self, chunk: bytes) -> list[dict]:
        """解析 Chat Completions SSE 块

        Returns:
            事件列表
        """
        # 解析 SSE 格式：data: {...}
        events = []
        try:
            lines = chunk.decode("utf-8").strip().split("\n")
            for line in lines:
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        continue
                    data = json.loads(data_str)
                    events.extend(self._convert_chat_delta(data))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return events

    def _convert_chat_delta(self, data: dict) -> list[dict]:
        """转换 Chat Completions delta 到 Responses 事件"""
        events = []
        choices = data.get("choices", [])

        for choice in choices:
            delta = choice.get("delta", {})
            content = delta.get("content", "")

            if content:
                events.append({
                    "event": "response.output_text.delta",
                    "type": "output_text",
                    "delta": content,
                    "output_index": choice.get("index", 0),
                    "content_index": 0  # 单一文本块，固定为 0
                })

        return events

    def _format_sse(self, event: str, data: dict) -> bytes:
        """格式化为 SSE 事件"""
        return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
```

## 现有模块变更

### config.py

添加 `convert_responses` 字段到 `Upstream` 类：

```python
@dataclass
class Upstream:
    """上游服务配置"""
    url: str
    protocol: str = "anthropic"
    convert_responses: bool = False  # 新增

def load_config(config_path: str) -> Config:
    # ...
    for name, upstream_data in upstreams_data.items():
        config.upstreams[name] = Upstream(
            url=upstream_data["url"],
            protocol=upstream_data.get("protocol", "anthropic"),
            convert_responses=upstream_data.get("convert_responses", False)  # 新增
        )
```

### proxy.py

添加 Responses API 处理分支：

```python
from src.responses_converter import ResponsesConverter
from src.session_manager import SessionManager
from src.responses_models import ResponsesRequest

class ProxyServer:
    def __init__(self, config: Config, log_manager: LogManager):
        # ... 原有代码 ...

        # 新增：Responses 转换器
        self.session_manager = SessionManager()
        self.responses_converter = ResponsesConverter(self.session_manager)

    def _should_convert_responses(self, ctx: RequestContext) -> bool:
        """判断是否需要转换 Responses API"""
        return (
            ctx.path == "/responses" and
            ctx.upstream is not None and
            ctx.upstream.convert_responses
        )

    async def handle_request(self, request: web.Request) -> web.Response:
        """处理所有请求"""
        # ... 匹配路由逻辑 ...

        # 新增：Responses API 转换分支
        if self._should_convert_responses(ctx):
            return await self._handle_responses(ctx)

        # ... 原有逻辑 ...

    async def _handle_responses(self, ctx: RequestContext) -> web.Response:
        """处理 /responses 请求（转换模式）"""
        import json

        # 1. 解析 Responses API 请求
        try:
            req_body = json.loads(ctx.body)
            responses_req = ResponsesRequest(
                model=req_body.get("model", ""),
                input=req_body.get("input", []),
                instructions=req_body.get("instructions"),
                previous_response_id=req_body.get("previous_response_id"),
                tools=req_body.get("tools"),
                stream=req_body.get("stream", False)
            )
        except (json.JSONDecodeError, KeyError) as e:
            return web.Response(status=400, text=f"Invalid request: {e}")

        # 2. 转换为 Chat Completions 请求
        chat_body = self.responses_converter.convert_request(responses_req)

        # 3. 构建上游 URL
        url = f"{ctx.upstream.url}/v1/chat/completions"

        # 4. 准备请求头
        headers = self._filter_headers(ctx.headers)
        headers["Content-Type"] = "application/json"

        # 5. 发送请求
        if responses_req.stream:
            return await self._forward_responses_streaming(
                ctx, url, headers, chat_body, responses_req
            )
        else:
            return await self._forward_responses(
                ctx, url, headers, chat_body, responses_req
            )

    async def _forward_responses(
        self,
        ctx: RequestContext,
        url: str,
        headers: dict,
        chat_body: dict,
        responses_req: ResponsesRequest
    ) -> web.Response:
        """非流式：发送 Chat Completions，转换响应"""
        import json

        try:
            async with self.client_session.post(
                url,
                json=chat_body,
                headers=headers
            ) as resp:
                if self._should_retry(resp.status, await resp.read(), ctx.attempt):
                    return await self._retry_responses(ctx, responses_req)

                chat_resp = await resp.json()
                responses_resp = self.responses_converter.convert_response(
                    chat_resp, responses_req
                )

                # 记录日志
                elapsed_ms = (time.time() - ctx.start_time) * 1000
                self.log_manager.log_request(
                    method=ctx.method,
                    path=ctx.path,
                    upstream=f"{ctx.matched_route.upstream} (converted)",
                    status_code=resp.status,
                    elapsed_ms=elapsed_ms,
                    retries=ctx.attempt,
                    request_body=json.dumps(chat_body),
                    response_body=json.dumps(responses_resp)
                )

                return web.Response(
                    status=200,
                    body=json.dumps(responses_resp),
                    content_type="application/json"
                )
        except aiohttp.ClientError as e:
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> [ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

            if ctx.attempt < self._get_max_retries():
                return await self._retry_responses(ctx, responses_req)
            return web.Response(status=502, text=f"Upstream error: {str(e)}")

    async def _forward_responses_streaming(
        self,
        ctx: RequestContext,
        url: str,
        headers: dict,
        chat_body: dict,
        responses_req: ResponsesRequest
    ) -> web.StreamResponse:
        """流式：转换 SSE 流"""
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(ctx._request)

        try:
            async with self.client_session.post(
                url,
                json=chat_body,
                headers=headers
            ) as upstream_resp:
                async for chunk in self.responses_converter.convert_stream(
                    upstream_resp.content.iter_any(),
                    responses_req
                ):
                    await response.write(chunk)

            # 记录日志
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log_manager.log_request(
                method=ctx.method,
                path=ctx.path,
                upstream=f"{ctx.matched_route.upstream} (converted/streaming)",
                status_code=200,
                elapsed_ms=elapsed_ms,
                retries=ctx.attempt,
                request_body=json.dumps(chat_body),
                response_body="[streaming response]"
            )
        except aiohttp.ClientError as e:
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> [STREAMING ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

        return response

    async def _retry_responses(
        self,
        ctx: RequestContext,
        responses_req: ResponsesRequest
    ) -> web.Response:
        """重试 Responses 请求"""
        delay = 1.0
        for rule in self.config.retry_rules:
            delay = max(delay, rule.delay)

        actual_delay = calculate_delay(ctx.attempt, delay, 0.5)
        await asyncio.sleep(actual_delay)

        ctx.attempt += 1
        return await self._handle_responses(ctx)
```

## 文件结构

```
llm-route/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── proxy.py               # 修改：添加 Responses 处理
│   ├── retry.py
│   ├── config.py              # 修改：添加 convert_responses 字段
│   ├── tray.py
│   ├── log_window.py
│   ├── port.py
│   ├── log_file.py
│   ├── single_instance.py
│   ├── responses_models.py    # 新增
│   ├── session_manager.py     # 新增
│   └── responses_converter.py # 新增
├── config.yaml                # 修改：添加配置示例
├── presets/
├── tests/
│   ├── test_responses_models.py    # 新增
│   ├── test_session_manager.py     # 新增
│   └── test_responses_converter.py # 新增
└── README.md
```

## 请求流程

```
客户端请求 /responses (Responses API 格式)
    ↓
proxy.py: handle_request()
    ↓
匹配路由，获取上游配置
    ↓
检查 convert_responses == true?
    ↓ 是
responses_converter.convert_request()
    ↓
转换为 Chat Completions 格式
    ↓
发送到上游 /v1/chat/completions
    ↓
收到 Chat Completions 响应
    ↓
responses_converter.convert_response() 或 convert_stream()
    ↓
转换为 Responses API 格式
    ↓
返回客户端
    ↓
session_manager.save_session() 保存会话
```

## 错误处理

1. **请求解析失败**：返回 400 Bad Request
2. **上游连接失败**：复用现有重试机制
3. **会话不存在**：视为新会话，`previous_response_id` 忽略
4. **会话过期**：自动清理，视为新会话

## 测试计划

1. **单元测试**
   - `test_responses_models.py`：数据模型解析和序列化
   - `test_session_manager.py`：会话存储、过期、清理
   - `test_responses_converter.py`：请求/响应转换逻辑

2. **集成测试**
   - 非流式请求转换
   - 流式请求转换
   - 多轮对话会话保持
   - 重试机制

3. **端到端测试**
   - Codex CLI → llm-route → Ollama
   - 验证完整请求/响应周期
