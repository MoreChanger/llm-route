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

        # SSE now uses data-only format (no event line)
        assert b"data: " in result
        assert b'"id": "test"' in result
        assert result.endswith(b"\n\n")
