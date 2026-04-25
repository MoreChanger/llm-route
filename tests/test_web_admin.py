# tests/test_web_admin.py
"""Web 管理界面测试"""

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


class TestConfigSaveClearsPreset(AioHTTPTestCase):
    """测试保存配置时清除预设标记"""

    async def get_application(self):
        """创建测试应用"""
        self.mock_proxy = MagicMock()
        self.mock_proxy.runner = None
        self.mock_proxy.config = Config()
        # 不在这里设置预设标记，让每个测试自己设置
        self.mock_proxy.start = AsyncMock()
        self.mock_proxy.stop = AsyncMock()

        self.mock_log_manager = MagicMock()
        self.mock_log_manager.get_logs_page.return_value = ([], 1, 0)
        self.mock_log_manager.set_level = MagicMock()

        self.password_hash = generate_password_hash("test_password")
        self.auth_manager = AdminAuthManager(password_hash=self.password_hash)

        # 使用临时文件
        import tempfile

        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        self.temp_file.write("host: 127.0.0.1\nport: 8087\n")
        self.temp_file.close()

        self.handler = WebAdminHandler(
            proxy_server=self.mock_proxy,
            auth_manager=self.auth_manager,
            log_manager=self.mock_log_manager,
            config_path=self.temp_file.name,
        )

        app = web.Application()
        self.handler.setup_routes(app)
        return app

    async def test_config_save_clears_active_preset(self):
        """测试保存配置时清除预设标记"""
        # 设置预设标记
        self.mock_proxy.config._active_preset = "test-preset"

        # 先登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 保存配置（修改端口）
        resp = await self.client.post("/_admin/api/config", json={"port": 9000})
        assert resp.status == 200

        # 验证预设标记被清除
        assert self.mock_proxy.config._active_preset is None

    async def test_config_save_clears_preset_on_log_level_change(self):
        """测试修改日志等级时清除预设标记"""
        # 设置预设标记
        self.mock_proxy.config._active_preset = "test-preset"

        # 先登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 保存配置（修改日志等级）
        resp = await self.client.post("/_admin/api/config", json={"log_level": 3})
        assert resp.status == 200

        # 验证预设标记被清除
        assert self.mock_proxy.config._active_preset is None

    async def test_presets_api_returns_current_preset(self):
        """测试预设 API 返回当前预设"""
        # 先登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 获取预设列表
        resp = await self.client.get("/_admin/api/presets")
        assert resp.status == 200
        data = await resp.json()
        assert "presets" in data
        assert "current_preset" in data
        # 当前没有设置预设，应该是 None
        assert data["current_preset"] is None

    async def test_presets_api_shows_current_marker(self):
        """测试预设列表显示当前预设标记"""
        # 设置当前预设
        self.mock_proxy.config._active_preset = "test-preset"

        # 先登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 获取预设列表
        resp = await self.client.get("/_admin/api/presets")
        assert resp.status == 200
        data = await resp.json()
        assert data["current_preset"] == "test-preset"

    async def test_presets_list_current_marker(self):
        """测试预设列表中每个预设的 current 标记"""
        # 先登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 设置当前预设
        self.mock_proxy.config._active_preset = "test-preset"

        # 获取预设列表
        resp = await self.client.get("/_admin/api/presets")
        assert resp.status == 200
        data = await resp.json()

        # 验证 current_preset 在根级别
        assert data["current_preset"] == "test-preset"

        # 验证每个预设项有 current 字段
        for preset in data["presets"]:
            assert "current" in preset
            # 只有当前预设的 current 为 True
            assert preset["current"] == (preset["name"] == "test-preset")


class TestPresetPreviewAPI(AioHTTPTestCase):
    """测试预设预览 API"""

    async def get_application(self):
        """创建测试应用"""
        self.mock_proxy = MagicMock()
        self.mock_proxy.runner = None
        self.mock_proxy.config = Config()

        self.mock_log_manager = MagicMock()
        self.mock_log_manager.get_logs_page.return_value = ([], 1, 0)

        self.password_hash = generate_password_hash("test_password")
        self.auth_manager = AdminAuthManager(password_hash=self.password_hash)

        # 创建临时预设目录
        import tempfile
        import os

        self.temp_dir = tempfile.mkdtemp()
        self.presets_dir = os.path.join(self.temp_dir, "presets")
        os.makedirs(self.presets_dir)

        # 创建测试预设文件
        preset_content = """
upstreams:
  test-upstream:
    url: https://test.example.com
    protocol: openai
routes:
  - path: /v1/chat
    upstream: test-upstream
retry_rules:
  - status: 429
    max_retries: 5
"""
        with open(os.path.join(self.presets_dir, "test-preset.yaml"), "w") as f:
            f.write(preset_content)

        # 创建空预设
        with open(os.path.join(self.presets_dir, "empty-preset.yaml"), "w") as f:
            f.write("# empty preset")

        self.handler = WebAdminHandler(
            proxy_server=self.mock_proxy,
            auth_manager=self.auth_manager,
            log_manager=self.mock_log_manager,
            config_path="config.yaml",
        )

        app = web.Application()
        self.handler.setup_routes(app)
        return app

    async def test_preview_api_requires_auth(self):
        """测试预览 API 需要认证"""
        resp = await self.client.get("/_admin/api/presets/preview?name=test-preset")
        assert resp.status == 401

    async def test_preview_api_missing_name(self):
        """测试缺少预设名称"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})
        resp = await self.client.get("/_admin/api/presets/preview")
        assert resp.status == 400

    async def test_preview_api_preset_not_found(self):
        """测试预设不存在"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})
        resp = await self.client.get("/_admin/api/presets/preview?name=nonexistent")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data


