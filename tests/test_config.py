"""配置模块测试"""

from pathlib import Path

from src.config import (
    Config,
    RetryRule,
    Upstream,
    Route,
    load_config,
    apply_preset,
)


class TestRetryRule:
    def test_retry_rule_creation(self):
        """测试重试规则创建"""
        rule = RetryRule(status=429, max_retries=10, delay=2.0, jitter=1.0)
        assert rule.status == 429
        assert rule.max_retries == 10
        assert rule.delay == 2.0
        assert rule.jitter == 1.0
        assert rule.body_contains is None

    def test_retry_rule_with_body_contains(self):
        """测试带 body_contains 的重试规则"""
        rule = RetryRule(status=400, body_contains="overloaded", max_retries=5)
        assert rule.status == 400
        assert rule.body_contains == "overloaded"


class TestUpstream:
    def test_upstream_creation(self):
        """测试上游配置创建"""
        upstream = Upstream(url="https://api.anthropic.com", protocol="anthropic")
        assert upstream.url == "https://api.anthropic.com"
        assert upstream.protocol == "anthropic"

    def test_upstream_default_protocol(self):
        """测试上游默认协议"""
        upstream = Upstream(url="https://api.example.com")
        assert upstream.protocol == "anthropic"


class TestRoute:
    def test_route_creation(self):
        """测试路由规则创建"""
        route = Route(path="/v1/messages", upstream="anthropic")
        assert route.path == "/v1/messages"
        assert route.upstream == "anthropic"


class TestConfig:
    def test_config_defaults(self):
        """测试配置默认值"""
        config = Config()
        assert config.host == "127.0.0.1"
        assert config.port == 8087
        assert config.upstreams == {}
        assert config.routes == []
        assert config.retry_rules == []

    def test_config_with_values(self):
        """测试带值的配置"""
        config = Config(
            host="0.0.0.0",
            port=9000,
            upstreams={"anthropic": Upstream(url="https://api.anthropic.com")},
            routes=[Route(path="/v1/messages", upstream="anthropic")],
            retry_rules=[RetryRule(status=429, max_retries=10, delay=2, jitter=1)],
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert len(config.upstreams) == 1
        assert len(config.routes) == 1
        assert len(config.retry_rules) == 1


class TestLoadConfig:
    def test_load_config_from_file(self, tmp_path: Path):
        """测试从文件加载配置"""
        config_content = """
host: 0.0.0.0
port: 9000
upstreams:
  test:
    url: https://api.test.com
    protocol: anthropic
routes:
  - path: /v1/messages
    upstream: test
retry_rules:
  - status: 429
    max_retries: 5
    delay: 1
    jitter: 0.5
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert "test" in config.upstreams
        assert config.upstreams["test"].url == "https://api.test.com"
        assert len(config.routes) == 1
        assert len(config.retry_rules) == 1

    def test_load_config_missing_file(self):
        """测试加载不存在的配置文件返回默认配置"""
        config = load_config("/nonexistent/path/config.yaml")
        assert config.host == "127.0.0.1"
        assert config.port == 8087

    def test_load_config_port_auto(self, tmp_path: Path):
        """测试 port: auto 配置"""
        config_content = """
port: auto
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config.port == "auto"

    def test_load_config_env_override(self, tmp_path: Path, monkeypatch):
        """测试环境变量覆盖端口"""
        monkeypatch.setenv("LLM_ROUTE_PORT", "9999")

        config_content = "port: 8087\n"
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config.port == 9999


class TestUpstreamConvertResponses:
    def test_upstream_convert_responses_default(self):
        """测试默认不转换"""
        upstream = Upstream(url="https://api.example.com")
        assert upstream.convert_responses is False

    def test_upstream_convert_responses_true(self):
        """测试启用转换"""
        upstream = Upstream(url="https://api.example.com", convert_responses=True)
        assert upstream.convert_responses is True

    def test_load_config_with_convert_responses(self, tmp_path: Path):
        """测试从配置文件加载 convert_responses"""
        config_content = """
upstreams:
  ollama:
    url: http://localhost:11434/v1
    protocol: openai
    convert_responses: true
  openai:
    url: https://api.openai.com
    protocol: openai
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config.upstreams["ollama"].convert_responses is True
        assert config.upstreams["openai"].convert_responses is False


class TestApplyPreset:
    def test_apply_preset_preserves_password(self, tmp_path: Path):
        """测试应用预设时保留密码字段"""
        # 创建带密码的配置文件
        config_content = """
host: 0.0.0.0
port: 9000
log_level: 2
admin_password: my_secret_password
admin_password_hash: $2b$12$test_hash_here
upstreams:
  test:
    url: https://api.test.com
    protocol: anthropic
routes:
  - path: /v1/messages
    upstream: test
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        # 创建预设文件
        preset_content = """
upstreams:
  preset_upstream:
    url: https://preset.example.com
    protocol: openai
routes:
  - path: /v1/chat/completions
    upstream: preset_upstream
"""
        preset_file = tmp_path / "preset.yaml"
        preset_file.write_text(preset_content)

        # 应用预设
        result = apply_preset(preset_file, str(config_file))
        assert result is True

        # 重新加载配置，验证密码被保留
        config = load_config(str(config_file))
        assert config.admin_password == "my_secret_password"
        assert config.admin_password_hash == "$2b$12$test_hash_here"
        # 同时验证预设被应用
        assert "preset_upstream" in config.upstreams
        assert len(config.routes) == 1
        assert config.routes[0].path == "/v1/chat/completions"

    def test_apply_preset_preserves_only_hash(self, tmp_path: Path):
        """测试应用预设时只保留 hash 密码"""
        # 只有 hash 的配置
        config_content = """
admin_password_hash: $2b$12$hash_only
upstreams:
  old:
    url: https://old.example.com
    protocol: anthropic
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        preset_content = """
upstreams:
  new:
    url: https://new.example.com
routes: []
"""
        preset_file = tmp_path / "preset.yaml"
        preset_file.write_text(preset_content)

        result = apply_preset(preset_file, str(config_file))
        assert result is True

        config = load_config(str(config_file))
        # hash 被保留，明文密码是默认值
        assert config.admin_password_hash == "$2b$12$hash_only"
        assert config.admin_password == "123456"  # 默认值

    def test_apply_preset_no_password_in_config(self, tmp_path: Path):
        """测试配置文件无密码时应用预设"""
        config_content = """
port: 8087
upstreams:
  old:
    url: https://old.example.com
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        preset_content = """
upstreams:
  new:
    url: https://new.example.com
routes: []
"""
        preset_file = tmp_path / "preset.yaml"
        preset_file.write_text(preset_content)

        result = apply_preset(preset_file, str(config_file))
        assert result is True

        config = load_config(str(config_file))
        # 无密码字段，使用默认值
        assert config.admin_password == "123456"
        assert config.admin_password_hash is None
