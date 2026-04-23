# Responses API 支持实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 llm-route 中添加 `/responses` 端点支持，将 Responses API 请求转换为 Chat Completions API，使 Codex CLI 等工具能与 Ollama、vLLM 等后端配合使用。

**Architecture:** 新增三个独立模块（数据模型、会话管理、转换器），修改现有配置和代理模块以支持可配置的 API 转换。转换逻辑参考 open-responses-server 的实现，但移除 MCP 相关功能。

**Tech Stack:** Python 3.10+, aiohttp, dataclasses

---

## 文件结构

```
新增文件:
- src/responses_models.py     — Responses API 数据模型
- src/session_manager.py      — 会话历史管理
- src/responses_converter.py  — API 转换逻辑

修改文件:
- src/config.py               — Upstream 添加 convert_responses 字段
- src/proxy.py                — 添加 Responses 处理分支
- config.yaml                 — 添加配置示例

新增测试:
- tests/test_responses_models.py
- tests/test_session_manager.py
- tests/test_responses_converter.py
```

---

### Task 1: 数据模型 — responses_models.py

**Files:**
- Create: `src/responses_models.py`
- Test: `tests/test_responses_models.py`

- [ ] **Step 1: Write the failing test for ResponsesRequest**

```python
# tests/test_responses_models.py
"""Responses API 数据模型测试"""
import pytest
from src.responses_models import (
    ResponseInput, ResponsesRequest, ResponseContent,
    ResponsesOutput, ResponsesResponse
)


class TestResponseInput:
    def test_create_with_string_content(self):
        """测试字符串内容"""
        inp = ResponseInput(type="message", role="user", content="Hello")
        assert inp.type == "message"
        assert inp.role == "user"
        assert inp.content == "Hello"

    def test_create_with_list_content(self):
        """测试列表内容"""
        content = [{"type": "input_text", "text": "Hello"}]
        inp = ResponseInput(type="message", role="user", content=content)
        assert inp.content == content


class TestResponsesRequest:
    def test_create_minimal(self):
        """测试最小请求"""
        req = ResponsesRequest(model="gpt-4", input="Hello")
        assert req.model == "gpt-4"
        assert req.input == "Hello"
        assert req.instructions is None
        assert req.previous_response_id is None
        assert req.tools is None
        assert req.stream is False

    def test_create_full(self):
        """测试完整请求"""
        req = ResponsesRequest(
            model="gpt-4",
            input=[ResponseInput(type="message", role="user", content="Hi")],
            instructions="Be helpful",
            previous_response_id="resp_abc123",
            tools=[{"type": "function", "name": "test"}],
            stream=True
        )
        assert req.model == "gpt-4"
        assert req.instructions == "Be helpful"
        assert req.previous_response_id == "resp_abc123"
        assert len(req.tools) == 1
        assert req.stream is True


class TestResponseContent:
    def test_create(self):
        """测试内容项"""
        content = ResponseContent(type="output_text", text="Hello world")
        assert content.type == "output_text"
        assert content.text == "Hello world"


class TestResponsesOutput:
    def test_create_minimal(self):
        """测试最小输出"""
        output = ResponsesOutput()
        assert output.type == "message"
        assert output.role == "assistant"
        assert output.content == []
        assert output.status == "completed"

    def test_create_with_content(self):
        """测试带内容的输出"""
        content = ResponseContent(type="output_text", text="Hi")
        output = ResponsesOutput(id="msg_123", content=[content])
        assert output.id == "msg_123"
        assert len(output.content) == 1


class TestResponsesResponse:
    def test_create(self):
        """测试响应创建"""
        output = ResponsesOutput(id="msg_123")
        resp = ResponsesResponse(
            id="resp_abc",
            model="gpt-4",
            output=output,
            previous_response_id="resp_prev"
        )
        assert resp.id == "resp_abc"
        assert resp.model == "gpt-4"
        assert resp.previous_response_id == "resp_prev"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_responses_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.responses_models'"

- [ ] **Step 3: Write the implementation**

```python
# src/responses_models.py
"""Responses API 数据模型"""
from dataclasses import dataclass, field
from typing import Optional, Union


@dataclass
class ResponseInput:
    """Responses API 输入项"""
    type: str  # "message"
    role: str  # "user" | "assistant"
    content: Union[str, list]


