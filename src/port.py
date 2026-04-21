"""端口检测与分配模块"""
import socket
import random
from typing import Optional


def is_port_available(host: str, port: int) -> bool:
    """检测端口是否可用

    Args:
        host: 主机地址
        port: 端口号

    Returns:
        True 如果端口可用，False 如果被占用
    """
    if port == 0:
        # 端口 0 是特殊端口，让系统自动分配
        return True

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
        # 如果能成功 bind，说明端口可用
        return True
    except OSError:
        # 如果 bind 失败，说明端口被占用
        return False


def find_available_port(host: str, start: int = 8087, max_attempts: int = 100) -> int:
    """从 start 开始寻找可用端口

    Args:
        host: 主机地址
        start: 起始端口号
        max_attempts: 最大尝试次数

    Returns:
        可用端口号

    Raises:
        RuntimeError: 如果在 max_attempts 内未找到可用端口
    """
    for port in range(start, start + max_attempts):
        if port > 65535:
            break
        if is_port_available(host, port):
            return port

    raise RuntimeError(f"No available port found in range {start}-{start + max_attempts - 1}")


def random_available_port(host: str) -> int:
    """随机分配一个可用端口

    在常用端口范围（1024-65535）内随机选择可用端口。

    Args:
        host: 主机地址

    Returns:
        可用端口号
    """
    # 在高位端口范围内随机选择，避免与常用服务冲突
    for _ in range(100):  # 最多尝试 100 次
        port = random.randint(20000, 65000)
        if is_port_available(host, port):
            return port

    # 如果随机失败，从 20000 开始顺序查找
    return find_available_port(host, 20000)
