"""日志弹窗模块"""
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from typing import Callable, Optional


class LogWindow:
    """日志弹窗窗口 - 文件驱动"""

    def __init__(self, get_logs_page: Callable[[int, int], tuple], title: str = "LLM-ROUTE 日志"):
        """
        Args:
            get_logs_page: 获取分页日志的回调函数，返回 (logs, total_pages, total_count)
            title: 窗口标题
        """
        self.get_logs_page = get_logs_page
        self.title = title
        self.window: Optional[tk.Tk] = None
        self.text_widget: Optional[scrolledtext.ScrolledText] = None
        self._running = False
        self._current_page = 1
        self._total_pages = 1
        self._total_count = 0
        self._page_label: Optional[tk.Label] = None
        self._last_line_count = 0  # 上次加载的行数
        self._auto_scroll = True  # 是否自动滚动到底部
        self._page_size = 100  # 每页行数
        self._page_size_var: Optional[tk.StringVar] = None

    def show(self):
        """显示日志窗口"""
        if self.window is not None:
            self.window.lift()
            return

        self.window = tk.Tk()
        self.window.title(self.title)
        self.window.geometry("900x550")

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

        # 监听滚动事件
        self.text_widget.bind('<MouseWheel>', self._on_user_scroll)
        self.text_widget.bind('<Button-4>', self._on_user_scroll)  # Linux
        self.text_widget.bind('<Button-5>', self._on_user_scroll)  # Linux

        # 分页框架
        page_frame = tk.Frame(self.window)
        page_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        # 上一页按钮
        self._prev_btn = tk.Button(
            page_frame,
            text="上一页",
            command=self._prev_page,
            width=8
        )
        self._prev_btn.pack(side=tk.LEFT, padx=5)

        # 页码显示
        self._page_label = tk.Label(page_frame, text="第 1 页 / 共 1 页 (共 0 条)")
        self._page_label.pack(side=tk.LEFT, padx=10)

        # 下一页按钮
        self._next_btn = tk.Button(
            page_frame,
            text="下一页",
            command=self._next_page,
            width=8
        )
        self._next_btn.pack(side=tk.LEFT, padx=5)

        # 跳转输入框
        tk.Label(page_frame, text="跳转到:").pack(side=tk.LEFT, padx=(15, 5))
        self._page_entry = tk.Entry(page_frame, width=6)
        self._page_entry.pack(side=tk.LEFT, padx=5)
        self._page_entry.bind('<Return>', self._goto_page)
        tk.Button(page_frame, text="跳转", command=self._goto_page, width=6).pack(side=tk.LEFT, padx=5)

        # 每页行数选择
        tk.Label(page_frame, text="每页行数:").pack(side=tk.LEFT, padx=(15, 5))
        self._page_size_var = tk.StringVar(value="100")
        page_size_combo = ttk.Combobox(
            page_frame,
            textvariable=self._page_size_var,
            values=["50", "100", "200", "500", "1000"],
            width=8,
            state="readonly"
        )
        page_size_combo.pack(side=tk.LEFT, padx=5)
        page_size_combo.bind('<<ComboboxSelected>>', self._on_page_size_change)

        # 按钮框架
        button_frame = tk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # 刷新按钮
        refresh_btn = tk.Button(
            button_frame,
            text="刷新",
            command=self._refresh
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)

        # 滚动到底部按钮
        scroll_btn = tk.Button(
            button_frame,
            text="滚动到底部",
            command=self._scroll_to_bottom
        )
        scroll_btn.pack(side=tk.LEFT, padx=5)

        # 复制当前页按钮
        copy_btn = tk.Button(
            button_frame,
            text="复制当前页",
            command=self._copy_page
        )
        copy_btn.pack(side=tk.LEFT, padx=5)

        # 关闭窗口时的处理
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动更新
        self._running = True
        self._load_page(1, initial=True)
        self._schedule_auto_refresh()

        # 运行主循环
        self.window.mainloop()

    def _on_page_size_change(self, event=None):
        """每页行数变更"""
        try:
            new_size = int(self._page_size_var.get())
            if new_size != self._page_size:
                self._page_size = new_size
                self._load_page(1)
        except ValueError:
            pass

    def _on_user_scroll(self, event=None):
        """用户滚动时检测是否在底部"""
        if self.text_widget is None:
            return
        # 延迟检测，等待滚动完成
        self.window.after(50, self._check_scroll_position)

    def _check_scroll_position(self):
        """检查滚动位置"""
        if self.text_widget is None:
            return
        yview = self.text_widget.yview()
        self._auto_scroll = (yview[1] >= 0.98)

    def _scroll_to_bottom(self):
        """滚动到底部"""
        if self.text_widget:
            self.text_widget.see(tk.END)
            self._auto_scroll = True

    def _schedule_auto_refresh(self):
        """调度自动刷新"""
        if not self._running or self.window is None:
            return

        try:
            # 如果在最后一页且开启了自动滚动，刷新
            if self._current_page == self._total_pages or self._total_pages == 1:
                self._update_new_logs()
        except Exception:
            pass

        # 每 2 秒自动刷新一次
        self.window.after(2000, self._schedule_auto_refresh)

    def _update_new_logs(self):
        """增量更新新日志（仅在最后一页时使用）"""
        if self.text_widget is None:
            return

        logs, total_pages, total_count = self.get_logs_page(self._current_page, self._page_size)
        self._total_pages = total_pages
        self._total_count = total_count

        # 计算新增的行数
        new_line_count = len(logs)
        if new_line_count > self._last_line_count:
            # 只追加新增的日志
            new_logs = logs[self._last_line_count:]
            if new_logs:
                self.text_widget.config(state=tk.NORMAL)
                for log in new_logs:
                    self.text_widget.insert(tk.END, log + "\n")
                self.text_widget.config(state=tk.DISABLED)

                # 如果自动滚动，滚动到底部
                if self._auto_scroll:
                    self.text_widget.see(tk.END)

            self._last_line_count = new_line_count

        # 更新页码显示
        self._page_label.config(text=f"第 {self._current_page} 页 / 共 {total_pages} 页 (共 {total_count} 条)")

        # 更新按钮状态
        self._prev_btn.config(state=tk.NORMAL if self._current_page > 1 else tk.DISABLED)
        self._next_btn.config(state=tk.NORMAL if self._current_page < total_pages else tk.DISABLED)

    def _load_page(self, page: int, initial: bool = False):
        """加载指定页"""
        if self.text_widget is None:
            return

        logs, total_pages, total_count = self.get_logs_page(page, self._page_size)
        self._current_page = page
        self._total_pages = total_pages
        self._total_count = total_count
        self._last_line_count = len(logs)

        # 更新文本
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", "\n".join(logs))
        self.text_widget.config(state=tk.DISABLED)

        # 如果是最后一页或初始加载，滚动到底部
        if page == self._total_pages or initial:
            self.text_widget.see(tk.END)
            self._auto_scroll = True

        # 更新页码显示
        self._page_label.config(text=f"第 {page} 页 / 共 {total_pages} 页 (共 {total_count} 条)")

        # 更新按钮状态
        self._prev_btn.config(state=tk.NORMAL if page > 1 else tk.DISABLED)
        self._next_btn.config(state=tk.NORMAL if page < total_pages else tk.DISABLED)

    def _prev_page(self):
        """上一页"""
        if self._current_page > 1:
            self._auto_scroll = False
            self._load_page(self._current_page - 1)

    def _next_page(self):
        """下一页"""
        if self._current_page < self._total_pages:
            self._load_page(self._current_page + 1)

    def _goto_page(self, event=None):
        """跳转到指定页"""
        try:
            page = int(self._page_entry.get().strip())
            if 1 <= page <= self._total_pages:
                self._auto_scroll = (page == self._total_pages)
                self._load_page(page)
                self._page_entry.delete(0, tk.END)
            else:
                messagebox.showwarning("提示", f"页码必须在 1-{self._total_pages} 之间")
        except ValueError:
            messagebox.showwarning("提示", "请输入有效的页码")

    def _refresh(self):
        """刷新当前页"""
        self._load_page(self._current_page)

    def _copy_page(self):
        """复制当前页日志"""
        if self.text_widget is None:
            return

        content = self.text_widget.get("1.0", tk.END)
        self.window.clipboard_clear()
        self.window.clipboard_append(content)
        messagebox.showinfo("提示", "当前页日志已复制到剪贴板")

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


def show_log_window(get_logs_page: Callable[[int, int], tuple], title: str = "LLM-ROUTE 日志"):
    """显示日志窗口（便捷函数）"""
    window = LogWindow(get_logs_page, title)
    window.show()
