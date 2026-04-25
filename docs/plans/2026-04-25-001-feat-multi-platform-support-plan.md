---
title: feat: Add multi-platform support for LLM-ROUTE
type: feat
status: active
date: 2026-04-25
deepened: 2026-04-25
reviewed: 2026-04-25
---

# feat: Add multi-platform support for LLM-ROUTE

## Overview

将 LLM-ROUTE 从仅支持 Windows 扩展为支持 Windows、Linux、macOS 和 Docker 的跨平台应用。**核心代理功能在所有平台上对等，托盘功能根据平台能力支持三级降级**，包括系统托盘、开机自启和完整的代理功能。

## Problem Frame

LLM-ROUTE 是一个 LLM API 路由代理工具，当前主要针对 Windows 平台设计：
- 系统托盘使用 Windows 特定的 `pystray._win32` 后端
- 开机自启仅支持 Windows 注册表方式
- 构建脚本 `build.bat` 仅适用于 Windows
- PyInstaller 配置包含 Windows 特定选项

用户需要在 Linux 服务器、macOS 开发环境和 Docker 容器中运行此工具，期望所有平台都具有相同的功能体验。

## Requirements Trace

- R1. 支持在 Windows、Linux、macOS 上运行核心代理功能
- R2. 所有平台支持系统托盘界面（Linux 需要可选依赖）
- R3. 所有平台支持开机自启功能
- R4. 支持 Docker 容器化部署（headless 模式）
- R5. 提供跨平台构建脚本和配置
- R6. 保持向后兼容，现有 Windows 用户不受影响

## Scope Boundaries

### In Scope
- 跨平台开机自启抽象层（Linux autostart/systemd、macOS LaunchAgent）
- 跨平台 PyInstaller 配置和构建脚本
- Docker 支持文件
- 系统托盘跨平台适配
- CI 配置（GitHub Actions 多平台测试）

### Out of Scope
- macOS 代码签名和公证（需要 Apple Developer 账号）
- Linux 发行版特定包（deb、rpm、AppImage）
- Windows 安装程序改进
- GUI 界面重新设计

## Context & Research

### Relevant Code and Patterns

**现有跨平台模式 (`src/single_instance.py:32-54`)**：
```python
if sys.platform == "win32":
    # Windows API 实现
else:
    # POSIX 信号实现
```
此模式应扩展到其他平台特定代码。

**需要修改的平台特定代码**：
| 文件 | 功能 | 当前状态 |
|------|------|----------|
| `src/tray.py:368-411` | 开机自启 | 仅 Windows 注册表 |
| `build.spec` | 打包配置 | `pystray._win32` 隐式导入 |
| `build.bat` | 构建脚本 | Windows 批处理 |

**依赖分析**：
- `pystray` 已支持跨平台，Linux 需要安装 `gir1.2-appindicator3-0.1`
- **重要**：AppIndicator 需要运行中的桌面环境。无头 Linux 服务器应使用 `--headless` 模式或 Level 3 降级
- `pyperclip` 跨平台，依赖系统剪贴板命令（Linux 需要 xclip/xsel）
- `tkinter` 跨平台，无需修改

### External References

- pystray 支持的后端：Linux (AppIndicator/GTK)、macOS (原生)、Windows (原生)
- Linux 开机自启：`~/.config/autostart/*.desktop` 或 systemd user service
- macOS 开机自启：`~/Library/LaunchAgents/*.plist`
- PyInstaller 跨平台：需要平台特定的 spec 配置

## Key Technical Decisions

1. **开机自启抽象层**：创建独立的 `src/autostart.py` 模块，封装所有平台的实现细节，而不是在 `tray.py` 中使用条件分支。

2. **Linux 开机自启方式**：选择 `~/.config/autostart/*.desktop` 方式而非 systemd user service，因为更通用且不依赖 systemd。

3. **构建策略**：使用单一 `build.spec` 配合平台检测，而非维护多个 spec 文件。创建 `build.sh` 作为 Linux/macOS 的构建入口。

4. **Docker 策略**：使用单一多目标 Dockerfile，支持 `--target headless` 和 `--target full` 两种构建输出，减少维护负担。

5. **托盘图标适配**：macOS 使用 22x22 图标，Windows 使用 64x64，通过运行时检测动态调整。

