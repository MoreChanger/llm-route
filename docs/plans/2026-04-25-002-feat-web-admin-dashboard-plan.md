---
title: feat: Add Web Admin Dashboard for Docker
type: feat
status: active
date: 2026-04-25
origin: docs/brainstorms/2026-04-25-web-dashboard-for-docker-requirements.md
---

# feat: Add Web Admin Dashboard for Docker

## Overview

Add a web-based admin dashboard for LLM-ROUTE Docker deployments, replacing the existing GUI mode (X11 forwarding). The dashboard provides service status/control, log viewing, preset management, and config editing — all accessible via `/_admin` path on the proxy port.

## Problem Frame

Docker containers cannot use the system tray (pystray). The existing GUI mode requires X11 forwarding, which is complex to configure and only works on Linux desktop environments. A web admin interface is the standard cross-platform solution for container management, accessible from any device with a browser.

**Key constraints from origin:**
- Path prefix: `/_admin` (underscore avoids route conflicts)
- Password: bcrypt hash, 5 failed attempts = 15 min lockout
- Session: in-memory, 24-hour expiry
- Config edits require container restart
- Remove Docker GUI mode entirely

## Requirements Trace

- R1. 服务状态显示：运行状态、监听端口、运行时间
- R2. 服务控制：启动/停止服务（需确认对话框）
- R3. 日志查看：分页显示、级别过滤、自动刷新；日志已过滤敏感头字段
- R4. 预设管理：列出预设、一键切换、显示当前激活预设
- R5. 配置编辑：修改端口、日志等级；保存后显示新地址，需重启容器生效
- R6. 访问方式：复用代理端口，路径 `/_admin`
- R7. 绑定地址：0.0.0.0，同时暴露代理 API（无认证）和管理界面（需密码）
- R8. 密码保护：bcrypt 哈希存储、登录失败锁定、24小时会话
- R9. 移除 Docker GUI 模式：删除 llm-route-gui 服务和 full stage
- R10. 加载状态：页面加载、操作时显示指示器
- R11. 错误处理：失败显示错误消息，支持重试
- R12. 禁用状态：运行时禁用启动按钮，停止时禁用停止按钮
- R13-R15. 无障碍访问：键盘导航、ARIA 标签、颜色对比度

## Scope Boundaries

- 不实现 Token 用量统计
- 不实现用户系统，仅单密码保护
- 不修改桌面端的托盘功能
- 不实现 WebSocket，日志采用轮询刷新
- 不实现 TLS，用户需自行配置反向代理
- 不实现 Logout 功能，会话 24 小时自动过期

## Security Model

- **Proxy API (无认证)**: 所有 `/v1/*` 路径无需认证，直接代理请求
- **Admin API (密码保护)**: `/_admin/*` 路径需要有效的会话 cookie
- **信任边界**: 绑定 0.0.0.0 会同时暴露代理 API 和管理界面到局域网
- **建议**: 在不可信网络中部署时，应通过反向代理（nginx/Traefik）添加 TLS 加密

## Context & Research

### Relevant Code and Patterns

**Route Registration (src/proxy.py:86-92)**
- Routes registered in `start()` method
- Health check added BEFORE catch-all route — admin routes must follow same pattern

**Config Management (src/config.py)**
- `load_config()` loads YAML with `yaml.safe_load()`
- `save_config()` preserves order with `sort_keys=False`
- Environment variable `LLM_ROUTE_PORT` override

**Log Pagination (src/log_file.py:157-189)**
- `get_logs_page(page, page_size)` returns `(logs, total_pages, total_count)`
- Thread-safe with `threading.Lock()`

**Session Pattern (src/session_manager.py)**
- In-memory dict with TTL expiry
- `generate_response_id()` for unique IDs

**Service State (src/proxy.py)**
- `self.runner` is `None` when stopped, non-None when running
- `start()` and `stop()` methods for lifecycle control

### Institutional Learnings

**Signal Handling (docs/solutions/integration-issues/multi-platform-autostart-docker-signals-2026-04-25.md)**
- Use `asyncio.Event` for thread-safe shutdown coordination
- Avoid `asyncio.get_event_loop()` in signal handlers

