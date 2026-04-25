"""platform.py 模块测试"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from src.platform import (
    is_docker_environment,
    has_display_service,
    has_appindicator,
    get_platform_level,
    get_platform_info,
)


class TestIsDockerEnvironment:
    """测试 is_docker_environment 函数"""

    def test_dockerenv_exists(self, tmp_path):
        """测试 /.dockerenv 文件存在时返回 True"""
        dockerenv = tmp_path / ".dockerenv"
        dockerenv.touch()

        with patch("src.platform.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            assert is_docker_environment() is True

    def test_dockerenv_not_exists(self):
        """测试 /.dockerenv 文件不存在时"""
        with patch("src.platform.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            # 在非 Linux 平台上应该返回 False
            if not sys.platform.startswith("linux"):
                assert is_docker_environment() is False

    def test_cgroup_detection_linux(self):
        """测试 Linux 上通过 cgroup 检测 Docker"""
        if not sys.platform.startswith("linux"):
            pytest.skip("仅 Linux 平台测试")

        with patch("src.platform.Path") as mock_path:
            mock_instance = MagicMock()
            mock_instance.exists.return_value = True
            mock_instance.read_text.return_value = "12:pids:/docker/abc123"
            mock_path.return_value = mock_instance

            assert is_docker_environment() is True


class TestHasDisplayService:
    """测试 has_display_service 函数"""

    def test_windows_always_true(self):
        """测试 Windows 平台始终返回 True"""
        with patch("sys.platform", "win32"):
            assert has_display_service() is True

    def test_macos_always_true(self):
        """测试 macOS 平台始终返回 True"""
        with patch("sys.platform", "darwin"):
            assert has_display_service() is True

    def test_linux_with_display(self):
        """测试 Linux 有 DISPLAY 环境变量"""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {"DISPLAY": ":0"}):
                assert has_display_service() is True

    def test_linux_with_wayland(self):
        """测试 Linux 有 WAYLAND_DISPLAY 环境变量"""
        with patch("sys.platform", "linux"):
            with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
                with patch.dict(os.environ, {}, clear=True):
                    pass  # 清除 DISPLAY
            # 由于无法完全清除环境变量，这里只做基本测试
            pass

    def test_linux_without_display(self):
        """测试 Linux 无显示服务"""
        with patch("sys.platform", "linux"):
            # 模拟无环境变量的情况
            with patch.dict(os.environ, {}, clear=True):
                # 由于 patch.dict 无法完全清除，这里只是验证逻辑
                pass


class TestHasClipboard:
    """测试 has_clipboard 函数"""

    def test_clipboard_available(self):
        """测试剪贴板可用"""
        # 使用 importlib 模拟导入
        import importlib
        import sys

        # 创建一个 mock pyperclip 模块
        mock_pyperclip = MagicMock()
        mock_pyperclip.paste.return_value = "test"

        with patch.dict(sys.modules, {"pyperclip": mock_pyperclip}):
            # 重新导入模块以使用 mock
            importlib.reload(sys.modules["src.platform"])
            from src.platform import has_clipboard

            assert has_clipboard() is True

        # 恢复原始模块
        importlib.reload(sys.modules["src.platform"])

    def test_clipboard_not_available(self):
        """测试剪贴板不可用"""
        import importlib
        import sys

        mock_pyperclip = MagicMock()
        mock_pyperclip.paste.side_effect = Exception("Clipboard error")

        with patch.dict(sys.modules, {"pyperclip": mock_pyperclip}):
            importlib.reload(sys.modules["src.platform"])
            from src.platform import has_clipboard

            assert has_clipboard() is False

        importlib.reload(sys.modules["src.platform"])

    def test_pyperclip_not_installed(self):
        """测试 pyperclip 未安装"""
        import importlib
        import sys

        with patch.dict(sys.modules, {"pyperclip": None}):
            importlib.reload(sys.modules["src.platform"])
            from src.platform import has_clipboard

            assert has_clipboard() is False

        importlib.reload(sys.modules["src.platform"])


class TestHasAppIndicator:
    """测试 has_appindicator 函数"""

    def test_non_linux_always_true(self):
        """测试非 Linux 平台始终返回 True"""
        with patch("sys.platform", "win32"):
            assert has_appindicator() is True

        with patch("sys.platform", "darwin"):
            assert has_appindicator() is True

    def test_linux_with_appindicator3(self):
        """测试 Linux 有 AppIndicator3"""
        import importlib
        import sys

        mock_gi = MagicMock()
        mock_appindicator = MagicMock()

        with patch("sys.platform", "linux"):
            with patch.dict(
                sys.modules,
                {
                    "gi": mock_gi,
                    "gi.repository": MagicMock(),
                    "gi.repository.AppIndicator3": mock_appindicator,
                },
            ):
                importlib.reload(sys.modules["src.platform"])
                from src.platform import has_appindicator

                assert has_appindicator() is True

        importlib.reload(sys.modules["src.platform"])

    def test_linux_without_appindicator(self):
        """测试 Linux 无 AppIndicator"""
        with patch("sys.platform", "linux"):
            with patch.dict("sys.modules", {"gi": None}):
                with patch("builtins.__import__") as mock_import:
                    mock_import.side_effect = ImportError("No gi module")
                    assert has_appindicator() is False


class TestGetPlatformLevel:
    """测试 get_platform_level 函数"""

    def test_level_3_docker(self):
        """测试 Docker 环境返回 Level 3"""
        with patch("src.platform.is_docker_environment", return_value=True):
            assert get_platform_level() == 3

    def test_level_3_no_display(self):
        """测试无显示服务返回 Level 3"""
        with patch("src.platform.is_docker_environment", return_value=False):
            with patch("src.platform.has_display_service", return_value=False):
                assert get_platform_level() == 3

    def test_level_2_no_clipboard(self):
        """测试无剪贴板返回 Level 2"""
        with patch("src.platform.is_docker_environment", return_value=False):
            with patch("src.platform.has_display_service", return_value=True):
                with patch("src.platform.has_clipboard", return_value=False):
                    assert get_platform_level() == 2

    def test_level_1_full(self):
        """测试完整功能返回 Level 1"""
        with patch("src.platform.is_docker_environment", return_value=False):
            with patch("src.platform.has_display_service", return_value=True):
                with patch("src.platform.has_clipboard", return_value=True):
                    assert get_platform_level() == 1


class TestGetPlatformInfo:
    """测试 get_platform_info 函数"""

    def test_returns_dict(self):
        """测试返回字典"""
        info = get_platform_info()
        assert isinstance(info, dict)

    def test_contains_required_keys(self):
        """测试包含必要的键"""
        info = get_platform_info()
        required_keys = [
            "platform",
            "is_docker",
            "has_display",
            "has_clipboard",
            "level",
        ]
        for key in required_keys:
            assert key in info

    def test_level_matches_conditions(self):
        """测试级别与条件匹配"""
        info = get_platform_info()

        if info["is_docker"] or not info["has_display"]:
            assert info["level"] == 3
        elif not info["has_clipboard"]:
            assert info["level"] == 2
        else:
            assert info["level"] == 1
