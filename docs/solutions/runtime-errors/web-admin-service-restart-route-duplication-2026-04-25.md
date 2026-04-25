---
title: Web Admin Service Restart Causes Route Registration Errors
date: 2026-04-25
category: runtime-errors
module: web_admin
problem_type: runtime_error
component: service_object
severity: medium
symptoms:
  - "RuntimeError: Route '/_admin/api/login' is already registered when restarting service via web UI"
  - "Uptime counter continues incrementing after service stops"
  - "Log pagination shows incorrect page count when filtering by level"
  - "HTTP header regex matches partial strings in URLs"
root_cause: logic_error
resolution_type: code_fix
tags:
  - aiohttp
  - service-lifecycle
  - route-registration
  - web-admin
  - docker
---

# Web Admin Service Restart Causes Route Registration Errors

## Problem

Multiple runtime issues in the Web Admin Dashboard for Docker deployments of LLM-ROUTE were identified during code review. The most critical issue (P1) was that restarting the service via the web UI caused aiohttp route registration errors. Additional issues included uptime counter not resetting on stop, incorrect log pagination when filtering, and an overly aggressive header sanitization regex.

## Symptoms

- **Route duplication error**: `RuntimeError: Route '/_admin/api/login' is already registered` when attempting to restart a stopped service via the web admin dashboard
- **Incorrect uptime**: Dashboard shows uptime continuing to grow after service has been stopped
- **Wrong pagination count**: Filtering logs by level shows more pages than actually available; users see empty pages when navigating
- **Over-redaction**: URLs containing "authorization:" in paths get incorrectly redacted in logs

## What Didn't Work

- **Original `setup_routes()` implementation**: Unconditionally registered routes each time it was called, but the aiohttp Application object persists across service stop/restart cycles, causing duplicate registration errors
- **Uptime calculation without reset**: The `_start_time` attribute was set on start but never cleared on stop, causing uptime to accumulate across stop/start cycles
- **Pagination before filtering**: Calculating `total_pages` before applying level filter resulted in pagination controls that didn't match the filtered content

## Solution

### Fix 1: Idempotent Route Registration

Make `setup_routes()` check if routes already exist before registering:

```python
def setup_routes(self, app: web.Application) -> None:
    """注册路由到 aiohttp 应用

    注意：必须在 catch-all 路由之前调用此方法。
    此方法幂等，重复调用不会重复注册路由。
    """
    # 检查路由是否已注册（支持服务重启场景）
    existing_routes = {r.path for r in app.router.routes()}
    if "/_admin/api/login" in existing_routes:
        return

    # 登录端点（无需认证）
    app.router.add_post("/_admin/api/login", self.handle_login)
    # ... rest of route registration
```

### Fix 2: Reset Uptime on Service Stop

Clear `_start_time` when the service stops:

```python
async def handle_service_stop(self, request: web.Request) -> web.Response:
    """停止服务"""
    try:
        await self.proxy_server.stop()
        self._start_time = None  # 重置启动时间
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
```

### Fix 3: Recalculate Pagination After Filtering

Apply level filter before calculating page count:

```python
logs, total_pages, total_count = self.log_manager.get_logs_page(page, page_size)

# 按级别过滤
if level:
    logs = [line for line in logs if level in line]
    # 重新计算过滤后的总页数
    filtered_count = len(logs)
    total_pages = max(1, (filtered_count + page_size - 1) // page_size) if filtered_count > 0 else 1
```

### Fix 4: Add Word Boundary to Header Regex

Prevent partial string matches:

```python
# Before: could match "authorization:" inside URLs
http_pattern = r'(Authorization|x-api-key):\s*[^\n\]\[{}"]+'

# After: only matches complete header field names
http_pattern = r'\b(Authorization|x-api-key):\s*[^\n\]\[{}"]+'
```

### Fix 5 & 6: Code Cleanup

- Removed unused `current_upstreams` variable that was calculated but never used
- Removed `KeyError` from exception handling (aiohttp's `request.json()` only raises `JSONDecodeError`)

## Why This Works

- **Route idempotency**: By checking for existing routes before registration, the method becomes idempotent — it can be safely called multiple times without side effects. The check uses a sentinel route path to detect prior registration.

- **Uptime reset**: Resetting `_start_time` to `None` when the service stops ensures uptime calculations correctly reflect only the time the service was actually running.

- **Filter-then-paginate**: Calculating pagination after filtering ensures the page count matches the actual filtered content.

- **Word boundary regex**: The `\b` anchor ensures the regex only matches when header names appear as complete words, not as substrings within URLs or other text.

## Prevention

- **Design lifecycle methods to be idempotent**: Methods like `setup()`, `initialize()`, `configure()` should be safe to call multiple times. Document this expectation in docstrings.

- **Audit state transitions**: When implementing state tracking (uptime, counters, flags), verify all state transitions are handled — especially reset/cleanup on stop or teardown.

- **Apply filters before pagination**: Always filter data before calculating pagination metadata. Write tests that verify pagination math with various filter combinations.

- **Use word boundaries in keyword regex**: When matching keywords that could appear within text, use `\b` word boundary anchors to prevent partial matches.

- **Test exception paths**: Verify exception handlers match the actual exceptions that can be raised by the code they wrap.

- **Static analysis**: Use linters (pylint, mypy) to detect unused variables and unreachable exception handlers.

## Related Issues

- **docs/solutions/integration-issues/multi-platform-autostart-docker-signals-2026-04-25.md**: Related Docker deployment patterns including aiohttp route ordering
- **docs/plans/2026-04-25-002-feat-web-admin-dashboard-plan.md**: Implementation plan for the Web Admin Dashboard feature