@dataclass
class ResponsesRequest:
    """Responses API 请求"""
    model: str
    input: Union[list, str]
    instructions: Optional[str] = None
    previous_response_id: Optional[str] = None
    tools: Optional[list] = None
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
    content: list = field(default_factory=list)
    status: str = "completed"


@dataclass
class ResponsesResponse:
    """Responses API 响应"""
    id: str
    model: str
    output: ResponsesOutput
    previous_response_id: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_responses_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/Dev/llm-route && git add src/responses_models.py tests/test_responses_models.py && git commit -m "feat: add Responses API data models

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 会话管理 — session_manager.py

**Files:**
- Create: `src/session_manager.py`
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing test for SessionManager**

```python
# tests/test_session_manager.py
"""会话管理模块测试"""
import pytest
import time
from src.session_manager import Session, SessionManager


class TestSession:
    def test_create(self):
        """测试会话创建"""
        session = Session(
            response_id="resp_123",
            messages=[{"role": "user", "content": "Hi"}],
            created_at=time.time()
        )
        assert session.response_id == "resp_123"
        assert len(session.messages) == 1


class TestSessionManager:
    def test_create(self):
        """测试管理器创建"""
        manager = SessionManager()
        assert manager._sessions == {}

    def test_generate_response_id(self):
        """测试 ID 生成"""
        manager = SessionManager()
        id1 = manager.generate_response_id()
        id2 = manager.generate_response_id()

        assert id1.startswith("resp_")
        assert id2.startswith("resp_")
        assert id1 != id2

    def test_get_messages_empty(self):
        """测试获取空会话"""
        manager = SessionManager()
        messages = manager.get_messages(None)
        assert messages == []

        messages = manager.get_messages("nonexistent")
        assert messages == []

    def test_save_and_get_messages(self):
        """测试保存和获取"""
        manager = SessionManager()
        response_id = manager.generate_response_id()
        messages = [{"role": "user", "content": "Hello"}]

        manager.save_session(response_id, messages)
        retrieved = manager.get_messages(response_id)

        assert retrieved == messages
        # 确保返回的是副本
        retrieved.append({"role": "assistant", "content": "Hi"})
        assert len(manager.get_messages(response_id)) == 1

    def test_max_sessions_limit(self):
        """测试会话数量上限"""
        manager = SessionManager(max_sessions=3)

        for i in range(5):
            response_id = manager.generate_response_id()
            manager.save_session(response_id, [{"role": "user", "content": str(i)}])
            time.sleep(0.01)  # 确保时间顺序

        # 应该只有 3 个会话
        assert len(manager._sessions) == 3

    def test_session_expiry(self):
        """测试会话过期"""
        manager = SessionManager(ttl_seconds=0.1)

        response_id = manager.generate_response_id()
        manager.save_session(response_id, [{"role": "user", "content": "Hi"}])

        # 立即获取应该成功
        assert manager.get_messages(response_id) == [{"role": "user", "content": "Hi"}]

        # 等待过期
        time.sleep(0.2)

        # 过期后应该返回空
        assert manager.get_messages(response_id) == []

    def test_cleanup_expired(self):
        """测试清理过期会话"""
        manager = SessionManager(ttl_seconds=0.1)

        # 创建 3 个会话
        ids = []
        for i in range(3):
            response_id = manager.generate_response_id()
            manager.save_session(response_id, [{"role": "user", "content": str(i)}])
            ids.append(response_id)
            time.sleep(0.01)

        # 等待部分过期
        time.sleep(0.15)

        # 清理
        cleaned = manager.cleanup_expired()
        assert cleaned >= 1  # 至少清理了一个
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_session_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.session_manager'"

- [ ] **Step 3: Write the implementation**

```python
# src/session_manager.py
"""会话管理模块"""
from dataclasses import dataclass
from typing import Optional
import time
import uuid


@dataclass
class Session:
    """会话数据"""
    response_id: str
    messages: list  # Chat Completions 格式消息
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

    def get_messages(self, previous_response_id: Optional[str]) -> list:
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

    def save_session(self, response_id: str, messages: list) -> None:
        """保存会话

        超出上限时清理最旧的会话。
        """
        # 清理最旧会话
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_session_manager.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/Dev/llm-route && git add src/session_manager.py tests/test_session_manager.py && git commit -m "feat: add session manager for conversation history

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 转换器 — responses_converter.py

**Files:**
- Create: `src/responses_converter.py`
- Test: `tests/test_responses_converter.py`

