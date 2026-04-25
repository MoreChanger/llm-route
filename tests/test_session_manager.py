# tests/test_session_manager.py
"""会话管理模块测试"""
import time
from src.session_manager import Session, SessionManager


class TestSession:
    def test_create(self):
        """测试会话创建"""
        session = Session(
            response_id="resp_123",
            messages=[{"role": "user", "content": "Hi"}],
            created_at=time.time()
        )
        assert session.response_id == "resp_123"
        assert len(session.messages) == 1


class TestSessionManager:
    def test_create(self):
        """测试管理器创建"""
        manager = SessionManager()
        assert manager._sessions == {}

    def test_generate_response_id(self):
        """测试 ID 生成"""
        manager = SessionManager()
        id1 = manager.generate_response_id()
        id2 = manager.generate_response_id()

        assert id1.startswith("resp_")
        assert id2.startswith("resp_")
        assert id1 != id2

    def test_get_messages_empty(self):
        """测试获取空会话"""
        manager = SessionManager()
        messages = manager.get_messages(None)
        assert messages == []

        messages = manager.get_messages("nonexistent")
        assert messages == []

    def test_save_and_get_messages(self):
        """测试保存和获取"""
        manager = SessionManager()
        response_id = manager.generate_response_id()
        messages = [{"role": "user", "content": "Hello"}]

        manager.save_session(response_id, messages)
        retrieved = manager.get_messages(response_id)

        assert retrieved == messages
        # 确保返回的是副本
        retrieved.append({"role": "assistant", "content": "Hi"})
        assert len(manager.get_messages(response_id)) == 1

    def test_max_sessions_limit(self):
        """测试会话数量上限"""
        manager = SessionManager(max_sessions=3)

        for i in range(5):
            response_id = manager.generate_response_id()
            manager.save_session(response_id, [{"role": "user", "content": str(i)}])
            time.sleep(0.01)  # 确保时间顺序

        # 应该只有 3 个会话
        assert len(manager._sessions) == 3

    def test_session_expiry(self):
        """测试会话过期"""
        manager = SessionManager(ttl_seconds=0.1)

        response_id = manager.generate_response_id()
        manager.save_session(response_id, [{"role": "user", "content": "Hi"}])

        # 立即获取应该成功
        assert manager.get_messages(response_id) == [{"role": "user", "content": "Hi"}]

        # 等待过期
        time.sleep(0.2)

        # 过期后应该返回空
        assert manager.get_messages(response_id) == []

    def test_cleanup_expired(self):
        """测试清理过期会话"""
        manager = SessionManager(ttl_seconds=0.1)

        # 创建 3 个会话
        ids = []
        for i in range(3):
            response_id = manager.generate_response_id()
            manager.save_session(response_id, [{"role": "user", "content": str(i)}])
            ids.append(response_id)
            time.sleep(0.01)

        # 等待部分过期
        time.sleep(0.15)

        # 清理
        cleaned = manager.cleanup_expired()
        assert cleaned >= 1  # 至少清理了一个
