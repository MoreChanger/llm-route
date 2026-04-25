---
title: Multi-Platform Autostart, Docker Signals, and Health Checks
date: 2026-04-25
category: integration-issues
module: platform-support
problem_type: integration_issue
component: tooling
symptoms:
  - Docker containers ignore SIGTERM and hang on shutdown
  - Docker health checks fail with no endpoint available
  - macOS autostart fails with XML parsing errors when app name contains special characters
  - Linux desktop entry files break when paths contain % characters
  - Windows autostart registry keys not cleaned up properly
  - Unsupported platforms throw UnsupportedPlatformError instead of graceful degradation
root_cause: incomplete_setup
resolution_type: code_fix
severity: critical
tags:
  - docker
  - signal-handling
  - asyncio
  - cross-platform
  - autostart
  - health-check
related_components:
  - src/main.py
  - src/proxy.py
  - src/autostart.py
  - src/platform.py
---

# Multi-Platform Autostart, Docker Signals, and Health Checks

## Problem

Implementing cross-platform support for LLM-ROUTE required proper handling of Docker signal shutdown, health check endpoints, and platform-specific autostart mechanisms (Windows Registry, Linux XDG autostart, macOS LaunchAgent). The initial implementation had critical issues that would cause Docker containers to hang on shutdown, health checks to fail, and autostart to fail on certain platforms with special characters in paths.

## Symptoms

- Docker containers ignore `SIGTERM` and hang indefinitely on shutdown (e.g., `docker stop` times out)
- Docker health checks fail with "no such endpoint" errors
- macOS autostart fails with XML parsing errors when app name contains characters like `&`, `<`, `>`
- Linux desktop entry files break when executable paths contain `%` characters
- Windows registry keys not cleaned up properly when calling `disable()` on unsupported platforms
- `_UnsupportedAutoStart` throws `UnsupportedPlatformError` instead of gracefully returning `False`

## What Didn't Work

1. **Using `asyncio.get_event_loop()` in signal handlers** - This approach causes issues in Python 3.10+ where `get_event_loop()` is deprecated when called outside the main thread. Signal handlers run in the main thread but the event loop may not be the current loop.

2. **Assuming autostart operation success without re-querying** - Toggling autostart would show incorrect UI state if the underlying OS operation failed silently.

3. **Not escaping XML special characters in macOS plist files** - Characters like `&`, `<`, `>` in app names or paths would create invalid XML that `launchctl` cannot parse.

4. **Not escaping `%` in Linux desktop entries** - The Desktop Entry Specification treats `%` as a special character that must be escaped as `%%`.

5. **Throwing exceptions from `_UnsupportedAutoStart`** - Violated Liskov Substitution Principle and forced callers to handle exceptions they shouldn't need to catch.

6. **Missing health check endpoint** - Docker's `HEALTHCHECK` directive had nothing to probe.

## Solution

### 1. Docker Signal Handling with asyncio.Event

Use `asyncio.Event` for thread-safe shutdown coordination between signal handlers and the event loop:

```python
def main():
    lock = None  # Initialize before try block to prevent UnboundLocalError
    shutdown_event = None

    def signal_handler(signum, frame):
        nonlocal shutdown_event
        safe_print(f"\n收到信号 {signum}，正在停止服务...")
        if shutdown_event is not None:
            shutdown_event.set()  # Thread-safe signal to event loop

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if headless:
        shutdown_event = asyncio.Event()
        asyncio.run(run_headless(server, log_manager, shutdown_event))


async def run_headless(server, log_manager, shutdown_event):
    await server.start()
    safe_print("按 Ctrl+C 停止服务...")
    await shutdown_event.wait()  # Wait for signal instead of polling
    safe_print("\n正在停止服务...")
    await server.stop()
    log_manager.stop()
```

### 2. Docker Health Check Endpoint

Add a dedicated health check endpoint in the proxy server:

```python
async def start(self) -> None:
    self.app = web.Application()
    # Add health check BEFORE catch-all route
    self.app.router.add_get("/health", self.handle_health)
    self.app.router.add_route("*", "/{path:.*}", self.handle_request)
    # ...

async def handle_health(self, request: web.Request) -> web.Response:
    """健康检查端点，用于 Docker HEALTHCHECK 和 Kubernetes 探针。"""
    return web.Response(text="OK", status=200, content_type="text/plain")
```

### 3. macOS LaunchAgent XML Escaping

Use `xml.sax.saxutils.escape()` to properly escape XML special characters:

```python
from xml.sax.saxutils import escape

def enable(self) -> bool:
    # ...
    escaped_label = escape(label)
    escaped_exec_path = escape(exec_path)

    content = self.PLIST_TEMPLATE.format(
        label=escaped_label,
        exec_path=escaped_exec_path,
    )

    # Load the LaunchAgent
    subprocess.run(["launchctl", "load", str(plist_file)], capture_output=True, timeout=5)
```

