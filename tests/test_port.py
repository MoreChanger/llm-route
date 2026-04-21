"""端口管理模块测试"""
import pytest
from unittest.mock import patch, MagicMock

from src.port import is_port_available, find_available_port, random_available_port


class TestIsPortAvailable:
    def test_port_available(self):
        """测试可用端口"""
        # 使用一个不太可能被占用的端口
        result = is_port_available("127.0.0.1", 59999)
        assert result is True

    def test_port_unavailable(self):
        """测试不可用端口"""
        # 模拟端口被占用
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 59998))

        try:
            result = is_port_available("127.0.0.1", 59998)
            assert result is False
        finally:
            sock.close()

    def test_port_zero_available(self):
        """测试端口 0 总是可用（系统会自动分配）"""
        # 端口 0 是特殊端口，用于让系统自动分配
        # 我们的实现应该返回 True
        result = is_port_available("127.0.0.1", 0)
        assert result is True


class TestFindAvailablePort:
    def test_find_from_available_port(self):
        """测试从可用端口开始查找"""
        port = find_available_port("127.0.0.1", 59997)
        assert port == 59997

    def test_find_next_available_port(self):
        """测试查找下一个可用端口"""
        import socket

        # 占用 59996 端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 59996))

        try:
            port = find_available_port("127.0.0.1", 59996)
            # 应该返回下一个可用端口
            assert port == 59997 or port == 59998
        finally:
            sock.close()

    def test_find_exhausted_ports(self):
        """测试端口耗尽情况"""
        # 使用一个不可能的范围，模拟端口耗尽
        with patch('src.port.is_port_available', return_value=False):
            with pytest.raises(RuntimeError, match="No available port"):
                find_available_port("127.0.0.1", 8087, max_attempts=5)


class TestRandomAvailablePort:
    def test_random_port_returns_int(self):
        """测试随机端口返回整数"""
        port = random_available_port("127.0.0.1")
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_random_port_is_available(self):
        """测试随机端口是可用的"""
        port = random_available_port("127.0.0.1")
        assert is_port_available("127.0.0.1", port)
