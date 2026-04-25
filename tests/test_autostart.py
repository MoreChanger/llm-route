"""autostart.py 模块测试"""
import os
import sys
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from src.autostart import (
    AutoStartManager,
    UnsupportedPlatformError,
    _AutoStartImpl,
    _WindowsAutoStart,
    _LinuxAutoStart,
    _MacOSAutoStart,
    _UnsupportedAutoStart,
)


class TestAutoStartManager:
    """测试 AutoStartManager 类"""

    def test_init_default_app_name(self):
        """测试默认应用名称"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            assert manager.app_name == "LLM-ROUTE"

    def test_init_custom_app_name(self):
        """测试自定义应用名称"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager("MyApp")
            assert manager.app_name == "MyApp"

    def test_windows_platform_selection(self):
        """测试 Windows 平台选择"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            assert isinstance(manager._impl, _WindowsAutoStart)

    def test_linux_platform_selection(self):
        """测试 Linux 平台选择"""
        with patch("sys.platform", "linux"):
            manager = AutoStartManager()
            assert isinstance(manager._impl, _LinuxAutoStart)

    def test_macos_platform_selection(self):
        """测试 macOS 平台选择"""
        with patch("sys.platform", "darwin"):
            manager = AutoStartManager()
            assert isinstance(manager._impl, _MacOSAutoStart)

    def test_unsupported_platform_selection(self):
        """测试不支持的平台选择"""
        with patch("sys.platform", "freebsd"):
            manager = AutoStartManager()
            assert isinstance(manager._impl, _UnsupportedAutoStart)

    def test_is_supported_true(self):
        """测试支持的平台"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            assert manager.is_supported() is True

    def test_is_supported_false(self):
        """测试不支持的平台"""
        with patch("sys.platform", "freebsd"):
            manager = AutoStartManager()
            assert manager.is_supported() is False

    def test_enable_delegates_to_impl(self):
        """测试 enable 委托给实现"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            with patch.object(manager._impl, "enable", return_value=True) as mock_enable:
                result = manager.enable()
                mock_enable.assert_called_once()
                assert result is True

    def test_disable_delegates_to_impl(self):
        """测试 disable 委托给实现"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            with patch.object(manager._impl, "disable", return_value=True) as mock_disable:
                result = manager.disable()
                mock_disable.assert_called_once()
                assert result is True

    def test_is_enabled_delegates_to_impl(self):
        """测试 is_enabled 委托给实现"""
        with patch("sys.platform", "win32"):
            manager = AutoStartManager()
            with patch.object(manager._impl, "is_enabled", return_value=False) as mock_is_enabled:
                result = manager.is_enabled()
                mock_is_enabled.assert_called_once()
                assert result is False


class TestAutoStartImpl:
    """测试 _AutoStartImpl 基类"""

    def test_get_executable_path_frozen(self):
        """测试打包后的可执行文件路径"""
        with patch("sys.platform", "win32"):
            impl = _WindowsAutoStart("TestApp")
            # 使用 MagicMock 模拟 sys.frozen 属性
            with patch.dict("sys.__dict__", {"frozen": True}):
                with patch("sys.executable", "/path/to/app.exe"):
                    path = impl._get_executable_path()
                    assert path == "/path/to/app.exe"

    def test_get_executable_path_development(self):
        """测试开发模式下的路径"""
        with patch("sys.platform", "win32"):
            impl = _WindowsAutoStart("TestApp")
            with patch.object(sys, "frozen", False, create=True):
                with patch("sys.executable", "/usr/bin/python"):
                    path = impl._get_executable_path()
                    assert "python" in path
                    assert "main.py" in path


class TestWindowsAutoStart:
    """测试 _WindowsAutoStart 类"""

    def test_enable_success(self):
        """测试启用成功"""
        impl = _WindowsAutoStart("TestApp")

        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key):
            with patch("winreg.SetValueEx"):
                with patch("winreg.CloseKey"):
                    result = impl.enable()
                    assert result is True

    def test_enable_failure(self):
        """测试启用失败"""
        impl = _WindowsAutoStart("TestApp")

        with patch("winreg.OpenKey", side_effect=WindowsError("Access denied")):
            result = impl.enable()
            assert result is False

    def test_disable_success(self):
        """测试禁用成功"""
        impl = _WindowsAutoStart("TestApp")

        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key):
            with patch("winreg.DeleteValue"):
                with patch("winreg.CloseKey"):
                    result = impl.disable()
                    assert result is True

    def test_disable_key_not_exists(self):
        """测试禁用时键不存在"""
        impl = _WindowsAutoStart("TestApp")

        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key):
            with patch("winreg.DeleteValue", side_effect=WindowsError("Key not found")):
                with patch("winreg.CloseKey"):
                    result = impl.disable()
                    assert result is True  # 键不存在视为成功

    def test_is_enabled_true(self):
        """测试已启用"""
        impl = _WindowsAutoStart("TestApp")

        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key):
            with patch("winreg.QueryValueEx", return_value=("path", 1)):
                with patch("winreg.CloseKey"):
                    result = impl.is_enabled()
                    assert result is True

    def test_is_enabled_false(self):
        """测试未启用"""
        impl = _WindowsAutoStart("TestApp")

        with patch("winreg.OpenKey", side_effect=WindowsError("Key not found")):
            result = impl.is_enabled()
            assert result is False