6. **平台能力检测**：创建 `src/platform.py` 统一管理平台检测和能力查询，包括 `has_display_service()`, `has_clipboard()`, `has_appindicator()` 函数。

7. **降级行为分级**：定义 3 级降级行为：
   - Level 1 (完整功能)：所有托盘功能可用
   - Level 2 (托盘降级)：无剪贴板/对话框
   - Level 3 (完全 headless)：无 GUI

8. **线程-异步边界保护**：使用以下机制防止死锁：
   - 所有跨线程回调使用 `asyncio.run_coroutine_threadsafe()` 配合超时
   - 托盘事件处理设置 5 秒超时，超时后记录警告并恢复
   - 使用线程安全队列传递托盘事件到主事件循环，避免直接调用

## Open Questions

### Resolved During Planning

- **Linux 系统托盘依赖**：需要 `gir1.2-appindicator3-0.1` 或 `gir1.2-ayatanaappindicator3-0.1`，在 README 中文档化安装方式。
- **macOS 后端**：pystray 原生支持，无需额外依赖。
- **开机自启检测**：使用文件存在性检测（Linux desktop 文件、macOS plist 文件）。

### Deferred to Implementation

- macOS App Bundle 图标资源（需要 `.icns` 格式转换）
- CI 中 macOS 和 Windows runner 的具体测试配置
- Docker 镜像的具体大小优化
- Linux Wayland 与 X11 的差异处理
- macOS App Bundle 日志文件存储位置（`~/Library/Logs/` vs 应用同目录）
- **Docker 单实例锁**：在 Docker 中跳过 SingleInstanceLock 检查（容器隔离保证单实例）

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### 跨平台开机自启架构

```
┌─────────────────────────────────────────────────────────────┐
│                      TrayManager                            │
│  (托盘菜单，调用 autostart.enable/disable/is_enabled)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   AutoStartManager                          │
│  enable() / disable() / is_enabled()                        │
├─────────────────────────────────────────────────────────────┤
│  sys.platform 检测                                          │
│  ┌─────────────┬─────────────┬─────────────┐               │
│  │  win32      │  linux      │  darwin     │               │
│  │  注册表      │  .desktop   │  .plist     │               │
│  └─────────────┴─────────────┴─────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 跨平台构建流程

```
┌─────────────────────────────────────────────────────────────┐
│                    build.spec                               │
│  (平台检测 + 条件化配置)                                     │
├─────────────────────────────────────────────────────────────┤
│  platform.system() 检测                                     │
│  ┌─────────────┬─────────────┬─────────────┐               │
│  │  Windows    │  Linux      │  macOS      │               │
│  │  EXE + icon │  COLLECT    │  BUNDLE     │               │
│  │  pystray._  │  gi imports │  .app + icns│               │
│  │  win32      │             │             │               │
│  └─────────────┴─────────────┴─────────────┘               │
└─────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     build.bat       build.sh        build.sh
     (Windows)       (Linux)         (macOS)
```

### Docker 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                   Dockerfile                                │
│  阶段1: builder (Python 依赖)                               │
│  阶段2: runtime (GUI 依赖 + 应用代码)                        │
├─────────────────────────────────────────────────────────────┤
│  环境检测: /.dockerenv 存在 → 自动 headless 模式            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   main.py                                   │
│  is_running_in_docker() → 切换 --headless                   │
│  is_headless_environment() → 禁用托盘                       │
└─────────────────────────────────────────────────────────────┘
```

### 平台能力检测架构

```
┌─────────────────────────────────────────────────────────────┐
│                   platform.py                               │
│  has_display_service() → 检测 DISPLAY/WAYLAND_DISPLAY       │
│  has_clipboard() → 检测 pyperclip 可用性                     │
│  has_appindicator() → 检测 Linux AppIndicator 支持           │
│  get_platform_level() → 返回降级级别 (1/2/3)                 │
└─────────────────────────────────────────────────────────────┘
```

## Output Structure

