"""跨平台开机自启模块

支持 Windows、Linux、macOS 的开机自启功能。
"""

import logging
import os
import sys
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


# 模块级日志
_logger = logging.getLogger(__name__)


class UnsupportedPlatformError(Exception):
    """不支持的平台异常"""

    pass


class AutoStartManager:
    """跨平台开机自启管理器"""

    def __init__(self, app_name: str = "LLM-ROUTE"):
        """
        Args:
            app_name: 应用名称，用于注册表键名、文件名等
        """
        self.app_name = app_name
        self._impl = self._get_platform_impl()

    def _get_platform_impl(self) -> "_AutoStartImpl":
        """获取平台特定的实现"""
        if sys.platform == "win32":
            return _WindowsAutoStart(self.app_name)
        elif sys.platform == "linux":
            return _LinuxAutoStart(self.app_name)
        elif sys.platform == "darwin":
            return _MacOSAutoStart(self.app_name)
        else:
            return _UnsupportedAutoStart(self.app_name)

    def enable(self) -> bool:
        """启用开机自启

        Returns:
            True 表示成功启用
        """
        return self._impl.enable()

    def disable(self) -> bool:
        """禁用开机自启

        Returns:
            True 表示成功禁用
        """
        return self._impl.disable()

    def is_enabled(self) -> bool:
        """检查是否已启用开机自启

        Returns:
            True 表示已启用
        """
        return self._impl.is_enabled()

    def is_supported(self) -> bool:
        """检查当前平台是否支持开机自启

        Returns:
            True 表示支持
        """
        return not isinstance(self._impl, _UnsupportedAutoStart)


class _AutoStartImpl(ABC):
    """开机自启实现基类"""

    def __init__(self, app_name: str):
        self.app_name = app_name

    @abstractmethod
    def enable(self) -> bool:
        pass

    @abstractmethod
    def disable(self) -> bool:
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        pass

    def _get_executable_path(self) -> str:
        """获取可执行文件路径"""
        if getattr(sys, "frozen", False):
            # 打包后的可执行文件
            return sys.executable
        else:
            # 开发模式下返回 Python 解释器和脚本路径
            return f'"{sys.executable}" "{Path(__file__).parent.parent / "main.py"}"'


class _WindowsAutoStart(_AutoStartImpl):
    """Windows 注册表实现"""

    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _log_error(self, message: str, error: Exception) -> None:
        """记录错误到日志

        Args:
            message: 错误描述
            error: 异常对象
        """
        error_code = getattr(error, 'winerror', None) or getattr(error, 'errno', 'unknown')
        _logger.error(f"[AutoStart] {message}: {error} (code: {error_code})")

    def enable(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH,
                0,
                winreg.KEY_WRITE,
            ) as key:
                exe_path = self._get_executable_path()
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, exe_path)
            return True
        except PermissionError as e:
            self._log_error("权限不足，无法写入注册表", e)
            return False
        except FileNotFoundError as e:
            self._log_error("注册表路径不存在", e)
            return False
        except WindowsError as e:
            self._log_error("注册表操作失败", e)
            return False

    def disable(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH,
                0,
                winreg.KEY_WRITE,
            ) as key:
                try:
                    winreg.DeleteValue(key, self.app_name)
                except WindowsError:
                    pass  # 键不存在，视为成功
            return True
        except PermissionError as e:
            self._log_error("权限不足，无法写入注册表", e)
            return False
        except FileNotFoundError as e:
            self._log_error("注册表路径不存在", e)
            return False
        except WindowsError as e:
            self._log_error("注册表操作失败", e)
            return False

    def is_enabled(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.REG_PATH,
                0,
                winreg.KEY_READ,
            ) as key:
                winreg.QueryValueEx(key, self.app_name)
            return True
        except WindowsError:
            return False


class _LinuxAutoStart(_AutoStartImpl):
    """Linux XDG autostart 实现"""

    DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name={app_name}