**Route Ordering**
- Catch-all route `/{path:.*}` matches everything
- Admin routes must be registered before catch-all

### Docker Configuration

**Current state:**
- `llm-route-gui` service with X11 forwarding (to remove)
- `full` stage in Dockerfile (to remove)
- `config.yaml` mounted `:ro` (change to writable)

## Key Technical Decisions

- **Route prefix `/_admin`**: Underscore indicates internal route, avoids conflicts with `/v1/*` proxy paths
- **Inline HTML/CSS/JS**: Embed static assets in Python to avoid Docker packaging complexity
- **Session class naming**: Use `AdminAuthManager` to avoid collision with existing `SessionManager`
- **Config mount**: Change `:ro` to writable in docker-compose.yml to support config editing
- **Service stop behavior**: Stop proxy but keep admin routes alive (admin runs on same server)

## Open Questions

### Resolved During Planning

- **代理 API 认证**: 代理 API 无认证，管理界面需密码。用户自行确保网络安全或通过反向代理添加 TLS。
- **Docker 配置编辑**: 移除 `:ro` 标志，允许容器写入配置文件。
- **Logout 功能**: 会话 24 小时自动过期，不实现主动 logout。简化实现，避免额外的会话撤销逻辑。

### Deferred to Implementation

- **日志大文件性能**: 是否需要限制最大行数？可考虑日志轮转或 seek-based 分页

## Output Structure

