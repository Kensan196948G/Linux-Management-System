"""
RateLimiter 単体テスト

check_and_record / record_success / is_locked の動作を検証する。
"""

import time

import pytest


@pytest.fixture
def fresh_limiter(tmp_path, monkeypatch):
    """テスト専用の新規RateLimiterインスタンスを返す。"""
    import backend.core.rate_limiter as rl_module

    test_db = tmp_path / "rate_limit_test.db"
    monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", test_db)

    from backend.core.rate_limiter import RateLimiter

    return RateLimiter()


class TestCheckAndRecord:
    """check_and_record のテスト"""

    def test_first_failure_is_allowed(self, fresh_limiter):
        """1回目の失敗は許可される"""
        allowed, remaining = fresh_limiter.check_and_record("1.2.3.4", "test@example.com")
        assert allowed is True
        assert remaining == 0

    def test_four_failures_still_allowed(self, fresh_limiter):
        """4回の失敗は許可される"""
        for i in range(4):
            allowed, remaining = fresh_limiter.check_and_record("1.2.3.4", "test@example.com")
            assert allowed is True

    def test_five_failures_triggers_lock(self, fresh_limiter):
        """5回の失敗でロックされる"""
        for _ in range(4):
            fresh_limiter.check_and_record("1.2.3.4", "test@example.com")
        allowed, remaining = fresh_limiter.check_and_record("1.2.3.4", "test@example.com")
        assert allowed is False
        assert remaining > 0

    def test_locked_remaining_seconds_is_positive(self, fresh_limiter):
        """ロック後の残り秒数は正の値"""
        for _ in range(5):
            fresh_limiter.check_and_record("1.2.3.4", "user@example.com")
        _, remaining = fresh_limiter.check_and_record("1.2.3.4", "user@example.com")
        assert remaining > 0
        assert remaining <= 300  # LOCKOUT_DURATION

    def test_ip_based_lock(self, fresh_limiter):
        """同一IPで異なるメールでもロックされる"""
        for i in range(5):
            fresh_limiter.check_and_record("192.168.1.1", f"user{i}@example.com")
        # 同じIPで別メールも影響を受ける
        locked, _ = fresh_limiter.is_locked("192.168.1.1", "new@example.com")
        assert locked is True

    def test_email_based_lock(self, fresh_limiter):
        """同一メールで異なるIPでもロックされる"""
        for i in range(5):
            fresh_limiter.check_and_record(f"10.0.0.{i}", "victim@example.com")
        locked, _ = fresh_limiter.is_locked("10.0.0.99", "victim@example.com")
        assert locked is True

    def test_sixth_failure_also_locked(self, fresh_limiter):
        """6回目以降も引き続きロックされる"""
        for _ in range(6):
            allowed, _ = fresh_limiter.check_and_record("1.2.3.4", "test@example.com")
        assert allowed is False


class TestIsLocked:
    """is_locked のテスト"""

    def test_not_locked_initially(self, fresh_limiter):
        """初期状態ではロックされていない"""
        locked, remaining = fresh_limiter.is_locked("5.6.7.8", "clean@example.com")
        assert locked is False
        assert remaining == 0

    def test_locked_after_five_failures(self, fresh_limiter):
        """5回失敗後はロック状態"""
        for _ in range(5):
            fresh_limiter.check_and_record("5.6.7.8", "locked@example.com")
        locked, remaining = fresh_limiter.is_locked("5.6.7.8", "locked@example.com")
        assert locked is True
        assert remaining > 0

    def test_remaining_seconds_decreases_over_time(self, fresh_limiter, monkeypatch):
        """時間経過とともに残り秒数が減少する"""
        for _ in range(5):
            fresh_limiter.check_and_record("1.1.1.1", "time@example.com")

        _, remaining1 = fresh_limiter.is_locked("1.1.1.1", "time@example.com")

        # 時間を2秒進める（monkeypatching time.time）
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 2)

        _, remaining2 = fresh_limiter.is_locked("1.1.1.1", "time@example.com")
        assert remaining2 < remaining1


class TestRecordSuccess:
    """record_success のテスト"""

    def test_success_clears_failures(self, fresh_limiter):
        """成功後は失敗カウンタがリセットされる"""
        for _ in range(4):
            fresh_limiter.check_and_record("9.8.7.6", "clear@example.com")

        fresh_limiter.record_success("9.8.7.6", "clear@example.com")

        locked, _ = fresh_limiter.is_locked("9.8.7.6", "clear@example.com")
        assert locked is False

    def test_success_after_lock_clears_lock(self, fresh_limiter):
        """5回失敗後でも成功でリセットされる"""
        for _ in range(5):
            fresh_limiter.check_and_record("3.3.3.3", "unlock@example.com")

        # まずロックされていること確認
        locked, _ = fresh_limiter.is_locked("3.3.3.3", "unlock@example.com")
        assert locked is True

        # 成功でリセット
        fresh_limiter.record_success("3.3.3.3", "unlock@example.com")

        locked, _ = fresh_limiter.is_locked("3.3.3.3", "unlock@example.com")
        assert locked is False

    def test_can_attempt_again_after_success_reset(self, fresh_limiter):
        """リセット後は再び試行可能"""
        for _ in range(4):
            fresh_limiter.check_and_record("4.4.4.4", "retry@example.com")
        fresh_limiter.record_success("4.4.4.4", "retry@example.com")

        # 再び試行
        allowed, _ = fresh_limiter.check_and_record("4.4.4.4", "retry@example.com")
        assert allowed is True


class TestGetAllLocked:
    """get_all_locked のテスト"""

    def test_empty_when_no_locks(self, fresh_limiter):
        """ロックなしの場合は空リスト"""
        locked = fresh_limiter.get_all_locked()
        assert locked == []

    def test_returns_locked_entries(self, fresh_limiter):
        """ロック中のエントリが返る"""
        for _ in range(5):
            fresh_limiter.check_and_record("7.7.7.7", "locked2@example.com")

        locked = fresh_limiter.get_all_locked()
        assert len(locked) >= 1

        entry = locked[0]
        assert "ip" in entry
        assert "email" in entry
        assert "attempts" in entry
        assert "remaining_seconds" in entry
        assert entry["remaining_seconds"] > 0

    def test_cleared_lock_not_in_list(self, fresh_limiter):
        """解除されたロックは一覧に含まれない"""
        for _ in range(5):
            fresh_limiter.check_and_record("8.8.8.8", "clearme@example.com")

        fresh_limiter.clear_lock("8.8.8.8")

        locked = fresh_limiter.get_all_locked()
        ips = [e["ip"] for e in locked]
        assert "8.8.8.8" not in ips


class TestClearLock:
    """clear_lock のテスト"""

    def test_clear_existing_lock(self, fresh_limiter):
        """既存ロックを解除できる"""
        for _ in range(5):
            fresh_limiter.check_and_record("2.2.2.2", "clear2@example.com")

        result = fresh_limiter.clear_lock("2.2.2.2")
        assert result is True

        locked, _ = fresh_limiter.is_locked("2.2.2.2", "clear2@example.com")
        assert locked is False

    def test_clear_nonexistent_returns_false(self, fresh_limiter):
        """存在しない識別子の解除はFalseを返す"""
        result = fresh_limiter.clear_lock("nonexistent@example.com")
        assert result is False
