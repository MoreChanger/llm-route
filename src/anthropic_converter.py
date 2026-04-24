# src/anthropic_converter.py
"""Anthropic Messages API 请求格式转换器

解决 Claude Code 等客户端发送的请求格式与京东云等服务商不兼容的问题。

主要功能：
- 将 content 数组格式转换为字符串格式
- 保持其他字段不变
"""
import json
from typing import Union


def convert_anthropic_request(body: Union[bytes, str, dict]) -> bytes:
    """转换 Anthropic Messages API 请求格式

    将 messages 中每条消息的 content 从数组格式转换为字符串格式。

    Args:
        body: 原始请求体（bytes、str 或 dict）

    Returns:
        转换后的请求体（bytes）
    """
    # 解析请求体
    if isinstance(body, bytes):
        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            try:
                body_str = body.decode("gbk")
            except UnicodeDecodeError:
                body_str = body.decode("utf-8", errors="ignore")
        data = json.loads(body_str)
    elif isinstance(body, str):
        data = json.loads(body)
    elif isinstance(body, dict):
        data = body
    else:
        return body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    # 转换 messages 中的 content 格式
    if "messages" in data and isinstance(data["messages"], list):
        for message in data["messages"]:
            if isinstance(message, dict) and "content" in message:
                message["content"] = _convert_content(message["content"])

    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _convert_content(content) -> Union[str, list]:
    """转换单条消息的 content 字段

    支持的格式：
    - 字符串：直接返回
    - 数组：提取文本内容合并为字符串
      - [{"type": "text", "text": "hello"}] -> "hello"
      - [{"type": "text", "text": "hello"}, {"type": "text", "text": " world"}] -> "hello world"

    Args:
        content: 原始 content 字段

    Returns:
        转换后的 content（字符串或原数组）
    """
    # 字符串格式，无需转换
    if isinstance(content, str):
        return content

    # 数组格式，提取文本
    if isinstance(content, list):
        text_parts = []
        has_non_text = False

        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                # 支持 type: "text" 格式
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(item["text"])
                else:
                    # 包含非文本类型（如 image），标记不转换
                    has_non_text = True

        # 如果包含非文本类型（图片等），保持原格式
        if has_non_text:
            return content

        # 纯文本内容，合并为字符串
        return "".join(text_parts)

    # 其他格式，直接返回
    return content
