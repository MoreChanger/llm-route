"""代理服务模块测试"""

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.http_writer import HttpVersion11

from src.proxy import (
    ProxyServer,
    match_route,
    RequestContext,
    RollingBuffer,
    STREAMING_LOG_MAX_SIZE,
)
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
                "anthropic": Upstream(
                    url="https://api.anthropic.com", protocol="anthropic"
                ),
                "openai": Upstream(url="https://api.openai.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/messages", upstream="anthropic"),
                Route(path="/v1/chat/completions", upstream="openai"),
            ],
            retry_rules=[
                RetryRule(status=429, max_retries=2, delay=0.1, jitter=0.05),
            ],
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
            async with session.get("http://127.0.0.1:18087/unknown") as resp:
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
            async with session.get("http://127.0.0.1:18087/unknown/path") as resp:
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
                "http://127.0.0.1:18087/v1/messages",
                json={"test": "data"},
                headers={"Content-Type": "application/json"},
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
        assert server._is_streaming_request({}, b"{}") is False

        log_manager.stop()


# 在 tests/test_proxy.py 末尾添加


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
                    convert_responses=True,
                ),
                "openai": Upstream(
                    url="https://api.openai.com",
                    protocol="openai",
                    convert_responses=False,
                ),
            },
            routes=[
                Route(path="/v1/responses", upstream="ollama"),
                Route(path="/v1/chat/completions", upstream="openai"),
            ],
            retry_rules=[],
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
            path="/v1/responses",
            headers={},
            body=b"{}",
            upstream=config_with_convert.upstreams["ollama"],
        )

        assert server._should_convert_responses(ctx) is True
        log_manager.stop()

    def test_should_convert_responses_false_path(
        self, config_with_convert, log_manager
    ):
        """测试路径不匹配"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/chat/completions",
            headers={},
            body=b"{}",
            upstream=config_with_convert.upstreams["ollama"],
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_should_convert_responses_false_flag(
        self, config_with_convert, log_manager
    ):
        """测试标志为 False"""
        server = ProxyServer(config_with_convert, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/responses",
            headers={},
            body=b"{}",
            upstream=config_with_convert.upstreams["openai"],
        )

        assert server._should_convert_responses(ctx) is False
        log_manager.stop()

    def test_parse_responses_request(self, config_with_convert, log_manager):
        """测试解析 Responses 请求"""
        server = ProxyServer(config_with_convert, log_manager)

        body = json.dumps(
            {
                "model": "gpt-4",
                "input": "Hello",
                "instructions": "Be helpful",
                "stream": True,
            }
        ).encode()

        req = server._parse_responses_request(body)

        assert req.model == "gpt-4"
        assert req.input == "Hello"
        assert req.instructions == "Be helpful"
        assert req.stream is True
        log_manager.stop()


class TestRollingBuffer:
    """RollingBuffer 类的边界条件测试"""

    def test_init_with_max_size(self):
        """测试初始化"""
        buffer = RollingBuffer(max_size=100)
        assert buffer.max_size == 100
        assert buffer.size == 0
        assert buffer.truncated is False

    def test_append_single_chunk(self):
        """测试添加单个数据块"""
        buffer = RollingBuffer(max_size=100)
        buffer.append(b"hello")
        assert buffer.size == 5
        assert buffer.get_data() == b"hello"
        assert buffer.truncated is False

    def test_append_multiple_chunks(self):
        """测试添加多个数据块"""
        buffer = RollingBuffer(max_size=100)
        buffer.append(b"hello")
        buffer.append(b" ")
        buffer.append(b"world")
        assert buffer.size == 11
        assert buffer.get_data() == b"hello world"

    def test_append_empty_chunk(self):
        """测试添加空数据块"""
        buffer = RollingBuffer(max_size=100)
        buffer.append(b"hello")
        buffer.append(b"")
        assert buffer.size == 5
        assert buffer.get_data() == b"hello"

    def test_truncation_when_exceeds_max_size(self):
        """测试超过最大大小时的截断"""
        buffer = RollingBuffer(max_size=10)
        buffer.append(b"12345")
        buffer.append(b"67890")
        buffer.append(b"abcde")
        assert buffer.truncated is True
        assert buffer.size <= 10

    def test_truncation_discards_oldest_first(self):
        """测试截断时丢弃最旧的数据"""
        buffer = RollingBuffer(max_size=10)
        buffer.append(b"aaaaa")
        buffer.append(b"bbbbb")
        buffer.append(b"ccccc")
        data = buffer.get_data()
        assert b"aaaaa" not in data
        assert b"ccccc" in data

    def test_single_chunk_larger_than_max_size(self):
        """测试单个数据块超过最大大小"""
        buffer = RollingBuffer(max_size=10)
        buffer.append(b"this is a very long chunk that exceeds max size")
        assert buffer.size == 47
        assert buffer.truncated is False

    def test_exact_max_size(self):
        """测试恰好等于最大大小"""
        buffer = RollingBuffer(max_size=10)
        buffer.append(b"12345")
        buffer.append(b"67890")
        assert buffer.size == 10
        assert buffer.truncated is False

    def test_one_byte_over_max_size(self):
        """测试超过最大大小一个字节"""
        buffer = RollingBuffer(max_size=10)
        buffer.append(b"12345")
        buffer.append(b"67890")
        buffer.append(b"X")
        assert buffer.truncated is True

    def test_get_data_returns_bytes(self):
        """测试 get_data 返回 bytes 类型"""
        buffer = RollingBuffer(max_size=100)
        buffer.append(b"test")
        result = buffer.get_data()
        assert isinstance(result, bytes)

    def test_size_property(self):
        """测试 size 属性"""
        buffer = RollingBuffer(max_size=100)
        assert buffer.size == 0
        buffer.append(b"a")
        assert buffer.size == 1
        buffer.append(b"bc")
        assert buffer.size == 3

    def test_truncated_property_initially_false(self):
        """测试 truncated 属性初始为 False"""
        buffer = RollingBuffer(max_size=100)
        assert buffer.truncated is False

    def test_multiple_truncations(self):
        """测试多次截断"""
        buffer = RollingBuffer(max_size=5)
        buffer.append(b"aaa")
        buffer.append(b"bbb")
        buffer.append(b"ccc")
        buffer.append(b"ddd")
        assert buffer.truncated is True
        assert buffer.size <= 5


class TestStreamingRequestExceptions:
    """流式请求处理的异常情况测试"""

    @pytest.fixture
    def config(self):
        """测试配置"""
        return Config(
            host="127.0.0.1",
            port=18089,
            upstreams={
                "anthropic": Upstream(
                    url="https://api.anthropic.com", protocol="anthropic"
                ),
            },
            routes=[
                Route(path="/v1/messages", upstream="anthropic"),
            ],
            retry_rules=[],
        )

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    @pytest.mark.asyncio
    async def test_forward_streaming_missing_request_object(self, config, log_manager):
        """测试流式请求缺少请求对象"""
        server = ProxyServer(config, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/messages",
            headers={"Accept": "text/event-stream"},
            body=b'{"stream": true}',
            upstream=config.upstreams["anthropic"],
            matched_route=config.routes[0],
            _request=None,
        )

        response = await server._forward_streaming(ctx)
        assert response.status == 500

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_forward_streaming_timeout(self, config, log_manager):
        """测试流式请求超时"""
        server = ProxyServer(config, log_manager)

        mock_request = MagicMock(spec=web.Request)
        mock_request._payload_writer = AsyncMock()
        mock_request.drain = AsyncMock()
        mock_request.version = HttpVersion11
        mock_request.keep_alive = True

        ctx = RequestContext(
            method="POST",
            path="/v1/messages",
            headers={"Accept": "text/event-stream"},
            body=b'{"stream": true}',
            upstream=config.upstreams["anthropic"],
            matched_route=config.routes[0],
            _request=mock_request,
        )

        async def timeout_iterator():
            raise asyncio.TimeoutError("Read timeout")
            yield b""

        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.content.iter_any = timeout_iterator
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.status = 200
        mock_session.request = MagicMock(return_value=mock_response)

        server.client_session = mock_session

        response = await server._forward_streaming(ctx)
        assert response is not None

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_forward_streaming_client_exception(self, config, log_manager):
        """测试流式请求客户端异常"""
        server = ProxyServer(config, log_manager)

        mock_request = MagicMock(spec=web.Request)
        mock_request._payload_writer = AsyncMock()
        mock_request.drain = AsyncMock()
        mock_request.version = HttpVersion11
        mock_request.keep_alive = True

        ctx = RequestContext(
            method="POST",
            path="/v1/messages",
            headers={"Accept": "text/event-stream"},
            body=b'{"stream": true}',
            upstream=config.upstreams["anthropic"],
            matched_route=config.routes[0],
            _request=mock_request,
        )

        import aiohttp

        mock_session = MagicMock()
        mock_session.request = MagicMock(
            side_effect=aiohttp.ClientError("Connection failed")
        )

        server.client_session = mock_session

        response = await server._forward_streaming(ctx)
        assert response is not None

        log_manager.stop()


class TestForwardResponsesStreamingErrors:
    """_forward_responses_streaming 方法的错误处理测试"""

    @pytest.fixture
    def config_with_convert(self):
        """带转换功能的测试配置"""
        return Config(
            host="127.0.0.1",
            port=18090,
            upstreams={
                "ollama": Upstream(
                    url="http://localhost:11434/v1",
                    protocol="openai",
                    convert_responses=True,
                ),
            },
            routes=[
                Route(path="/v1/responses", upstream="ollama"),
            ],
            retry_rules=[],
        )

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    @pytest.mark.asyncio
    async def test_forward_responses_streaming_missing_request(
        self, config_with_convert, log_manager
    ):
        """测试流式响应转换缺少请求对象"""
        server = ProxyServer(config_with_convert, log_manager)

        from src.responses_models import ResponsesRequest

        ctx = RequestContext(
            method="POST",
            path="/v1/responses",
            headers={},
            body=b'{"model": "test", "input": "hello", "stream": true}',
            upstream=config_with_convert.upstreams["ollama"],
            matched_route=config_with_convert.routes[0],
            _request=None,
        )

        responses_req = ResponsesRequest(
            model="test",
            input="hello",
            stream=True,
        )

        response = await server._forward_responses_streaming(
            ctx, "http://test.url", {}, {}, responses_req
        )
        assert response.status == 500

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_forward_responses_streaming_timeout(
        self, config_with_convert, log_manager
    ):
        """测试流式响应转换超时"""
        server = ProxyServer(config_with_convert, log_manager)

        from src.responses_models import ResponsesRequest

        mock_request = MagicMock(spec=web.Request)
        mock_request._payload_writer = AsyncMock()
        mock_request.drain = AsyncMock()
        mock_request.version = HttpVersion11
        mock_request.keep_alive = True

        ctx = RequestContext(
            method="POST",
            path="/v1/responses",
            headers={},
            body=b'{"model": "test", "input": "hello", "stream": true}',
            upstream=config_with_convert.upstreams["ollama"],
            matched_route=config_with_convert.routes[0],
            _request=mock_request,
        )

        responses_req = ResponsesRequest(
            model="test",
            input="hello",
            stream=True,
        )

        async def timeout_iterator():
            raise asyncio.TimeoutError("Read timeout")
            yield b""

        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.content.iter_any = timeout_iterator
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_response)

        server.client_session = mock_session

        response = await server._forward_responses_streaming(
            ctx, "http://test.url", {}, {}, responses_req
        )
        assert response is not None

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_forward_responses_streaming_client_error(
        self, config_with_convert, log_manager
    ):
        """测试流式响应转换客户端错误"""
        server = ProxyServer(config_with_convert, log_manager)

        from src.responses_models import ResponsesRequest

        mock_request = MagicMock(spec=web.Request)
        mock_request._payload_writer = AsyncMock()
        mock_request.drain = AsyncMock()
        mock_request.version = HttpVersion11
        mock_request.keep_alive = True

        ctx = RequestContext(
            method="POST",
            path="/v1/responses",
            headers={},
            body=b'{"model": "test", "input": "hello", "stream": true}',
            upstream=config_with_convert.upstreams["ollama"],
            matched_route=config_with_convert.routes[0],
            _request=mock_request,
        )

        responses_req = ResponsesRequest(
            model="test",
            input="hello",
            stream=True,
        )

        import aiohttp

        mock_session = MagicMock()
        mock_session.post = MagicMock(
            side_effect=aiohttp.ClientError("Connection failed")
        )

        server.client_session = mock_session

        response = await server._forward_responses_streaming(
            ctx, "http://test.url", {}, {}, responses_req
        )
        assert response is not None

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_forward_responses_streaming_upstream_error(
        self, config_with_convert, log_manager
    ):
        """测试流式响应转换上游返回错误"""
        server = ProxyServer(config_with_convert, log_manager)

        from src.responses_models import ResponsesRequest

        mock_request = MagicMock(spec=web.Request)
        mock_request._payload_writer = AsyncMock()
        mock_request.drain = AsyncMock()
        mock_request.version = HttpVersion11
        mock_request.keep_alive = True

        ctx = RequestContext(
            method="POST",
            path="/v1/responses",
            headers={},
            body=b'{"model": "test", "input": "hello", "stream": true}',
            upstream=config_with_convert.upstreams["ollama"],
            matched_route=config_with_convert.routes[0],
            _request=mock_request,
        )

        responses_req = ResponsesRequest(
            model="test",
            input="hello",
            stream=True,
        )

        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.read = AsyncMock(return_value=b'{"error": "Internal error"}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_response)

        server.client_session = mock_session

        response = await server._forward_responses_streaming(
            ctx, "http://test.url", {}, {}, responses_req
        )
        assert response.status == 500

        log_manager.stop()


class TestRetryMechanism:
    """重试机制的边界条件测试"""

    @pytest.fixture
    def config_with_retry(self):
        """带重试规则的测试配置"""
        return Config(
            host="127.0.0.1",
            port=18091,
            upstreams={
                "test": Upstream(url="https://test.api.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/test", upstream="test"),
            ],
            retry_rules=[
                RetryRule(status=429, max_retries=3, delay=0.01, jitter=0.0),
                RetryRule(status=503, max_retries=2, delay=0.01, jitter=0.0),
            ],
        )

    @pytest.fixture
    def log_manager(self):
        """测试日志管理器"""
        lm = LogManager()
        lm.start(log_level=2)
        return lm

    def test_should_retry_within_limit(self, config_with_retry, log_manager):
        """测试在重试限制内"""
        server = ProxyServer(config_with_retry, log_manager)

        assert server._should_retry(429, b"", 0) is True
        assert server._should_retry(429, b"", 1) is True
        assert server._should_retry(429, b"", 2) is True

        log_manager.stop()

    def test_should_retry_exceeds_limit(self, config_with_retry, log_manager):
        """测试超过重试限制"""
        server = ProxyServer(config_with_retry, log_manager)

        assert server._should_retry(429, b"", 3) is False
        assert server._should_retry(429, b"", 4) is False

        log_manager.stop()

    def test_should_retry_different_status(self, config_with_retry, log_manager):
        """测试不同状态码的重试"""
        server = ProxyServer(config_with_retry, log_manager)

        assert server._should_retry(429, b"", 0) is True
        assert server._should_retry(503, b"", 0) is True
        assert server._should_retry(500, b"", 0) is False
        assert server._should_retry(200, b"", 0) is False

        log_manager.stop()

    def test_should_retry_body_contains(self, config_with_retry, log_manager):
        """测试响应体包含特定内容时重试"""
        config = Config(
            host="127.0.0.1",
            port=18092,
            upstreams={
                "test": Upstream(url="https://test.api.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/test", upstream="test"),
            ],
            retry_rules=[
                RetryRule(
                    status=200,
                    max_retries=2,
                    delay=0.01,
                    jitter=0.0,
                    body_contains="retry_me",
                ),
            ],
        )
        lm = LogManager()
        lm.start(log_level=2)
        server = ProxyServer(config, lm)

        assert server._should_retry(200, b"retry_me please", 0) is True
        assert server._should_retry(200, b"no retry here", 0) is False

        lm.stop()

    def test_get_max_retries(self, config_with_retry, log_manager):
        """测试获取最大重试次数"""
        server = ProxyServer(config_with_retry, log_manager)

        assert server._get_max_retries() == 3

        log_manager.stop()

    def test_get_max_retries_no_rules(self, log_manager):
        """测试没有重试规则时"""
        config = Config(
            host="127.0.0.1",
            port=18093,
            upstreams={
                "test": Upstream(url="https://test.api.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/test", upstream="test"),
            ],
            retry_rules=[],
        )
        lm = LogManager()
        lm.start(log_level=2)
        server = ProxyServer(config, lm)

        assert server._get_max_retries() == 0

        lm.stop()

    def test_should_retry_with_empty_body(self, config_with_retry, log_manager):
        """测试空响应体时的重试"""
        server = ProxyServer(config_with_retry, log_manager)

        assert server._should_retry(429, b"", 0) is True
        assert server._should_retry(503, b"", 0) is True

        log_manager.stop()

    @pytest.mark.asyncio
    async def test_retry_increments_attempt(self, config_with_retry, log_manager):
        """测试重试增加尝试次数"""
        server = ProxyServer(config_with_retry, log_manager)

        ctx = RequestContext(
            method="POST",
            path="/v1/test",
            headers={},
            body=b"{}",
            upstream=config_with_retry.upstreams["test"],
            matched_route=config_with_retry.routes[0],
            attempt=0,
        )

        initial_attempt = ctx.attempt

        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"{}")
        mock_response.headers = {}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_response)
        mock_session.close = AsyncMock()

        server.client_session = mock_session

        await server._retry(ctx, 429)

        assert ctx.attempt == initial_attempt + 1

        log_manager.stop()

    def test_should_retry_body_contains_unicode(self, config_with_retry, log_manager):
        """测试响应体包含 Unicode 字符时的重试"""
        config = Config(
            host="127.0.0.1",
            port=18094,
            upstreams={
                "test": Upstream(url="https://test.api.com", protocol="openai"),
            },
            routes=[
                Route(path="/v1/test", upstream="test"),
            ],
            retry_rules=[
                RetryRule(
                    status=200,
                    max_retries=2,
                    delay=0.01,
                    jitter=0.0,
                    body_contains="错误",
                ),
            ],
        )
        lm = LogManager()
        lm.start(log_level=2)
        server = ProxyServer(config, lm)

        assert server._should_retry(200, "发生错误".encode("utf-8"), 0) is True
        assert server._should_retry(200, b"no error", 0) is False

        lm.stop()
