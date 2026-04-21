"""重试策略模块"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryRule:
    """重试规则"""
    status: int
    max_retries: int = 10
    delay: float = 2.0
    jitter: float = 1.0
    body_contains: Optional[str] = None


def should_retry(response, rules: list[RetryRule]) -> bool:
    """检查响应是否需要重试

    按顺序检查规则列表，如果状态码匹配且（body_contains 为空或响应体包含该字符串），
    则返回 True。

    Args:
        response: httpx.Response 对象
        rules: 重试规则列表

    Returns:
        True 如果需要重试，False 否则
    """
    for rule in rules:
        if response.status_code == rule.status:
            if rule.body_contains is None:
                return True
            if rule.body_contains in response.text:
                return True
    return False


def calculate_delay(attempt: int, delay: float, jitter: float) -> float:
    """计算重试延迟时间

    使用线性退避策略：delay + attempt * jitter

    Args:
        attempt: 当前尝试次数（从 0 开始）
        delay: 基础延迟（秒）
        jitter: 每次尝试增加的延迟（秒）

    Returns:
        延迟时间（秒）
    """
    return delay + attempt * jitter
