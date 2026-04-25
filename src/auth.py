"""Web Admin 认证模块

提供 bcrypt 密码验证、登录锁定和会话管理。
"""

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional

import bcrypt


@dataclass
class AdminSession:
    """管理员会话"""

    token: str
    created_at: float


class AdminAuthManager:
    """管理员认证管理器

    功能：
    - bcrypt 密码验证
    - 登录失败锁定（5 次 = 15 分钟）
    - 会话管理（24 小时 TTL）
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION = 15 * 60  # 15 分钟
    SESSION_TTL = 24 * 60 * 60  # 24 小时

    def __init__(self, password_hash: Optional[str] = None):
        """
        Args:
            password_hash: bcrypt 哈希的密码，来自 config.yaml
        """
        self._password_hash = password_hash
        self._failed_attempts: dict[str, int] = {}  # ip -> count
        self._lockout_until: dict[str, float] = {}  # ip -> timestamp
        self._sessions: dict[str, AdminSession] = {}  # token -> session
        self._lock = threading.Lock()

    def set_password_hash(self, password_hash: Optional[str]) -> None:
        """设置密码哈希"""
        self._password_hash = password_hash

    def has_password(self) -> bool:
        """检查是否配置了密码"""
        return self._password_hash is not None and len(self._password_hash) > 0

    def verify_password(self, password: str) -> bool:
        """验证密码

        Args:
            password: 明文密码

        Returns:
            密码是否正确
        """
        if not self._password_hash:
            return False

        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), self._password_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False

    def check_lockout(self, ip: str) -> bool:
        """检查 IP 是否被锁定

        Args:
            ip: 客户端 IP 地址

        Returns:
            True 表示被锁定，False 表示未锁定
        """
        with self._lock:
            lockout_time = self._lockout_until.get(ip)
            if lockout_time is None:
                return False

            # 检查锁定是否过期
            if time.time() > lockout_time:
                # 锁定已过期，清除记录
                del self._lockout_until[ip]
                self._failed_attempts.pop(ip, None)
                return False

            return True

    def get_lockout_remaining(self, ip: str) -> int:
        """获取锁定剩余时间（秒）

        Args:
            ip: 客户端 IP 地址

        Returns:
            剩余秒数，0 表示未锁定
        """
        with self._lock:
            lockout_time = self._lockout_until.get(ip)
            if lockout_time is None:
                return 0

            remaining = int(lockout_time - time.time())
            return max(0, remaining)

    def record_failure(self, ip: str) -> int:
        """记录登录失败

        Args:
            ip: 客户端 IP 地址

        Returns:
            当前失败次数
        """
        with self._lock:
            count = self._failed_attempts.get(ip, 0) + 1
            self._failed_attempts[ip] = count

            # 达到最大失败次数，触发锁定
            if count >= self.MAX_FAILED_ATTEMPTS:
                self._lockout_until[ip] = time.time() + self.LOCKOUT_DURATION
                # 重置失败计数
                self._failed_attempts.pop(ip, None)

            return count

    def clear_failures(self, ip: str) -> None:
        """清除登录失败记录（登录成功后调用）

        Args:
            ip: 客户端 IP 地址
        """
        with self._lock:
            self._failed_attempts.pop(ip, None)

    def create_session(self) -> str:
        """创建新会话

        Returns:
            会话 token
        """
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = AdminSession(token=token, created_at=time.time())
            # 清理过期会话
            self._cleanup_expired_sessions()
        return token

    def validate_session(self, token: Optional[str]) -> bool:
        """验证会话是否有效

        Args:
            token: 会话 token

        Returns:
            True 表示有效，False 表示无效或已过期
        """
        if not token:
            return False

        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return False

            # 检查是否过期
            if time.time() - session.created_at > self.SESSION_TTL:
                del self._sessions[token]
                return False

            return True

    def _cleanup_expired_sessions(self) -> int:
        """清理过期会话

        Returns:
            清理的会话数量
        """
        now = time.time()
        expired = [
            token
            for token, session in self._sessions.items()
            if now - session.created_at > self.SESSION_TTL
        ]
        for token in expired:
            del self._sessions[token]
        return len(expired)


def generate_password_hash(password: str) -> str:
    """生成 bcrypt 密码哈希

    Args:
        password: 明文密码

    Returns:
        bcrypt 哈希字符串
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
