"""Web 管理界面模块

提供 Docker 环境下的 Web 管理界面，包括：
- 登录页面
- 服务状态查看
- 服务控制（启动/停止）
- 日志查看
- 预设管理
- 配置编辑
"""

import json
import time
from typing import Optional, TYPE_CHECKING

from aiohttp import web

from src.auth import AdminAuthManager
from src.config import list_presets, apply_preset, load_config, save_config

if TYPE_CHECKING:
    from src.proxy import ProxyServer
    from src.log_file import LogManager


# ============================================================================
# HTML/CSS/JS 模板
# ============================================================================

# 登录页面 HTML
LOGIN_PAGE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM-ROUTE 管理登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e0e0e0;
        }
        .login-container {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 40px;
            width: 100%;
            max-width: 380px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        h1 {
            text-align: center;
            margin-bottom: 8px;
            font-size: 24px;
            color: #fff;
        }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 32px;
            font-size: 14px;
        }
        .form-group { margin-bottom: 20px; }
        label {
            display: block;
            margin-bottom: 8px;
            font-size: 14px;
            color: #aaa;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #333;
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 16px;
            transition: border-color 0.2s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #4a9eff;
        }
        .error-message {
            background: rgba(255,68,68,0.1);
            border: 1px solid #ff4444;
            color: #ff6b6b;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }
        .lockout-message {
            background: rgba(255,165,0,0.1);
            border: 1px solid #ffa500;
            color: #ffc107;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #4a9eff 0%, #2d7dd2 100%);
            border: none;
            border-radius: 8px;
            color: #fff;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.2s;
        }
        button:hover { opacity: 0.9; }
        button:active { transform: scale(0.98); }
        button:disabled {
            background: #555;
            cursor: not-allowed;
            opacity: 0.6;
        }
        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #fff;
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>LLM-ROUTE</h1>
        <p class="subtitle">管理界面登录</p>
        <div id="errorMessage" class="error-message" role="alert" aria-live="polite"></div>
        <div id="lockoutMessage" class="lockout-message" role="alert" aria-live="polite"></div>
        <form id="loginForm">
            <div class="form-group">
                <label for="password">管理员密码</label>
                <input type="password" id="password" name="password"
                       placeholder="请输入密码" autocomplete="current-password"
                       aria-required="true" autofocus>
            </div>
            <button type="submit" id="submitBtn">登录</button>
        </form>
    </div>
    <script>
        const form = document.getElementById('loginForm');
        const passwordInput = document.getElementById('password');
        const submitBtn = document.getElementById('submitBtn');
        const errorMessage = document.getElementById('errorMessage');
        const lockoutMessage = document.getElementById('lockoutMessage');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = passwordInput.value;
            if (!password) return;

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="loading"></span>登录中...';
            errorMessage.style.display = 'none';
            lockoutMessage.style.display = 'none';

            try {
                const resp = await fetch('/_admin/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({password})
                });
                const data = await resp.json();

                if (resp.ok) {
                    window.location.href = '/_admin/';
                } else if (resp.status === 429) {
                    const remaining = data.remaining || 900;
                    const mins = Math.ceil(remaining / 60);
                    lockoutMessage.textContent = `登录尝试过多，请 ${mins} 分钟后重试`;
                    lockoutMessage.style.display = 'block';
                    submitBtn.disabled = true;
                    // 倒计时
                    let countdown = remaining;
                    const timer = setInterval(() => {
                        countdown--;
                        if (countdown <= 0) {
                            clearInterval(timer);
                            lockoutMessage.style.display = 'none';
                            submitBtn.disabled = false;
                        } else {
                            const m = Math.ceil(countdown / 60);
                            lockoutMessage.textContent = `登录尝试过多，请 ${m} 分钟后重试`;
                        }
                    }, 1000);
                } else {
                    errorMessage.textContent = data.error || '登录失败';
                    errorMessage.style.display = 'block';
                    submitBtn.disabled = false;
                    passwordInput.value = '';
                    passwordInput.focus();
                }
            } catch (err) {
                errorMessage.textContent = '网络错误，请重试';
                errorMessage.style.display = 'block';
                submitBtn.disabled = false;
            }
            submitBtn.innerHTML = '登录';
        });
    </script>
