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
            # 格式3: {"type": "function_call_output", "call_id": "xxx", "output": "结果"}
            elif item.get("type") == "function_call_output":
                call_id = item.get("call_id", "")
                output = item.get("output", "")
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": output
                })
            # 格式4: {"type": "function_call", "id": "xxx", "name": "tool_name", "arguments": "{}"}
            elif item.get("type") == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", "{}")
                        }
                    }]
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
        finish_reason = chat_resp.get("choices", [{}])[0].get("finish_reason")

        # 保存会话历史
        messages = self.sessions.get_messages(req.previous_response_id)
        if req.instructions:
            messages = [{"role": "system", "content": req.instructions}] + messages
        messages.extend(self._parse_input(req.input))
        messages.append(assistant_message)
        self.sessions.save_session(response_id, messages)

        # 构建输出
        output = self._convert_output(assistant_message, finish_reason)

        # 构建响应
        return {
            "id": response_id,
            "model": chat_resp.get("model", req.model),
            "output": output,
            "previous_response_id": req.previous_response_id
        }

    def _convert_output(self, message: dict, finish_reason: str = None) -> list:
        """将 Chat Completions 消息转换为 Responses 输出列表"""
        outputs = []

        # 处理 tool_calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tool_call in tool_calls:
                outputs.append({
                    "type": "function_call",
                    "id": tool_call.get("id", ""),
                    "call_id": tool_call.get("id", ""),
                    "name": tool_call.get("function", {}).get("name", ""),
                    "arguments": tool_call.get("function", {}).get("arguments", "{}"),
                    "status": "completed"
                })

        # 处理文本内容
        content = message.get("content")
        if content:
            outputs.append({
                "type": "message",
                "id": f"msg_{self.sessions.generate_response_id()}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
                "status": "completed"
            })

        # 如果没有任何输出，添加空消息
        if not outputs:
            outputs.append({
                "type": "message",
                "id": f"msg_{self.sessions.generate_response_id()}",
                "role": "assistant",
                "content": [],
                "status": "completed"
            })

        return outputs

    # ========== 流式转换 ==========

    async def convert_stream(
        self,
        chat_stream,  # aiohttp StreamReader
        req: ResponsesRequest
    ) -> AsyncIterator[bytes]:
        """将 Chat Completions SSE 流转换为 Responses SSE 流

        Args:
            chat_stream: aiohttp StreamReader（上游响应内容）
            req: 原始 Responses API 请求

        Yields:
            Responses API SSE 事件字节
        """
        response_id = self.sessions.generate_response_id()
        msg_id = f"msg_{response_id}"

        # 工具调用状态跟踪
        tool_calls_state = {}  # {index: {id, name, arguments}}
        tool_call_counter = 0
        full_content = ""
        has_tool_calls = False
        output_items = []  # 跟踪所有输出项

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

        # 2. 处理流式行
        async for line in self._read_sse_lines(chat_stream):
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                continue

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            events = self._convert_chat_delta(data)
            for event in events:
                if event.get("is_tool_call"):
                    # 处理工具调用
                    tool_index = event.get("tool_index", 0)
                    tool_id = event.get("tool_id", "")
                    tool_name = event.get("tool_name", "")
                    delta_args = event.get("delta", "")

                    # 首次出现该工具调用
                    if tool_index not in tool_calls_state:
                        tool_calls_state[tool_index] = {
                            "id": tool_id or f"call_{tool_index}",
                            "name": tool_name,
                            "arguments": "",
                            "output_index": tool_call_counter
                        }
                        tool_call_counter += 1
                        has_tool_calls = True

                        # 发送 output_item.added 事件
                        yield self._format_sse("response.output_item.added", {
                            "type": "response.output_item.added",
                            "output_index": tool_calls_state[tool_index]["output_index"],
                            "item": {
                                "type": "function_call",
                                "id": tool_calls_state[tool_index]["id"],
                                "name": tool_name,
                                "status": "in_progress"
                            }
                        })
                        output_items.append(("function_call", tool_index))

                    # 累积参数
                    if delta_args:
                        tool_calls_state[tool_index]["arguments"] += delta_args

                        # 发送参数增量事件
                        yield self._format_sse("response.function_call_arguments.delta", {
                            "type": "response.function_call_arguments.delta",
                            "item_id": tool_calls_state[tool_index]["id"],
                            "output_index": tool_calls_state[tool_index]["output_index"],
                            "delta": delta_args
                        })

                    # 更新工具名称（可能在后续 chunk 中出现）
                    if tool_name and not tool_calls_state[tool_index]["name"]:
                        tool_calls_state[tool_index]["name"] = tool_name

                elif event.get("is_text"):
                    # 处理文本内容
                    delta_content = event.get("delta", "")
                    if delta_content:
                        full_content += delta_content

                        # 如果还没有发送文本 output_item.added
                        if ("message", 0) not in output_items:
                            yield self._format_sse("response.output_item.added", {
                                "type": "response.output_item.added",
                                "output_index": tool_call_counter,
                                "item": {
                                    "type": "message",
                                    "id": msg_id,
                                    "role": "assistant",
                                    "status": "in_progress"
                                }
                            })
                            output_items.append(("message", 0))

                        # 发送文本增量事件
                        yield self._format_sse("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": msg_id,
                            "output_index": tool_call_counter,
                            "content_index": 0,
                            "delta": delta_content
                        })

        # 3. 发送工具调用完成事件
        for tool_index, tc in tool_calls_state.items():
            yield self._format_sse("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "id": tc["id"],
                "output_index": tc["output_index"],
                "arguments": tc["arguments"]
            })
            yield self._format_sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": tc["output_index"],
                "item": {
                    "type": "function_call",
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                    "status": "completed"
                }
            })

        # 4. 发送文本完成事件（如果有文本内容）
        if full_content:
            yield self._format_sse("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": tool_call_counter,
                "item": {
                    "type": "message",
                    "id": msg_id,
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_content}],
                    "status": "completed"
                }
            })

        # 5. 构建输出列表
        outputs = []
        for tool_index, tc in sorted(tool_calls_state.items(), key=lambda x: x[1]["output_index"]):
            outputs.append({
                "type": "function_call",
                "id": tc["id"],
                "call_id": tc["id"],
                "name": tc["name"],
                "arguments": tc["arguments"],
                "status": "completed"
            })
        if full_content:
            outputs.append({
                "type": "message",
                "id": msg_id,
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_content}],
                "status": "completed"
            })

        # 6. 发送 response.completed 事件
        yield self._format_sse("response.completed", {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "model": req.model,
                "previous_response_id": req.previous_response_id,
                "status": "completed",
                "output": outputs
            }
        })

        # 7. 保存会话
        messages = self.sessions.get_messages(req.previous_response_id)
        if req.instructions:
            messages = [{"role": "system", "content": req.instructions}] + messages
        messages.extend(self._parse_input(req.input))

        # 构建助手消息
        if tool_calls_state:
            assistant_msg = {
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    }
                    for tc in tool_calls_state.values()
                ]
            }
        else:
            assistant_msg = {"role": "assistant", "content": full_content}

        messages.append(assistant_msg)
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

    async def _read_sse_lines(self, content) -> AsyncIterator[str]:
        """逐行读取 SSE 数据，处理跨 chunk 的行"""
        buffer = ""
        async for chunk in content.iter_any():
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line
        # 处理剩余内容
        if buffer.strip():
            yield buffer.strip()

    def _convert_chat_delta(self, data: dict) -> list[dict]:
        """转换 Chat Completions delta 到 Responses 事件"""
        events = []
        choices = data.get("choices", [])

        for choice in choices:
            delta = choice.get("delta", {})
            output_index = choice.get("index", 0)

            # 处理文本内容
            content = delta.get("content")
            if content:
                events.append({
                    "event": "response.output_text.delta",
                    "type": "response.output_text.delta",
                    "delta": content,
                    "output_index": output_index,
                    "content_index": 0,
                    "is_text": True
                })

            # 处理 tool_calls
            tool_calls = delta.get("tool_calls") or []
            for tool_delta in tool_calls:
                tool_index = tool_delta.get("index", 0)
                tool_id = tool_delta.get("id", "")
                func = tool_delta.get("function", {})
                func_name = func.get("name", "")
                func_args = func.get("arguments", "")

                events.append({
                    "event": "response.function_call_arguments.delta",
                    "type": "response.function_call_arguments.delta",
                    "tool_index": tool_index,
                    "tool_id": tool_id,
                    "tool_name": func_name,
                    "delta": func_args,
                    "output_index": output_index,
                    "is_tool_call": True
                })

        return events

    def _format_sse(self, event: str, data: dict) -> bytes:
        """格式化为 SSE 事件（使用 data-only 格式，不包含 event 行）"""
        return f"data: {json.dumps(data)}\n\n".encode("utf-8")