```
src/
├── autostart.py          # 新增：跨平台开机自启抽象层
├── platform.py           # 新增：平台能力检测
├── tray.py               # 修改：使用 autostart.py + platform.py
└── main.py               # 修改：添加 Docker 环境检测

build.spec                # 修改：跨平台配置
build.sh                  # 新增：Linux/macOS 构建脚本
build.bat                 # 保留：Windows 构建脚本

Dockerfile                # 新增：多目标 Docker 镜像（headless/full）
docker-compose.yml        # 新增：Docker Compose 配置
docker-entrypoint.sh      # 新增：Docker 入口脚本

.github/
└── workflows/
    └── test.yml          # 新增：CI 多平台测试

tests/
├── test_autostart.py     # 新增：开机自启模块测试
└── test_platform.py      # 新增：平台检测模块测试

requirements.txt          # 可能修改：添加平台特定依赖注释
```

## Implementation Units

- [ ] **Unit 0: Create platform capability detection module**

**Goal:** 创建 `src/platform.py` 模块，统一管理平台检测和能力查询。

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Create: `src/platform.py`
- Create: `tests/test_platform.py`

**Approach:**
- 定义 `has_display_service()` 检测显示服务可用性
- 定义 `has_clipboard()` 检测剪贴板访问能力
- 定义 `has_appindicator()` 检测 Linux AppIndicator 支持
- 定义 `get_platform_level()` 返回降级级别 (1=完整, 2=托盘降级, 3=headless)
- 定义 `is_docker_environment()` 检测 Docker 环境

**Patterns to follow:**
- `src/single_instance.py` 中的平台检测模式

**Test scenarios:**
- Happy path: 各平台正确检测显示服务可用性
- Happy path: Linux 检测 AppIndicator 支持存在/不存在
- Edge case: Docker 环境正确识别
- Edge case: 无 DISPLAY 时返回正确降级级别

**Verification:**
- 单元测试通过
- 各平台返回正确的降级级别

---

- [ ] **Unit 1: Create cross-platform autostart module**

**Goal:** 创建 `src/autostart.py` 模块，封装 Windows、Linux、macOS 的开机自启实现。

**Requirements:** R3

**Dependencies:** Unit 0

**Files:**
- Create: `src/autostart.py`
- Create: `tests/test_autostart.py`

**Approach:**
- 定义 `AutoStartManager` 类，提供 `enable()`, `disable()`, `is_enabled()` 统一接口
- Windows: 使用注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- Linux: 创建 `~/.config/autostart/{app_name}.desktop` 文件
- macOS: 创建 `~/Library/LaunchAgents/com.user.{app_name}.plist` 文件
- macOS 禁用时: 先执行 `launchctl unload` 再删除 plist 文件
- 使用 `sys.platform` 检测平台，延迟导入平台特定模块
- 不支持的平台抛出 `UnsupportedPlatformError`

**Patterns to follow:**
- `src/single_instance.py` 中的平台检测和条件分支模式
- 使用 `Path` 进行跨平台路径操作
- 使用 `getattr(sys, 'frozen', False)` 检测打包环境

**Test scenarios:**
- Happy path [Windows]: `enable(True)` → 注册表键值存在
- Happy path [Windows]: `enable(False)` → 注册表键值被删除
- Happy path [Windows]: `is_enabled()` 返回正确布尔值
- Happy path [Linux]: `enable(True)` → `.desktop` 文件存在且符合 XDG 规范
- Happy path [Linux]: `enable(False)` → `.desktop` 文件被删除
- Happy path [macOS]: `enable(True)` → plist 文件存在且有效
- Happy path [macOS]: `enable(False)` → plist 文件被删除
- Edge case: `~/.config/autostart` 目录不存在时自动创建
- Edge case: Windows 注册表写入权限不足 → 抛出 `PermissionError`
- Edge case: macOS plist 路径包含空格 → 正确转义
- Edge case: 未知平台 → 抛出 `UnsupportedPlatformError`

**Verification:**
- 单元测试通过
- 在各平台上手动验证开机自启功能

---

- [ ] **Unit 2: Refactor tray.py to use autostart module**

**Goal:** 重构 `src/tray.py`，使用新的 `autostart.py` 和 `platform.py` 模块替换现有的 Windows 专有代码。

**Requirements:** R2, R3

**Dependencies:** Unit 0, Unit 1

**Files:**
- Modify: `src/tray.py`
- Modify: `tests/test_autostart.py` (添加集成测试)

