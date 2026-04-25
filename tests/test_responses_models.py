# tests/test_responses_models.py
"""Responses API 数据模型测试"""

from src.responses_models import (
    ResponseInput,
    ResponsesRequest,
    ResponseContent,
    ResponsesOutput,
    ResponsesResponse,
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
            stream=True,
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
            previous_response_id="resp_prev",
        )
        assert resp.id == "resp_abc"
        assert resp.model == "gpt-4"
        assert resp.previous_response_id == "resp_prev"
