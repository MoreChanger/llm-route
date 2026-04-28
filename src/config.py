"""配置加载与校验模块"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union
import os

import yaml


@dataclass
class RetryRule:
    """重试规则"""

    status: int
    max_retries: int = 10
    delay: float = 2.0
    jitter: float = 1.0
    body_contains: Optional[str] = None


@dataclass
class Upstream:
    """上游服务配置"""

    url: str
    protocol: str = "anthropic"
    convert_responses: bool = False  # 是否转换 /responses 为 /v1/chat/completions


@dataclass
class Route:
    """路由规则"""

    path: str
    upstream: str


@dataclass
class Config:
    """主配置"""

    host: str = "127.0.0.1"
    port: Union[int, str] = 8087  # int 或 "auto"
    log_level: int = 2  # 1=基础, 2=详细, 3=完整
    log_retention_days: int = 7  # 日志保留天数
    log_structured: bool = False  # 是否使用结构化日志 (JSON格式)
    admin_password: str = "123456"  # 明文密码，首次登录后应修改
    admin_password_hash: Optional[str] = None  # bcrypt 哈希（可选，优先使用）
    trusted_proxies: list[str] = field(default_factory=list)  # 可信代理 IP 列表
    upstreams: dict[str, Upstream] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    retry_rules: list[RetryRule] = field(default_factory=list)
    _active_preset: Optional[str] = None  # 当前激活的预设名称（系统管理字段）


def get_presets_dir() -> Path:
    """获取预设目录路径"""
    # 优先使用可执行文件同目录
    if getattr(os, "frozen", False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent.parent
    return base_dir / "presets"


def list_presets() -> list[tuple[str, Path]]:
    """列出所有可用预设

    Returns:
        [(显示名称, 预设文件路径), ...]
    """
    presets_dir = get_presets_dir()
    if not presets_dir.exists():
        return []

    presets = []
    for preset_file in sorted(presets_dir.glob("*.yaml")):
        name = preset_file.stem  # 文件名（不含扩展名）
        presets.append((name, preset_file))

    return presets


def apply_preset(
    preset_path: Path, config_path: str, preset_name: Optional[str] = None
) -> bool:
    """应用预设到配置文件

    Args:
        preset_path: 预设文件路径
        config_path: 目标配置文件路径
        preset_name: 预设名称（可选，用于标记当前激活的预设）

    Returns:
        是否成功
    """
    try:
        # 读取预设内容
        with open(preset_path, "r", encoding="utf-8") as f:
            preset_data = yaml.safe_load(f) or {}

        # 读取当前配置
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {}

        # 保持原始顺序构建新配置
        ordered_config = {}

        # 1. host（如果存在）
        if "host" in config_data:
            ordered_config["host"] = config_data["host"]

        # 2. port（如果存在）
        if "port" in config_data:
            ordered_config["port"] = config_data["port"]

        # 3. log_level（如果存在）
        if "log_level" in config_data:
            ordered_config["log_level"] = config_data["log_level"]

        # 4. admin_password（如果存在）
        if "admin_password" in config_data:
            ordered_config["admin_password"] = config_data["admin_password"]

        # 5. admin_password_hash（如果存在）
        if "admin_password_hash" in config_data:
            ordered_config["admin_password_hash"] = config_data["admin_password_hash"]

        # 6. log_retention_days（如果存在）
        if "log_retention_days" in config_data:
            ordered_config["log_retention_days"] = config_data["log_retention_days"]

        # 7. log_structured（如果存在）
        if "log_structured" in config_data:
            ordered_config["log_structured"] = config_data["log_structured"]

        # 8. upstreams
        if preset_data.get("upstreams"):
            ordered_config["upstreams"] = preset_data["upstreams"]

        # 9. routes
        if preset_data.get("routes"):
            ordered_config["routes"] = preset_data["routes"]

        # 10. retry_rules
        if preset_data.get("retry_rules"):
            ordered_config["retry_rules"] = preset_data["retry_rules"]

        # 11. _active_preset（预设标记）
        if preset_name:
            ordered_config["_active_preset"] = preset_name

        # 写回配置文件（使用 sort_keys=False 保持顺序）
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(
                ordered_config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

        return True
    except Exception as e:
        print(f"应用预设失败: {e}")
        return False


def load_config(config_path: str) -> Config:
    """从 YAML 文件加载配置

    如果文件不存在，返回默认配置。
    支持环境变量覆盖：
    - LLM_ROUTE_PORT: 覆盖端口配置
    """
    config = Config()

    path = Path(config_path)
    if not path.exists():
        return config

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # 加载基本配置
    config.host = data.get("host", "127.0.0.1")
    config.port = data.get("port", 8087)
    config.log_level = data.get("log_level", 2)
    config.log_retention_days = data.get("log_retention_days", 7)
    config.log_structured = data.get("log_structured", False)
    config.admin_password = data.get("admin_password", "123456")
    config.admin_password_hash = data.get("admin_password_hash")
    config.trusted_proxies = data.get("trusted_proxies", [])
    config._active_preset = data.get("_active_preset")

    # 加载上游配置
    upstreams_data = data.get("upstreams", {})
    for name, upstream_data in upstreams_data.items():
        config.upstreams[name] = Upstream(
            url=upstream_data["url"],
            protocol=upstream_data.get("protocol", "anthropic"),
            convert_responses=upstream_data.get("convert_responses", False),
        )

    # 加载路由配置
    routes_data = data.get("routes", [])
    for route_data in routes_data:
        config.routes.append(
            Route(path=route_data["path"], upstream=route_data["upstream"])
        )

    # 加载重试规则
    retry_data = data.get("retry_rules", [])
    for rule_data in retry_data:
        config.retry_rules.append(
            RetryRule(
                status=rule_data["status"],
                max_retries=rule_data.get("max_retries", 10),
                delay=rule_data.get("delay", 2.0),
                jitter=rule_data.get("jitter", 1.0),
                body_contains=rule_data.get("body_contains"),
            )
        )

    # 环境变量覆盖
    env_port = os.environ.get("LLM_ROUTE_PORT")
    if env_port:
        if env_port.lower() == "auto":
            config.port = "auto"
        else:
            try:
                port_value = int(env_port)
                if 1 <= port_value <= 65535:
                    config.port = port_value
                else:
                    print(f"警告: LLM_ROUTE_PORT 值 {port_value} 超出有效范围 (1-65535)，使用默认端口")
            except ValueError:
                print(f"警告: LLM_ROUTE_PORT 值 '{env_port}' 不是有效的端口号，使用默认端口")

    return config


def save_config(config: Config, config_path: str):
    """保存配置到 YAML 文件

    Args:
        config: 配置对象
        config_path: 配置文件路径
    """
    # 读取现有配置以保留注释和顺序
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # 更新基本配置
    data["host"] = config.host
    data["port"] = config.port
    data["log_level"] = config.log_level
    if config.log_retention_days != 7:
        data["log_retention_days"] = config.log_retention_days
    if config.log_structured:
        data["log_structured"] = config.log_structured
    if config.admin_password != "123456":
        # 只有非默认密码才保存
        data["admin_password"] = config.admin_password
    if config.admin_password_hash is not None:
        data["admin_password_hash"] = config.admin_password_hash
    if config._active_preset is not None:
        data["_active_preset"] = config._active_preset

    # 写回文件
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