**Approach:**
- 移除 `tray.py` 中的 `_check_auto_start()` 和 `_set_auto_start()` 方法
- 在 `TrayManager.__init__()` 中创建 `AutoStartManager` 实例
- 修改 `_toggle_auto_start()` 和 `_get_autostart_text()` 使用新模块
- 添加 macOS 托盘图标尺寸适配（22x22 vs 64x64）
- 使用 `platform.get_platform_level()` 决定可用功能
- **交互状态设计**：
  - 禁用状态：菜单项灰色显示，附带 tooltip 说明原因（如"需要桌面环境"）
  - 加载状态：操作期间菜单项显示"处理中..."，禁用点击
  - 错误状态：失败后显示错误图标，tooltip 包含错误信息
  - 平台限制提示：功能不可用时显示"⚠️ 需安装 xclip"等引导信息

**Patterns to follow:**
- 保持现有的托盘菜单结构和回调模式
- 使用 `AutoStartManager` 的统一接口

**Test scenarios:**
- Happy path: 初始化时调用 `autostart.is_enabled()` 并正确设置菜单项勾选状态
- Happy path: 切换自启-启用 → 调用 `enable()`，菜单显示 "开机自启 ✓"
- Happy path: 切换自启-禁用 → 调用 `disable()`，菜单显示 "开机自启"（无勾选）
- Happy path: 异步操作期间显示"处理中..."状态
- Edge case: 权限不足导致 `enable()` 返回 `False` → 菜单状态不变，显示错误 tooltip
- Edge case: 平台不支持自启功能时菜单项灰色显示，tooltip 说明原因
- Edge case: 功能不可用时显示平台限制引导（如"⚠️ 需桌面环境"）
- Integration: 托盘图标状态与服务状态同步

**Verification:**
- 现有 `tray.py` 相关测试不受影响
- 在各平台上验证托盘菜单功能

---

- [ ] **Unit 3: Update PyInstaller build configuration**

**Goal:** 更新 `build.spec` 支持跨平台打包，包括正确的隐式导入和平台特定配置。

**Requirements:** R5

**Dependencies:** None

**Files:**
- Modify: `build.spec`

**Approach:**
- 使用 `platform.system()` 或 `sys.platform` 检测当前平台
- Linux: 添加 `gi`, `gi.repository` 到 `hiddenimports`
- macOS: 配置 `BUNDLE` 创建 `.app`，设置 `bundle_identifier`
- Windows: 保持现有配置，保留 `pystray._win32` 导入
- 条件化 Windows 特定选项 (`win_no_prefer_redirects`, `win_private_assemblies`)
- 添加 macOS 图标配置（`.icns` 格式）

**Technical design:**
```python
# 方向性伪代码
import platform
system = platform.system()

hiddenimports = ['PIL._tkinter_finder']
if system == 'Linux':
    # GI 需要显式声明具体 repositories，通用 'gi.repository' 不够
    hiddenimports.extend([
        'gi', 'gi.repository',
        'gi.repository.AppIndicator3',
        'gi.repository.GLib',
        'gi.repository.GdkPixbuf'
    ])
    # 还需要 datas 配置包含 typelib 文件
    from PyInstaller.utils.hooks import collect_data_files
    datas.extend(collect_data_files('gi'))
elif system == 'Windows':
    hiddenimports.append('pystray._win32')

# macOS 需要 BUNDLE 创建 .app
if system == 'Darwin':
    app = BUNDLE(coll, name='LLM-ROUTE.app', icon='icon.icns', ...)
```

**Patterns to follow:**
- PyInstaller 官方跨平台配置模式
- 使用 `collect_data_files` 收集平台特定数据

**Test scenarios:**
- Happy path [Windows]: `pyinstaller build.spec` → 输出 `dist/llm-route.exe`，双击可启动
- Happy path [Linux]: `pyinstaller build.spec` → 输出 `dist/llm-route`，具有执行权限，GI imports 正确
- Happy path [macOS]: `pyinstaller build.spec` → 输出 `dist/llm-route.app`，包含 .icns 图标
- Edge case: 缺失图标文件时优雅处理
- Edge case: macOS ARM 上 UPX 压缩可能不兼容
- Edge case: Linux 缺少 GI typelib 时打包失败并提示
- Integration: 打包后的应用能正确启动并显示托盘

