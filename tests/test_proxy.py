"""代理服务模块测试"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from aiohttp import web

from src.proxy import ProxyServer, match_route, RequestContext
from src.config import Config, Upstream, Route, RetryRule
from src.log_file import LogManager


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

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    @pytest.mark.asyncio
    async def test_proxy_server_creation(self, config, log_manager):
        """测试代理服务器创建"""
        server = ProxyServer(config, log_manager)
        assert server.config == config
        assert server.app is None
        assert server.runner is None
        log_manager.stop()

    @pytest.mark.asyncio
    async def test_start_stop_server(self, config, log_manager):
        """测试启动和停止服务器"""
        server = ProxyServer(config, log_manager)

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
        log_manager.stop()

    @pytest.mark.asyncio
    async def test_handle_unknown_path(self, config, log_manager):
        """测试处理未知路径"""
        server = ProxyServer(config, log_manager)
        await server.start()

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:18087/unknown/path") as resp:
                assert resp.status == 404

        await server.stop()
        log_manager.stop()

    @pytest.mark.asyncio
    async def test_streaming_request(self, config, log_manager):
        """测试流式请求处理"""
        server = ProxyServer(config, log_manager)
        await server.start()

        # 测试流式请求路径存在
        import aiohttp
        async with aiohttp.ClientSession() as session:
            # 发送请求到已知路由
            async with session.post(
                f"http://127.0.0.1:18087/v1/messages",
                json={"test": "data"},
                headers={"Content-Type": "application/json"}
            ) as resp:
                # 由于没有真实上游，会返回 502 或其他错误
                # 这里只验证请求被正确路由
                assert resp.status in [200, 401, 403, 502, 503]

        await server.stop()
        log_manager.stop()

    def test_is_streaming_request(self, config, log_manager):
        """测试流式请求检测"""
        server = ProxyServer(config, log_manager)

        # 带有 Accept: text/event-stream 的请求
        headers = {"Accept": "text/event-stream"}
        assert server._is_streaming_request(headers) is True

        # 请求体中有 stream: true
        body = b'{"stream": true}'
        assert server._is_streaming_request({}, body) is True

        # 非流式请求
        assert server._is_streaming_request({}, b'{}') is False

        log_manager.stop()


# 在 tests/test_proxy.py 末尾添加

import json
from src.responses_models import ResponsesRequest


class TestProxyResponsesHandling:
    @pytest.fixture
    def config_with_convert(self):
        """带转换功能的测试配置"""
        return Config(
            host="127.0.0.1",
            port=18088,
            upstreams={
                "ollama": Upstream(
                    url="http://localhost:11434/v1",
                    protocol="openai",
                    convert_responses=True
                ),
                "openai": Upstream(
                    url="https://api.openai.com",
                    protocol="openai",
                    convert_responses=False
                ),
            },
            routes=[
                Route(path="/responses", upstream="ollama"),
                Route(path="/v1/chat/completions", upstream="openai"),
            ],
            retry_rules=[]
        )

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    def test_should_convert_responses_true(self, config_with_convert, log_manager):
        """测试需要转换的情况"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/responses",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["ollama"]
        )

        assert server._should_convert_responses(ctx) is True
        log_manager.stop()

    def test_should_convert_responses_false_path(self, config_with_convert, log_manager):
        """测试路径不匹配"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/chat/completions",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["ollama"]
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_should_convert_responses_false_flag(self, config_with_convert, log_manager):
        """测试标志为 False"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/responses",
            headers={},
            body=b'{}',
            upstream=config_with_convert.upstreams["openai"]
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_parse_responses_request(self, config_with_convert, log_manager):
        """测试解析 Responses 请求"""
        server = ProxyServer(config_with_convert, log_manager)

        body = json.dumps({
            "model": "gpt-4",
            "input": "Hello",
            "instructions": "Be helpful",
            "stream": True
        }).encode()

        req = server._parse_responses_request(body)

        assert req.model == "gpt-4"
        assert req.input == "Hello"
        assert req.instructions == "Be helpful"
        assert req.stream is True
        log_manager.stop()
