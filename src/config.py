"""配置加载与校验模块"""
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
    upstreams: dict[str, Upstream] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    retry_rules: list[RetryRule] = field(default_factory=list)


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

    # 加载上游配置
    upstreams_data = data.get("upstreams", {})
    for name, upstream_data in upstreams_data.items():
        config.upstreams[name] = Upstream(
            url=upstream_data["url"],
            protocol=upstream_data.get("protocol", "anthropic")
        )

    # 加载路由配置
    routes_data = data.get("routes", [])
    for route_data in routes_data:
        config.routes.append(Route(
            path=route_data["path"],
            upstream=route_data["upstream"]
        ))

    # 加载重试规则
    retry_data = data.get("retry_rules", [])
    for rule_data in retry_data:
        config.retry_rules.append(RetryRule(
            status=rule_data["status"],
            max_retries=rule_data.get("max_retries", 10),
            delay=rule_data.get("delay", 2.0),
            jitter=rule_data.get("jitter", 1.0),
            body_contains=rule_data.get("body_contains")
        ))

    # 环境变量覆盖
    env_port = os.environ.get("LLM_ROUTE_PORT")
    if env_port:
        if env_port.lower() == "auto":
            config.port = "auto"
        else:
            config.port = int(env_port)

    return config