**Verification:**
- 各平台 `pyinstaller build.spec --clean` 成功
- 打包后的应用在目标平台正常运行

---

- [ ] **Unit 4: Create cross-platform build scripts**

**Goal:** 创建 `build.sh` 作为 Linux/macOS 的构建入口，更新 `build.bat` 保持一致性。

**Requirements:** R5

**Dependencies:** Unit 3

**Files:**
- Create: `build.sh`
- Modify: `build.bat`

**Approach:**
- `build.sh`: Bash 脚本，检测平台并调用 PyInstaller
- 支持命令行参数：`--clean`, `--debug`
- 打包后输出文件位置提示
- macOS: 提示代码签名步骤（可选）
- `build.bat`: 更新提示信息，保持功能不变

**Test scenarios:**
- Happy path [Windows]: `.\build.bat` → 生成 `dist/llm-route.exe`，退出码 0
- Happy path [Linux/macOS]: `./build.sh` → 生成 `dist/llm-route`，退出码 0
- Edge case: PyInstaller 未安装时的错误提示
- Edge case: 脚本在非项目根目录执行时的路径解析
- Integration: CI 中使用构建脚本

**Verification:**
- `./build.sh` 在 Linux/macOS 上成功执行
- `build.bat` 在 Windows 上成功执行

---

- [ ] **Unit 5: Add Docker support**

**Goal:** 创建 Docker 支持文件，支持容器化部署。

**Requirements:** R4

**Dependencies:** Unit 0

**Files:**
- Create: `Dockerfile` (多目标：headless/full)
- Create: `docker-compose.yml`
- Create: `docker-entrypoint.sh`

**Approach:**
- **推荐单一 Dockerfile** 使用多阶段目标：`docker build --target headless` 或 `docker build --target full`
- `headless` 目标：仅核心 Python 依赖，最小化镜像大小
- `full` 目标：包含 GUI 依赖（用于有显示环境），支持 X11 socket 挂载
- 使用多阶段构建减小镜像大小
- `docker-entrypoint.sh`: 处理 SIGTERM 信号和启动逻辑
- 非 root 用户运行容器

**Technical design:**
```dockerfile
# 方向性结构 - 多目标 Dockerfile
# 阶段1: builder (Python 依赖)
FROM python:3.11-slim AS builder
# ... 安装 Python 依赖

# 阶段2a: headless 运行时（默认目标）
FROM python:3.11-slim AS headless
# 仅核心依赖
COPY --from=builder /app /app
CMD ["python", "-m", "src.main", "--headless"]

# 阶段2b: full 运行时（带 GUI 依赖）
FROM python:3.11-slim AS full
# 安装 GUI 库用于 pystray
RUN apt-get install -y gir1.2-appindicator3-0.1
COPY --from=builder /app /app
# 支持 X11 socket 挂载
```

**Test scenarios:**
- Happy path: `docker build -t llm-route .` → 成功构建镜像（默认 headless 目标）
- Happy path: `docker build --target full -t llm-route-full .` → 成功构建带 GUI 依赖的镜像
- Happy path: `docker run -p 8087:8087 llm-route` → 容器正常运行，HTTP 响应正常
- Happy path: `docker run -v ./config.yaml:/app/config.yaml llm-route` → 使用挂载配置
- Happy path: `docker stop <container>` → 容器优雅退出（10秒内）
- Edge case: 配置文件持久化
- Edge case: 非 root 用户运行
- Integration: API 请求正常路由

**Verification:**
- Docker 镜像构建成功
- 容器内服务正常响应 HTTP 请求

---

- [ ] **Unit 6: Add main.py Docker environment detection**

**Goal:** 在 `src/main.py` 中添加 Docker 和 headless 环境检测，自动适配运行模式。

**Requirements:** R4

**Dependencies:** Unit 0, Unit 5

**Files:**
- Modify: `src/main.py`

**Approach:**
- 使用 `platform.is_docker_environment()` 检测 Docker 环境
- 在无显示环境时自动切换到 `--headless` 模式
- **Docker 环境中跳过 SingleInstanceLock 检查**（容器隔离天然保证单实例）
- 添加 SIGTERM 信号处理，确保优雅关闭
- 记录启动模式到日志