</body>
</html>
'''

# 仪表盘页面 HTML
DASHBOARD_PAGE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM-ROUTE 管理面板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f0f1a;
            min-height: 100vh;
            color: #e0e0e0;
        }
        .header {
            background: rgba(255,255,255,0.03);
            border-bottom: 1px solid #222;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 { font-size: 18px; color: #fff; }
        .header-right { display: flex; align-items: center; gap: 16px; }
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }
        .status-running { background: rgba(76,175,80,0.2); color: #4caf50; }
        .status-stopped { background: rgba(244,67,54,0.2); color: #f44336; }
        .main { padding: 24px; max-width: 1400px; margin: 0 auto; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
        .card {
            background: rgba(255,255,255,0.03);
            border: 1px solid #222;
            border-radius: 12px;
            padding: 20px;
        }
        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .card-title { font-size: 15px; font-weight: 600; color: #fff; }
        .card-content { font-size: 14px; }
        .stat-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #1a1a2e; }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: #888; }
        .stat-value { color: #fff; font-weight: 500; }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
        }
        .btn:hover { opacity: 0.9; }
        .btn:active { transform: scale(0.98); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: linear-gradient(135deg, #4a9eff 0%, #2d7dd2 100%); color: #fff; }
        .btn-danger { background: linear-gradient(135deg, #ff4444 0%, #cc3333 100%); color: #fff; }
        .btn-secondary { background: #333; color: #fff; }
        .btn-group { display: flex; gap: 10px; margin-top: 16px; }
        .log-container {
            background: #0a0a12;
            border-radius: 8px;
            padding: 12px;
            max-height: 400px;
            overflow-y: auto;
            font-family: "SF Mono", Consolas, monospace;
            font-size: 12px;
            line-height: 1.6;
        }
        .log-line { white-space: pre-wrap; word-break: break-all; }
        .log-info { color: #e0e0e0; }
        .log-error { color: #ff6b6b; }
        .log-controls { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
        select, input[type="number"] {
            background: #1a1a2e;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 8px 12px;
            color: #fff;
            font-size: 13px;
        }
        select:focus, input:focus { outline: none; border-color: #4a9eff; }
        .checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
        .checkbox-label input { width: 16px; height: 16px; }
        .pagination { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
        .pagination button { padding: 6px 12px; }
        .pagination span { color: #888; font-size: 13px; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; margin-bottom: 8px; color: #aaa; font-size: 13px; }
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px 14px;
            border: 1px solid #333;
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 14px;
        }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: #4a9eff; }
        .notice {
            background: rgba(255,165,0,0.1);
            border: 1px solid #ffa500;
            border-radius: 8px;
            padding: 12px;
            margin-top: 16px;
            font-size: 13px;
            color: #ffc107;
        }
        .loading-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .loading-spinner {
            width: 40px; height: 40px;
            border: 3px solid #333;
            border-top-color: #4a9eff;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hidden { display: none !important; }
        .preset-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .preset-name { font-weight: 500; }
        .preset-current { color: #4caf50; font-size: 12px; }
    </style>
</head>
<body>
    <div id="loadingOverlay" class="loading-overlay hidden">
        <div class="loading-spinner"></div>
    </div>
    <header class="header">
        <h1>LLM-ROUTE 管理面板</h1>
        <div class="header-right">
            <span id="statusBadge" class="status-badge">--</span>
            <span id="uptime" style="color:#888;font-size:13px;">--</span>
        </div>
    </header>
    <main class="main">
        <div class="grid">
            <!-- 服务状态 -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">服务状态</span>
                </div>
                <div class="card-content">
                    <div class="stat-row">
                        <span class="stat-label">状态</span>
                        <span id="serviceStatus" class="stat-value">--</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">监听地址</span>
                        <span id="listenAddr" class="stat-value">--</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">运行时间</span>
                        <span id="serviceUptime" class="stat-value">--</span>
                    </div>
                    <div class="btn-group">
                        <button id="btnStart" class="btn btn-primary" onclick="startService()">启动服务</button>
                        <button id="btnStop" class="btn btn-danger" onclick="confirmStop()">停止服务</button>
                    </div>
                </div>
            </div>

            <!-- 预设管理 -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">配置预设</span>
                </div>
                <div class="card-content">
                    <div id="presetList">加载中...</div>
                </div>
            </div>

            <!-- 配置编辑 -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">配置编辑</span>
                </div>
                <div class="card-content">
                    <div class="form-group">
                        <label for="configPort">监听端口</label>
                        <input type="number" id="configPort" min="1" max="65535" placeholder="8087">
                    </div>
                    <div class="form-group">
                        <label for="configLogLevel">日志等级</label>
                        <select id="configLogLevel">
                            <option value="1">基础信息</option>
                            <option value="2">详细信息</option>
                            <option value="3">完整信息</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
                    <div class="notice">⚠️ 配置修改后需要重启容器才能生效</div>
                </div>
            </div>

            <!-- 日志查看 -->
            <div class="card" style="grid-column: 1 / -1;">
                <div class="card-header">
                    <span class="card-title">日志查看</span>
                </div>
                <div class="card-content">
                    <div class="log-controls">
                        <select id="logLevel" onchange="loadLogs()">
                            <option value="">全部级别</option>
                            <option value="INFO">INFO</option>
                            <option value="ERROR">ERROR</option>
                        </select>
                        <select id="pageSize" onchange="loadLogs()">
                            <option value="50">50 行/页</option>
                            <option value="100" selected>100 行/页</option>
                            <option value="200">200 行/页</option>
                        </select>
                        <label class="checkbox-label">
                            <input type="checkbox" id="autoRefresh" onchange="toggleAutoRefresh()">
                            自动刷新
                        </label>
                        <button class="btn btn-secondary" onclick="loadLogs()">刷新</button>
                    </div>
                    <div id="logContainer" class="log-container">加载中...</div>
                    <div class="pagination">
                        <button class="btn btn-secondary" onclick="prevPage()">上一页</button>
                        <span id="pageInfo">第 1 页 / 共 1 页</span>
                        <button class="btn btn-secondary" onclick="nextPage()">下一页</button>
                        <input type="number" id="jumpPage" min="1" style="width:70px;" placeholder="页码">
                        <button class="btn btn-secondary" onclick="jumpToPage()">跳转</button>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        let currentPage = 1;
        let totalPages = 1;
        let autoRefreshTimer = null;
        let startTime = null;

        // 工具函数
        function showLoading() { document.getElementById('loadingOverlay').classList.remove('hidden'); }
        function hideLoading() { document.getElementById('loadingOverlay').classList.add('hidden'); }

        async function api(path, options = {}) {
            const resp = await fetch('/_admin/api' + path, options);
            if (resp.status === 401) {
                window.location.href = '/_admin/login';
                throw new Error('Unauthorized');
            }
            return resp;
        }

        function formatUptime(seconds) {
            if (!seconds) return '--';
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) return `${h}时${m}分${s}秒`;
            if (m > 0) return `${m}分${s}秒`;
            return `${s}秒`;
        }

        // 状态刷新
        async function refreshStatus() {
            try {
                const resp = await api('/status');
                const data = await resp.json();

                const isRunning = data.running;
                const badge = document.getElementById('statusBadge');
                badge.textContent = isRunning ? '运行中' : '已停止';
                badge.className = 'status-badge ' + (isRunning ? 'status-running' : 'status-stopped');

                document.getElementById('serviceStatus').textContent = isRunning ? '运行中' : '已停止';
                document.getElementById('listenAddr').textContent = `${data.host}:${data.port}`;
                document.getElementById('serviceUptime').textContent = formatUptime(data.uptime);
                document.getElementById('uptime').textContent = '运行 ' + formatUptime(data.uptime);

                document.getElementById('btnStart').disabled = isRunning;
                document.getElementById('btnStop').disabled = !isRunning;

                startTime = data.start_time;
            } catch (e) {
                console.error('刷新状态失败:', e);
            }
        }

        // 服务控制
        async function startService() {
            showLoading();
            try {
                await api('/service/start', {method: 'POST'});
                await refreshStatus();
            } catch (e) {}
            hideLoading();
        }

        function confirmStop() {
            if (confirm('确定要停止服务吗？这将中断所有正在进行的请求。')) {
                stopService();
            }
        }

        async function stopService() {
            showLoading();
            try {
                await api('/service/stop', {method: 'POST'});
                await refreshStatus();
            } catch (e) {}
            hideLoading();
        }

        // 日志
        async function loadLogs() {
            const level = document.getElementById('logLevel').value;
            const pageSize = document.getElementById('pageSize').value;

            try {
                const resp = await api(`/logs?page=${currentPage}&page_size=${pageSize}&level=${level}`);
                const data = await resp.json();

                const container = document.getElementById('logContainer');
                if (data.logs.length === 0) {
                    container.innerHTML = '<div style="color:#888;text-align:center;padding:20px;">暂无日志</div>';
                } else {
                    container.innerHTML = data.logs.map(line => {
                        const cls = line.includes('ERROR') ? 'log-error' : 'log-info';
                        return `<div class="log-line ${cls}">${escapeHtml(line)}</div>`;
                    }).join('');
                    container.scrollTop = container.scrollHeight;
                }

                totalPages = data.total_pages;
                document.getElementById('pageInfo').textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页 (${data.total_count} 行)`;
            } catch (e) {
                console.error('加载日志失败:', e);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function prevPage() { if (currentPage > 1) { currentPage--; loadLogs(); } }
        function nextPage() { if (currentPage < totalPages) { currentPage++; loadLogs(); } }
        function jumpToPage() {
            const page = parseInt(document.getElementById('jumpPage').value);
            if (page >= 1 && page <= totalPages) { currentPage = page; loadLogs(); }
        }

        function toggleAutoRefresh() {
            if (document.getElementById('autoRefresh').checked) {
                autoRefreshTimer = setInterval(loadLogs, 3000);
            } else {
                clearInterval(autoRefreshTimer);
            }
        }

        // 预设
        async function loadPresets() {
            try {
                const resp = await api('/presets');
                const data = await resp.json();
                const container = document.getElementById('presetList');

                if (data.presets.length === 0) {
                    container.innerHTML = '<div style="color:#888;">暂无预设</div>';
                    return;
                }

                container.innerHTML = data.presets.map(p => `
                    <div class="preset-item">
                        <span>
                            <span class="preset-name">${p.name}</span>
                            ${p.current ? '<span class="preset-current"> (当前)</span>' : ''}
                        </span>
                        ${p.current ? '' : `<button class="btn btn-secondary" style="padding:6px 12px;" onclick="applyPreset('${p.name}')">应用</button>`}
                    </div>
                `).join('');
            } catch (e) {
                console.error('加载预设失败:', e);
            }
        }

        async function applyPreset(name) {
            if (!confirm(`确定要应用预设 "${name}" 吗？这将重启服务。`)) return;
            showLoading();
            try {
                const resp = await api('/presets/apply', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({preset: name})
                });
                const data = await resp.json();
                if (resp.ok) {
                    alert('预设已应用');
                    await Promise.all([refreshStatus(), loadPresets(), loadConfig()]);
                } else {
                    alert('应用失败: ' + data.error);
                }
            } catch (e) {}
            hideLoading();
        }

        // 配置
        async function loadConfig() {
            try {
                const resp = await api('/config');
                const data = await resp.json();
                document.getElementById('configPort').value = data.port || 8087;
                document.getElementById('configLogLevel').value = data.log_level || 2;
            } catch (e) {
                console.error('加载配置失败:', e);
            }
        }

        async function saveConfig() {
            const port = parseInt(document.getElementById('configPort').value);
            const logLevel = parseInt(document.getElementById('configLogLevel').value);

            if (!port || port < 1 || port > 65535) {
                alert('请输入有效的端口号 (1-65535)');
                return;
            }

            showLoading();
            try {
                const resp = await api('/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({port, log_level: logLevel})
                });
                const data = await resp.json();
                if (resp.ok) {
                    alert('配置已保存。新地址: http://<IP>:' + port + '/_admin\\n请重启容器使配置生效。');
                } else {
                    alert('保存失败: ' + data.error);
                }
            } catch (e) {}
            hideLoading();
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {
            refreshStatus();
            loadLogs();
            loadPresets();
            loadConfig();
            setInterval(refreshStatus, 5000);
        });
    </script>
</body>
</html>
'''