```
src/
├── web_admin.py          # Admin handlers, auth, session management
├── auth.py               # bcrypt password, lockout logic
├── proxy.py              # Modified: add admin routes
├── config.py             # Modified: add admin_password_hash field
├── main.py               # Modified: init web admin
docker-compose.yml        # Modified: remove gui service, change volume mount
Dockerfile                # Modified: remove full stage
config.yaml               # Modified: add admin_password_hash field
tests/
├── test_web_admin.py     # New: admin route tests
├── test_auth.py          # New: password and lockout tests
```

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌─────────────────────────────────────────────────────────────┐
│                      aiohttp Application                     │
├─────────────────────────────────────────────────────────────┤
│  Route Registration Order (in ProxyServer.start()):          │
│                                                              │
│  1. GET  /health           → handle_health()                 │
│  2. GET  /_admin/*         → AdminHandler (auth required)    │
│  3. POST /_admin/api/login → handle_login()                  │
│  4. GET  /_admin/api/*     → Admin API endpoints             │
│  5. *    /{path:.*}        → handle_request() (proxy)        │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    AdminAuthManager                          │
├─────────────────────────────────────────────────────────────┤
│  - password_hash: str (from config)                          │
│  - failed_attempts: dict[ip, count]                          │
│  - lockout_until: dict[ip, timestamp]                        │
│  - sessions: dict[token, AdminSession]                       │
│                                                              │
│  Methods:                                                    │
│  + verify_password(password) → bool                          │
│  + check_lockout(ip) → bool                                  │
│  + record_failure(ip) → None                                 │
│  + create_session() → token                                  │
│  + validate_session(token) → bool                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Request Flow                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  GET /_admin/                                                │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────┐    No session    ┌─────────────────┐       │
│  │ Check Cookie │ ───────────────►│ Return Login    │       │
│  └─────────────┘                  │ Page (HTML)     │       │
│       │ Session valid             └─────────────────┘       │
│       ▼                                                      │
│  ┌─────────────────┐                                         │
│  │ Return Admin    │                                         │
│  │ Dashboard (HTML)│                                         │
│  └─────────────────┘                                         │
│                                                              │
│  POST /_admin/api/login                                      │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────┐    Locked    ┌──────────────────┐      │
│  │ Check lockout   │ ────────────►│ Return 429 error │      │
│  └─────────────────┘             │ (15 min wait)     │      │
│       │ Not locked               └──────────────────┘      │
│       ▼                                                      │
│  ┌─────────────────┐    Fail     ┌──────────────────┐      │
│  │ bcrypt verify   │ ────────────►│ Increment fail   │      │
│  └─────────────────┘             │ Return 401       │      │
│       │ Success                                            │
│       ▼                                                      │
│  ┌─────────────────┐                                         │
│  │ Create session  │                                         │
│  │ Set cookie      │                                         │
│  │ Return success  │                                         │
│  └─────────────────┘                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Units

- [ ] **Unit 1: Auth Module — Password Hashing and Lockout**

**Goal:** Create authentication module with bcrypt password verification and login lockout logic.

**Requirements:** R8 (密码保护)

**Dependencies:** None

**Files:**
- Create: `src/auth.py`
- Modify: `requirements.txt` (add bcrypt)
- Test: `tests/test_auth.py`

**Approach:**
- Create `AdminAuthManager` class (avoid naming collision with existing `SessionManager`)
- Load password hash from config on initialization
- Implement bcrypt verification using `bcrypt.checkpw()`
- Track failed attempts per IP with in-memory dict
- Implement 5-failure lockout with 15-minute expiry
- Session creation/validation with random token and 24-hour TTL
- **Note:** Add `bcrypt>=4.0.0` to requirements.txt

**Patterns to follow:**
- `src/session_manager.py` for TTL session pattern
- `src/log_file.py` for thread-safe locking pattern

**Test scenarios:**
- Happy path: Correct password returns True
- Error path: Wrong password returns False
- Error path: 5 failed attempts triggers 15-minute lockout
- Edge case: Lockout expires after 15 minutes
- Edge case: Session token is valid within 24 hours
- Edge case: Session token is invalid after 24 hours

**Verification:**
- `pytest tests/test_auth.py` passes
- bcrypt dependency added to requirements.txt

---

- [ ] **Unit 2: Web Admin Handlers — Core API Endpoints**

**Goal:** Create web admin handler class with API endpoints for status, logs, presets, and config.

**Requirements:** R1, R3, R4, R5 (状态、日志、预设、配置)

**Dependencies:** Unit 1 (auth module)

**Files:**
- Create: `src/web_admin.py`
- Test: `tests/test_web_admin.py`

**Approach:**
- Create `WebAdminHandler` class with reference to `ProxyServer` and `AdminAuthManager`
- Implement API endpoints as async methods:
  - `GET /_admin/api/status` — service status, port, uptime
  - `GET /_admin/api/logs?page=N&level=X` — paginated logs with filtering
  - `GET /_admin/api/presets` — list available presets
  - `POST /_admin/api/presets/apply` — switch preset
  - `GET /_admin/api/config` — get current config (port, log_level only)
  - `POST /_admin/api/config` — update config (requires restart notice)
  - `POST /_admin/api/service/start` — start proxy
  - `POST /_admin/api/service/stop` — stop proxy
- Add auth middleware that checks session token from cookie
- Return JSON responses with proper status codes
- Filter sensitive headers in log responses

**Patterns to follow:**
- `src/proxy.py:126-131` for route handler pattern
- `src/config.py` for preset management
- `src/log_file.py:157-189` for log pagination

**Test scenarios:**
- Happy path: GET /status returns running state and port
- Happy path: GET /logs?page=1 returns paginated logs
- Happy path: GET /presets returns available preset list
- Happy path: POST /config updates config file
- Error path: Auth required for protected endpoints
- Error path: Invalid preset name returns 404
- Integration: Log entries do not contain Authorization headers

**Verification:**
- `pytest tests/test_web_admin.py` passes
- All API endpoints return correct JSON structure

---

- [ ] **Unit 3: Web Admin UI — HTML/CSS/JS Dashboard**

**Goal:** Create web admin UI with login page and dashboard, embedded in Python.

**Requirements:** R10, R11, R12, R13, R14, R15 (交互状态、无障碍)

**Dependencies:** Unit 2 (API endpoints)

**Files:**
- Modify: `src/web_admin.py` (add HTML/CSS/JS as string constants)

**Approach:**
- Embed HTML/CSS/JS as f-string constants in `web_admin.py` (avoids Docker packaging)
- Create login page with password input, error display, lockout countdown
- Create dashboard with:
  - Status card showing running state, port, uptime
  - Service control buttons with confirmation dialogs
  - Log viewer with pagination, level filter, auto-refresh toggle
  - Preset selector with current preset indicator
  - Config editor for port and log_level
- Implement loading spinners for all async operations
- Disable start button when running, stop button when stopped
- Add ARIA labels for accessibility
- Ensure 4.5:1 color contrast ratio

**Patterns to follow:**
- Use vanilla JS (no framework dependencies)
- Follow inline HTML/CSS patterns from existing `src/proxy.py` health check endpoint

**Test scenarios:**
- Happy path: Login page displays correctly
- Happy path: Dashboard loads after successful login
- Happy path: Status updates reflect actual service state
- Happy path: Log pagination navigates between pages
- Happy path: Preset switch shows confirmation dialog
- Edge case: Empty log list shows "no logs" message
- Edge case: Config save shows restart required notice
- Accessibility: Tab navigation works for all controls
- Accessibility: Color contrast meets 4.5:1 minimum

**Verification:**
- Manual browser test of login flow
- Manual browser test of all dashboard features
- Accessibility audit (keyboard navigation, ARIA labels)

---

- [ ] **Unit 4: Proxy Integration — Register Admin Routes**

**Goal:** Integrate web admin routes into ProxyServer, register before catch-all.

**Requirements:** R6, R7 (访问方式、绑定地址)

**Dependencies:** Unit 2, Unit 3

**Files:**
- Modify: `src/proxy.py`
- Modify: `src/main.py`
- Modify: `tests/test_proxy.py`

**Approach:**
- In `ProxyServer.__init__`, add optional `web_admin_handler` parameter
- In `ProxyServer.start()`, register admin routes BEFORE catch-all:
  ```python
  # Order matters!
  self.app.router.add_get("/health", self.handle_health)
  self.app.router.add_static("/_admin", ...) or add_route for each path
  self.app.router.add_route("*", "/{path:.*}", self.handle_request)
  ```
- In `main.py`, create `AdminAuthManager` and `WebAdminHandler` during initialization
- Pass handler to `ProxyServer` constructor
- Ensure admin routes work even when proxy is "stopped" (admin runs on same server)

**Patterns to follow:**
- `src/proxy.py:86-92` for route registration order
- `src/main.py` for initialization flow

**Test scenarios:**
- Happy path: GET /_admin returns login page
- Happy path: GET /_admin/api/status works when proxy running
- Happy path: GET /_admin/api/status works when proxy stopped
- Happy path: Proxy routes (catch-all) still work for /v1/* paths
- Integration: Full login → dashboard flow

**Verification:**
- `pytest tests/test_proxy.py` passes
- Admin routes accessible at `/_admin`
- Proxy routes still work for API calls

---

- [ ] **Unit 5: Config Updates — Password Hash Field**

**Goal:** Add admin_password_hash field to config and implement config editing.

**Requirements:** R5, R8 (配置编辑、密码字段)

**Dependencies:** Unit 1

**Files:**
- Modify: `src/config.py`
- Modify: `config.yaml`
- Modify: `tests/test_config.py`

**Approach:**
- Add `admin_password_hash: Optional[str] = None` to `Config` dataclass
- Update `load_config()` to read the new field
- Update `save_config()` to write the new field
- Add utility function to generate password hash for initial setup:
  ```python
  def generate_password_hash(password: str) -> str:
      return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
  ```
- Add validation: warn if no password configured (admin is unprotected)

**Patterns to follow:**
- `src/config.py:146-204` for load pattern
- `src/config.py:207-231` for save pattern

**Test scenarios:**
- Happy path: Load config with admin_password_hash
- Happy path: Save config preserves admin_password_hash
- Happy path: generate_password_hash creates valid bcrypt hash
- Edge case: Config without admin_password_hash loads successfully (None)
- Edge case: Config order preserved after save

**Verification:**
- `pytest tests/test_config.py` passes
- config.yaml includes admin_password_hash field (commented example)

---

- [ ] **Unit 6: Docker Cleanup — Remove GUI Mode**

**Goal:** Remove Docker GUI mode, update volume mounts for config editing.

**Requirements:** R9 (移除 GUI 模式)

**Dependencies:** None

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `README.md`

**Approach:**
- In `docker-compose.yml`:
  - Remove `llm-route-gui` service (lines 33-57)
  - Change `./config.yaml:/app/config.yaml:ro` to `./config.yaml:/app/config.yaml` (writable)
  - Remove `profiles: [gui]` references
- In `Dockerfile`:
  - Remove `full` stage (lines 64-111)
  - Keep only `builder` and `headless` stages
- In `README.md`:
  - Update Docker documentation to mention web admin
  - Remove references to X11 forwarding and GUI mode

**Test expectation:** none -- Docker configuration changes, verified by build

**Verification:**
- `docker compose config` validates successfully
- `docker build --target headless -t llm-route:test .` succeeds
- No references to GUI mode remain in documentation

---

- [ ] **Unit 7: Log Sanitization — Filter Sensitive Headers**

**Goal:** Filter Authorization and x-api-key headers from log output.

**Requirements:** R3 (日志内容已过滤敏感头字段)

**Dependencies:** None

**Files:**
- Modify: `src/log_file.py`
- Modify: `tests/test_log_file.py`

**Approach:**
- Modify `log_request()` method to sanitize request/response bodies before logging
- Create helper function to redact sensitive headers:
  ```python
  SENSITIVE_HEADERS = {'authorization', 'x-api-key'}

  def sanitize_headers(headers: str) -> str:
      # Redact values for sensitive header names
  ```
- Apply sanitization to both request_body and response_body parameters

**Patterns to follow:**
- `src/log_file.py:102-143` for log_request pattern

**Test scenarios:**
- Happy path: Normal logs preserved unchanged
- Happy path: Authorization header value replaced with [REDACTED]
- Happy path: x-api-key header value replaced with [REDACTED]
- Edge case: Case-insensitive header matching
- Edge case: Multiple sensitive headers in same log

**Verification:**
- `pytest tests/test_log_file.py` passes
- Logs do not contain plaintext API keys

## System-Wide Impact

- **Interaction graph:** Admin routes call `ProxyServer.start()/stop()`, read `LogManager`, modify `Config`
- **Error propagation:** Auth failures return 401/429; config errors return 400 with message
- **State lifecycle risks:** Service stop keeps admin alive (same aiohttp app); config changes require restart
- **API surface parity:** Web admin API mirrors tray functionality; both should stay in sync
- **Integration coverage:** Login → session → API access → service control flow needs integration test
- **Unchanged invariants:** Proxy API behavior unchanged; existing routes work identically; tray functionality unaffected

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Route ordering breaks admin | Explicit comment in proxy.py about registration order; tests verify both admin and proxy routes work |
| Config edit without restart causes confusion | Clear UI message "重启容器生效" after config save |
| Memory leak in session storage | Use TTL cleanup similar to SessionManager; add cleanup on startup |
| bcrypt not in requirements | Unit 1 explicitly adds dependency |
| Docker volume read-only | Unit 6 changes mount to writable |

## Documentation / Operational Notes

- **First-time setup:** Document how to generate initial password hash
  ```bash
  python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
  ```
- **Password in config:** admin_password_hash goes in config.yaml
- **Network security:** Document that 0.0.0.0 binding exposes proxy API without auth; recommend reverse proxy with TLS
- **Session behavior:** Sessions expire after 24 hours or on service restart

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-25-web-dashboard-for-docker-requirements.md](docs/brainstorms/2026-04-25-web-dashboard-for-docker-requirements.md)
- **Institutional learning:** [docs/solutions/integration-issues/multi-platform-autostart-docker-signals-2026-04-25.md](docs/solutions/integration-issues/multi-platform-autostart-docker-signals-2026-04-25.md)
- Related code: `src/proxy.py`, `src/config.py`, `src/log_file.py`, `src/session_manager.py`