**Patterns to follow:**
- 现有的 `--headless` 命令行参数处理逻辑
- 使用环境变量进行运行时配置

**Test scenarios:**
- Happy path: `/.dockerenv` 存在 → `is_docker()` 返回 `True`
- Happy path: 在容器内且未指定 `--headless` → 自动启用 headless 模式
- Happy path: 有 DISPLAY 时正常启动托盘
- Happy path: Docker 环境中跳过 SingleInstanceLock 检查
- Edge case: `/.dockerenv` 文件被删除的边缘情况（使用 cgroup 备用检测）
- Edge case: Docker 中有 DISPLAY 时仍支持托盘
- Integration: SIGTERM 信号正确触发 `server.stop()` 和 `log_manager.stop()`

**Verification:**
- Docker 容器启动日志显示正确的运行模式
- 非 Docker 环境不受影响

---

- [ ] **Unit 7: Add GitHub Actions CI configuration**

**Goal:** 创建 GitHub Actions 工作流，支持多平台测试。

**Requirements:** R6

**Dependencies:** None

**Files:**
- Create: `.github/workflows/test.yml`

**Approach:**
- 使用 `matrix` 策略测试 Ubuntu、macOS、Windows
- 每个 runner 安装 Python 依赖并运行 pytest
- Linux runner 额外安装 GUI 依赖（`gir1.2-appindicator3-0.1`）
- 测试覆盖率报告

**Technical design:**
```yaml
# 方向性结构
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
  - run: pip install -r requirements-dev.txt
  - run: pytest --cov=src
```

**Test scenarios:**
- Happy path: 所有平台测试通过
- Edge case: 平台特定测试正确跳过（使用 `@pytest.mark.skipif`）
- Integration: Release 触发构建产物打包

**Verification:**
- GitHub Actions 页面显示所有平台绿色通过
- 代码覆盖率报告生成

---

- [ ] **Unit 8: Update documentation**

**Goal:** 更新 README 和相关文档，说明跨平台使用方式。

**Requirements:** R1, R4, R5

**Dependencies:** Unit 4, Unit 5

**Files:**
- Modify: `README.md`

**Approach:**
- 添加平台支持矩阵
- Linux: 说明 GUI 依赖安装方式
- macOS: 说明使用方式和开机自启
- Docker: 添加快速启动示例
- 构建：说明各平台构建步骤
- 说明降级行为和功能差异

**Test scenarios:**
- Test expectation: none -- 文档更新

**Verification:**
- 文档清晰说明各平台使用方式
- 用户能按文档在目标平台成功运行

## System-Wide Impact

### Interaction Graph

```
Layer 1: 托盘 UI (tray.py) [独立线程]
  │─ pystray.Icon.run() [平台特定事件循环]
  │   └─ Windows: win32 消息循环
  │   └─ Linux: GTK/GLib 主循环 (可能与 asyncio 竞争)
  │   └─ macOS: rumps/Objective-C 运行时
  │
  │─ 用户菜单操作 → on_exit/on_port_change/on_toggle_service
  │   └─ asyncio.run_coroutine_threadsafe() [回到主事件循环]
  │
  ▼
Layer 2: 主程序协调器 (main.py) [asyncio 事件循环]
  │─ SingleInstanceLock 检查
  │─ 配置加载
  │─ ProxyServer 启动
  │─ TrayManager 启动 (非 headless)
  │
  ▼
Layer 3: 代理服务 (proxy.py)
  │─ 端口绑定
  │─ 上游连接
  │─ 请求路由
  │
  ▼
Layer 4: 配置持久化 (config.py)
  └─ YAML 读写 (无文件锁)
```

**新增交互节点：**
- `platform.py` → 被 `tray.py`, `main.py` 调用进行能力检测
- `autostart.py` → 被 `tray.py` 调用进行开机自启管理
- 信号处理入口点 → SIGTERM/SIGINT 触发优雅关闭

### Error Propagation

