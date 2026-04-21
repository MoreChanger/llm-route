"""代理服务模块测试"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from aiohttp import web

from src.proxy import ProxyServer, match_route
from src.config import Config, Upstream, Route, RetryRule


class TestMatchRoute:
    def test_match_exact_path(self):
        """测试精确路径匹配"""
        routes = [
            Route(path="/v1/messages", upstream="anthropic"),
            Route(path="/v1/chat/completions", upstream="openai"),
        ]
        result = match_route("/v1/messages", routes)
        assert result.upstream == "anthropic"

    def test_match_different_path(self):
        """测试不同路径匹配"""
        routes = [
            Route(path="/v1/messages", upstream="anthropic"),
            Route(path="/v1/chat/completions", upstream="openai"),
        ]
        result = match_route("/v1/chat/completions", routes)
        assert result.upstream == "openai"

    def test_no_match_returns_none(self):
        """测试无匹配返回 None"""
        routes = [
            Route(path="/v1/messages", upstream="anthropic"),
        ]
        result = match_route("/v1/unknown", routes)
        assert result is None

    def test_match_first_in_list(self):
        """测试匹配列表中第一个"""
        routes = [
            Route(path="/v1/models", upstream="anthropic"),
            Route(path="/v1/models", upstream="openai"),  # 重复路径
        ]
        result = match_route("/v1/models", routes)
        assert result.upstream == "anthropic"


class TestProxyServer:
    @pytest.fixture
    def config(self):
        """测试配置"""
        return Config(
            host="127.0.0.1",
            port=18087,
            upstreams={
                "anthropic": Upstream(url="https://api.anthropic.com", protocol="anthropic"),
                "openai": Upstream(url="https://api.openai.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/messages", upstream="anthropic"),
                Route(path="/v1/chat/completions", upstream="openai"),
            ],
            retry_rules=[
                RetryRule(status=429, max_retries=2, delay=0.1, jitter=0.05),
            ]
        )

    @pytest.mark.asyncio
    async def test_proxy_server_creation(self, config):
        """测试代理服务器创建"""
        server = ProxyServer(config)
        assert server.config == config
        assert server.app is None
        assert server.runner is None

    @pytest.mark.asyncio
    async def test_start_stop_server(self, config):
        """测试启动和停止服务器"""
        server = ProxyServer(config)

        await server.start()
        assert server.runner is not None

        # 验证服务器正在运行
        import aiohttp
        async with aiohttp.ClientSession() as session:
            # 发送一个请求，应该返回 404（没有匹配的路由）
            async with session.get(f"http://127.0.0.1:18087/unknown") as resp:
                assert resp.status == 404

        await server.stop()
        assert server.runner is None

    @pytest.mark.asyncio
    async def test_handle_unknown_path(self, config):
        """测试处理未知路径"""
        server = ProxyServer(config)
        await server.start()

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:18087/unknown/path") as resp:
                assert resp.status == 404

        await server.stop()