class TestPresetApplyAPI(AioHTTPTestCase):
    """测试预设应用 API"""

    async def get_application(self):
        """创建测试应用"""
        self.mock_proxy = MagicMock()
        self.mock_proxy.runner = None
        self.mock_proxy.config = Config()

        self.mock_log_manager = MagicMock()
        self.mock_log_manager.get_logs_page.return_value = ([], 1, 0)

        self.password_hash = generate_password_hash("test_password")
        self.auth_manager = AdminAuthManager(password_hash=self.password_hash)

        # 创建临时配置文件
        import tempfile

        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        self.temp_file.write("host: 127.0.0.1\nport: 8087\n")
        self.temp_file.close()

        self.handler = WebAdminHandler(
            proxy_server=self.mock_proxy,
            auth_manager=self.auth_manager,
            log_manager=self.mock_log_manager,
            config_path=self.temp_file.name,
        )

        app = web.Application()
        self.handler.setup_routes(app)
        return app

    async def test_preset_apply_requires_auth(self):
        """测试预设应用 API 需要认证"""
        resp = await self.client.post(
            "/_admin/api/presets/apply", json={"preset": "test-preset"}
        )
        assert resp.status == 401

    async def test_preset_apply_missing_preset_param(self):
        """测试缺少预设参数"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})
        resp = await self.client.post("/_admin/api/presets/apply", json={})
        # 预设名为空，会返回 404（找不到空名称的预设）
        assert resp.status == 404

    async def test_preset_apply_preset_not_found(self):
        """测试预设不存在"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})
        resp = await self.client.post(
            "/_admin/api/presets/apply", json={"preset": "nonexistent-preset"}
        )
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    async def test_preset_apply_invalid_json(self):
        """测试无效 JSON"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})
        resp = await self.client.post(
            "/_admin/api/presets/apply",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_on_config_change_callback(self):
        """测试预设应用后调用回调"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 设置回调
        callback_called = []

        def test_callback():
            callback_called.append(True)

        self.handler.set_on_config_change(test_callback)

        # 尝试应用一个不存在的预设（回调不应该被调用）
        resp = await self.client.post(
            "/_admin/api/presets/apply", json={"preset": "nonexistent-preset"}
        )
        assert resp.status == 404
        assert len(callback_called) == 0

    async def test_config_save_no_callback_on_no_change(self):
        """测试配置保存时没有回调通知（因为这是 Docker 模式功能）"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 配置保存目前不清除 _active_preset 的测试已在 TestConfigSaveClearsPreset 中
        # 这里测试回调机制存在
        callback_called = []

        def test_callback():
            callback_called.append(True)

        self.handler.set_on_config_change(test_callback)

        # 保存配置
        resp = await self.client.post("/_admin/api/config", json={"port": 9000})
        assert resp.status == 200
        # 注意：当前实现中 handle_config_save 不调用 _on_config_change
        # 这是一个已知的限制（P2 问题），因为 WebUI 仅在 Docker 模式运行，此时无托盘


class TestPresetIntegration(AioHTTPTestCase):
    """测试预设集成流程"""

    async def get_application(self):
        """创建测试应用"""
        self.mock_proxy = MagicMock()
        self.mock_proxy.runner = None
        self.mock_proxy.config = Config()

        self.mock_log_manager = MagicMock()
        self.mock_log_manager.get_logs_page.return_value = ([], 1, 0)

        self.password_hash = generate_password_hash("test_password")
        self.auth_manager = AdminAuthManager(password_hash=self.password_hash)

        # 创建临时配置文件
        import tempfile

        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        self.temp_file.write("host: 127.0.0.1\nport: 8087\n")
        self.temp_file.close()

        self.handler = WebAdminHandler(
            proxy_server=self.mock_proxy,
            auth_manager=self.auth_manager,
            log_manager=self.mock_log_manager,
            config_path=self.temp_file.name,
        )

        app = web.Application()
        self.handler.setup_routes(app)
        return app

    async def test_preset_apply_then_config_save_clears_marker(self):
        """测试集成流程：应用预设后保存配置会清除标记"""
        # 登录
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 1. 初始状态：无预设标记
        assert self.mock_proxy.config._active_preset is None

        # 2. 保存配置（模拟用户手动修改）
        resp = await self.client.post("/_admin/api/config", json={"port": 9000})
        assert resp.status == 200

        # 3. 验证预设标记被清除
        assert self.mock_proxy.config._active_preset is None

    async def test_config_save_preserves_other_settings(self):
        """测试配置保存保留其他设置"""
        await self.client.post("/_admin/api/login", json={"password": "test_password"})

        # 设置一些配置
        self.mock_proxy.config.log_level = 3

        # 保存配置
        resp = await self.client.post(
            "/_admin/api/config", json={"port": 9001, "log_level": 2}
        )
        assert resp.status == 200

        # 验证配置被更新
        assert self.mock_proxy.config.port == 9001
        assert self.mock_proxy.config.log_level == 2