class TestLinuxAutoStart:
    """测试 _LinuxAutoStart 类"""

    def test_get_autostart_dir_default(self):
        """测试默认 autostart 目录"""
        impl = _LinuxAutoStart("TestApp")

        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.home", return_value=Path("/home/user")):
                dir_path = impl._get_autostart_dir()
                assert dir_path == Path("/home/user/.config/autostart")

    def test_get_autostart_dir_xdg_config(self):
        """测试 XDG_CONFIG_HOME 环境变量"""
        impl = _LinuxAutoStart("TestApp")

        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}):
            dir_path = impl._get_autostart_dir()
            assert dir_path == Path("/custom/config/autostart")

    def test_get_desktop_file(self):
        """测试 desktop 文件路径"""
        impl = _LinuxAutoStart("TestApp")

        with patch.object(impl, "_get_autostart_dir", return_value=Path("/home/user/.config/autostart")):
            file_path = impl._get_desktop_file()
            assert file_path == Path("/home/user/.config/autostart/testapp.desktop")

    def test_enable_success(self, tmp_path):
        """测试启用成功"""
        impl = _LinuxAutoStart("TestApp")

        autostart_dir = tmp_path / "autostart"
        with patch.object(impl, "_get_autostart_dir", return_value=autostart_dir):
            with patch.object(impl, "_get_executable_path", return_value="/usr/bin/testapp"):
                with patch.object(sys, "frozen", False, create=True):
                    result = impl.enable()
                    assert result is True
                    assert impl._get_desktop_file().exists()

    def test_enable_with_icon(self, tmp_path):
        """测试启用时包含图标"""
        impl = _LinuxAutoStart("TestApp")

        autostart_dir = tmp_path / "autostart"
        icon_path = tmp_path / "icon.png"
        icon_path.touch()

        with patch.object(impl, "_get_autostart_dir", return_value=autostart_dir):
            with patch.object(impl, "_get_executable_path", return_value="/usr/bin/testapp"):
                # 模拟 frozen 属性
                with patch.dict("sys.__dict__", {"frozen": True}):
                    with patch("sys.executable", str(tmp_path / "app")):
                        result = impl.enable()
                        assert result is True

    def test_disable_success(self, tmp_path):
        """测试禁用成功"""
        impl = _LinuxAutoStart("TestApp")

        autostart_dir = tmp_path / "autostart"
        autostart_dir.mkdir()
        desktop_file = autostart_dir / "testapp.desktop"
        desktop_file.touch()

        with patch.object(impl, "_get_desktop_file", return_value=desktop_file):
            result = impl.disable()
            assert result is True
            assert not desktop_file.exists()

    def test_disable_file_not_exists(self, tmp_path):
        """测试禁用时文件不存在"""
        impl = _LinuxAutoStart("TestApp")

        with patch.object(impl, "_get_desktop_file", return_value=tmp_path / "nonexistent.desktop"):
            result = impl.disable()
            assert result is True

    def test_is_enabled_true(self, tmp_path):
        """测试已启用"""
        impl = _LinuxAutoStart("TestApp")

        desktop_file = tmp_path / "testapp.desktop"
        desktop_file.touch()

        with patch.object(impl, "_get_desktop_file", return_value=desktop_file):
            result = impl.is_enabled()
            assert result is True

    def test_is_enabled_false(self, tmp_path):
        """测试未启用"""
        impl = _LinuxAutoStart("TestApp")

        with patch.object(impl, "_get_desktop_file", return_value=tmp_path / "nonexistent.desktop"):
            result = impl.is_enabled()
            assert result is False