class WebAdminHandler:
    """Web 管理界面处理器"""

    def __init__(
        self,
        proxy_server: "ProxyServer",
        auth_manager: AdminAuthManager,
        log_manager: "LogManager",
        config_path: str,
    ):
        """
        Args:
            proxy_server: 代理服务器实例
            auth_manager: 认证管理器
            log_manager: 日志管理器
            config_path: 配置文件路径
        """
        self.proxy_server = proxy_server
        self.auth_manager = auth_manager
        self.log_manager = log_manager
        self.config_path = config_path
        self._start_time: Optional[float] = None

    def set_start_time(self, start_time: float) -> None:
        """设置服务启动时间"""
        self._start_time = start_time

    def setup_routes(self, app: web.Application) -> None:
        """注册路由到 aiohttp 应用

        注意：必须在 catch-all 路由之前调用此方法。
        """
        # 登录端点（无需认证）
        app.router.add_post("/_admin/api/login", self.handle_login)

        # 静态页面
        app.router.add_get("/_admin/login", self.handle_login_page)
        app.router.add_get("/_admin/", self.handle_dashboard)
        app.router.add_get("/_admin", self.handle_dashboard_redirect)

        # API 端点（需要认证）
        app.router.add_get("/_admin/api/status", self.require_auth(self.handle_status))
        app.router.add_get("/_admin/api/logs", self.require_auth(self.handle_logs))
        app.router.add_get("/_admin/api/presets", self.require_auth(self.handle_presets))
        app.router.add_post(
            "/_admin/api/presets/apply", self.require_auth(self.handle_preset_apply)
        )
        app.router.add_get("/_admin/api/config", self.require_auth(self.handle_config_get))
        app.router.add_post("/_admin/api/config", self.require_auth(self.handle_config_save))
        app.router.add_post(
            "/_admin/api/service/start", self.require_auth(self.handle_service_start)
        )
        app.router.add_post(
            "/_admin/api/service/stop", self.require_auth(self.handle_service_stop)
        )

    def require_auth(self, handler):
        """认证装饰器"""

        async def wrapper(request: web.Request) -> web.Response:
            # 检查是否有密码配置
            if not self.auth_manager.has_password():
                # 无密码保护，允许访问
                return await handler(request)

            # 从 cookie 获取 session token
            token = request.cookies.get("admin_session")
            if not self.auth_manager.validate_session(token):
                return web.Response(status=401, text="Unauthorized")

            return await handler(request)

        return wrapper

    # ========== 页面处理 ==========

    async def handle_login_page(self, request: web.Request) -> web.Response:
        """返回登录页面"""
        return web.Response(text=LOGIN_PAGE_HTML, content_type="text/html")

    async def handle_dashboard(self, request: web.Request) -> web.Response:
        """返回仪表盘页面"""
        # 检查认证
        if self.auth_manager.has_password():
            token = request.cookies.get("admin_session")
            if not self.auth_manager.validate_session(token):
                return web.Response(status=302, headers={"Location": "/_admin/login"})

        return web.Response(text=DASHBOARD_PAGE_HTML, content_type="text/html")

    async def handle_dashboard_redirect(self, request: web.Request) -> web.Response:
        """重定向到带斜杠的路径"""
        return web.Response(status=302, headers={"Location": "/_admin/"})

    # ========== API 处理 ==========

    async def handle_login(self, request: web.Request) -> web.Response:
        """处理登录请求"""
        # 检查是否配置了密码
        if not self.auth_manager.has_password():
            return web.json_response({"error": "Admin password not configured"}, status=400)

        # 获取客户端 IP
        client_ip = request.remote or "unknown"

        # 检查是否被锁定
        if self.auth_manager.check_lockout(client_ip):
            remaining = self.auth_manager.get_lockout_remaining(client_ip)
            return web.json_response(
                {"error": "Too many failed attempts", "remaining": remaining}, status=429
            )

        # 解析请求
        try:
            data = await request.json()
            password = data.get("password", "")
        except (json.JSONDecodeError, KeyError):
            return web.json_response({"error": "Invalid request"}, status=400)

        # 验证密码
        if self.auth_manager.verify_password(password):
            # 清除失败记录
            self.auth_manager.clear_failures(client_ip)
            # 创建会话
            token = self.auth_manager.create_session()
            # 设置 cookie 并返回
            response = web.json_response({"success": True})
            response.set_cookie(
                "admin_session",
                token,
                max_age=24 * 60 * 60,  # 24 小时
                httponly=True,
                samesite="Lax",
            )
            return response
        else:
            # 记录失败
            self.auth_manager.record_failure(client_ip)
            return web.json_response({"error": "Invalid password"}, status=401)

    async def handle_status(self, request: web.Request) -> web.Response:
        """返回服务状态"""
        is_running = self.proxy_server.runner is not None

        # 计算运行时间
        uptime = 0
        if is_running and self._start_time:
            uptime = int(time.time() - self._start_time)

        return web.json_response(
            {
                "running": is_running,
                "host": self.proxy_server.config.host,
                "port": self.proxy_server.config.port,
                "uptime": uptime,
                "start_time": self._start_time,
            }
        )

    async def handle_logs(self, request: web.Request) -> web.Response:
        """返回分页日志"""
        page = int(request.query.get("page", 1))
        page_size = int(request.query.get("page_size", 100))
        level = request.query.get("level", "")

        logs, total_pages, total_count = self.log_manager.get_logs_page(page, page_size)

        # 按级别过滤
        if level:
            logs = [line for line in logs if level in line]

        return web.json_response(
            {"logs": logs, "page": page, "total_pages": total_pages, "total_count": total_count}
        )

    async def handle_presets(self, request: web.Request) -> web.Response:
        """返回可用预设列表"""
        presets = list_presets()

        # 获取当前配置的上游名称作为当前预设标记
        current_upstreams = set(self.proxy_server.config.upstreams.keys())
        preset_list = []
        for name, path in presets:
            # 简单判断：如果预设文件名在配置中有对应，标记为当前
            preset_list.append({"name": name, "path": str(path), "current": False})

        return web.json_response({"presets": preset_list})

    async def handle_preset_apply(self, request: web.Request) -> web.Response:
        """应用预设"""
        try:
            data = await request.json()
            preset_name = data.get("preset", "")
        except (json.JSONDecodeError, KeyError):
            return web.json_response({"error": "Invalid request"}, status=400)

        # 查找预设
        presets = list_presets()
        preset_path = None
        for name, path in presets:
            if name == preset_name:
                preset_path = path
                break

        if not preset_path:
            return web.json_response({"error": "Preset not found"}, status=404)

        # 应用预设
        if apply_preset(preset_path, self.config_path):
            return web.json_response({"success": True})
        else:
            return web.json_response({"error": "Failed to apply preset"}, status=500)

    async def handle_config_get(self, request: web.Request) -> web.Response:
        """获取当前配置"""
        config = self.proxy_server.config
        return web.json_response(
            {
                "port": config.port,
                "log_level": config.log_level,
                "host": config.host,
            }
        )

    async def handle_config_save(self, request: web.Request) -> web.Response:
        """保存配置"""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid request"}, status=400)

        config = self.proxy_server.config

        # 更新配置
        if "port" in data:
            port = data["port"]
            if isinstance(port, int) and 1 <= port <= 65535:
                config.port = port
            else:
                return web.json_response({"error": "Invalid port"}, status=400)

        if "log_level" in data:
            level = data["log_level"]
            if isinstance(level, int) and 1 <= level <= 3:
                config.log_level = level
                self.log_manager.set_level(level)

        # 保存到文件
        try:
            save_config(config, self.config_path)
            return web.json_response(
                {"success": True, "port": config.port, "log_level": config.log_level}
            )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_service_start(self, request: web.Request) -> web.Response:
        """启动服务"""
        try:
            await self.proxy_server.start()
            self._start_time = time.time()
            return web.json_response({"success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_service_stop(self, request: web.Request) -> web.Response:
        """停止服务"""
        try:
            await self.proxy_server.stop()
            return web.json_response({"success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
