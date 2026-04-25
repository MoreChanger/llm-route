"""日志文件管理模块

特性：
- 日志文件大小限制 + 自动滚动
- 行偏移索引 + seek 高效分页
- 自动压缩过期日志
- 异步日志写入
- 结构化日志支持
"""

import gzip
import json
import queue
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any


# 敏感头字段列表（小写）
SENSITIVE_HEADERS = {"authorization", "x-api-key"}

# 默认配置
DEFAULT_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_COMPRESS_AFTER_DAYS = 1  # 1天后压缩
DEFAULT_FLUSH_INTERVAL = 1.0  # 异步写入刷新间隔（秒）


def sanitize_sensitive_content(content: str) -> str:
    """过滤敏感头字段值

    将 Authorization 和 x-api-key 头字段的值替换为 [REDACTED]。

    Args:
        content: 原始内容字符串

    Returns:
        过滤后的内容字符串
    """
    if not content:
        return content

    # 匹配 JSON 格式的敏感头
    def redact_json_header(match: re.Match) -> str:
        header_name = match.group(1)
        return f'"{header_name}": "[REDACTED]"'

    # JSON 格式（带引号）
    json_pattern = r'"(authorization|x-api-key)":\s*"[^"]*"'
    result = re.sub(json_pattern, redact_json_header, content, flags=re.IGNORECASE)

    # 匹配 HTTP 头格式
    def redact_http_header(match: re.Match) -> str:
        header_name = match.group(1)
        return f"{header_name}: [REDACTED]"

    # HTTP 头格式
    http_pattern = r'\b(Authorization|x-api-key):\s*[^\n\]\[{}"]+'
    result = re.sub(http_pattern, redact_http_header, result, flags=re.IGNORECASE)

    return result


