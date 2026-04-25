"""日志文件管理模块"""

import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import threading
import os


# 敏感头字段列表（小写）
SENSITIVE_HEADERS = {"authorization", "x-api-key"}

# 默认日志文件大小限制 (10MB)
DEFAULT_MAX_LOG_SIZE = 10 * 1024 * 1024


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
    # "Authorization": "Bearer xxx" 或 "x-api-key": "xxx"
    def redact_json_header(match: re.Match) -> str:
        header_name = match.group(1)
        return f'"{header_name}": "[REDACTED]"'

    # JSON 格式（带引号）
    json_pattern = r'"(authorization|x-api-key)":\s*"[^"]*"'
    result = re.sub(json_pattern, redact_json_header, content, flags=re.IGNORECASE)

    # 匹配 HTTP 头格式
    # Authorization: Bearer xxx 或 x-api-key: xxx
    def redact_http_header(match: re.Match) -> str:
        header_name = match.group(1)
        return f"{header_name}: [REDACTED]"

    # HTTP 头格式（可能在日志中出现）
    # 匹配整个值部分（冒号后到行尾或下一个结构符号）
    # 使用单词边界确保只匹配完整的头字段名
    http_pattern = r'\b(Authorization|x-api-key):\s*[^\n\]\[{}"]+'
    result = re.sub(http_pattern, redact_http_header, result, flags=re.IGNORECASE)

    return result


class LogManager:
    """日志管理器 - 文件驱动，支持日志滚动和高效分页"""

    def __init__(self):
        self._log_file: Optional[object] = None
        self._log_path: Optional[Path] = None
        self._lock = threading.Lock()
        self._log_level: int = 2  # 默认详细信息
        self._log_retention_days: int = 7  # 默认保留7天
        self._max_log_size: int = DEFAULT_MAX_LOG_SIZE  # 单文件最大大小
        self._line_count: int = 0  # 当前行数
        self._current_size: int = 0  # 当前文件大小
        self._line_offsets: list[int] = []  # 行偏移索引（用于高效分页）
        self._base_timestamp: str = ""  # 基础时间戳（用于滚动命名）

    def get_logs_dir(self) -> Path:
        """获取日志目录路径"""
        # 打包后的 exe：使用 exe 所在目录
        # 注意：必须检查 sys.frozen 而不是 os.path
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            # 开发模式：使用项目根目录
            base_dir = Path(__file__).parent.parent
        return base_dir / "logs"

    def start(self, log_level: int = 2, log_retention_days: int = 7) -> Path:
        """启动日志管理器

        Args:
            log_level: 日志等级
            log_retention_days: 日志保留天数

        Returns:
            日志文件路径
        """
        self._log_level = log_level
        self._log_retention_days = log_retention_days

        # 创建日志目录
        logs_dir = self.get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 创建日志文件（按启动时间命名）
        self._base_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_path = logs_dir / f"{self._base_timestamp}.log"
        self._log_file = open(self._log_path, "w", encoding="utf-8")
        self._line_count = 0
        self._current_size = 0
        self._line_offsets = [0]  # 第一行从偏移0开始

        # 清理过期日志
        self._cleanup_old_logs()

        return self._log_path

    def _rotate_log_file(self):
        """滚动日志文件（当文件超过大小限制时）"""
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

    def _cleanup_old_logs(self):
        """清理过期的日志文件"""
        if self._log_retention_days <= 0:
            return  # 0 表示永不过期

        logs_dir = self.get_logs_dir()
        if not logs_dir.exists():
            return

        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=self._log_retention_days)

        # 查找所有日志文件
        log_files = list(logs_dir.glob("*.log"))

        for log_file in log_files:
            # 跳过当前日志文件
            if self._log_path and log_file == self._log_path:
                continue

            try:
                # 从文件名解析日期 (格式: YYYY-MM-DD_HH-MM-SS.log)
                filename = log_file.stem
                file_date = datetime.strptime(filename, "%Y-%m-%d_%H-%M-%S")

                # 删除过期文件
                if file_date < cutoff_date:
                    log_file.unlink()
                    try:
                        print(f"已清理过期日志: {log_file.name}")
                    except (UnicodeEncodeError, OSError):
                        pass
            except (ValueError, OSError):
                # 文件名格式不匹配或删除失败，跳过
                pass

    def stop(self):
        """停止日志管理器"""
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

    def log(self, message: str, level: str = "INFO"):
        """记录日志

        Args:
            message: 日志内容
            level: 日志级别（INFO、ERROR等）
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {level:5} {message}"

        with self._lock:
            # 检查是否需要滚动文件
            line_size = len(log_line.encode("utf-8")) + 1  # +1 for newline
            if self._current_size + line_size > self._max_log_size and self._current_size > 0:
                self._rotate_log_file()

            # 写入文件
            if self._log_file:
                # 记录行偏移（用于高效分页）
                self._line_offsets.append(self._current_size)

                self._log_file.write(log_line + "\n")
                self._log_file.flush()
                self._line_count += 1
                self._current_size += line_size

        # 打印到控制台（无控制台模式下忽略错误）
        try:
            print(log_line)
        except (UnicodeEncodeError, OSError):
            # Windows 无控制台模式或编码问题
            pass

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

        if self._log_level == 1:
            # 基础信息
            self.log(f"{method} {path} -> {upstream} [{status_code}]")
        elif self._log_level == 2:
            # 详细信息
            retry_str = f" (重试{retries}次)" if retries > 0 else ""
            self.log(
                f"{method} {path} -> {upstream} [{status_code}] {elapsed_ms:.0f}ms{retry_str}"
            )
        else:
            # 完整信息
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
            if self._log_file:
                self._log_file.flush()
            return len(self._line_offsets)

    def get_logs_page(
        self, page: int, page_size: int = 100
    ) -> tuple[list[str], int, int]:
        """从文件获取分页日志（使用 seek 优化大文件读取）

        Args:
            page: 页码（从1开始）
            page_size: 每页行数

        Returns:
            (当前页日志, 总页数, 总行数)
        """
        if not self._log_path or not self._log_path.exists():
            return [], 1, 0

        with self._lock:
            # 刷新文件缓冲区
            if self._log_file:
                self._log_file.flush()

            # 使用行偏移索引高效定位
            total = len(self._line_offsets)

            # 如果索引不完整（外部修改等），重新构建
            if total == 0 or self._line_offsets[-1] < self._current_size - 1000:
                self._rebuild_line_index()
                total = len(self._line_offsets)

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            page = max(1, min(page, total_pages))
            start_line = (page - 1) * page_size
            end_line = min(start_line + page_size, total)

            if start_line >= total:
                return [], total_pages, total

            # 使用 seek 定位到起始行
            with open(self._log_path, "r", encoding="utf-8") as f:
                start_offset = self._line_offsets[start_line]
                f.seek(start_offset)

                # 读取指定行数
                logs = []
                for i in range(start_line, end_line):
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
            # 刷新文件缓冲区
            if self._log_file:
                self._log_file.flush()

            # 使用 deque 高效读取最后 N 行
            from collections import deque

            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = deque(f, maxlen=n)

            return [line.rstrip("\n\r") for line in lines]
