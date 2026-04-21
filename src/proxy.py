"""HTTP 代理服务模块"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from aiohttp import web

from src.config import Config, Route, Upstream
from src.retry import calculate_delay


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

    def __init__(self, config: Config):
        self.config = config
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.client_session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        """启动代理服务器"""
        # 创建 aiohttp 应用
        self.app = web.Application()
        self.app.router.add_route("*", "/{path:.*}", self.handle_request)

        # 创建 HTTP 客户端会话
        self.client_session = aiohttp.ClientSession()

        # 启动服务器
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(
            self.runner,
            self.config.host,
            self.config.port if isinstance(self.config.port, int) else 8087
        )
        await self.site.start()

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
            _request=request
        )

        # 匹配路由
        ctx.matched_route = match_route(ctx.path, self.config.routes)
        if ctx.matched_route is None:
            return web.Response(status=404, text="Not Found")

        # 获取上游配置
        upstream_name = ctx.matched_route.upstream
        ctx.upstream = self.config.upstreams.get(upstream_name)
        if ctx.upstream is None:
            return web.Response(status=502, text=f"Unknown upstream: {upstream_name}")

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

                # 返回响应（过滤掉 hop-by-hop 头）
                filtered_headers = self._filter_response_headers(response_headers)
                return web.Response(
                    status=response.status,
                    body=body,
                    headers=filtered_headers
                )

        except aiohttp.ClientError as e:
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
                async for chunk in upstream_resp.content.iter_any():
                    await response.write(chunk)
        except aiohttp.ClientError as e:
            # 流式传输错误，记录日志
            pass

        return response