class AsyncLogWriter:
    """异步日志写入器

    使用后台线程批量写入日志，减少 I/O 阻塞。
    """

    def __init__(self, flush_interval: float = DEFAULT_FLUSH_INTERVAL):
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._flush_interval = flush_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._buffer: list[str] = []
        self._log_file: Optional[Any] = None
        self._lock = threading.Lock()

    def start(self, log_file):
        """启动异步写入器"""
        self._log_file = log_file
        self._running = True
        self._thread = threading.Thread(target=self._write_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止异步写入器"""
        if not self._running:
            return

        self._running = False
        # 发送停止信号
        self._queue.put(None)
        # 等待线程结束
        if self._thread:
            self._thread.join(timeout=5)
        # 写入剩余缓冲
        self._flush_buffer()

    def write(self, line: str):
        """添加日志到写入队列"""
        if self._running:
            self._queue.put(line)

    def _write_loop(self):
        """后台写入循环"""
        while self._running:
            try:
                # 批量获取日志行
                deadline = time.time() + self._flush_interval
                while time.time() < deadline:
                    try:
                        line = self._queue.get(timeout=0.1)
                        if line is None:
                            # 停止信号
                            self._flush_buffer()
                            return
                        self._buffer.append(line)
                    except queue.Empty:
                        if self._buffer:
                            break
                        continue

                # 刷新缓冲
                if self._buffer:
                    self._flush_buffer()

            except Exception:
                pass

    def _flush_buffer(self):
        """刷新缓冲到文件"""
        if not self._buffer or not self._log_file:
            return

        with self._lock:
            try:
                for line in self._buffer:
                    self._log_file.write(line + "\n")
                self._log_file.flush()
            except Exception:
                pass
            self._buffer.clear()

    def flush(self):
        """立即刷新缓冲"""
        # 清空队列
        while True:
            try:
                line = self._queue.get_nowait()
                if line is not None:
                    self._buffer.append(line)
            except queue.Empty:
                break
        self._flush_buffer()


class LogManager:
    """日志管理器

    功能：
    - 日志文件大小限制 + 自动滚动
    - 行偏移索引 + seek 高效分页
    - 自动压缩过期日志
    - 异步日志写入
    - 结构化日志支持
    """

    def __init__(self):
        self._log_file: Optional[Any] = None
        self._log_path: Optional[Path] = None
        self._lock = threading.Lock()
        self._log_level: int = 2
        self._log_retention_days: int = 7
        self._max_log_size: int = DEFAULT_MAX_LOG_SIZE
        self._line_count: int = 0
        self._current_size: int = 0
        self._line_offsets: list[int] = []
        self._base_timestamp: str = ""

        # 结构化日志开关
        self._structured_logging: bool = False

        # 异步写入器
        self._async_writer: Optional[AsyncLogWriter] = None

    def get_logs_dir(self) -> Path:
        """获取日志目录路径"""
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent.parent
        return base_dir / "logs"

    def start(
        self,
        log_level: int = 2,
        log_retention_days: int = 7,
        structured_logging: bool = False,
    ) -> Path:
        """启动日志管理器

        Args:
            log_level: 日志等级 (1=基础, 2=详细, 3=完整)
            log_retention_days: 日志保留天数
            structured_logging: 是否使用结构化日志 (JSON格式)

        Returns:
            日志文件路径
        """
        self._log_level = log_level
        self._log_retention_days = log_retention_days
        self._structured_logging = structured_logging

        # 创建日志目录
        logs_dir = self.get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 创建日志文件
        self._base_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = logs_dir / f"{self._base_timestamp}.log"
        self._log_file = open(self._log_path, "w", encoding="utf-8")
        self._line_count = 0
        self._current_size = 0
        self._line_offsets = [0]

        # 启动异步写入器
        self._async_writer = AsyncLogWriter()
        self._async_writer.start(self._log_file)

        # 清理过期日志（包括压缩旧的日志）
        self._cleanup_old_logs()

        return self._log_path

    def _rotate_log_file(self):
        """滚动日志文件"""
        if self._async_writer:
            self._async_writer.flush()
        if self._log_file:
            self._log_file.close()

        # 创建新的滚动文件
        logs_dir = self.get_logs_dir()
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = logs_dir / f"{self._base_timestamp}_{timestamp}.log"
        self._log_file = open(self._log_path, "w", encoding="utf-8")
        self._line_count = 0
        self._current_size = 0
        self._line_offsets = [0]

        # 更新异步写入器的文件引用
        if self._async_writer:
            self._async_writer._log_file = self._log_file

    def _cleanup_old_logs(self):
        """清理过期的日志文件（包括压缩）"""
        if self._log_retention_days <= 0:
            return

        logs_dir = self.get_logs_dir()
        if not logs_dir.exists():
            return

        cutoff_date = datetime.now() - timedelta(days=self._log_retention_days)
        compress_date = datetime.now() - timedelta(days=DEFAULT_COMPRESS_AFTER_DAYS)

        # 处理普通日志文件
        for log_file in logs_dir.glob("*.log"):
            if self._log_path and log_file == self._log_path:
                continue

            try:
                filename = log_file.stem
                # 处理滚动文件名 (YYYY-MM-DD_HH-MM-SS_HH-MM-SS)
                base_name = filename.split("_")[0] + "_" + filename.split("_")[1]
                file_date = datetime.strptime(base_name, "%Y-%m-%d_%H-%M-%S")

                if file_date < cutoff_date:
                    # 删除过期文件
                    log_file.unlink()
                    self._print_safe(f"已清理过期日志: {log_file.name}")
                elif file_date < compress_date:
                    # 压缩旧文件
                    self._compress_log_file(log_file)
            except (ValueError, OSError):
                pass

        # 处理压缩文件
        for gz_file in logs_dir.glob("*.log.gz"):
            try:
                # 从文件名解析日期
                filename = gz_file.stem  # 去掉 .gz
                base_name = filename.split("_")[0] + "_" + filename.split("_")[1]
                file_date = datetime.strptime(base_name, "%Y-%m-%d_%H-%M-%S")

                if file_date < cutoff_date:
                    gz_file.unlink()
                    self._print_safe(f"已清理过期压缩日志: {gz_file.name}")
            except (ValueError, OSError):
                pass

    def _compress_log_file(self, log_file: Path):
        """压缩日志文件"""
        if not log_file.exists():
            return

        gz_path = log_file.with_suffix(log_file.suffix + ".gz")

        try:
            with open(log_file, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    f_out.writelines(f_in)

            log_file.unlink()
            self._print_safe(f"已压缩日志: {log_file.name} -> {gz_path.name}")
        except Exception:
            pass

    def _print_safe(self, message: str):
        """安全打印（忽略编码错误）"""
        try:
            print(message)
        except (UnicodeEncodeError, OSError):
            pass

    def stop(self):
        """停止日志管理器"""
        # 停止异步写入器
        if self._async_writer:
            self._async_writer.stop()
            self._async_writer = None

        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def set_level(self, level: int):
        """设置日志等级"""
        self._log_level = level

    def get_level(self) -> int:
        """获取当前日志等级"""
        return self._log_level

    def get_level_name(self) -> str:
        """获取日志等级名称"""
        names = {1: "基础信息", 2: "详细信息", 3: "完整信息"}
        return names.get(self._log_level, "详细信息")

    def get_log_path(self) -> Optional[Path]:
        """获取当前日志文件路径"""
        return self._log_path

    def log(self, message: str, level: str = "INFO", **extra: Any):
        """记录日志

        Args:
            message: 日志内容
            level: 日志级别（INFO、ERROR等）
            **extra: 额外的结构化字段
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        if self._structured_logging:
            # 结构化日志 (JSON)
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                **extra,
            }
            log_line = json.dumps(log_entry, ensure_ascii=False)
        else:
            # 传统格式
            log_line = f"[{timestamp}] {level:5} {message}"

        with self._lock:
            # 检查是否需要滚动
            line_size = len(log_line.encode("utf-8")) + 1
            if (
                self._current_size + line_size > self._max_log_size
                and self._current_size > 0
            ):
                self._rotate_log_file()

            if self._log_file:
                # 记录行偏移
                self._line_offsets.append(self._current_size)

                # 异步写入
                if self._async_writer:
                    self._async_writer.write(log_line)

                self._line_count += 1
                self._current_size += line_size

        # 控制台输出
        self._print_safe(log_line)

    def log_request(
        self,
        method: str,
        path: str,
        upstream: str,
        status_code: int,
        elapsed_ms: float,
        retries: int = 0,
        request_body: str = "",
        response_body: str = "",
    ):
        """记录请求日志

        Args:
            method: HTTP 方法
            path: 请求路径
            upstream: 上游服务名称
            status_code: 响应状态码
            elapsed_ms: 请求耗时（毫秒）
            retries: 重试次数
            request_body: 请求体
            response_body: 响应体
        """
        # 过滤敏感头字段
        request_body = sanitize_sensitive_content(request_body)
        response_body = sanitize_sensitive_content(response_body)

        if self._structured_logging:
            # 结构化日志
            self.log(
                f"{method} {path}",
                level="INFO",
                method=method,
                path=path,
                upstream=upstream,
                status_code=status_code,
                elapsed_ms=round(elapsed_ms, 2),
                retries=retries,
            )
            if self._log_level == 3:
                if request_body:
                    self.log("request body", level="DEBUG", body=request_body)
                if response_body:
                    self.log("response body", level="DEBUG", body=response_body)
        else:
            # 传统格式
            if self._log_level == 1:
                self.log(f"{method} {path} -> {upstream} [{status_code}]")
            elif self._log_level == 2:
                retry_str = f" (重试{retries}次)" if retries > 0 else ""
                self.log(
                    f"{method} {path} -> {upstream} [{status_code}] {elapsed_ms:.0f}ms{retry_str}"
                )
            else:
                retry_str = f" (重试{retries}次)" if retries > 0 else ""
                self.log(
                    f"{method} {path} -> {upstream} [{status_code}] {elapsed_ms:.0f}ms{retry_str}"
                )
                if request_body:
                    self.log(f"  请求: {request_body}")
                if response_body:
                    self.log(f"  响应: {response_body}")

    def get_line_count(self) -> int:
        """获取日志文件总行数"""
        with self._lock:
            if self._async_writer:
                self._async_writer.flush()
            return len(self._line_offsets)

    def get_logs_page(
        self, page: int, page_size: int = 100
    ) -> tuple[list[str], int, int]:
        """从文件获取分页日志（使用 seek 优化）

        Args:
            page: 页码（从1开始）
            page_size: 每页行数

        Returns:
            (当前页日志, 总页数, 总行数)
        """
        if not self._log_path or not self._log_path.exists():
            return [], 1, 0

        with self._lock:
            # 刷新写入缓冲
            if self._async_writer:
                self._async_writer.flush()

            total = len(self._line_offsets)

            # 如果索引不完整，重新构建
            if total == 0 or self._line_offsets[-1] < self._current_size - 1000:
                self._rebuild_line_index()
                total = len(self._line_offsets)

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            page = max(1, min(page, total_pages))
            start_line = (page - 1) * page_size
            end_line = min(start_line + page_size, total)

            if start_line >= total:
                return [], total_pages, total

            # 使用 seek 定位
            with open(self._log_path, "r", encoding="utf-8") as f:
                start_offset = self._line_offsets[start_line]
                f.seek(start_offset)

                logs = []
                for _ in range(start_line, end_line):
                    line = f.readline()
                    if not line:
                        break
                    logs.append(line.rstrip("\n\r"))

            return logs, total_pages, total

    def _rebuild_line_index(self):
        """重建行偏移索引"""
        self._line_offsets = []
        if not self._log_path or not self._log_path.exists():
            return

        with open(self._log_path, "r", encoding="utf-8") as f:
            offset = 0
            for line in f:
                self._line_offsets.append(offset)
                offset += len(line.encode("utf-8"))

        self._current_size = offset if self._line_offsets else 0

    def get_last_n_lines(self, n: int) -> list[str]:
        """获取最后 N 行日志

        Args:
            n: 行数

        Returns:
            日志列表
        """
        if not self._log_path or not self._log_path.exists():
            return []

        with self._lock:
            if self._async_writer:
                self._async_writer.flush()

            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = deque(f, maxlen=n)

            return [line.rstrip("\n\r") for line in lines]

    def get_log_stats(self) -> dict:
        """获取日志统计信息

        Returns:
            包含日志文件数量、总大小等信息的字典
        """
        logs_dir = self.get_logs_dir()
        if not logs_dir.exists():
            return {"files": 0, "total_size": 0, "compressed_files": 0}

        log_files = list(logs_dir.glob("*.log"))
        gz_files = list(logs_dir.glob("*.log.gz"))

        total_size = sum(f.stat().st_size for f in log_files if f.exists())
        compressed_size = sum(f.stat().st_size for f in gz_files if f.exists())

        return {
            "files": len(log_files),
            "compressed_files": len(gz_files),
            "total_size": total_size,
            "compressed_size": compressed_size,
            "total_size_human": self._format_size(total_size),
            "compressed_size_human": self._format_size(compressed_size),
            "current_file": str(self._log_path.name) if self._log_path else None,
            "current_size": self._current_size,
            "current_lines": len(self._line_offsets),
        }

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
