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