| 来源 | 错误类型 | 当前行为 | 跨平台改进 |
|------|----------|----------|------------|
| pystray 初始化失败 | RuntimeError | 静默失败 | 检测并提示安装依赖，或降级到 headless |
| Linux 无 AppIndicator | ImportError | 静默失败 | 检测 `has_appindicator()`，提示安装 `gir1.2-appindicator3-0.1` |
| 注册表/文件权限不足 | PermissionError | 异常传播 | 统一处理，返回 `False` 并记录日志 |
| Docker 无显示服务 | - | - | 自动切换 headless 模式 |
| SIGTERM 信号 | - | 未处理 | 触发 `server.stop()` 和 `log_manager.stop()` |

### State Lifecycle Risks

| 平台 | 写入目标 | 部分写入风险 | 清理风险 | 缓解措施 |
|------|----------|-------------|---------|---------|
| Windows | 注册表 | 低（原子操作） | 低 | - |
| Linux | `~/.config/autostart/*.desktop` | 高（目录可能不存在） | 中（文件残留） | 先创建目录，写入后验证 |
| macOS | `~/Library/LaunchAgents/*.plist` | 中 | 高（LaunchAgent 继续尝试启动） | 禁用时同时执行 `launchctl unload` |

**配置文件一致性风险：**
- 写入中途崩溃 → `config.yaml` 损坏 → 下次启动使用默认配置（数据丢失）
- 托盘缓存状态与文件不同步 → 添加状态刷新触发点

### API Surface Parity

**命令行参数（所有平台一致）：**
| 参数 | 行为 |
|------|------|
| `--headless` | 一致，Docker 环境自动启用 |
| `--config` | 一致，路径格式跨平台差异 |
| `--port` | 一致 |

**环境变量（新增）：**
| 变量 | 用途 |
|------|------|
| `LLM_ROUTE_PORT` | 覆盖端口配置 |
| `LLM_ROUTE_CONFIG` | 配置文件路径 |
| `LLM_ROUTE_LOG_LEVEL` | 日志等级 |
| `LLM_ROUTE_HEADLESS` | 强制 headless 模式 |

**托盘菜单功能差异：**
| 功能 | Windows | Linux | macOS | Docker |
|------|---------|-------|-------|--------|
| 复制代理地址 | ✅ | ⚠️ 需 xclip/xsel | ✅ | ❌ |
| 日志详情窗口 | ✅ | ✅ | ✅ | ❌ |
| 更换端口对话框 | ✅ | ✅ | ✅ | ❌ |
| 开机自启 | ✅ | ⚠️ 需桌面环境 | ⚠️ 需登录用户 | ❌ |

### Integration Coverage

- 托盘 UI → 主程序协调器：菜单操作正确触发异步操作
- 主程序 → 代理服务：启动/停止状态同步
- 代理服务 → 配置：配置变更正确应用
- Docker 环境 → 信号处理：SIGTERM 正确触发清理链

### Unchanged Invariants

- 核心 `ProxyServer` 功能不受此变更影响
- 现有 Windows 用户体验保持不变
- 配置文件格式保持兼容

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Linux GUI 依赖复杂 | Medium | Medium | 文档化依赖安装，提供 headless 替代 |
| macOS 代码签名缺失 | High | Low | 应用可运行但会显示"未验证开发者"警告，文档化绕过方式 |
| CI 多平台配置复杂 | Medium | Low | 先实现基础测试，逐步完善 |
| Windows 现有功能回归 | Low | High | 保持现有测试，添加新测试覆盖 |
| 线程-异步边界死锁 | Medium | High | 使用线程安全队列 + 5秒超时 + 看门狗机制（见技术决策 8） |
| 状态缓存不一致 | High | Low | 添加状态刷新触发点 |
| 文件权限跨平台差异 | Medium | Medium | 创建统一文件操作封装 |

## Documentation / Operational Notes

- **README.md**: 添加平台支持矩阵、各平台安装和使用说明、Docker 快速启动、降级行为说明
- **Docker Hub**: 考虑发布官方镜像（可选）
- **Release Notes**: 说明跨平台支持为重大更新

## Sources & References

- pystray 文档: https://github.com/moses-palmer/pystray
- PyInstaller Spec Files: https://pyinstaller.org/en/stable/spec-files.html
- Linux autostart spec: https://specifications.freedesktop.org/autostart-spec/
- macOS LaunchAgent: https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/
