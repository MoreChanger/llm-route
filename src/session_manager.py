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

    def __init__(self, max_sessions: int = 1000, ttl_seconds: int = 3600):
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
            response_id=response_id, messages=messages, created_at=time.time()
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
            self._sessions.keys(), key=lambda k: self._sessions[k].created_at
        )
        del self._sessions[oldest_id]

    def cleanup_expired(self) -> int:
        """清理所有过期会话

        Returns:
            清理的会话数量
        """
        now = time.time()
        expired = [
            k
            for k, v in self._sessions.items()
            if now - v.created_at > self._ttl_seconds
        ]
        for k in expired:
            del self._sessions[k]
        return len(expired)