Exec={exec_path}
Icon={icon_path}
Comment={comment}
Terminal=false
Categories=Network;
X-GNOME-Autostart-enabled=true
"""

    def _get_autostart_dir(self) -> Path:
        """获取 autostart 目录路径"""
        config_home = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        return Path(config_home) / "autostart"

    def _get_desktop_file(self) -> Path:
        """获取 desktop 文件路径"""
        return self._get_autostart_dir() / f"{self.app_name.lower()}.desktop"

    def enable(self) -> bool:
        try:
            autostart_dir = self._get_autostart_dir()
            autostart_dir.mkdir(parents=True, exist_ok=True)

            desktop_file = self._get_desktop_file()
            exec_path = self._get_executable_path()

            # 尝试找到图标文件
            icon_path = ""
            if getattr(sys, "frozen", False):
                icon_candidate = Path(sys.executable).parent / "icon.png"
                if icon_candidate.exists():
                    icon_path = str(icon_candidate)

            # Desktop Entry 规范转义：处理特殊字符
            # % 字符需要转义为 %%
            # 换行符和制表符需要移除
            escaped_app_name = (
                self.app_name.replace("%", "%%").replace("\n", "").replace("\t", "")
            )
            escaped_exec_path = exec_path.replace("%", "%%")
            escaped_icon_path = icon_path.replace("%", "%%") if icon_path else ""
            escaped_comment = (
                f"{self.app_name} LLM API Router".replace("%", "%%")
                .replace("\n", "")
                .replace("\t", "")
            )

            content = self.DESKTOP_ENTRY.format(
                app_name=escaped_app_name,
                exec_path=escaped_exec_path,
                icon_path=escaped_icon_path,
                comment=escaped_comment,
            )

            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)

            # 设置可执行权限
            desktop_file.chmod(0o755)
            return True
        except (IOError, OSError, PermissionError):
            return False

    def disable(self) -> bool:
        try:
            desktop_file = self._get_desktop_file()
            if desktop_file.exists():
                desktop_file.unlink()
            return True
        except (IOError, OSError, PermissionError):
            return False

    def is_enabled(self) -> bool:
        return self._get_desktop_file().exists()


class _MacOSAutoStart(_AutoStartImpl):
    """macOS LaunchAgent 实现"""

    PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exec_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""

    def _get_launchagents_dir(self) -> Path:
        """获取 LaunchAgents 目录路径"""
        return Path.home() / "Library" / "LaunchAgents"

    def _get_plist_file(self) -> Path:
        """获取 plist 文件路径"""
        return self._get_launchagents_dir() / f"com.user.{self.app_name.lower()}.plist"

    def _get_label(self) -> str:
        """获取 LaunchAgent 标签"""
        return f"com.user.{self.app_name.lower()}"

    def enable(self) -> bool:
        try:
            launchagents_dir = self._get_launchagents_dir()
            launchagents_dir.mkdir(parents=True, exist_ok=True)

            plist_file = self._get_plist_file()
            exec_path = self._get_executable_path()
            label = self._get_label()

            # 使用 xml.sax.saxutils 转义 XML 特殊字符
            from xml.sax.saxutils import escape

            escaped_label = escape(label)
            escaped_exec_path = escape(exec_path)

            content = self.PLIST_TEMPLATE.format(
                label=escaped_label,
                exec_path=escaped_exec_path,
            )

            with open(plist_file, "w", encoding="utf-8") as f:
                f.write(content)

            # 加载 LaunchAgent 使其立即生效
            try:
                subprocess.run(
                    ["launchctl", "load", str(plist_file)],
                    capture_output=True,
                    timeout=5,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass  # 加载失败不阻止启用，用户可以注销后生效

            return True
        except (IOError, OSError, PermissionError):
            return False

    def disable(self) -> bool:
        try:
            plist_file = self._get_plist_file()
            label = self._get_label()

            if plist_file.exists():
                # 先执行 launchctl unload
                try:
                    subprocess.run(
                        ["launchctl", "unload", str(plist_file)],
                        capture_output=True,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

                # 执行 launchctl remove 移除服务注册
                try:
                    subprocess.run(
                        ["launchctl", "remove", label],
                        capture_output=True,
                        timeout=5,
                    )
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

                # 删除 plist 文件
                plist_file.unlink()

            return True
        except (IOError, OSError, PermissionError):
            return False

    def is_enabled(self) -> bool:
        return self._get_plist_file().exists()


class _UnsupportedAutoStart(_AutoStartImpl):
    """不支持的平台"""

    def enable(self) -> bool:
        # 返回 False 而不是抛出异常，保持与基类契约一致
        # 调用者可以通过 is_supported() 预先检查
        return False

    def disable(self) -> bool:
        # 返回 False 而不是抛出异常，保持与基类契约一致
        return False

    def is_enabled(self) -> bool:
        return False


if __name__ == "__main__":
    # 测试
    manager = AutoStartManager()
    print(f"Platform: {sys.platform}")
    print(f"Supported: {manager.is_supported()}")
    print(f"Enabled: {manager.is_enabled()}")