- [ ] **Step 1: Write the failing test for ResponsesConverter**

```python
# tests/test_responses_converter.py
"""Responses API 转换器测试"""
import pytest
import json
from src.session_manager import SessionManager
from src.responses_converter import ResponsesConverter
from src.responses_models import ResponsesRequest, ResponseInput


class TestResponsesConverter:
    @pytest.fixture
    def converter(self):
        """创建转换器"""
        manager = SessionManager()
        return ResponsesConverter(manager)

    # ========== 请求转换测试 ==========

    def test_convert_request_simple_string_input(self, converter):
        """测试简单字符串输入转换"""
        req = ResponsesRequest(model="gpt-4", input="Hello")
        result = converter.convert_request(req)

        assert result["model"] == "gpt-4"
        assert result["stream"] is False
        assert len(result["messages"]) == 1
        assert result["messages"][0] == {"role": "user", "content": "Hello"}

    def test_convert_request_with_instructions(self, converter):
        """测试带系统指令的转换"""
        req = ResponsesRequest(
            model="gpt-4",
            input="Hello",
            instructions="Be helpful"
        )
        result = converter.convert_request(req)

        assert len(result["messages"]) == 2
        assert result["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert result["messages"][1] == {"role": "user", "content": "Hello"}

    def test_convert_request_with_history(self, converter):
        """测试带历史消息的转换"""
        # 先创建一个会话
        response_id = converter.sessions.generate_response_id()
        converter.sessions.save_session(response_id, [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ])

        req = ResponsesRequest(
            model="gpt-4",
            input="New question",
            previous_response_id=response_id
        )
        result = converter.convert_request(req)

        assert len(result["messages"]) == 3
        assert result["messages"][0] == {"role": "user", "content": "Previous question"}
        assert result["messages"][1] == {"role": "assistant", "content": "Previous answer"}
        assert result["messages"][2] == {"role": "user", "content": "New question"}

    def test_convert_request_with_tools(self, converter):
        """测试带工具的转换"""
        req = ResponsesRequest(
            model="gpt-4",
            input="Hello",
            tools=[{
                "type": "function",
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object"}
            }]
        )
        result = converter.convert_request(req)

        assert "tools" in result
        assert len(result["tools"]) == 1
        assert result["tools"][0]["type"] == "function"
        assert result["tools"][0]["function"]["name"] == "get_weather"

    def test_convert_request_with_streaming(self, converter):
        """测试流式请求"""
        req = ResponsesRequest(model="gpt-4", input="Hello", stream=True)
        result = converter.convert_request(req)

        assert result["stream"] is True

    def test_convert_request_list_input(self, converter):
        """测试列表输入格式"""
        req = ResponsesRequest(
            model="gpt-4",
            input=[
                {"type": "message", "role": "user", "content": "Hi"},
                {"type": "message", "role": "assistant", "content": "Hello!"},
                {"type": "message", "role": "user", "content": "How are you?"}
            ]
        )
        result = converter.convert_request(req)

        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][2]["role"] == "user"

    # ========== 响应转换测试 ==========

    def test_convert_response(self, converter):
        """测试响应转换"""
        req = ResponsesRequest(model="gpt-4", input="Hello")
        chat_resp = {
            "model": "gpt-4",
            "choices": [{
                "message": {"role": "assistant", "content": "Hi there!"}
            }]
        }

        result = converter.convert_response(chat_resp, req)

        assert result["id"].startswith("resp_")
        assert result["model"] == "gpt-4"
        assert result["output"]["type"] == "message"
        assert result["output"]["role"] == "assistant"
        assert len(result["output"]["content"]) == 1
        assert result["output"]["content"][0]["type"] == "output_text"
        assert result["output"]["content"][0]["text"] == "Hi there!"

    def test_convert_response_saves_session(self, converter):
        """测试响应转换保存会话"""
        req = ResponsesRequest(model="gpt-4", input="Hello")
        chat_resp = {
            "choices": [{
                "message": {"role": "assistant", "content": "Hi!"}
            }]
        }

        result = converter.convert_response(chat_resp, req)

        # 验证会话已保存
        saved_messages = converter.sessions.get_messages(result["id"])
        assert len(saved_messages) == 2  # user + assistant
        assert saved_messages[0]["role"] == "user"
        assert saved_messages[1]["role"] == "assistant"

    # ========== SSE 格式化测试 ==========

    def test_format_sse(self, converter):
        """测试 SSE 格式化"""
        data = {"id": "test", "status": "in_progress"}
        result = converter._format_sse("response.created", data)

        assert b"event: response.created" in result
        assert b'"id": "test"' in result
        assert result.endswith(b"\n\n")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_responses_converter.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.responses_converter'"

- [ ] **Step 3: Write the implementation**

```python
# src/responses_converter.py
"""Responses API 与 Chat Completions API 转换器"""
import json
from typing import AsyncIterator, Union

