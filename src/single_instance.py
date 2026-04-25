"""单实例锁模块"""
import os
import sys
from pathlib import Path
from typing import Optional


class SingleInstanceLock:
    """单实例锁 - 确保程序只有一个实例运行"""

    def __init__(self, app_name: str = "llm-route"):
        """
        Args:
            app_name: 应用名称，用于锁文件名
        """
        self.app_name = app_name
        self._lock_file: Optional[object] = None
        self._lock_path: Optional[Path] = None

    def _get_lock_path(self) -> Path:
        """获取锁文件路径 - 放在程序目录"""
        # 优先使用可执行文件同目录
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent.parent

        return base_dir / f".{self.app_name}.lock"

    def _is_process_running(self, pid: int) -> bool:
        """检查指定 PID 的进程是否还在运行"""
        if sys.platform == "win32":
            import ctypes
            # 使用 Windows API 检查进程是否存在
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259

            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                try:
                    exit_code = ctypes.c_ulong()
                    if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return exit_code.value == STILL_ACTIVE
                finally:
                    kernel32.CloseHandle(handle)
            return False
        else:
            # Linux/macOS: 发送信号 0 检查进程是否存在
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

    def acquire(self) -> bool:
        """尝试获取锁

        Returns:
            True 表示获取成功（可以启动），False 表示已有实例在运行
        """
        self._lock_path = self._get_lock_path()

        # 检查锁文件是否存在
        if self._lock_path.exists():
            try:
                # 读取 PID
                with open(self._lock_path, "r") as f:
                    content = f.read().strip()

                if content:
                    old_pid = int(content)
                    # 检查该进程是否还在运行
                    if self._is_process_running(old_pid):
                        # 进程还在运行，拒绝启动
                        return False
                    else:
                        # 进程已退出，删除残留锁文件
                        self._lock_path.unlink()
            except (ValueError, IOError):
                # 锁文件损坏，删除它
                try:
                    self._lock_path.unlink()
                except Exception:
                    pass

        # 创建锁文件
        try:
            # 写入当前 PID
            with open(self._lock_path, "w") as f:
                f.write(str(os.getpid()))
            return True
        except IOError:
            # 无法创建锁文件，允许启动（降级处理）
            return True

    def release(self):
        """释放锁"""
        if self._lock_path and self._lock_path.exists():
            try:
                self._lock_path.unlink()
            except Exception:
                pass

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动释放锁"""
        self.release()
        return False
