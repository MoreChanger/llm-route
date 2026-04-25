"""重试策略模块测试"""

from unittest.mock import MagicMock

from src.retry import should_retry, calculate_delay, RetryRule


class TestRetryRule:
    def test_retry_rule_defaults(self):
        """测试重试规则默认值"""
        rule = RetryRule(status=429)
        assert rule.status == 429
        assert rule.max_retries == 10
        assert rule.delay == 2.0
        assert rule.jitter == 1.0
        assert rule.body_contains is None


class TestShouldRetry:
    def test_match_status_only(self):
        """测试仅匹配状态码"""
        rule = RetryRule(status=429)
        response = MagicMock()
        response.status_code = 429
        response.text = "any text"

        assert should_retry(response, [rule]) is True

    def test_match_status_with_body(self):
        """测试匹配状态码和响应体"""
        rule = RetryRule(status=400, body_contains="overloaded")
        response = MagicMock()
        response.status_code = 400
        response.text = "Error: service overloaded"

        assert should_retry(response, [rule]) is True

    def test_status_match_body_not_match(self):
        """测试状态码匹配但响应体不匹配"""
        rule = RetryRule(status=400, body_contains="overloaded")
        response = MagicMock()
        response.status_code = 400
        response.text = "Error: bad request"

        assert should_retry(response, [rule]) is False

    def test_no_match(self):
        """测试不匹配任何规则"""
        rule = RetryRule(status=429)
        response = MagicMock()
        response.status_code = 200
        response.text = "OK"

        assert should_retry(response, [rule]) is False

    def test_multiple_rules_first_match(self):
        """测试多个规则，第一个匹配"""
        rules = [RetryRule(status=429), RetryRule(status=500)]
        response = MagicMock()
        response.status_code = 429
        response.text = ""

        assert should_retry(response, rules) is True

    def test_multiple_rules_second_match(self):
        """测试多个规则，第二个匹配"""
        rules = [
            RetryRule(status=429, body_contains="rate limit"),
            RetryRule(status=500),
        ]
        response = MagicMock()
        response.status_code = 500
        response.text = ""

        assert should_retry(response, rules) is True

    def test_empty_rules(self):
        """测试空规则列表"""
        response = MagicMock()
        response.status_code = 500
        response.text = ""

        assert should_retry(response, []) is False


class TestCalculateDelay:
    def test_first_retry(self):
        """测试第一次重试延迟"""
        delay = calculate_delay(0, delay=2.0, jitter=1.0)
        assert delay == 2.0

    def test_second_retry(self):
        """测试第二次重试延迟"""
        delay = calculate_delay(1, delay=2.0, jitter=1.0)
        assert delay == 3.0

    def test_third_retry(self):
        """测试第三次重试延迟"""
        delay = calculate_delay(2, delay=2.0, jitter=1.0)
        assert delay == 4.0

    def test_zero_jitter(self):
        """测试零抖动"""
        delay = calculate_delay(5, delay=2.0, jitter=0.0)
        assert delay == 2.0

    def test_custom_delay_jitter(self):
        """测试自定义延迟和抖动"""
        delay = calculate_delay(3, delay=5.0, jitter=2.0)
        assert delay == 11.0  # 5 + 3*2
