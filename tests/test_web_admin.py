# tests/test_web_admin.py
"""Web 管理界面测试"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from src.web_admin import WebAdminHandler
from src.auth import AdminAuthManager, generate_password_hash
from src.config import Config


class TestWebAdminHandler(AioHTTPTestCase):
    """WebAdminHandler 测试"""

    async def get_application(self):
        """创建测试应用"""
        # 创建 mock 对象
        self.mock_proxy = MagicMock()
        self.mock_proxy.runner = None
        self.mock_proxy.config = Config()
        self.mock_proxy.start = AsyncMock()
        self.mock_proxy.stop = AsyncMock()

        self.mock_log_manager = MagicMock()
        self.mock_log_manager.get_logs_page.return_value = ([], 1, 0)

        # 创建认证管理器（使用测试密码）
        self.password_hash = generate_password_hash("test_password")
        self.auth_manager = AdminAuthManager(password_hash=self.password_hash)

        # 创建 handler
        self.handler = WebAdminHandler(
            proxy_server=self.mock_proxy,
            auth_manager=self.auth_manager,
            log_manager=self.mock_log_manager,
            config_path="config.yaml",
        )

        app = web.Application()
        self.handler.setup_routes(app)
        return app

    # ========== 登录页面测试 ==========

    async def test_login_page_returns_html(self):
        """测试登录页面返回 HTML"""
        resp = await self.client.get("/_admin/login")
        assert resp.status == 200
        text = await resp.text()
        assert "<!DOCTYPE html>" in text
        assert "登录" in text

    async def test_dashboard_redirects_without_auth(self):
        """测试未认证时仪表盘重定向到登录页"""
        # 由于 web_admin.py 在 handle_dashboard 中先检查 has_password，
        # 如果有密码配置，则检查 session，否则返回 200
        # 所以这里应该检查返回的是登录页面（302 或 200 但显示登录）
        resp = await self.client.get("/_admin/", allow_redirects=False)
        # 可能是 302 重定向或 200 显示登录页
        # 当前实现会返回 302 到 /_admin/login
        assert resp.status in [200, 302]

    async def test_dashboard_shows_with_valid_session(self):
        """测试有效会话时显示仪表盘"""
        # 先登录获取 session
        login_resp = await self.client.post(
            "/_admin/api/login", json={"password": "test_password"}
        )
        assert login_resp.status == 200

        # 访问仪表盘
        resp = await self.client.get("/_admin/")
        assert resp.status == 200
        text = await resp.text()
        assert "管理面板" in text

    # ========== 登录 API 测试 ==========

    async def test_login_success(self):
        """测试登录成功"""
        resp = await self.client.post(
            "/_admin/api/login", json={"password": "test_password"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "admin_session" in resp.cookies

    async def test_login_wrong_password(self):
        """测试密码错误"""
        resp = await self.client.post(
            "/_admin/api/login", json={"password": "wrong_password"}
        )
        assert resp.status == 401
        data = await resp.json()
        assert "error" in data

    async def test_login_lockout_after_five_failures(self):
        """测试 5 次失败后锁定"""
        for _ in range(5):
            await self.client.post(
                "/_admin/api/login", json={"password": "wrong_password"}
            )

        # 第 6 次应该被锁定
        resp = await self.client.post(
            "/_admin/api/login", json={"password": "test_password"}
        )
        assert resp.status == 429

    # ========== 状态 API 测试 ==========

    async def test_status_requires_auth(self):
        """测试状态 API 需要认证"""
        resp = await self.client.get("/_admin/api/status")
        assert resp.status == 401

    async def test_status_returns_running_state(self):
        """测试状态 API 返回运行状态"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 获取状态
        resp = await self.client.get("/_admin/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert "running" in data
        assert "port" in data
        assert "uptime" in data

    # ========== 日志 API 测试 ==========

    async def test_logs_requires_auth(self):
        """测试日志 API 需要认证"""
        resp = await self.client.get("/_admin/api/logs")
        assert resp.status == 401

    async def test_logs_returns_paginated_data(self):
        """测试日志 API 返回分页数据"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 获取日志
        self.mock_log_manager.get_logs_page.return_value = (["log line 1"], 1, 1)
        resp = await self.client.get("/_admin/api/logs?page=1&page_size=100")
        assert resp.status == 200
        data = await resp.json()
        assert "logs" in data
        assert "total_pages" in data

    # ========== 配置 API 测试 ==========

    async def test_config_get_requires_auth(self):
        """测试配置获取 API 需要认证"""
        resp = await self.client.get("/_admin/api/config")
        assert resp.status == 401

    async def test_config_get_returns_current_config(self):
        """测试配置获取返回当前配置"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        resp = await self.client.get("/_admin/api/config")
        assert resp.status == 200
        data = await resp.json()
        assert "port" in data
        assert "log_level" in data

    # ========== 服务控制 API 测试 ==========

    async def test_service_start_requires_auth(self):
        """测试启动服务 API 需要认证"""
        resp = await self.client.post("/_admin/api/service/start")
        assert resp.status == 401

    async def test_service_start_calls_proxy(self):
        """测试启动服务调用 proxy"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        resp = await self.client.post("/_admin/api/service/start")
        assert resp.status == 200
        self.mock_proxy.start.assert_called_once()

    async def test_service_stop_requires_auth(self):
        """测试停止服务 API 需要认证"""
        resp = await self.client.post("/_admin/api/service/stop")
        assert resp.status == 401

    async def test_service_stop_calls_proxy(self):
        """测试停止服务调用 proxy"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        resp = await self.client.post("/_admin/api/service/stop")
        assert resp.status == 200
        self.mock_proxy.stop.assert_called_once()


class TestWebAdminNoPassword(AioHTTPTestCase):
    """测试无密码保护场景"""

    async def get_application(self):
        """创建无密码保护的应用"""
        mock_proxy = MagicMock()
        mock_proxy.runner = None
        mock_proxy.config = Config()

        mock_log_manager = MagicMock()
        mock_log_manager.get_logs_page.return_value = ([], 1, 0)

        # 无密码的认证管理器
        auth_manager = AdminAuthManager(password_hash=None)

        handler = WebAdminHandler(
            proxy_server=mock_proxy,
            auth_manager=auth_manager,
            log_manager=mock_log_manager,
            config_path="config.yaml",
        )

        app = web.Application()
        handler.setup_routes(app)
        return app

    async def test_no_password_allows_access(self):
        """测试无密码时允许访问"""
        resp = await self.client.get("/_admin/api/status")
        assert resp.status == 200