Also call `launchctl remove` when disabling to fully unregister the service:

```python
def disable(self) -> bool:
    if plist_file.exists():
        subprocess.run(["launchctl", "unload", str(plist_file)], capture_output=True, timeout=10)
        subprocess.run(["launchctl", "remove", label], capture_output=True, timeout=5)
        plist_file.unlink()
```

### 4. Linux Desktop Entry Escaping

Escape `%` as `%%` per the Desktop Entry Specification:

```python
def enable(self) -> bool:
    escaped_app_name = self.app_name.replace("%", "%%").replace("\n", "").replace("\t", "")
    escaped_exec_path = exec_path.replace("%", "%%")
    escaped_icon_path = icon_path.replace("%", "%%") if icon_path else ""
    escaped_comment = f"{self.app_name} LLM API Router".replace("%", "%%").replace("\n", "").replace("\t", "")
```

### 5. Windows Registry Context Manager

Use context managers for proper resource cleanup:

```python
def enable(self) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH, 0, winreg.KEY_WRITE) as key:
            exe_path = self._get_executable_path()
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, exe_path)
        return True
    except WindowsError:
        return False
```

### 6. Graceful Degradation for Unsupported Platforms

Return `False` instead of throwing exceptions:

```python
class _UnsupportedAutoStart(_AutoStartImpl):
    def enable(self) -> bool:
        return False  # Not raise UnsupportedPlatformError

    def disable(self) -> bool:
        return False

    def is_enabled(self) -> bool:
        return False
```

### 7. State Synchronization After Toggle

Always re-query actual state after toggle operations:

```python
def _toggle_auto_start(self):
    if self._autostart_manager.is_enabled():
        success = self._autostart_manager.disable()
    else:
        success = self._autostart_manager.enable()

    # Re-query actual state instead of assuming success
    self._auto_start = self._autostart_manager.is_enabled()
    self._update_menu()
```

## Why This Works

1. **asyncio.Event for signals** - `Event.set()` is thread-safe and works correctly from signal handlers. The main event loop waits on the event instead of polling, eliminating the race condition between signal delivery and event loop state.

2. **Health check endpoint** - Provides a simple, reliable endpoint for Docker and Kubernetes to verify the service is running. The `/health` endpoint returns before any routing logic, ensuring it's always accessible.

3. **XML escaping** - `xml.sax.saxutils.escape()` handles all five XML special characters (`&`, `<`, `>`, `"`, `'`) correctly, preventing malformed plist files that would fail to load.

4. **Desktop Entry escaping** - The `%` character has special meaning in desktop entries (field codes like `%f` for file path). Escaping to `%%` ensures literal `%` characters don't get misinterpreted.

5. **Context managers** - The `with` statement ensures registry keys are closed even if an exception occurs, preventing resource leaks.

6. **Liskov compliance** - By returning `False` instead of throwing, `_UnsupportedAutoStart` maintains the same contract as other implementations. Callers can use `is_supported()` to check ahead, but aren't forced to catch exceptions.

7. **State re-query** - The UI reflects the actual OS state, not an assumption based on operation success. This handles edge cases where the OS operation fails silently.

## Prevention

- **Test signal handling in Docker** - Always verify `docker stop` shuts down cleanly within the default 10-second timeout. If it times out, the signal handler isn't working.

- **Add health check endpoint early** - When building containerized services, add `/health` endpoint before setting up Docker HEALTHCHECK. The endpoint should return 200 with minimal logic.

- **Escape special characters for target format** - When generating config files (XML, desktop entries, JSON), always use proper escaping functions:
  - XML: `xml.sax.saxutils.escape()`
  - Desktop Entry: `replace("%", "%%")`
  - JSON: `json.dumps()` (handles escaping automatically)

- **Use context managers for OS resources** - Registry keys, file handles, and network connections should always use `with` statements for cleanup.

- **Follow Liskov Substitution Principle** - Subclass methods should never throw exceptions that the base class doesn't throw. Return sentinel values or use the Null Object pattern instead.

- **Re-query state after mutations** - After any operation that should change state, query the actual state rather than assuming the operation succeeded.

- **Initialize variables before try blocks** - Variables used in `finally` blocks must be initialized before the `try` to prevent `UnboundLocalError` if the exception happens early.

## Related Issues

- Origin plan: `docs/plans/2026-04-25-001-feat-multi-platform-support-plan.md`
- Implementation files: `src/main.py`, `src/proxy.py`, `src/autostart.py`, `src/platform.py`
- Docker files: `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`