class TestMacOSAutoStart:
    """测试 _MacOSAutoStart 类"""

    def test_get_launchagents_dir(self):
        """测试 LaunchAgents 目录路径"""
        impl = _MacOSAutoStart("TestApp")

        with patch("pathlib.Path.home", return_value=Path("/Users/user")):
            dir_path = impl._get_launchagents_dir()
            assert dir_path == Path("/Users/user/Library/LaunchAgents")

    def test_get_plist_file(self):
        """测试 plist 文件路径"""
        impl = _MacOSAutoStart("TestApp")

        with patch.object(impl, "_get_launchagents_dir", return_value=Path("/Users/user/Library/LaunchAgents")):
            file_path = impl._get_plist_file()
            assert file_path == Path("/Users/user/Library/LaunchAgents/com.user.testapp.plist")

    def test_get_label(self):
        """测试 LaunchAgent 标签"""
        impl = _MacOSAutoStart("TestApp")
        label = impl._get_label()
        assert label == "com.user.testapp"

    def test_enable_success(self, tmp_path):
        """测试启用成功"""
        impl = _MacOSAutoStart("TestApp")

        launchagents_dir = tmp_path / "LaunchAgents"
        with patch.object(impl, "_get_launchagents_dir", return_value=launchagents_dir):
            with patch.object(impl, "_get_executable_path", return_value="/Applications/TestApp.app/Contents/MacOS/TestApp"):
                result = impl.enable()
                assert result is True
                assert impl._get_plist_file().exists()

    def test_disable_success(self, tmp_path):
        """测试禁用成功"""
        impl = _MacOSAutoStart("TestApp")

        launchagents_dir = tmp_path / "LaunchAgents"
        launchagents_dir.mkdir()
        plist_file = launchagents_dir / "com.user.testapp.plist"
        plist_file.touch()

        with patch.object(impl, "_get_plist_file", return_value=plist_file):
            with patch("subprocess.run"):
                result = impl.disable()
                assert result is True
                assert not plist_file.exists()

    def test_disable_with_launchctl_unload(self, tmp_path):
        """测试禁用时执行 launchctl unload"""
        impl = _MacOSAutoStart("TestApp")

        launchagents_dir = tmp_path / "LaunchAgents"
        launchagents_dir.mkdir()
        plist_file = launchagents_dir / "com.user.testapp.plist"
        plist_file.touch()

        with patch.object(impl, "_get_plist_file", return_value=plist_file):
            with patch("subprocess.run") as mock_run:
                result = impl.disable()
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert args[0] == "launchctl"
                assert args[1] == "unload"
                assert result is True

    def test_disable_launchctl_timeout(self, tmp_path):
        """测试 launchctl unload 超时"""
        impl = _MacOSAutoStart("TestApp")

        launchagents_dir = tmp_path / "LaunchAgents"
        launchagents_dir.mkdir()
        plist_file = launchagents_dir / "com.user.testapp.plist"
        plist_file.touch()

        with patch.object(impl, "_get_plist_file", return_value=plist_file):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("launchctl", 5)):
                result = impl.disable()
                assert result is True
                assert not plist_file.exists()

    def test_is_enabled_true(self, tmp_path):
        """测试已启用"""
        impl = _MacOSAutoStart("TestApp")

        plist_file = tmp_path / "com.user.testapp.plist"
        plist_file.touch()

        with patch.object(impl, "_get_plist_file", return_value=plist_file):
            result = impl.is_enabled()
            assert result is True

    def test_is_enabled_false(self, tmp_path):
        """测试未启用"""
        impl = _MacOSAutoStart("TestApp")

        with patch.object(impl, "_get_plist_file", return_value=tmp_path / "nonexistent.plist"):
            result = impl.is_enabled()
            assert result is False


class TestUnsupportedAutoStart:
    """测试 _UnsupportedAutoStart 类"""

    def test_enable_raises_exception(self):
        """测试启用抛出异常"""
        impl = _UnsupportedAutoStart("TestApp")
        with pytest.raises(UnsupportedPlatformError):
            impl.enable()

    def test_disable_raises_exception(self):
        """测试禁用抛出异常"""
        impl = _UnsupportedAutoStart("TestApp")
        with pytest.raises(UnsupportedPlatformError):
            impl.disable()

    def test_is_enabled_returns_false(self):
        """测试 is_enabled 返回 False"""
        impl = _UnsupportedAutoStart("TestApp")
        assert impl.is_enabled() is False


class TestIntegration:
    """集成测试"""

    @pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 平台测试")
    def test_windows_integration(self):
        """Windows 平台集成测试"""
        manager = AutoStartManager("TestLLMRoute")
        assert manager.is_supported() is True
        # 不实际修改注册表，只测试接口可用
        assert hasattr(manager, "enable")
        assert hasattr(manager, "disable")
        assert hasattr(manager, "is_enabled")

    @pytest.mark.skipif(sys.platform != "linux", reason="仅 Linux 平台测试")
    def test_linux_integration(self):
        """Linux 平台集成测试"""
        manager = AutoStartManager("TestLLMRoute")
        assert manager.is_supported() is True
        assert hasattr(manager, "enable")
        assert hasattr(manager, "disable")
        assert hasattr(manager, "is_enabled")

    @pytest.mark.skipif(sys.platform != "darwin", reason="仅 macOS 平台测试")
    def test_macos_integration(self):
        """macOS 平台集成测试"""
        manager = AutoStartManager("TestLLMRoute")
        assert manager.is_supported() is True
        assert hasattr(manager, "enable")
        assert hasattr(manager, "disable")
        assert hasattr(manager, "is_enabled")
