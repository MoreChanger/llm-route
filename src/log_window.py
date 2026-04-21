"""日志弹窗模块"""
import tkinter as tk
from tkinter import scrolledtext, messagebox
from typing import Callable, Optional
import queue
import threading


class LogWindow:
    """日志弹窗窗口"""

    def __init__(self, get_logs: Callable[[], list[str]], title: str = "LLM-ROUTE 日志"):
        """
        Args:
            get_logs: 获取日志列表的回调函数
            title: 窗口标题
        """
        self.get_logs = get_logs
        self.title = title
        self.window: Optional[tk.Tk] = None
        self.text_widget: Optional[scrolledtext.ScrolledText] = None
        self._update_thread: Optional[threading.Thread] = None
        self._running = False
        self._update_queue: queue.Queue = queue.Queue()

    def show(self):
        """显示日志窗口"""
        if self.window is not None:
            self.window.lift()
            return

        self.window = tk.Tk()
        self.window.title(self.title)
        self.window.geometry("800x500")

        # 创建文本框
        self.text_widget = scrolledtext.ScrolledText(
            self.window,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white"
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 按钮框架
        button_frame = tk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # 复制全部按钮
        copy_btn = tk.Button(
            button_frame,
            text="复制全部",
            command=self._copy_all
        )
        copy_btn.pack(side=tk.LEFT, padx=5)

        # 清空按钮
        clear_btn = tk.Button(
            button_frame,
            text="清空",
            command=self._clear
        )
        clear_btn.pack(side=tk.LEFT, padx=5)

        # 关闭窗口时的处理
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动更新
        self._running = True
        self._schedule_update()

        # 运行主循环
        self.window.mainloop()

    def _schedule_update(self):
        """调度日志更新"""
        if not self._running or self.window is None:
            return

        try:
            logs = self.get_logs()
            if logs:
                self._update_text(logs)
        except Exception:
            pass

        # 每 500ms 更新一次
        self.window.after(500, self._schedule_update)

    def _update_text(self, logs: list[str]):
        """更新文本框内容"""
        if self.text_widget is None:
            return

        current = self.text_widget.get("1.0", tk.END).strip()
        new_content = "\n".join(logs)

        if current != new_content:
            self.text_widget.config(state=tk.NORMAL)
            self.text_widget.delete("1.0", tk.END)
            self.text_widget.insert("1.0", new_content)
            self.text_widget.see(tk.END)
            self.text_widget.config(state=tk.DISABLED)

    def _copy_all(self):
        """复制全部日志"""
        if self.text_widget is None:
            return

        content = self.text_widget.get("1.0", tk.END)
        self.window.clipboard_clear()
        self.window.clipboard_append(content)
        messagebox.showinfo("提示", "日志已复制到剪贴板")

    def _clear(self):
        """清空日志显示"""
        if self.text_widget is None:
            return

        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.config(state=tk.DISABLED)

    def _on_close(self):
        """关闭窗口"""
        self._running = False
        if self.window:
            self.window.destroy()
            self.window = None
            self.text_widget = None

    def close(self):
        """从外部关闭窗口"""
        self._on_close()


def show_log_window(get_logs: Callable[[], list[str]], title: str = "LLM-ROUTE 日志"):
    """显示日志窗口（便捷函数）"""
    window = LogWindow(get_logs, title)
    window.show()
