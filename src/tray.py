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
        self._auto_start = self._check_auto_start()

    def _create_icon(self, is_running: bool = True) -> Image.Image:
        """创建托盘图标

        Args:
            is_running: 服务是否运行中
        """
        width = 64
        height = 64
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        margin = 8

        if is_running:
            # 绿色 - 服务运行中
            fill_color = (76, 175, 80, 255)    # 绿色
            outline_color = (56, 142, 60, 255) # 深绿边框
        else:
            # 红色 - 服务已停止
            fill_color = (244, 67, 54, 255)    # 红色
            outline_color = (198, 40, 40, 255) # 深红边框

        draw.ellipse(
            [margin, margin, width - margin, height - margin],
            fill=fill_color,
            outline=outline_color,
            width=2
        )

        return image

    def _update_icon(self):
        """根据服务状态更新图标"""
        if self.tray:
            is_running = self.proxy_server.runner is not None
            new_icon = self._create_icon(is_running)
            self.tray.icon = new_icon

    def _create_menu(self) -> pystray.Menu:
        """创建托盘菜单"""
        return pystray.Menu(
            pystray.MenuItem(
                self._get_status_text,
                lambda icon: None
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
        port = self.proxy_server.config.port
        if is_running:
            return f"[运行中] :{port}"
        return "[已停止]"

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
        # 先获取当前状态（切换前）
        was_running = self.proxy_server.runner is not None
        # 使用回调函数，由主线程的事件循环处理
        self.on_toggle_service()
        # 延迟更新菜单，等待服务状态改变
        if self.tray:
            import threading
            # 延迟 500ms 后更新，给服务足够时间启动/停止
            threading.Timer(0.5, self._update_menu).start()

    def _change_port(self):
        """更换端口"""
        from src.port import is_port_available

        result = {"port": None}

        def show_dialog():
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.title("更换端口")
            root.geometry("320x130")
            root.resizable(False, False)

            # 确保窗口在最前面
            root.attributes('-topmost', True)
            root.focus_force()

            current_port = self.proxy_server.config.port

            tk.Label(root, text="请输入新端口号（1-65535）：").pack(pady=15)

            port_var = tk.StringVar(value=str(current_port))
            entry = tk.Entry(root, textvariable=port_var, width=25)
            entry.pack(pady=5)
            entry.select_range(0, tk.END)
            entry.focus_set()

            def on_ok(event=None):
                try:
                    port_str = port_var.get().strip()
                    if port_str.lower() == "auto":
                        result["port"] = "auto"
                        root.destroy()
                    else:
                        port = int(port_str)
                        if not (1 <= port <= 65535):
                            messagebox.showerror("错误", "端口必须在 1-65535 之间", parent=root)
                            return

                        # 检测端口是否可用
                        if not is_port_available(self.proxy_server.config.host, port):
                            messagebox.showerror("错误", f"端口 {port} 已被占用，请选择其他端口", parent=root)
                            return

                        result["port"] = port
                        root.destroy()
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的端口号", parent=root)

            def on_auto():
                result["port"] = "auto"
                root.destroy()

            def on_cancel():
                root.destroy()

            # 绑定回车键
            entry.bind('<Return>', on_ok)

            btn_frame = tk.Frame(root)
            btn_frame.pack(pady=15)

            tk.Button(btn_frame, text="确定", command=on_ok, width=8).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="自动分配", command=on_auto, width=8).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="取消", command=on_cancel, width=8).pack(side=tk.LEFT, padx=5)

            # 运行主循环
            root.mainloop()

        # 在新线程中运行对话框
        thread = threading.Thread(target=show_dialog, daemon=False)
        thread.start()
        thread.join(timeout=30)  # 等待对话框关闭

        if result["port"] is not None:
            self.on_port_change(result["port"])
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
        """更新菜单和图标"""
        if self.tray:
            # 更新图标颜色
            self._update_icon()
            # 完全替换菜单来强制刷新
            self.tray.menu = self._create_menu()
            self.tray.update_menu()

    def _quit(self):
        """退出程序"""
        self.on_exit()
        if self.tray:
            self.tray.stop()

    def run(self):
        """运行托盘"""
        # 托盘启动时服务应该已经在运行（由 main.py 先启动服务）
        # 默认创建绿色图标，后续通过 _update_menu 更新
        is_running = self.proxy_server.runner is not None
        icon = self._create_icon(is_running)
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
