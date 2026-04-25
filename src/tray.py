"""系统托盘模块"""
import sys
import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from src.log_window import show_log_window
from src.autostart import AutoStartManager
from src.platform import get_platform_level


class TrayManager:
    """系统托盘管理器"""

    def __init__(
        self,
        proxy_server,
        log_manager,
        on_exit: Callable[[], None],
        on_port_change: Callable[[int], None],
        on_toggle_service: Callable[[], None],
        on_preset_change: Callable[[str], None],
        on_log_level_change: Callable[[int], None],
        config_path: str
    ):
        """
        Args:
            proxy_server: ProxyServer 实例
            log_manager: LogManager 实例
            on_exit: 退出回调
            on_port_change: 端口变更回调
            on_toggle_service: 切换服务状态回调
            on_preset_change: 预设变更回调
            on_log_level_change: 日志等级变更回调
            config_path: 配置文件路径
        """
        self.proxy_server = proxy_server
        self.log_manager = log_manager
        self.on_exit = on_exit
        self.on_port_change = on_port_change
        self.on_toggle_service = on_toggle_service
        self.on_preset_change = on_preset_change
        self.on_log_level_change = on_log_level_change
        self.config_path = config_path
        self.tray: Optional[pystray.Icon] = None
        self._autostart_manager = AutoStartManager()
        self._auto_start = self._autostart_manager.is_enabled()
        self._current_preset = self._detect_current_preset()
        self._platform_level = get_platform_level()

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
        # 构建预设子菜单
        preset_items = self._create_preset_menu_items()
        # 构建日志等级子菜单
        log_level_items = self._create_log_level_menu_items()

        menu_items = [
            pystray.MenuItem(
                self._get_status_text,
                lambda icon: None
            ),
            pystray.Menu.SEPARATOR,
        ]

        # Level 1 (完整功能): 所有功能可用
        if self._platform_level == 1:
            menu_items.extend([
                pystray.MenuItem(
                    "复制代理地址",
                    self._copy_address
                ),
            ])

        menu_items.extend([
            pystray.MenuItem(
                "日志详情",
                self._show_logs
            ),
            pystray.MenuItem(
                "日志等级",
                pystray.Menu(*log_level_items)
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
                "加载预设",
                pystray.Menu(*preset_items) if preset_items else None
            ),
        ])

        # 开机自启选项仅在支持的平台显示
        if self._autostart_manager.is_supported():
            menu_items.extend([
                pystray.MenuItem(
                    self._get_autostart_text,
                    self._toggle_auto_start
                ),
            ])

        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._quit
            )
        ])

        return pystray.Menu(*menu_items)

    def _create_preset_menu_items(self) -> list:
        """创建预设菜单项"""
        from src.config import list_presets

        items = []
        presets = list_presets()

        for name, preset_path in presets:
            # 显示名称，当前预设带勾
            display_name = name + (" ✓" if name == self._current_preset else "")
            # 创建一个闭包来捕获参数
            def make_callback(n, p):
                def callback(icon, item):
                    self._load_preset(n, p)
                return callback
            items.append(
                pystray.MenuItem(
                    display_name,
                    make_callback(name, preset_path)
                )
            )

        if not items:
            items.append(pystray.MenuItem("(无预设)", self._noop))

        return items

    def _create_log_level_menu_items(self) -> list:
        """创建日志等级菜单项"""
        levels = [
            (1, "基础信息"),
            (2, "详细信息"),
            (3, "完整信息")
        ]

        items = []
        current_level = self.log_manager.get_level()

        for level, name in levels:
            display_name = name + (" ✓" if level == current_level else "")
            def make_callback(l):
                def callback(icon, item):
                    self._set_log_level(l)
                return callback
            items.append(
                pystray.MenuItem(
                    display_name,
                    make_callback(level)
                )
            )

        return items

    def _set_log_level(self, level: int):
        """设置日志等级"""
        self.log_manager.set_level(level)
        self.on_log_level_change(level)
        self._update_menu()

    def _noop(self, icon, item):
        """空操作回调"""
        pass

    def _detect_current_preset(self) -> Optional[str]:
        """检测当前使用的是哪个预设"""
        from src.config import list_presets, load_config

        try:
            current_config = load_config(self.config_path)
            presets = list_presets()

            for name, preset_path in presets:
                with open(preset_path, "r", encoding="utf-8") as f:
                    preset_data = __import__('yaml').safe_load(f) or {}

                # 比较 upstreams 和 routes
                if (preset_data.get("upstreams") == {k: {"url": v.url, "protocol": v.protocol}
                                                      for k, v in current_config.upstreams.items()}
                    and preset_data.get("routes") == [{"path": r.path, "upstream": r.upstream}
                                                      for r in current_config.routes]):
                    return name
        except Exception:
            pass
        return None

    def _load_preset(self, name: str, preset_path):
        """加载预设"""
        from src.config import apply_preset

        if name == self._current_preset:
            return  # 已经是当前预设

        if apply_preset(preset_path, self.config_path):
            self._current_preset = name
            self.on_preset_change(name)
            self._update_menu()

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
        return "开机自启" + (" ✓" if self._auto_start else "")

    def _copy_address(self):
        """复制代理地址"""
        port = self.proxy_server.config.port
        address = f"http://127.0.0.1:{port}"

        # 使用 pyperclip 复制到剪贴板
        try:
            import pyperclip
            pyperclip.copy(address)
        except Exception:
            pass  # 剪贴板不可用时静默失败

    def _show_logs(self):
        """显示日志窗口"""
        def show():
            show_log_window(self.proxy_server.get_logs_page)

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
        if self._autostart_manager.is_enabled():
            success = self._autostart_manager.disable()
        else:
            success = self._autostart_manager.enable()

        # 无论成功与否，重新查询实际状态以保持同步
        self._auto_start = self._autostart_manager.is_enabled()
        self._update_menu()

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
