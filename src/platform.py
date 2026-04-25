"""平台能力检测模块

提供跨平台能力检测函数，用于判断当前运行环境和可用功能。
"""
import os
import sys
from pathlib import Path


def is_docker_environment() -> bool:
    """检测是否运行在 Docker 容器中

    检测方式：
    1. 检查 /.dockerenv 文件是否存在
    2. 检查 /proc/1/cgroup 是否包含 docker 或 kubepods

    Returns:
        True 如果在 Docker 环境中
    """
    # 方法1: 检查 /.dockerenv 文件
    if Path("/.dockerenv").exists():
        return True

    # 方法2: 检查 cgroup (Linux)
    if sys.platform.startswith("linux"):
        try:
            cgroup_path = Path("/proc/1/cgroup")
            if cgroup_path.exists():
                content = cgroup_path.read_text()
                if "docker" in content or "kubepods" in content:
                    return True
        except (IOError, OSError):
            pass

    return False


def has_display_service() -> bool:
    """检测是否有显示服务可用

    检测方式：
    - Windows: 始终返回 True
    - macOS: 始终返回 True
    - Linux: 检查 DISPLAY 或 WAYLAND_DISPLAY 环境变量

    Returns:
        True 如果有显示服务
    """
    if sys.platform == "win32":
        # Windows 始终有显示服务（即使是远程桌面）
        return True

    if sys.platform == "darwin":
        # macOS 始终有显示服务
        return True

    # Linux: 检查显示相关环境变量
    display = os.environ.get("DISPLAY")
    wayland = os.environ.get("WAYLAND_DISPLAY")

    return bool(display or wayland)


def has_clipboard() -> bool:
    """检测剪贴板是否可用

    检测方式：尝试使用 pyperclip 读取剪贴板

    Returns:
        True 如果剪贴板可用
    """
    try:
        import pyperclip
        # 尝试读取剪贴板内容
        pyperclip.paste()
        return True
    except Exception:
        return False


def has_appindicator() -> bool:
    """检测 Linux 是否有 AppIndicator 支持

    检测方式：尝试导入 gi.repository 中的 AppIndicator 模块

    Returns:
        True 如果 AppIndicator 可用（非 Linux 平台始终返回 True）
    """
    if sys.platform != "linux":
        # 非 Linux 平台不需要 AppIndicator
        return True

    try:
        import gi
        # 尝试 AppIndicator3
        try:
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import AppIndicator3  # noqa: F401
            return True
        except (ValueError, ImportError):
            pass

        # 尝试 AyatanaAppIndicator3
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3  # noqa: F401
            return True
        except (ValueError, ImportError):
            pass

        return False
    except ImportError:
        return False


def get_platform_level() -> int:
    """获取当前平台的功能级别

    级别定义：
    - Level 1 (完整功能): 所有托盘功能可用
    - Level 2 (托盘降级): 托盘可用但剪贴板/对话框不可用
    - Level 3 (完全 headless): 无 GUI

    Returns:
        平台功能级别 (1, 2, 或 3)
    """
    # Level 3: Docker 环境或无显示服务
    if is_docker_environment() or not has_display_service():
        return 3

    # Level 2: 显示服务存在但剪贴板不可用
    if not has_clipboard():
        return 2

    # Level 1: 完整功能
    return 1


def get_platform_info() -> dict:
    """获取平台详细信息

    Returns:
        包含平台信息的字典
    """
    return {
        "platform": sys.platform,
        "is_docker": is_docker_environment(),
        "has_display": has_display_service(),
        "has_clipboard": has_clipboard(),
        "has_appindicator": has_appindicator() if sys.platform == "linux" else None,
        "level": get_platform_level(),
    }


if __name__ == "__main__":
    # 测试输出
    import json
    print(json.dumps(get_platform_info(), indent=2))
