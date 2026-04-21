"""系统托盘模块"""
import sys
import subprocess
from pathlib import Path
from typing import Callable, Optional
import threading

import pystray
from PIL import Image, ImageDraw

from src.log_window import show_log_window


class TrayManager:
    """系统托盘管理器"""

    def __init__(
        self,
        proxy_server,
        on_exit: Callable[[], None],
        on_port_change: Callable[[int], None],
        on_toggle_service: Callable[[], None]
    ):
        """
        Args:
            proxy_server: ProxyServer 实例
            on_exit: 退出回调
            on_port_change: 端口变更回调
            on_toggle_service: 切换服务状态回调
        """
        self.proxy_server = proxy_server
        self.on_exit = on_exit
        self.on_port_change = on_port_change
        self.on_toggle_service = on_toggle_service
        self.tray: Optional[pystray.Icon] = None
        self._is_running = False
        self._auto_start = self._check_auto_start()

    def _create_icon(self) -> Image.Image:
        """创建托盘图标"""
        # 创建一个简单的图标（绿色圆形表示运行）
        width = 64
        height = 64
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 画一个绿色圆形
        margin = 8
        draw.ellipse(
            [margin, margin, width - margin, height - margin],
            fill=(76, 175, 80, 255),  # 绿色
            outline=(56, 142, 60, 255),
            width=2
        )

        return image

    def _create_menu(self) -> pystray.Menu:
        """创建托盘菜单"""
        return pystray.Menu(
            pystray.MenuItem(
                self._get_status_text,
                lambda icon: None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "复制代理地址",
                self._copy_address
            ),
            pystray.MenuItem(
                "日志详情",
                self._show_logs
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                self._get_service_text,
                self._toggle_service
            ),
            pystray.MenuItem(
                "更换端口...",
                self._change_port
            ),
            pystray.MenuItem(
                self._get_autostart_text,
                self._toggle_auto_start
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._quit
            )
        )

    def _get_status_text(self, icon) -> str:
        """获取状态文本"""
        # 根据服务器实际状态判断
        is_running = self.proxy_server.runner is not None
        if is_running:
            port = self.proxy_server.config.port
            return f"● 服务运行中 :{port}"
        return "○ 服务已停止"

    def _get_service_text(self, icon) -> str:
        """获取服务状态文本"""
        is_running = self.proxy_server.runner is not None
        return "停止服务" if is_running else "启动服务"

    def _get_autostart_text(self, icon) -> str:
        """获取开机自启文本"""
        return ("✓ " if self._auto_start else "  ") + "开机自启"

    def _copy_address(self):
        """复制代理地址"""
        port = self.proxy_server.config.port
        address = f"http://127.0.0.1:{port}"

        # 使用 pyperclip 复制到剪贴板
        import pyperclip
        pyperclip.copy(address)

    def _show_logs(self):
        """显示日志窗口"""
        def show():
            show_log_window(self.proxy_server.get_logs)

        thread = threading.Thread(target=show, daemon=True)
        thread.start()

    def _toggle_service(self):
        """切换服务状态"""
        # 使用回调函数，由主线程的事件循环处理
        self.on_toggle_service()
        # 更新菜单显示
        self._update_menu()

    def _change_port(self):
        """更换端口"""
        import tkinter as tk
        from tkinter import simpledialog, messagebox

        def ask_port():
            root = tk.Tk()
            root.withdraw()

            current_port = self.proxy_server.config.port

            # 创建自定义对话框
            dialog = tk.Toplevel(root)
            dialog.title("更换端口")
            dialog.geometry("300x120")
            dialog.resizable(False, False)

            tk.Label(dialog, text="请输入新端口号（1-65535）：").pack(pady=10)

            port_var = tk.StringVar(value=str(current_port))
            entry = tk.Entry(dialog, textvariable=port_var, width=20)
            entry.pack(pady=5)
            entry.select_range(0, tk.END)
            entry.focus()

            result = {"port": None}

            def on_ok():
                try:
                    port_str = port_var.get().strip()
                    if port_str.lower() == "auto":
                        result["port"] = "auto"
                        dialog.destroy()
                    else:
                        port = int(port_str)
                        if 1 <= port <= 65535:
                            result["port"] = port
                            dialog.destroy()
                        else:
                            messagebox.showerror("错误", "端口必须在 1-65535 之间")
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的端口号")

            def on_auto():
                result["port"] = "auto"
                dialog.destroy()

            btn_frame = tk.Frame(dialog)
            btn_frame.pack(pady=10)

            tk.Button(btn_frame, text="确定", command=on_ok, width=8).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="自动分配", command=on_auto, width=8).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="取消", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=5)

            dialog.wait_window()
            root.destroy()

            return result["port"]

        new_port = ask_port()
        if new_port is not None:
            self.on_port_change(new_port)
            self._update_menu()

    def _toggle_auto_start(self):
        """切换开机自启"""
        self._auto_start = not self._auto_start
        self._set_auto_start(self._auto_start)
        self._update_menu()

    def _check_auto_start(self) -> bool:
        """检查是否已设置开机自启"""
        if sys.platform == "win32":
            import winreg
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_READ
                )
                winreg.QueryValueEx(key, "LLM-ROUTE")
                winreg.CloseKey(key)
                return True
            except WindowsError:
                return False
        return False

    def _set_auto_start(self, enable: bool):
        """设置开机自启"""
        if sys.platform == "win32":
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    key_path,
                    0,
                    winreg.KEY_WRITE
                )

                if enable:
                    exe_path = sys.executable
                    winreg.SetValueEx(key, "LLM-ROUTE", 0, winreg.REG_SZ, f'"{exe_path}"')
                else:
                    try:
                        winreg.DeleteValue(key, "LLM-ROUTE")
                    except WindowsError:
                        pass

                winreg.CloseKey(key)
            except WindowsError as e:
                print(f"设置开机自启失败: {e}")

    def _update_menu(self):
        """更新菜单"""
        if self.tray:
            self.tray.menu = self._create_menu()

    def _quit(self):
        """退出程序"""
        self.on_exit()
        if self.tray:
            self.tray.stop()

    def run(self):
        """运行托盘"""
        self._is_running = True

        icon = self._create_icon()
        menu = self._create_menu()

        self.tray = pystray.Icon(
            "llm-route",
            icon,
            "LLM-ROUTE",
            menu
        )

        self.tray.run()

    def stop(self):
        """停止托盘"""
        if self.tray:
            self.tray.stop()
