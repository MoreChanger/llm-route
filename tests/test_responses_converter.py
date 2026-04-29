# tests/test_responses_converter.py
"""Responses API 转换器测试"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from src.session_manager import SessionManager
from src.responses_converter import ResponsesConverter
from src.responses_models import ResponsesRequest


class MockStream:
    """模拟 SSE 流"""

    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks
        self.index = 0

    async def iter_any(self):
        for chunk in self.chunks:
            yield chunk


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
        req = ResponsesRequest(model="gpt-4", input="Hello", instructions="Be helpful")
        result = converter.convert_request(req)

        assert len(result["messages"]) == 2
        assert result["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert result["messages"][1] == {"role": "user", "content": "Hello"}

    def test_convert_request_with_history(self, converter):
        """测试带历史消息的转换"""
        # 先创建一个会话
        response_id = converter.sessions.generate_response_id()
        converter.sessions.save_session(
            response_id,
            [
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ],
        )

        req = ResponsesRequest(
            model="gpt-4", input="New question", previous_response_id=response_id
        )
        result = converter.convert_request(req)

        assert len(result["messages"]) == 3
        assert result["messages"][0] == {"role": "user", "content": "Previous question"}
        assert result["messages"][1] == {
            "role": "assistant",
            "content": "Previous answer",
        }
        assert result["messages"][2] == {"role": "user", "content": "New question"}

    def test_convert_request_with_tools(self, converter):
        """测试带工具的转换"""
        req = ResponsesRequest(
            model="gpt-4",
            input="Hello",
            tools=[
                {
                    "type": "function",
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                }
            ],
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
                {"type": "message", "role": "user", "content": "How are you?"},
            ],
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
            "choices": [{"message": {"role": "assistant", "content": "Hi there!"}}],
        }

        result = converter.convert_response(chat_resp, req)

        assert result["id"].startswith("resp_")
        assert result["model"] == "gpt-4"
        # output is now a list
        assert isinstance(result["output"], list)
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "message"
        assert result["output"][0]["role"] == "assistant"
        assert len(result["output"][0]["content"]) == 1
        assert result["output"][0]["content"][0]["type"] == "output_text"
        assert result["output"][0]["content"][0]["text"] == "Hi there!"

    def test_convert_response_saves_session(self, converter):
        """测试响应转换保存会话"""
        req = ResponsesRequest(model="gpt-4", input="Hello")
        chat_resp = {"choices": [{"message": {"role": "assistant", "content": "Hi!"}}]}

        result = converter.convert_response(chat_resp, req)

        # 验证会话已保存
        saved_messages = converter.sessions.get_messages(result["id"])
        assert len(saved_messages) == 2  # user + assistant
        assert saved_messages[0]["role"] == "user"
        assert saved_messages[1]["role"] == "assistant"

    # ========== SSE 格式化测试 ==========

    def test_sse_event(self, converter):
        """测试 SSE 事件格式化"""
        data = {"id": "test", "status": "in_progress"}
        result = converter._sse_event("response.created", data)

        assert result.startswith(b"data: ")
        assert result.endswith(b"\n\n")
        parsed = json.loads(result[6:-2].decode("utf-8"))
        assert parsed["type"] == "response.created"
        assert parsed["id"] == "test"
        assert parsed["status"] == "in_progress"

    def test_sse_event_with_chinese(self, converter):
        """测试 SSE 事件格式化包含中文"""
        data = {"content": "你好世界"}
        result = converter._sse_event("response.output_text.delta", data)

        assert "你好世界" in result.decode("utf-8")

    # ========== convert_stream 方法测试 ==========

    @pytest.mark.asyncio
    async def test_convert_stream_text_content(self, converter):
        """测试流式转换文本内容"""
        sse_chunks = [
            b'data: {"model": "gpt-4", "choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}\n',
            b'data: {"model": "gpt-4", "choices": [{"delta": {"content": " World"}, "finish_reason": null}]}\n',
            b'data: {"model": "gpt-4", "choices": [{"delta": {}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="Hi")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]

        assert "response.created" in event_types
        assert "response.in_progress" in event_types
        assert "response.output_item.added" in event_types
        assert "response.output_text.delta" in event_types
        assert "response.output_item.done" in event_types
        assert "response.completed" in event_types

    @pytest.mark.asyncio
    async def test_convert_stream_empty_content(self, converter):
        """测试流式转换空内容"""
        sse_chunks = [
            b'data: {"model": "gpt-4", "choices": [{"delta": {}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="Hi")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]

        assert "response.created" in event_types
        assert "response.completed" in event_types

    @pytest.mark.asyncio
    async def test_convert_stream_invalid_json(self, converter):
        """测试流式转换处理无效 JSON"""
        sse_chunks = [
            b"data: invalid json\n",
            b'data: {"model": "gpt-4", "choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="Hi")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.completed" in event_types

    @pytest.mark.asyncio
    async def test_convert_stream_with_model_update(self, converter):
        """测试流式转换更新模型名称"""
        sse_chunks = [
            b'data: {"model": "gpt-4-turbo", "choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="Hi")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        completed_event = next(
            json.loads(e[6:-2])
            for e in events
            if json.loads(e[6:-2])["type"] == "response.completed"
        )
        assert completed_event["response"]["model"] == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_convert_stream_without_finish_reason(self, converter):
        """测试流式转换无 finish_reason 时的收尾"""
        sse_chunks = [
            b'data: {"model": "gpt-4", "choices": [{"delta": {"content": "Hi"}, "finish_reason": null}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="Hi")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.completed" in event_types

    @pytest.mark.asyncio
    async def test_convert_stream_with_previous_response_id(self, converter):
        """测试流式转换带 previous_response_id"""
        prev_id = "resp_previous"
        converter.sessions.save_session(
            prev_id, [{"role": "user", "content": "Previous"}]
        )

        sse_chunks = [
            b'data: {"model": "gpt-4", "choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(
            model="gpt-4", input="Hi", previous_response_id=prev_id
        )

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        created_event = next(
            json.loads(e[6:-2])
            for e in events
            if json.loads(e[6:-2])["type"] == "response.created"
        )
        assert created_event["response"]["previous_response_id"] == prev_id

    # ========== _read_sse_lines 方法测试 ==========

    @pytest.mark.asyncio
    async def test_read_sse_lines_basic(self, converter):
        """测试基本的 SSE 行读取"""
        chunks = [b"data: test1\n\ndata: test2\n\n"]
        mock_stream = MockStream(chunks)

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert "data: test1" in lines
        assert "data: test2" in lines

    @pytest.mark.asyncio
    async def test_read_sse_lines_split_chunks(self, converter):
        """测试跨块分割的 SSE 行读取"""
        chunks = [
            b"data: test",
            b"1\n\ndata: te",
            b"st2\n\n",
        ]
        mock_stream = MockStream(chunks)

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert "data: test1" in lines
        assert "data: test2" in lines

    @pytest.mark.asyncio
    async def test_read_sse_lines_empty_lines(self, converter):
        """测试包含空行的 SSE 行读取"""
        chunks = [b"data: test\n\n\n\ndata: test2\n\n"]
        mock_stream = MockStream(chunks)

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert len(lines) == 2
        assert "data: test" in lines
        assert "data: test2" in lines

    @pytest.mark.asyncio
    async def test_read_sse_lines_trailing_data(self, converter):
        """测试末尾无换行符的数据"""
        chunks = [b"data: test1\n\ndata: test2"]
        mock_stream = MockStream(chunks)

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert "data: test1" in lines
        assert "data: test2" in lines

    @pytest.mark.asyncio
    async def test_read_sse_lines_utf8_decode_error(self, converter):
        """测试 UTF-8 解码错误处理"""
        chunks = [b"data: test\n\n", b"\xff\xfe invalid utf8\n\n"]
        mock_stream = MockStream(chunks)

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert "data: test" in lines

    @pytest.mark.asyncio
    async def test_read_sse_lines_empty_stream(self, converter):
        """测试空流"""
        mock_stream = MockStream([])

        lines = []
        async for line in converter._read_sse_lines(mock_stream):
            lines.append(line)

        assert lines == []

    # ========== _process_tool_delta 方法测试 ==========

    @pytest.mark.asyncio
    async def test_process_tool_delta_first_occurrence(self, converter):
        """测试工具调用首次出现"""
        response_obj = {"output": []}
        tool_calls_state = {}

        events = []
        async for event in converter._process_tool_delta(
            {"index": 0, "id": "call_123", "function": {"name": "get_weather"}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            events.append(event)

        assert 0 in tool_calls_state
        assert tool_calls_state[0]["id"] == "call_123"
        assert tool_calls_state[0]["name"] == "get_weather"
        assert len(response_obj["output"]) == 1
        assert response_obj["output"][0]["type"] == "function_call"

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.output_item.added" in event_types

    @pytest.mark.asyncio
    async def test_process_tool_delta_arguments_accumulation(self, converter):
        """测试工具调用参数累积"""
        response_obj = {"output": [{"id": "call_123", "type": "function_call", "arguments": ""}]}
        tool_calls_state = {0: {"id": "call_123", "name": "get_weather", "arguments": "", "output_index": 0}}

        events = []
        async for event in converter._process_tool_delta(
            {"index": 0, "function": {"arguments": '{"city":'}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            events.append(event)

        assert tool_calls_state[0]["arguments"] == '{"city":'

        async for event in converter._process_tool_delta(
            {"index": 0, "function": {"arguments": ' "Beijing"}'}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            events.append(event)

        assert tool_calls_state[0]["arguments"] == '{"city": "Beijing"}'

    @pytest.mark.asyncio
    async def test_process_tool_delta_multiple_tools(self, converter):
        """测试多个工具调用"""
        response_obj = {"output": []}
        tool_calls_state = {}

        async for _ in converter._process_tool_delta(
            {"index": 0, "id": "call_1", "function": {"name": "get_weather"}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            pass

        async for _ in converter._process_tool_delta(
            {"index": 1, "id": "call_2", "function": {"name": "get_time"}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            pass

        assert len(tool_calls_state) == 2
        assert len(response_obj["output"]) == 2

    @pytest.mark.asyncio
    async def test_process_tool_delta_without_id(self, converter):
        """测试工具调用无 ID 时自动生成"""
        response_obj = {"output": []}
        tool_calls_state = {}

        async for _ in converter._process_tool_delta(
            {"index": 0, "function": {"name": "test"}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            pass

        assert tool_calls_state[0]["id"].startswith("call_")

    @pytest.mark.asyncio
    async def test_process_tool_delta_empty_arguments(self, converter):
        """测试工具调用空参数"""
        response_obj = {"output": [{"id": "call_123", "type": "function_call", "arguments": ""}]}
        tool_calls_state = {0: {"id": "call_123", "name": "test", "arguments": "", "output_index": 0}}

        events = []
        async for event in converter._process_tool_delta(
            {"index": 0, "function": {}},
            "resp_1",
            response_obj,
            tool_calls_state,
        ):
            events.append(event)

        assert tool_calls_state[0]["arguments"] == ""
        delta_events = [e for e in events if "function_call_arguments.delta" in e.decode()]
        assert len(delta_events) == 0

    # ========== _finish_response 方法测试 ==========

    @pytest.mark.asyncio
    async def test_finish_response_tool_calls(self, converter):
        """测试工具调用完成处理"""
        response_obj = {
            "output": [
                {
                    "id": "call_123",
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": '{"city": "Beijing"}',
                    "status": "in_progress",
                }
            ]
        }
        tool_calls_state = {
            0: {
                "id": "call_123",
                "name": "get_weather",
                "arguments": '{"city": "Beijing"}',
                "output_index": 0,
            }
        }

        events = []
        async for event in converter._finish_response(
            "tool_calls",
            "resp_1",
            response_obj,
            tool_calls_state,
            "msg_1",
            None,
            "",
        ):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.function_call_arguments.done" in event_types
        assert "response.output_item.done" in event_types
        assert "response.completed" in event_types

        assert response_obj["output"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_finish_response_text_content(self, converter):
        """测试文本内容完成处理"""
        response_obj = {
            "output": [
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": ""}],
                    "status": "in_progress",
                }
            ]
        }

        events = []
        async for event in converter._finish_response(
            "stop",
            "resp_1",
            response_obj,
            {},
            "msg_1",
            0,
            "Hello World",
        ):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.output_item.done" in event_types
        assert "response.completed" in event_types

        assert response_obj["output"][0]["status"] == "completed"
        assert response_obj["output"][0]["content"][0]["text"] == "Hello World"

    @pytest.mark.asyncio
    async def test_finish_response_empty_content(self, converter):
        """测试空内容完成处理"""
        response_obj = {"output": []}

        events = []
        async for event in converter._finish_response(
            "stop",
            "resp_1",
            response_obj,
            {},
            "msg_1",
            None,
            "",
        ):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.completed" in event_types
        assert response_obj["status"] == "completed"

    @pytest.mark.asyncio
    async def test_finish_response_mixed_content(self, converter):
        """测试混合内容（工具调用+文本）完成处理"""
        response_obj = {
            "output": [
                {
                    "id": "call_123",
                    "type": "function_call",
                    "name": "get_weather",
                    "arguments": '{"city": "Beijing"}',
                    "status": "in_progress",
                },
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": ""}],
                    "status": "in_progress",
                },
            ]
        }
        tool_calls_state = {
            0: {
                "id": "call_123",
                "name": "get_weather",
                "arguments": '{"city": "Beijing"}',
                "output_index": 0,
            }
        }

        events = []
        async for event in converter._finish_response(
            "tool_calls",
            "resp_1",
            response_obj,
            tool_calls_state,
            "msg_1",
            1,
            "Here's the weather:",
        ):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.function_call_arguments.done" in event_types
        assert event_types.count("response.output_item.done") == 2
        assert "response.completed" in event_types

    # ========== _finalize_stream 方法测试 ==========

    @pytest.mark.asyncio
    async def test_finalize_stream_with_content(self, converter):
        """测试流收尾有内容"""
        response_obj = {"output": [], "status": "in_progress"}

        events = []
        async for event in converter._finalize_stream(
            "resp_1",
            response_obj,
            "msg_1",
            None,
            "Hello",
        ):
            events.append(event)

        assert response_obj["status"] == "completed"
        assert len(response_obj["output"]) == 1
        assert response_obj["output"][0]["content"][0]["text"] == "Hello"

        event_types = [json.loads(e[6:-2])["type"] for e in events]
        assert "response.completed" in event_types

    @pytest.mark.asyncio
    async def test_finalize_stream_with_existing_output(self, converter):
        """测试流收尾已有输出"""
        response_obj = {
            "output": [
                {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": ""}],
                    "status": "in_progress",
                }
            ],
            "status": "in_progress",
        }

        events = []
        async for event in converter._finalize_stream(
            "resp_1",
            response_obj,
            "msg_1",
            0,
            "Hello",
        ):
            events.append(event)

        assert response_obj["status"] == "completed"
        assert response_obj["output"][0]["content"][0]["text"] == "Hello"
        assert response_obj["output"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_finalize_stream_empty_content(self, converter):
        """测试流收尾空内容"""
        response_obj = {"output": [], "status": "in_progress"}

        events = []
        async for event in converter._finalize_stream(
            "resp_1",
            response_obj,
            "msg_1",
            None,
            "",
        ):
            events.append(event)

        assert response_obj["status"] == "completed"
        assert len(response_obj["output"]) == 0

    # ========== convert_stream 工具调用集成测试 ==========

    @pytest.mark.asyncio
    async def test_convert_stream_with_tool_calls(self, converter):
        """测试流式转换工具调用"""
        sse_chunks = [
            b'data: {"model": "gpt-4", "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_123", "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": null}]}\n',
            b'data: {"model": "gpt-4", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"city\\""}}]}, "finish_reason": null}]}\n',
            b'data: {"model": "gpt-4", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": \\"Beijing\\"}"}}]}, "finish_reason": null}]}\n',
            b'data: {"model": "gpt-4", "choices": [{"delta": {}, "finish_reason": "tool_calls"}]}\n',
            b"data: [DONE]\n",
        ]

        mock_stream = MockStream(sse_chunks)
        req = ResponsesRequest(model="gpt-4", input="What's the weather?")

        events = []
        async for event in converter.convert_stream(mock_stream, req):
            events.append(event)

        event_types = [json.loads(e[6:-2])["type"] for e in events]

        assert "response.created" in event_types
        assert "response.output_item.added" in event_types
        assert "response.function_call_arguments.delta" in event_types
        assert "response.function_call_arguments.done" in event_types
        assert "response.output_item.done" in event_types
        assert "response.completed" in event_types

        args_done_event = next(
            json.loads(e[6:-2])
            for e in events
            if json.loads(e[6:-2])["type"] == "response.function_call_arguments.done"
        )
        assert args_done_event["arguments"] == '{"city": "Beijing"}'

    # ========== 辅助方法测试 ==========

    def test_generate_id(self, converter):
        """测试 ID 生成"""
        id1 = converter._generate_id("resp")
        id2 = converter._generate_id("msg")
        id3 = converter._generate_id("call")

        assert id1.startswith("resp_")
        assert id2.startswith("msg_")
        assert id3.startswith("call_")
        assert id1 != id2 != id3

    def test_generate_id_uniqueness(self, converter):
        """测试 ID 生成唯一性"""
        ids = [converter._generate_id("resp") for _ in range(100)]
        assert len(set(ids)) == 100