from src.responses_models import ResponsesRequest
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

    def _parse_input(self, input_data: Union[list, str]) -> list[dict]:
        """解析 Responses input 字段

        input 可能是：
        - 字符串：单轮用户输入
        - 字典列表：多轮对话
        """
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        messages = []
        for item in input_data:
            if isinstance(item, dict) and item.get("type") == "message":
                content = item.get("content", "")
                # 处理列表格式内容
                if isinstance(content, list):
                    text = ""
                    for content_item in content:
                        if isinstance(content_item, dict):
                            if content_item.get("type") == "input_text":
                                text += content_item.get("text", "")
                            elif content_item.get("type") == "text":
                                text += content_item.get("text", "")
                        elif isinstance(content_item, str):
                            text += content_item
                    content = text

                messages.append({
                    "role": item.get("role", "user"),
                    "content": content
                })
        return messages

    def _convert_tools(self, tools: list) -> list:
        """转换工具格式

        Responses API 和 Chat Completions API 的工具格式略有差异。
        """
        converted = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            if tool.get("type") == "function":
                func_data = {
                    "name": tool.get("name", ""),
                }
                if "description" in tool:
                    func_data["description"] = tool["description"]
                if "parameters" in tool:
                    func_data["parameters"] = tool["parameters"]

                converted.append({
                    "type": "function",
                    "function": func_data
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
        assistant_message = chat_resp.get("choices", [{}])[0].get("message", {})

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
                if event.get("delta"):
                    full_content += event["delta"]
                yield self._format_sse(event.get("event", "response.output_text.delta"), event)

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
        """解析 Chat Completions SSE 块"""
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
                    "content_index": 0
                })

        return events

    def _format_sse(self, event: str, data: dict) -> bytes:
        """格式化为 SSE 事件"""
        return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_responses_converter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/Dev/llm-route && git add src/responses_converter.py tests/test_responses_converter.py && git commit -m "feat: add Responses API to Chat Completions converter

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 配置扩展 — config.py

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test for convert_responses field**

```python
# 在 tests/test_config.py 末尾添加

class TestUpstreamConvertResponses:
    def test_upstream_convert_responses_default(self):
        """测试默认不转换"""
        upstream = Upstream(url="https://api.example.com")
        assert upstream.convert_responses is False

    def test_upstream_convert_responses_true(self):
        """测试启用转换"""
        upstream = Upstream(
            url="https://api.example.com",
            convert_responses=True
        )
        assert upstream.convert_responses is True

    def test_load_config_with_convert_responses(self, tmp_path: Path):
        """测试从配置文件加载 convert_responses"""
        config_content = """
upstreams:
  ollama:
    url: http://localhost:11434/v1
    protocol: openai
    convert_responses: true
  openai:
    url: https://api.openai.com
    protocol: openai
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config.upstreams["ollama"].convert_responses is True
        assert config.upstreams["openai"].convert_responses is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_config.py::TestUpstreamConvertResponses -v`
Expected: FAIL with "TypeError: Upstream.__init__() got an unexpected keyword argument 'convert_responses'"

- [ ] **Step 3: Modify config.py**

找到 `Upstream` 类定义，添加 `convert_responses` 字段：

```python
# src/config.py 修改

@dataclass
class Upstream:
    """上游服务配置"""
    url: str
    protocol: str = "anthropic"
    convert_responses: bool = False  # 新增：是否转换 /responses 为 /v1/chat/completions
```

同时修改 `load_config` 函数中加载上游配置的部分：

