"""HTTP 代理服务模块"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional
import logging

import aiohttp
from aiohttp import web

from src.config import Config, Route, Upstream
from src.retry import calculate_delay
from src.log_file import LogManager
from src.responses_converter import ResponsesConverter
from src.session_manager import SessionManager
from src.responses_models import ResponsesRequest
from src.anthropic_converter import convert_anthropic_request

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """请求上下文"""
    method: str
    path: str
    headers: dict
    body: bytes
    query_string: str = ""
    matched_route: Optional[Route] = None
    upstream: Optional[Upstream] = None
    attempt: int = 0
    start_time: float = 0.0  # 请求开始时间
    _request: Optional[web.Request] = None  # 原始请求对象，用于流式响应


def match_route(path: str, routes: list[Route]) -> Optional[Route]:
    """匹配路由规则

    Args:
        path: 请求路径
        routes: 路由规则列表

    Returns:
        匹配的 Route 或 None
    """
    for route in routes:
        if route.path == path:
            return route
    return None


class ProxyServer:
    """HTTP 代理服务器"""

    def __init__(self, config: Config, log_manager: LogManager):
        self.config = config
        self.log_manager = log_manager
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.client_session: Optional[aiohttp.ClientSession] = None

        # 新增：Responses 转换器
        self.session_manager = SessionManager()
        self.responses_converter = ResponsesConverter(self.session_manager)

    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        self.log_manager.log(message, level)

    def get_logs(self) -> list[str]:
        """获取日志列表"""
        return self.log_manager.get_logs()

    def get_logs_page(self, page: int, page_size: int = 100) -> tuple[list[str], int, int]:
        """获取分页日志"""
        return self.log_manager.get_logs_page(page, page_size)

    async def start(self) -> None:
        """启动代理服务器"""
        # 创建 aiohttp 应用
        self.app = web.Application()
        self.app.router.add_route("*", "/{path:.*}", self.handle_request)

        # 创建 HTTP 客户端会话（设置超时）
        timeout = aiohttp.ClientTimeout(total=120, connect=30)
        self.client_session = aiohttp.ClientSession(timeout=timeout)

        # 启动服务器
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(
            self.runner,
            self.config.host,
            self.config.port if isinstance(self.config.port, int) else 8087
        )
        await self.site.start()

        port = self.config.port if isinstance(self.config.port, int) else 8087
        self.log(f"服务启动，监听 {self.config.host}:{port}")

    async def stop(self) -> None:
        """停止代理服务器"""
        if self.client_session:
            await self.client_session.close()
            self.client_session = None

        if self.runner:
            await self.runner.cleanup()
            self.runner = None

        self.site = None
        self.app = None
        self.log("服务已停止")

    async def handle_request(self, request: web.Request) -> web.Response:
        """处理所有请求"""
        # 创建请求上下文
        body = await request.read()
        ctx = RequestContext(
            method=request.method,
            path=request.path,
            headers=dict(request.headers),
            body=body,
            query_string=request.query_string,
            start_time=time.time(),
            _request=request
        )

        # 匹配路由
        ctx.matched_route = match_route(ctx.path, self.config.routes)
        if ctx.matched_route is None:
            # 记录 404 请求
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> 404 Not Found ({elapsed_ms:.0f}ms)")
            return web.Response(status=404, text="Not Found")

        # 获取上游配置
        upstream_name = ctx.matched_route.upstream
        ctx.upstream = self.config.upstreams.get(upstream_name)
        if ctx.upstream is None:
            # 记录配置错误
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> 502 Unknown upstream: {upstream_name} ({elapsed_ms:.0f}ms)", "ERROR")
            return web.Response(status=502, text=f"Unknown upstream: {upstream_name}")

        # 新增：Responses API 转换分支
        if self._should_convert_responses(ctx):
            return await self._handle_responses(ctx)

        # 新增：Anthropic Messages API 格式转换（京东云等服务商兼容性）
        if self._should_convert_anthropic(ctx):
            ctx.body = convert_anthropic_request(ctx.body)

        # 检测是否为流式请求
        if self._is_streaming_request(ctx.headers, body):
            return await self._forward_streaming(ctx)

        # 代理请求
        return await self.proxy_request(ctx)

    async def proxy_request(self, ctx: RequestContext) -> web.Response:
        """代理请求到上游服务"""
        # 准备请求头（移除 hop-by-hop 头）
        headers = self._filter_headers(ctx.headers)

        # 构建上游 URL
        url = f"{ctx.upstream.url}{ctx.path}"
        if ctx.query_string:
            url = f"{url}?{ctx.query_string}"

        try:
            async with self.client_session.request(
                ctx.method,
                url,
                headers=headers,
                data=ctx.body,
            ) as response:
                body = await response.read()
                response_headers = dict(response.headers)

                # 检查是否需要重试
                if self._should_retry(response.status, body, ctx.attempt):
                    return await self._retry(ctx)

                # 记录请求日志
                elapsed_ms = (time.time() - ctx.start_time) * 1000
                self.log_manager.log_request(
                    method=ctx.method,
                    path=ctx.path,
                    upstream=ctx.matched_route.upstream,
                    status_code=response.status,
                    elapsed_ms=elapsed_ms,
                    retries=ctx.attempt,
                    request_body=ctx.body.decode('utf-8', errors='ignore'),
                    response_body=body.decode('utf-8', errors='ignore')
                )

                # 返回响应（过滤掉 hop-by-hop 头）
                filtered_headers = self._filter_response_headers(response_headers)
                return web.Response(
                    status=response.status,
                    body=body,
                    headers=filtered_headers
                )

        except aiohttp.ClientError as e:
            # 记录错误日志
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> {ctx.matched_route.upstream} [ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

            # 连接错误，尝试重试
            if ctx.attempt < self._get_max_retries():
                return await self._retry(ctx)
            return web.Response(status=502, text=f"Upstream error: {str(e)}")

    def _filter_headers(self, headers: dict) -> dict:
        """过滤请求头，移除 hop-by-hop 头"""
        hop_by_hop = {
            'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
            'upgrade', 'host'
        }
        return {
            k: v for k, v in headers.items()
            if k.lower() not in hop_by_hop
        }

    def _filter_response_headers(self, headers: dict) -> dict:
        """过滤响应头"""
        hop_by_hop = {
            'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
            'upgrade'
        }
        return {
            k: v for k, v in headers.items()
            if k.lower() not in hop_by_hop
        }

    def _should_retry(self, status: int, body: bytes, attempt: int) -> bool:
        """检查是否需要重试"""
        if attempt >= self._get_max_retries():
            return False

        for rule in self.config.retry_rules:
            if status == rule.status:
                if rule.body_contains is None:
                    return True
                if rule.body_contains in body.decode('utf-8', errors='ignore'):
                    return True
        return False

    def _get_max_retries(self) -> int:
        """获取最大重试次数"""
        if self.config.retry_rules:
            return max(rule.max_retries for rule in self.config.retry_rules)
        return 0

    async def _retry(self, ctx: RequestContext) -> web.Response:
        """执行重试"""
        # 找到匹配的重试规则
        delay = 1.0
        for rule in self.config.retry_rules:
            delay = max(delay, rule.delay)

        # 计算延迟
        actual_delay = calculate_delay(ctx.attempt, delay, 0.5)
        await asyncio.sleep(actual_delay)

        # 增加尝试次数并重试
        ctx.attempt += 1
        return await self.proxy_request(ctx)

    def _is_streaming_request(self, headers: dict, body: bytes = b"") -> bool:
        """检测是否为流式请求"""
        accept = headers.get("Accept", "")
        if "text/event-stream" in accept:
            return True

        try:
            import json
            if body:
                data = json.loads(body)
                if data.get("stream") is True:
                    return True
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        return False

    async def _forward_streaming(
        self,
        ctx: RequestContext
    ) -> web.StreamResponse:
        """处理流式请求"""
        # 准备请求头（移除 hop-by-hop 头）
        headers = self._filter_headers(ctx.headers)

        # 构建上游 URL
        url = f"{ctx.upstream.url}{ctx.path}"
        if ctx.query_string:
            url = f"{url}?{ctx.query_string}"

        # 创建流式响应
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(ctx._request)

        try:
            async with self.client_session.request(
                ctx.method,
                url,
                headers=headers,
                data=ctx.body,
            ) as upstream_resp:
                # 收集响应内容用于日志
                resp_chunks = []
                async for chunk in upstream_resp.content.iter_any():
                    resp_chunks.append(chunk)
                    await response.write(chunk)

                # 记录流式请求完成
                elapsed_ms = (time.time() - ctx.start_time) * 1000
                resp_body = b"".join(resp_chunks).decode('utf-8', errors='ignore')
                self.log_manager.log_request(
                    method=ctx.method,
                    path=ctx.path,
                    upstream=ctx.matched_route.upstream,
                    status_code=upstream_resp.status,
                    elapsed_ms=elapsed_ms,
                    retries=ctx.attempt,
                    request_body=ctx.body.decode('utf-8', errors='ignore'),
                    response_body=resp_body
                )
        except aiohttp.ClientError as e:
            # 流式传输错误，记录日志
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> {ctx.matched_route.upstream} [STREAMING ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

        return response

    def _should_convert_responses(self, ctx: RequestContext) -> bool:
        """判断是否需要转换 Responses API"""
        return (
            ctx.path == "/v1/responses" and
            ctx.upstream is not None and
            ctx.upstream.convert_responses
        )

    def _should_convert_anthropic(self, ctx: RequestContext) -> bool:
        """判断是否需要转换 Anthropic Messages API 格式

        当满足以下条件时进行格式转换：
        1. 请求路径为 /v1/messages
        2. 上游协议为 anthropic
        3. 请求方法为 POST
        """
        return (
            ctx.path == "/v1/messages" and
            ctx.upstream is not None and
            ctx.upstream.protocol == "anthropic" and
            ctx.method == "POST"
        )

    def _parse_responses_request(self, body: bytes) -> ResponsesRequest:
        """解析 Responses API 请求"""
        # 尝试多种编码
        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            try:
                body_str = body.decode("gbk")
            except UnicodeDecodeError:
                body_str = body.decode("utf-8", errors="ignore")

        req_body = json.loads(body_str)
        return ResponsesRequest(
            model=req_body.get("model", ""),
            input=req_body.get("input", []),
            instructions=req_body.get("instructions"),
            previous_response_id=req_body.get("previous_response_id"),
            tools=req_body.get("tools"),
            stream=req_body.get("stream", False)
        )

    async def _handle_responses(self, ctx: RequestContext) -> web.Response:
        """处理 /responses 请求（转换模式）"""
        try:
            responses_req = self._parse_responses_request(ctx.body)
        except (json.JSONDecodeError, KeyError) as e:
            return web.Response(status=400, text=f"Invalid request: {e}")

        chat_body = self.responses_converter.convert_request(responses_req)
        url = f"{ctx.upstream.url}/v1/chat/completions"
        headers = self._filter_headers(ctx.headers)
        headers["Content-Type"] = "application/json"

        if responses_req.stream:
            return await self._forward_responses_streaming(
                ctx, url, headers, chat_body, responses_req
            )
        else:
            return await self._forward_responses(ctx, url, headers, chat_body, responses_req)

    async def _forward_responses(
        self,
        ctx: RequestContext,
        url: str,
        headers: dict,
        chat_body: dict,
        responses_req: ResponsesRequest
    ) -> web.Response:
        """非流式：发送 Chat Completions，转换响应"""
        try:
            # 简化请求头，只保留必要的认证信息
            simple_headers = {
                "Content-Type": "application/json",
                "Authorization": headers.get("Authorization", ""),
            }
            if "x-api-key" in headers:
                simple_headers["x-api-key"] = headers["x-api-key"]
            async with self.client_session.post(
                url,
                json=chat_body,
                headers=simple_headers
            ) as resp:
                resp_body = await resp.read()
                if self._should_retry(resp.status, resp_body, ctx.attempt):
                    return await self._retry_responses(ctx, responses_req)

                chat_resp = json.loads(resp_body)
                responses_resp = self.responses_converter.convert_response(
                    chat_resp, responses_req
                )

                elapsed_ms = (time.time() - ctx.start_time) * 1000
                self.log_manager.log_request(
                    method=ctx.method,
                    path=ctx.path,
                    upstream=f"{ctx.matched_route.upstream} (converted)",
                    status_code=resp.status,
                    elapsed_ms=elapsed_ms,
                    retries=ctx.attempt,
                    request_body=json.dumps(chat_body),
                    response_body=json.dumps(responses_resp)
                )

                return web.Response(
                    status=resp.status if resp.status >= 400 else 200,
                    body=json.dumps(responses_resp),
                    content_type="application/json"
                )
        except aiohttp.ClientError as e:
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> [ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

            if ctx.attempt < self._get_max_retries():
                return await self._retry_responses(ctx, responses_req)
            return web.Response(status=502, text=f"Upstream error: {str(e)}")

    async def _forward_responses_streaming(
        self,
        ctx: RequestContext,
        url: str,
        headers: dict,
        chat_body: dict,
        responses_req: ResponsesRequest
    ) -> web.StreamResponse:
        """流式：转换 SSE 流"""
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(ctx._request)

        # 收集响应内容用于调试
        response_chunks = []

        try:
            # 简化请求头，只保留必要的认证信息
            simple_headers = {
                "Content-Type": "application/json",
                "Authorization": headers.get("Authorization", ""),
            }
            if "x-api-key" in headers:
                simple_headers["x-api-key"] = headers["x-api-key"]
            async with self.client_session.post(
                url,
                json=chat_body,
                headers=simple_headers
            ) as upstream_resp:
                # 检查上游响应状态
                if upstream_resp.status >= 400:
                    # 上游返回错误，直接转发错误响应
                    error_body = await upstream_resp.read()
                    elapsed_ms = (time.time() - ctx.start_time) * 1000
                    self.log_manager.log_request(
                        method=ctx.method,
                        path=ctx.path,
                        upstream=f"{ctx.matched_route.upstream} (converted)",
                        status_code=upstream_resp.status,
                        elapsed_ms=elapsed_ms,
                        retries=ctx.attempt,
                        request_body=json.dumps(chat_body),
                        response_body=error_body.decode('utf-8', errors='ignore')
                    )
                    return web.Response(
                        status=upstream_resp.status,
                        body=error_body,
                        content_type="application/json"
                    )

                async for chunk in self.responses_converter.convert_stream(
                    upstream_resp.content,
                    responses_req
                ):
                    response_chunks.append(chunk)
                    await response.write(chunk)

            elapsed_ms = (time.time() - ctx.start_time) * 1000
            # 记录详细的流式响应内容
            resp_body = b"".join(response_chunks).decode('utf-8', errors='ignore')
            self.log_manager.log_request(
                method=ctx.method,
                path=ctx.path,
                upstream=f"{ctx.matched_route.upstream} (converted/streaming)",
                status_code=200,
                elapsed_ms=elapsed_ms,
                retries=ctx.attempt,
                request_body=json.dumps(chat_body),
                response_body=resp_body
            )
        except aiohttp.ClientError as e:
            elapsed_ms = (time.time() - ctx.start_time) * 1000
            self.log(f"{ctx.method} {ctx.path} -> [STREAMING ERROR] {elapsed_ms:.0f}ms - {str(e)}", "ERROR")

        return response

    async def _retry_responses(
        self,
        ctx: RequestContext,
        responses_req: ResponsesRequest
    ) -> web.Response:
        """重试 Responses 请求"""
        delay = 1.0
        for rule in self.config.retry_rules:
            delay = max(delay, rule.delay)

        actual_delay = calculate_delay(ctx.attempt, delay, 0.5)
        await asyncio.sleep(actual_delay)

        ctx.attempt += 1
        return await self._handle_responses(ctx)
