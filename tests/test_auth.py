# tests/test_auth.py
"""认证模块测试"""

import time
import pytest
from src.auth import AdminAuthManager, generate_password_hash


class TestGeneratePasswordHash:
    """测试密码哈希生成"""

    def test_generates_valid_bcrypt_hash(self):
        """测试生成有效的 bcrypt 哈希"""
        password = "test_password"
        hash_str = generate_password_hash(password)

        # bcrypt 哈希应以 $2b$ 开头
        assert hash_str.startswith("$2b$")
        assert len(hash_str) == 60  # bcrypt 哈希长度固定

    def test_different_passwords_different_hashes(self):
        """测试不同密码生成不同哈希"""
        hash1 = generate_password_hash("password1")
        hash2 = generate_password_hash("password2")
        assert hash1 != hash2

    def test_same_password_different_hashes(self):
        """测试相同密码每次生成不同哈希（因为 salt 不同）"""
        hash1 = generate_password_hash("same_password")
        hash2 = generate_password_hash("same_password")
        # bcrypt 每次生成不同的 salt
        assert hash1 != hash2


class TestAdminAuthManager:
    """测试 AdminAuthManager 类"""

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器"""
        password_hash = generate_password_hash("correct_password")
        return AdminAuthManager(password_hash=password_hash)

    @pytest.fixture
    def auth_manager_no_password(self):
        """创建无密码的认证管理器"""
        return AdminAuthManager(password_hash=None)

    # ========== 密码验证测试 ==========

    def test_verify_password_correct(self, auth_manager):
        """测试正确密码验证"""
        assert auth_manager.verify_password("correct_password") is True

    def test_verify_password_incorrect(self, auth_manager):
        """测试错误密码验证"""
        assert auth_manager.verify_password("wrong_password") is False

    def test_verify_password_no_password_configured(self, auth_manager_no_password):
        """测试未配置密码时验证失败"""
        assert auth_manager_no_password.verify_password("any_password") is False

    def test_has_password_true(self, auth_manager):
        """测试已配置密码"""
        assert auth_manager.has_password() is True

    def test_has_password_false(self, auth_manager_no_password):
        """测试未配置密码"""
        assert auth_manager_no_password.has_password() is False

    def test_set_password_hash(self, auth_manager_no_password):
        """测试动态设置密码哈希"""
        password_hash = generate_password_hash("new_password")
        auth_manager_no_password.set_password_hash(password_hash)
        assert auth_manager_no_password.has_password() is True
        assert auth_manager_no_password.verify_password("new_password") is True

    # ========== 锁定测试 ==========

    def test_check_lockout_initially_false(self, auth_manager):
        """测试初始状态未被锁定"""
        assert auth_manager.check_lockout("192.168.1.1") is False

    def test_record_failure_increments_count(self, auth_manager):
        """测试记录失败增加计数"""
        count = auth_manager.record_failure("192.168.1.1")
        assert count == 1
        count = auth_manager.record_failure("192.168.1.1")
        assert count == 2

    def test_lockout_after_five_failures(self, auth_manager):
        """测试 5 次失败后锁定"""
        ip = "192.168.1.100"
        for _ in range(4):
            auth_manager.record_failure(ip)
            assert auth_manager.check_lockout(ip) is False

        # 第 5 次失败触发锁定
        auth_manager.record_failure(ip)
        assert auth_manager.check_lockout(ip) is True

    def test_lockout_remaining(self, auth_manager):
        """测试锁定剩余时间"""
        ip = "192.168.1.100"
        # 触发锁定
        for _ in range(5):
            auth_manager.record_failure(ip)

        remaining = auth_manager.get_lockout_remaining(ip)
        assert remaining > 0
        assert remaining <= 15 * 60  # 最多 15 分钟

    def test_lockout_expires(self, auth_manager):
        """测试锁定过期"""
        ip = "192.168.1.100"
        # 手动设置一个已过期的锁定
        auth_manager._lockout_until[ip] = time.time() - 1

        assert auth_manager.check_lockout(ip) is False
        assert ip not in auth_manager._lockout_until

    def test_clear_failures(self, auth_manager):
        """测试清除失败记录"""
        ip = "192.168.1.1"
        auth_manager.record_failure(ip)
        auth_manager.record_failure(ip)

        auth_manager.clear_failures(ip)

        assert ip not in auth_manager._failed_attempts

    def test_different_ips_tracked_separately(self, auth_manager):
        """测试不同 IP 独立跟踪"""
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        auth_manager.record_failure(ip1)
        auth_manager.record_failure(ip1)

        count = auth_manager.record_failure(ip2)
        assert count == 1  # ip2 只有 1 次

    # ========== 会话测试 ==========

    def test_create_session(self, auth_manager):
        """测试创建会话"""
        token = auth_manager.create_session()
        assert token is not None
        assert len(token) > 30  # token 应该足够长

    def test_validate_session_valid(self, auth_manager):
        """测试验证有效会话"""
        token = auth_manager.create_session()
        assert auth_manager.validate_session(token) is True

    def test_validate_session_invalid(self, auth_manager):
        """测试验证无效会话"""
        assert auth_manager.validate_session("invalid_token") is False
        assert auth_manager.validate_session(None) is False
        assert auth_manager.validate_session("") is False

    def test_session_expiry(self, auth_manager):
        """测试会话过期"""
        token = auth_manager.create_session()

        # 手动设置会话过期
        auth_manager._sessions[token].created_at = (
            time.time() - 25 * 60 * 60
        )  # 25 小时前

        assert auth_manager.validate_session(token) is False

    def test_multiple_sessions(self, auth_manager):
        """测试多个会话"""
        token1 = auth_manager.create_session()
        token2 = auth_manager.create_session()

        assert auth_manager.validate_session(token1) is True
        assert auth_manager.validate_session(token2) is True
        assert token1 != token2

    def test_cleanup_expired_sessions(self, auth_manager):
        """测试清理过期会话"""
        # 创建几个会话
        token1 = auth_manager.create_session()
        token2 = auth_manager.create_session()

        # 让 token1 过期
        auth_manager._sessions[token1].created_at = time.time() - 25 * 60 * 60

        # 创建新会话会触发清理
        auth_manager.create_session()

        assert auth_manager.validate_session(token1) is False
        assert auth_manager.validate_session(token2) is True
