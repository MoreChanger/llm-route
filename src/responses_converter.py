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
        - 字典列表：多轮对话，可能格式有：
          - {"type": "message", "role": "user", "content": "..."}
          - {"role": "user", "content": [{"type": "input_text", "text": "..."}]}
        """
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        messages = []
        for item in input_data:
            if not isinstance(item, dict):
                continue

            # 格式1: {"type": "message", "role": "user", "content": "..."}
            if item.get("type") == "message":
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
            # 格式2: {"role": "user", "content": [{"type": "input_text", "text": "..."}]}
            elif "role" in item and "content" in item:
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
        msg_id = f"msg_{response_id}"

        # 1. 发送 response.created 事件
        yield self._format_sse("response.created", {
            "type": "response.created",
            "response": {
                "id": response_id,
                "model": req.model,
                "previous_response_id": req.previous_response_id,
                "status": "in_progress"
            }
        })

        # 2. 发送 output_item.added 事件
        yield self._format_sse("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": msg_id,
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
                # 添加 item_id
                event["item_id"] = msg_id
                yield self._format_sse(event.get("event", "response.output_text.delta"), event)

        # 4. 发送 output_item.done 事件
        yield self._format_sse("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "message",
                "id": msg_id,
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_content}],
                "status": "completed"
            }
        })

        # 5. 发送 response.completed 事件
        yield self._format_sse("response.completed", {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "model": req.model,
                "previous_response_id": req.previous_response_id,
                "status": "completed",
                "output": [{
                    "type": "message",
                    "id": msg_id,
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_content}]
                }]
            }
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
                    "type": "response.output_text.delta",
                    "delta": content,
                    "output_index": choice.get("index", 0),
                    "content_index": 0
                })

        return events

    def _format_sse(self, event: str, data: dict) -> bytes:
        """格式化为 SSE 事件（使用 data-only 格式，不包含 event 行）"""
        return f"data: {json.dumps(data)}\n\n".encode("utf-8")
