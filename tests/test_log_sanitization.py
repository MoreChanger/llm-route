# tests/test_log_sanitization.py
"""日志敏感信息过滤测试"""

from src.log_file import sanitize_sensitive_content


class TestSanitizeSensitiveContent:
    """测试敏感内容过滤"""

    # ========== JSON 格式测试 ==========

    def test_json_authorization_header(self):
        """测试 JSON 格式的 Authorization 头"""
        content = '{"Authorization": "Bearer sk-secret-key-12345"}'
        result = sanitize_sensitive_content(content)
        assert "sk-secret-key-12345" not in result
        assert "[REDACTED]" in result

    def test_json_x_api_key_header(self):
        """测试 JSON 格式的 x-api-key 头"""
        content = '{"x-api-key": "my-api-key-67890"}'
        result = sanitize_sensitive_content(content)
        assert "my-api-key-67890" not in result
        assert "[REDACTED]" in result

    def test_json_case_insensitive(self):
        """测试 JSON 格式大小写不敏感"""
        content1 = '{"authorization": "Bearer secret1"}'
        content2 = '{"AUTHORIZATION": "Bearer secret2"}'
        content3 = '{"Authorization": "Bearer secret3"}'

        for content in [content1, content2, content3]:
            result = sanitize_sensitive_content(content)
            assert "secret" not in result

    def test_json_multiple_headers(self):
        """测试 JSON 格式多个敏感头"""
        content = '{"Authorization": "Bearer key1", "x-api-key": "key2", "other": "value"}'
        result = sanitize_sensitive_content(content)
        assert "key1" not in result
        assert "key2" not in result
        assert "value" in result  # 非敏感值保留

    # ========== HTTP 头格式测试 ==========

    def test_http_authorization_header(self):
        """测试 HTTP 头格式的 Authorization"""
        content = 'Authorization: Bearer sk-test-key\nContent-Type: application/json'
        result = sanitize_sensitive_content(content)
        assert "sk-test-key" not in result
        assert "[REDACTED]" in result

    def test_http_x_api_key_header(self):
        """测试 HTTP 头格式的 x-api-key"""
        content = 'x-api-key: my-secret-key\nHost: api.example.com'
        result = sanitize_sensitive_content(content)
        assert "my-secret-key" not in result
        assert "[REDACTED]" in result

    # ========== 边界情况测试 ==========

    def test_empty_content(self):
        """测试空内容"""
        assert sanitize_sensitive_content("") == ""
        assert sanitize_sensitive_content(None) is None

    def test_no_sensitive_content(self):
        """测试无敏感内容"""
        content = '{"model": "gpt-4", "messages": []}'
        result = sanitize_sensitive_content(content)
        assert result == content

    def test_preserves_structure(self):
        """测试保留 JSON 结构"""
        content = '{"Authorization": "Bearer secret", "model": "gpt-4"}'
        result = sanitize_sensitive_content(content)
        assert '"model": "gpt-4"' in result
        assert result.startswith("{")
        assert result.endswith("}")

    def test_authorization_in_url(self):
        """测试 URL 中的 authorization（不应被过滤）"""
        # 这种情况不应被过滤，因为不是头格式
        content = '{"url": "https://example.com/authorization/endpoint"}'
        result = sanitize_sensitive_content(content)
        assert "authorization" in result.lower()

    def test_partial_key_name(self):
        """测试部分匹配的键名"""
        content = '{"x-api-key-backup": "value", "x-api-key": "secret"}'
        result = sanitize_sensitive_content(content)
        # x-api-key-backup 不应该被过滤
        # 但 x-api-key 应该被过滤
        assert "secret" not in result