```python
# src/config.py 修改 load_config 函数

def load_config(config_path: str) -> Config:
    # ... 前面的代码保持不变 ...

    # 加载上游配置
    upstreams_data = data.get("upstreams", {})
    for name, upstream_data in upstreams_data.items():
        config.upstreams[name] = Upstream(
            url=upstream_data["url"],
            protocol=upstream_data.get("protocol", "anthropic"),
            convert_responses=upstream_data.get("convert_responses", False)  # 新增
        )

    # ... 后面的代码保持不变 ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/Dev/llm-route && git add src/config.py tests/test_config.py && git commit -m "feat: add convert_responses field to Upstream config

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 代理集成 — proxy.py

**Files:**
- Modify: `src/proxy.py`
- Modify: `tests/test_proxy.py`

- [ ] **Step 1: Write the failing test for Responses handling**

```python
# 在 tests/test_proxy.py 末尾添加

from src.responses_models import ResponsesRequest


class TestProxyResponsesHandling:
    @pytest.fixture
    def config_with_convert(self):
        """带转换功能的测试配置"""
        return Config(
            host="127.0.0.1",
            port=18088,
            upstreams={
                "ollama": Upstream(
                    url="http://localhost:11434/v1",
                    protocol="openai",
                    convert_responses=True
                ),
                "openai": Upstream(
                    url="https://api.openai.com",
                    protocol="openai",
                    convert_responses=False
                ),
            },
            routes=[
                Route(path="/responses", upstream="ollama"),
                Route(path="/v1/chat/completions", upstream="openai"),
            ],
            retry_rules=[]
        )

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    def test_should_convert_responses_true(self, config_with_convert, log_manager):
        """测试需要转换的情况"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/responses",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["ollama"]
        )

        assert server._should_convert_responses(ctx) is True
        log_manager.stop()

    def test_should_convert_responses_false_path(self, config_with_convert, log_manager):
        """测试路径不匹配"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/chat/completions",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["ollama"]
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_should_convert_responses_false_flag(self, config_with_convert, log_manager):
        """测试标志为 False"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/responses",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["openai"]
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_parse_responses_request(self, config_with_convert, log_manager):
        """测试解析 Responses 请求"""
        server = ProxyServer(config_with_convert, log_manager)

        body = json.dumps({
            "model": "gpt-4",
            "input": "Hello",
            "instructions": "Be helpful",
            "stream": True
        }).encode()

        req = server._parse_responses_request(body)

        assert req.model == "gpt-4"
        assert req.input == "Hello"
        assert req.instructions == "Be helpful"
        assert req.stream is True
        log_manager.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_proxy.py::TestProxyResponsesHandling -v`
Expected: FAIL with "AttributeError: 'ProxyServer' object has no attribute 'session_manager'"

- [ ] **Step 3: Modify proxy.py**

在 `ProxyServer` 类中添加 Responses 处理相关代码：

```python
# src/proxy.py 修改

# 在文件顶部添加导入
import json
import asyncio
from src.responses_converter import ResponsesConverter
from src.session_manager import SessionManager
from src.responses_models import ResponsesRequest
from src.retry import calculate_delay


class ProxyServer:
    def __init__(self, config: Config, log_manager: LogManager):
        self.config = config
        self.log_manager = log_manager
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.client_session: Optional[aiohttp.ClientSession] = None

        # 新增：Responses 转换器
        self.session_manager = SessionManager()
        self.responses_converter = ResponsesConverter(self.session_manager)

    # ... 原有方法保持不变 ...

    def _should_convert_responses(self, ctx: RequestContext) -> bool:
        """判断是否需要转换 Responses API"""
        return (
            ctx.path == "/responses" and
            ctx.upstream is not None and
            ctx.upstream.convert_responses
        )

    def _parse_responses_request(self, body: bytes) -> ResponsesRequest:
        """解析 Responses API 请求"""
        req_body = json.loads(body)
        return ResponsesRequest(
            model=req_body.get("model", ""),
            input=req_body.get("input", []),
            instructions=req_body.get("instructions"),
            previous_response_id=req_body.get("previous_response_id"),
            tools=req_body.get("tools"),
            stream=req_body.get("stream", False)
        )

    async def _handle_responses(self, ctx: RequestContext) -> web.Response:
        """处理 /responses 请求（转换模式）"""
        try:
            responses_req = self._parse_responses_request(ctx.body)
        except (json.JSONDecodeError, KeyError) as e:
            return web.Response(status=400, text=f"Invalid request: {e}")

        chat_body = self.responses_converter.convert_request(responses_req)
        url = f"{ctx.upstream.url}/v1/chat/completions"
        headers = self._filter_headers(ctx.headers)
        headers["Content-Type"] = "application/json"

        if responses_req.stream:
            return await self._forward_responses_streaming(
                ctx, url, headers, chat_body, responses_req
            )
        else:
            return await self._forward_responses(ctx, url, headers, chat_body, responses_req)

    async def _forward_responses(
        self,
        ctx: RequestContext,
        url: str,
        headers: dict,
        chat_body: dict,
        responses_req: ResponsesRequest
    ) -> web.Response:
        """非流式：发送 Chat Completions，转换响应"""
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

同时修改 `handle_request` 方法，添加 Responses 处理分支：

```python
# src/proxy.py 修改 handle_request 方法

async def handle_request(self, request: web.Request) -> web.Response:
    """处理所有请求"""
    body = await request.read()
    ctx = RequestContext(
        method=request.method,
        path=request.path,
        headers=dict(request.headers),
        body=body,
        query_string=request.query_string,
        start_time=time.time(),
        _request=request
    )

    # 匹配路由
    ctx.matched_route = match_route(ctx.path, self.config.routes)
    if ctx.matched_route is None:
        elapsed_ms = (time.time() - ctx.start_time) * 1000
        self.log(f"{ctx.method} {ctx.path} -> 404 Not Found ({elapsed_ms:.0f}ms)")
        return web.Response(status=404, text="Not Found")

    # 获取上游配置
    upstream_name = ctx.matched_route.upstream
    ctx.upstream = self.config.upstreams.get(upstream_name)
    if ctx.upstream is None:
        elapsed_ms = (time.time() - ctx.start_time) * 1000
        self.log(f"{ctx.method} {ctx.path} -> 502 Unknown upstream: {upstream_name} ({elapsed_ms:.0f}ms)", "ERROR")
        return web.Response(status=502, text=f"Unknown upstream: {upstream_name}")

    # 新增：Responses API 转换分支
    if self._should_convert_responses(ctx):
        return await self._handle_responses(ctx)

    # 检测是否为流式请求
    if self._is_streaming_request(ctx.headers, body):
        return await self._forward_streaming(ctx)

    # 代理请求
    return await self.proxy_request(ctx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/Dev/llm-route && python -m pytest tests/test_proxy.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:/Dev/llm-route && git add src/proxy.py tests/test_proxy.py && git commit -m "feat: integrate Responses API conversion into proxy

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 配置示例更新

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Update config.yaml with convert_responses example**

```yaml
# config.yaml 更新

host: 127.0.0.1
port: 8087
log_level: 2

upstreams:
  anthropic:
    url: https://modelservice.jdcloud.com/coding/anthropic
    protocol: anthropic
  openai:
    url: https://modelservice.jdcloud.com/coding/openai
    protocol: openai
  # 新增：Ollama 示例，启用 Responses 转换
  # ollama:
  #   url: http://localhost:11434/v1
  #   protocol: openai
  #   convert_responses: true

routes:
  - path: /v1/messages
    upstream: anthropic
  - path: /v1/models
    upstream: anthropic
  - path: /v1/chat/completions
    upstream: openai
  - path: /models
    upstream: anthropic
  # 新增：/responses 路由示例
  # - path: /responses
  #   upstream: ollama

retry_rules:
  - status: 400
    body_contains: overloaded
    max_retries: 10
    delay: 2
    jitter: 1
  - status: 400
    body_contains: Too many requests
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

- [ ] **Step 2: Commit**

```bash
cd D:/Dev/llm-route && git add config.yaml && git commit -m "docs: add convert_responses configuration example

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 运行完整测试

**Files:**
- All test files

- [ ] **Step 1: Run all tests**

Run: `cd D:/Dev/llm-route && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run linting**

Run: `cd D:/Dev/llm-route && python -m flake8 src/`
Expected: No errors (or only acceptable warnings)

- [ ] **Step 3: Final commit if any fixes needed**

```bash
cd D:/Dev/llm-route && git add -A && git commit -m "fix: resolve test and lint issues

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 自检结果

**1. 规格覆盖检查：**
- ✅ Responses API → Chat Completions 转换 → Task 3, 5
- ✅ 会话历史管理 → Task 2
- ✅ 配置化开关 → Task 4
- ✅ 流式支持 → Task 3, 5

**2. 占位符扫描：**
- ✅ 无 TBD/TODO
- ✅ 所有代码步骤都有完整实现

**3. 类型一致性检查：**
- ✅ ResponsesRequest 在各任务中定义一致
- ✅ SessionManager 方法签名一致
- ✅ ResponsesConverter 方法签名一致
