# src/responses_converter.py
"""Responses API 与 Chat Completions API 转换器

基于 OpenAI 官方 Responses API 规范实现
https://developers.openai.com/api/docs/guides/responses

主要功能:
- 将 Responses API 请求转换为 Chat Completions API 请求
- 将 Chat Completions API 响应转换为 Responses API 响应
- 支持流式和非流式转换
- 支持 function calling 双向转换
"""

import json
import time
import uuid
from typing import AsyncIterator, Union

from src.responses_models import ResponsesRequest
from src.session_manager import SessionManager


class ResponsesConverter:
    """Responses API 与 Chat Completions API 双向转换器

    Responses API 是 OpenAI 的新一代 API，使用 Item 而非 Message。
    Item 类型包括: message, function_call, function_call_output
    """

    def __init__(self, session_manager: SessionManager):
        self.sessions = session_manager

    # ============================================================
    # 请求转换: Responses API -> Chat Completions API
    # ============================================================

    def convert_request(self, req: ResponsesRequest) -> dict:
        """将 Responses 请求转换为 Chat Completions 请求体

        Args:
            req: Responses API 请求对象

        Returns:
            Chat Completions API 请求体（字典）
        """
        messages = []

        # 1. 获取历史消息（如果有 previous_response_id）
        if req.previous_response_id:
            messages.extend(self.sessions.get_messages(req.previous_response_id))

        # 2. 添加 system 指令（Responses API 使用 instructions 字段）
        if req.instructions:
            messages.append({"role": "system", "content": req.instructions})

        # 3. 添加当前输入（Responses API 使用 input 字段，可以是字符串或 Item 列表）
        messages.extend(self._parse_input(req.input))

        # 4. 构建请求体
        body = {"model": req.model, "messages": messages, "stream": req.stream}

        # 5. 转换工具定义（如果有）
        if req.tools:
            body["tools"] = self._convert_tools(req.tools)

        return body

    def _parse_input(self, input_data: Union[list, str]) -> list[dict]:
        """解析 Responses API 的 input 字段

        Responses API input 可以是:
        - 字符串: 简单的用户输入
        - Item 列表: 包含 message, function_call, function_call_output 等

        Args:
            input_data: Responses API 的 input 字段

        Returns:
            Chat Completions API 的 messages 列表
        """
        if isinstance(input_data, str):
            if input_data:  # 非空字符串
                return [{"role": "user", "content": input_data}]
            return []

        if not isinstance(input_data, list):
            # 非预期类型，尝试转为字符串
            if input_data:
                return [{"role": "user", "content": str(input_data)}]
            return []

        messages = []
        for item in input_data:
            if not isinstance(item, dict):
                # 如果是字符串，作为用户消息处理
                if isinstance(item, str) and item:
                    messages.append({"role": "user", "content": item})
                continue

            item_type = item.get("type")

            # Item 类型1: message - 包含角色和内容
            if item_type == "message":
                content = self._extract_text_content(item.get("content", ""))
                if content or item.get("role") == "assistant":
                    messages.append(
                        {
                            "role": item.get("role", "user"),
                            "content": content,
                        }
                    )

            # 兼容格式: {"role": "user", "content": "..."} (无 type 字段)
            elif "role" in item and "content" in item and item_type is None:
                content = self._extract_text_content(item.get("content", ""))
                if content:
                    messages.append(
                        {
                            "role": item.get("role", "user"),
                            "content": content,
                        }
                    )

            # Item 类型2: function_call_output - 工具调用结果
            elif item_type == "function_call_output":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.get("call_id", ""),
                        "content": item.get("output", ""),
                    }
                )

            # Item 类型3: function_call - 助手的工具调用
            elif item_type == "function_call":
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": item.get("name", ""),
                                    "arguments": item.get("arguments", "{}"),
                                },
                            }
                        ],
                    }
                )

        return messages

    def _extract_text_content(self, content) -> str:
        """从各种内容格式中提取文本

        内容可以是:
        - 字符串: 直接返回
        - 列表: 包含 {"type": "input_text/text", "text": "..."} 的对象列表
        """
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") in ("input_text", "text", "output_text"):
                        text_parts.append(item.get("text", ""))
            return "".join(text_parts)

        return str(content) if content else ""

    def _convert_tools(self, tools: list) -> list:
        """转换工具定义格式

        Responses API 的工具定义使用内部标签多态:
        {"type": "function", "name": "...", ...}

        Chat Completions API 使用外部标签多态:
        {"type": "function", "function": {"name": "...", ...}}
        """
        converted = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue

            tool_type = tool.get("type")

            # function 类型工具
            if tool_type == "function":
                # 已经是标准 Chat Completions 格式
                if "function" in tool and isinstance(tool["function"], dict):
                    converted.append(tool)
                # Responses API 简化格式，需要转换
                elif "name" in tool:
                    func_data = {"name": tool.get("name", "")}
                    if "description" in tool:
                        func_data["description"] = tool["description"]
                    if "parameters" in tool:
                        func_data["parameters"] = tool["parameters"]
                    converted.append({"type": "function", "function": func_data})
                else:
                    converted.append(tool)

            # 内置工具类型 (web_search, file_search, code_interpreter 等)
            else:
                converted.append(tool)

        return converted

    # ============================================================
    # 响应转换: Chat Completions API -> Responses API
    # ============================================================

    def convert_response(self, chat_resp: dict, req: ResponsesRequest) -> dict:
        """将 Chat Completions 响应转换为 Responses 响应

        Args:
            chat_resp: Chat Completions API 响应
            req: 原始 Responses API 请求

        Returns:
            Responses API 响应对象
        """
        response_id = self._generate_id("resp")

        # 提取响应内容
        choice = chat_resp.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason")

        # 构建输出 Items
        output = self._convert_output_items(message, finish_reason)

        # 保存会话历史
        self._save_conversation(response_id, req, message)

        # 构建 Responses API 响应对象
        return {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": chat_resp.get("model", req.model),
            "output": output,
            "previous_response_id": req.previous_response_id,
            "status": "completed",
        }

    def _convert_output_items(self, message: dict, finish_reason: str = None) -> list:
        """将 Chat Completions message 转换为 Responses output Items

        输出顺序:
        1. function_call Items (如果有工具调用)
        2. message Item (如果有文本内容)

        Note: 官方文档说明一个响应中可能同时包含工具调用和文本
        """
        outputs = []

        # 处理 tool_calls -> function_call Items
        tool_calls = message.get("tool_calls", [])
        for tool_call in tool_calls:
            call_id = tool_call.get("id", "")
            func = tool_call.get("function", {})
            outputs.append(
                {
                    "type": "function_call",
                    "id": call_id,
                    "call_id": call_id,  # 用于关联 function_call_output
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", "{}"),
                    "status": "completed",
                }
            )

        # 处理文本内容 -> message Item
        content = message.get("content")
        if content:
            outputs.append(
                {
                    "type": "message",
                    "id": self._generate_id("msg"),
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                    "status": "completed",
                }
            )

        # 如果没有任何输出，添加空消息
        if not outputs:
            outputs.append(
                {
                    "type": "message",
                    "id": self._generate_id("msg"),
                    "role": "assistant",
                    "content": [],
                    "status": "completed",
                }
            )

        return outputs

    # ============================================================
    # 流式转换: Chat Completions SSE -> Responses SSE
    # ============================================================

    async def convert_stream(
        self, chat_stream, req: ResponsesRequest
    ) -> AsyncIterator[bytes]:
        """将 Chat Completions SSE 流转换为 Responses SSE 流

        事件序列:
        1. response.created
        2. response.in_progress
        3. response.output_item.added (每个 Item 创建时)
        4. response.output_text.delta / response.function_call_arguments.delta
        5. response.output_item.done (每个 Item 完成时)
        6. response.completed

        SSE 格式: data: {json}\n\n (无 event 行)
        """
        response_id = self._generate_id("resp")
        msg_id = self._generate_id("msg")

        # 状态跟踪
        tool_calls_state = {}  # {index: {id, name, arguments, output_index}}
        text_output_index = None  # 文本消息的 output_index
        full_content = ""

        # 响应对象
        response_obj = {
            "id": response_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": req.model,
            "status": "in_progress",
            "output": [],
            "previous_response_id": req.previous_response_id,
        }

        # 1. 发送 response.created 事件
        yield self._sse_event("response.created", {"response": response_obj})

        # 2. 发送 response.in_progress 事件
        yield self._sse_event("response.in_progress", {"response": response_obj})

        # 3. 处理上游流
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

            # 更新模型名称
            if "model" in data and response_obj["model"] == req.model:
                response_obj["model"] = data["model"]

            # 处理 choices
            for choice in data.get("choices", []):
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                # ---------- 处理工具调用 ----------
                for tool_delta in delta.get("tool_calls") or []:
                    async for event in self._process_tool_delta(
                        tool_delta, response_id, response_obj, tool_calls_state
                    ):
                        yield event

                # ---------- 处理文本内容 ----------
                content = delta.get("content")
                if content:
                    full_content += content

                    # 首次发送文本，先创建 message Item
                    if text_output_index is None:
                        text_output_index = len(response_obj["output"])
                        response_obj["output"].append(
                            {
                                "id": msg_id,
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": ""}],
                                "status": "in_progress",
                            }
                        )

                        # 发送 output_item.added
                        yield self._sse_event(
                            "response.output_item.added",
                            {
                                "response_id": response_id,
                                "output_index": text_output_index,
                                "item": {
                                    "type": "message",
                                    "id": msg_id,
                                    "role": "assistant",
                                    "status": "in_progress",
                                },
                            },
                        )

                    # 发送文本增量
                    yield self._sse_event(
                        "response.output_text.delta",
                        {
                            "response_id": response_id,
                            "item_id": msg_id,
                            "output_index": text_output_index,
                            "content_index": 0,
                            "delta": content,
                        },
                    )

                # ---------- 处理完成信号 ----------
                if finish_reason:
                    async for event in self._finish_response(
                        finish_reason,
                        response_id,
                        response_obj,
                        tool_calls_state,
                        msg_id,
                        text_output_index,
                        full_content,
                    ):
                        yield event

                    # 保存会话
                    self._save_conversation(
                        response_id,
                        req,
                        {
                            "content": full_content or None,
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": tc["arguments"],
                                    },
                                }
                                for tc in tool_calls_state.values()
                            ],
                        }
                        if tool_calls_state
                        else {"content": full_content},
                    )
                    return

        # 流正常结束但无 finish_reason，发送完成
        async for event in self._finalize_stream(
            response_id, response_obj, msg_id, text_output_index, full_content
        ):
            yield event

    async def _process_tool_delta(
        self,
        tool_delta: dict,
        response_id: str,
        response_obj: dict,
        tool_calls_state: dict,
    ) -> AsyncIterator[bytes]:
        """处理工具调用增量数据"""
        index = tool_delta.get("index", 0)
        tool_id = tool_delta.get("id", "")
        func = tool_delta.get("function", {})
        func_name = func.get("name", "")
        func_args = func.get("arguments", "")

        # 首次出现该工具调用
        if index not in tool_calls_state:
            output_index = len(response_obj["output"])
            call_id = tool_id or self._generate_id("call")

            tool_calls_state[index] = {
                "id": call_id,
                "name": func_name,
                "arguments": "",
                "output_index": output_index,
            }

            # 添加到输出
            response_obj["output"].append(
                {
                    "id": call_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": func_name,
                    "arguments": "",
                    "status": "in_progress",
                }
            )

            # 发送 output_item.added
            yield self._sse_event(
                "response.output_item.added",
                {
                    "response_id": response_id,
                    "output_index": output_index,
                    "item": {
                        "type": "function_call",
                        "id": call_id,
                        "call_id": call_id,
                        "name": func_name,
                        "status": "in_progress",
                    },
                },
            )

        # 累积参数
        if func_args:
            tool_calls_state[index]["arguments"] += func_args

            # 发送参数增量
            yield self._sse_event(
                "response.function_call_arguments.delta",
                {
                    "response_id": response_id,
                    "item_id": tool_calls_state[index]["id"],
                    "output_index": tool_calls_state[index]["output_index"],
                    "delta": func_args,
                },
            )

    async def _finish_response(
        self,
        finish_reason: str,
        response_id: str,
        response_obj: dict,
        tool_calls_state: dict,
        msg_id: str,
        text_output_index: int,
        full_content: str,
    ) -> AsyncIterator[bytes]:
        """处理响应完成"""
        # 完成工具调用
        if finish_reason == "tool_calls":
            for index, tc in tool_calls_state.items():
                # 发送 arguments.done
                yield self._sse_event(
                    "response.function_call_arguments.done",
                    {
                        "response_id": response_id,
                        "item_id": tc["id"],
                        "output_index": tc["output_index"],
                        "arguments": tc["arguments"],
                    },
                )

                # 更新输出状态
                for item in response_obj["output"]:
                    if item.get("id") == tc["id"]:
                        item["arguments"] = tc["arguments"]
                        item["status"] = "completed"
                        break

                # 发送 output_item.done
                yield self._sse_event(
                    "response.output_item.done",
                    {
                        "response_id": response_id,
                        "output_index": tc["output_index"],
                        "item": {
                            "type": "function_call",
                            "id": tc["id"],
                            "call_id": tc["id"],
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                            "status": "completed",
                        },
                    },
                )

        # 完成文本消息
        if text_output_index is not None and full_content:
            for item in response_obj["output"]:
                if item.get("id") == msg_id:
                    item["content"] = [{"type": "output_text", "text": full_content}]
                    item["status"] = "completed"
                    break

            yield self._sse_event(
                "response.output_item.done",
                {
                    "response_id": response_id,
                    "output_index": text_output_index,
                    "item": {
                        "type": "message",
                        "id": msg_id,
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": full_content}],
                        "status": "completed",
                    },
                },
            )

        # 发送 response.completed
        response_obj["status"] = "completed"
        yield self._sse_event("response.completed", {"response": response_obj})

    async def _finalize_stream(
        self,
        response_id: str,
        response_obj: dict,
        msg_id: str,
        text_output_index: int,
        full_content: str,
    ) -> AsyncIterator[bytes]:
        """流结束但无 finish_reason 时的收尾处理"""
        if full_content:
            if text_output_index is None:
                text_output_index = 0
                response_obj["output"] = [
                    {
                        "id": msg_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": full_content}],
                        "status": "completed",
                    }
                ]
            else:
                for item in response_obj["output"]:
                    if item.get("id") == msg_id:
                        item["content"] = [
                            {"type": "output_text", "text": full_content}
                        ]
                        item["status"] = "completed"
                        break

        response_obj["status"] = "completed"
        yield self._sse_event("response.completed", {"response": response_obj})

    # ============================================================
    # 辅助方法
    # ============================================================

    def _generate_id(self, prefix: str) -> str:
        """生成唯一 ID

        格式: {prefix}_{uuid_hex}
        例如: resp_abc123, msg_def456, call_ghi789
        """
        return f"{prefix}_{uuid.uuid4().hex[:24]}"

    def _sse_event(self, event_type: str, data: dict) -> bytes:
        """格式化 SSE 事件

        格式: data: {json}\n\n
        注意: 不包含 event 行，与 open-responses-server 一致
        """
        data["type"] = event_type
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")

    async def _read_sse_lines(self, content) -> AsyncIterator[str]:
        """逐行读取 SSE 数据流"""
        buffer = ""
        async for chunk in content.iter_any():
            buffer += chunk.decode("utf-8", errors="ignore")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.strip():
                    yield line
        if buffer.strip():
            yield buffer.strip()

    def _save_conversation(
        self, response_id: str, req: ResponsesRequest, assistant_message: dict
    ):
        """保存会话历史，支持多轮对话

        使用 previous_response_id 可以获取历史消息
        """
        # 获取历史
        messages = list(self.sessions.get_messages(req.previous_response_id))

        # 添加 system 指令
        if req.instructions:
            messages = [{"role": "system", "content": req.instructions}] + messages

        # 添加用户输入
        messages.extend(self._parse_input(req.input))

        # 添加助手响应
        messages.append(assistant_message)

        # 保存
        self.sessions.save_session(response_id, messages)
