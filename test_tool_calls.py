"""工具调用转换测试"""
import pytest
from src.responses_converter import ResponsesConverter
from src.session_manager import SessionManager
from src.responses_models import ResponsesRequest


@pytest.fixture
def converter():
    """创建转换器实例"""
    return ResponsesConverter(SessionManager())


def test_parse_function_call_output(converter):
    """测试解析 function_call_output 输入"""
    input_data = [
        {"type": "function_call_output", "call_id": "call_123", "output": "sunny"}
    ]
    result = converter._parse_input(input_data)

    assert len(result) == 1
    assert result[0]["role"] == "tool"
    assert result[0]["tool_call_id"] == "call_123"
    assert result[0]["content"] == "sunny"


def test_parse_function_call(converter):
    """测试解析 function_call 输入"""
    input_data = [
        {"type": "function_call", "id": "call_123", "name": "get_weather", "arguments": '{"city": "Beijing"}'}
    ]
    result = converter._parse_input(input_data)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] is None
    assert len(result[0]["tool_calls"]) == 1
    assert result[0]["tool_calls"][0]["id"] == "call_123"
    assert result[0]["tool_calls"][0]["function"]["name"] == "get_weather"


def test_convert_response_with_tool_calls(converter):
    """测试转换包含 tool_calls 的响应"""
    chat_resp = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Beijing"}'
                    }
                }]
            },
            "finish_reason": "tool_calls"
        }],
        "model": "gpt-4"
    }
    req = ResponsesRequest(model="gpt-4", input="What's the weather?")

    result = converter.convert_response(chat_resp, req)

    assert "output" in result
    assert len(result["output"]) == 1
    assert result["output"][0]["type"] == "function_call"
    assert result["output"][0]["name"] == "get_weather"
    assert result["output"][0]["arguments"] == '{"city": "Beijing"}'


def test_convert_chat_delta_with_tool_calls(converter):
    """测试转换包含 tool_calls 的 delta"""
    data = {
        "choices": [{
            "index": 0,
            "delta": {
                "tool_calls": [{
                    "index": 0,
                    "id": "call_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city'
                    }
                }]
            }
        }]
    }

    events = converter._convert_chat_delta(data)

    assert len(events) == 1
    assert events[0]["is_tool_call"] is True
    assert events[0]["tool_id"] == "call_123"
    assert events[0]["tool_name"] == "get_weather"
    assert events[0]["delta"] == '{"city'
