"""
rate_limiter.py カバレッジ改善テスト

対象: backend/core/rate_limiter.py (62% -> 90%+)
未カバー箇所を重点的にテスト:
  - is_locked: ロックアウト期限切れ (remaining <= 0) の分岐
  - is_locked: count < MAX_ATTEMPTS の場合
  - get_all_locked: 複数エントリ + 期限切れエントリ除外
  - get_all_locked: lockout_end が過去の場合 (remaining <= 0) スキップ
  - clear_lock: メールアドレスでの解除
  - check_and_record: lockout_end 計算の remaining = max(0, ...) 分岐
  - _get_conn: テーブル/インデックス作成
"""

import time
from pathlib import Path

import pytest


@pytest.fixture
def fresh_limiter(tmp_path, monkeypatch):
    """テスト専用の新規 RateLimiter インスタンス"""
    import backend.core.rate_limiter as rl_module
    test_db = tmp_path / "rate_limit_test.db"
    monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", test_db)
    from backend.core.rate_limiter import RateLimiter
    return RateLimiter()


# ===================================================================
# _get_conn テスト
# ===================================================================

class TestGetConn:
    """_get_conn の分岐"""

    def test_creates_db_directory(self, tmp_path, monkeypatch):
        """DB ディレクトリが存在しない場合は作成"""
        import backend.core.rate_limiter as rl_module
        nested_db = tmp_path / "subdir" / "deep" / "rate_limit.db"
        monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", nested_db)
        from backend.core.rate_limiter import RateLimiter
        limiter = RateLimiter()
        conn = limiter._get_conn()
        assert nested_db.parent.exists()
        conn.close()

    def test_creates_table_and_indexes(self, fresh_limiter):
        """テーブルとインデックスが作成される"""
        conn = fresh_limiter._get_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='login_attempts'")
        assert cursor.fetchone() is not None
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ip_ts'")
        assert cursor.fetchone() is not None
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_email_ts'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent_table_creation(self, fresh_limiter):
        """複数回 _get_conn を呼んでもエラーにならない"""
        conn1 = fresh_limiter._get_conn()
        conn1.close()
        conn2 = fresh_limiter._get_conn()
        conn2.close()


# ===================================================================
# is_locked: 期限切れ分岐テスト
# ===================================================================

class TestIsLockedExpired:
    """is_locked のロックアウト期限切れ分岐"""

    def test_lock_expired_returns_false(self, fresh_limiter, monkeypatch):
        """LOCKOUT_DURATION 経過後はロック解除"""
        import backend.core.rate_limiter as rl_module

        # 5回失敗させる
        for _ in range(5):
            fresh_limiter.check_and_record("10.0.0.1", "expired@example.com")

        # ロック中であることを確認
        locked, remaining = fresh_limiter.is_locked("10.0.0.1", "expired@example.com")
        assert locked is True

        # LOCKOUT_DURATION + 1 秒後にタイムスタンプを進める
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + rl_module.LOCKOUT_DURATION + 1)

        locked, remaining = fresh_limiter.is_locked("10.0.0.1", "expired@example.com")
        assert locked is False
        assert remaining == 0

    def test_lock_almost_expired(self, fresh_limiter, monkeypatch):
        """ロックアウト期限直前はまだロック中"""
        import backend.core.rate_limiter as rl_module

        for _ in range(5):
            fresh_limiter.check_and_record("10.0.0.2", "almost@example.com")

        # LOCKOUT_DURATION - 10 秒後
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + rl_module.LOCKOUT_DURATION - 10)

        locked, remaining = fresh_limiter.is_locked("10.0.0.2", "almost@example.com")
        assert locked is True
        assert remaining > 0

    def test_is_locked_under_max_attempts(self, fresh_limiter):
        """MAX_ATTEMPTS 未満の場合はロックされない"""
        for _ in range(3):
            fresh_limiter.check_and_record("10.0.0.3", "under@example.com")
        locked, remaining = fresh_limiter.is_locked("10.0.0.3", "under@example.com")
        assert locked is False
        assert remaining == 0


# ===================================================================
# get_all_locked: 期限切れエントリ除外テスト
# ===================================================================

class TestGetAllLockedExpired:
    """get_all_locked の期限切れエントリ除外分岐"""

    def test_expired_entries_excluded(self, fresh_limiter, monkeypatch):
        """期限切れエントリは get_all_locked に含まれない"""
        import backend.core.rate_limiter as rl_module

        for _ in range(5):
            fresh_limiter.check_and_record("20.0.0.1", "expired_list@example.com")

        # LOCKOUT_DURATION + 1 秒後に進める
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + rl_module.LOCKOUT_DURATION + 1)

        locked = fresh_limiter.get_all_locked()
        emails = [e["email"] for e in locked]
        assert "expired_list@example.com" not in emails

    def test_multiple_locked_entries(self, fresh_limiter):
        """複数の IP/メール組み合わせがロック一覧に表示される"""
        for _ in range(5):
            fresh_limiter.check_and_record("30.0.0.1", "multi1@example.com")
        for _ in range(5):
            fresh_limiter.check_and_record("30.0.0.2", "multi2@example.com")

        locked = fresh_limiter.get_all_locked()
        assert len(locked) >= 2
        ips = {e["ip"] for e in locked}
        assert "30.0.0.1" in ips
        assert "30.0.0.2" in ips

    def test_get_all_locked_entry_fields(self, fresh_limiter):
        """各エントリのフィールドを検証"""
        for _ in range(5):
            fresh_limiter.check_and_record("40.0.0.1", "fields@example.com")

        locked = fresh_limiter.get_all_locked()
        assert len(locked) >= 1
        entry = locked[0]
        assert "ip" in entry
        assert "email" in entry
        assert "attempts" in entry
        assert "locked_until" in entry
        assert "remaining_seconds" in entry
        assert entry["attempts"] >= 5
        assert isinstance(entry["locked_until"], float)


# ===================================================================
# clear_lock: メールアドレスでの解除テスト
# ===================================================================

class TestClearLockByEmail:
    """clear_lock のメールアドレス指定分岐"""

    def test_clear_lock_by_email(self, fresh_limiter):
        """メールアドレスでロック解除"""
        for _ in range(5):
            fresh_limiter.check_and_record("50.0.0.1", "clearbyemail@example.com")

        locked, _ = fresh_limiter.is_locked("50.0.0.1", "clearbyemail@example.com")
        assert locked is True

        result = fresh_limiter.clear_lock("clearbyemail@example.com")
        assert result is True

        locked, _ = fresh_limiter.is_locked("50.0.0.1", "clearbyemail@example.com")
        assert locked is False

    def test_clear_lock_by_ip(self, fresh_limiter):
        """IP アドレスでロック解除"""
        for _ in range(5):
            fresh_limiter.check_and_record("60.0.0.1", "clearbyip@example.com")

        result = fresh_limiter.clear_lock("60.0.0.1")
        assert result is True

        locked, _ = fresh_limiter.is_locked("60.0.0.1", "clearbyip@example.com")
        assert locked is False


# ===================================================================
# check_and_record: remaining max(0, ...) 分岐テスト
# ===================================================================

class TestCheckAndRecordEdgeCases:
    """check_and_record の remaining 計算エッジケース"""

    def test_lockout_remaining_is_bounded_at_zero(self, fresh_limiter, monkeypatch):
        """remaining が max(0, ...) で 0 未満にならない"""
        import backend.core.rate_limiter as rl_module

        for _ in range(5):
            fresh_limiter.check_and_record("70.0.0.1", "bounded@example.com")

        # WINDOW_DURATION + 1 秒後（古い失敗がウィンドウ外になる）
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + rl_module.WINDOW_DURATION + 1)

        # check_and_record を呼ぶと新規失敗が記録されるがウィンドウ内の古い失敗は期限切れ
        allowed, remaining = fresh_limiter.check_and_record("70.0.0.1", "bounded@example.com")
        # 古い失敗はウィンドウ外なのでカウントは1（新規記録分のみ）
        assert allowed is True
        assert remaining == 0

    def test_different_ip_same_email_contributes(self, fresh_limiter):
        """異なるIPからの同一メール失敗がカウントされる"""
        for i in range(5):
            fresh_limiter.check_and_record(f"80.0.0.{i}", "shared@example.com")

        # 6回目は別のIPからでもロック
        allowed, remaining = fresh_limiter.check_and_record("80.0.0.99", "shared@example.com")
        assert allowed is False

    def test_window_expiry(self, fresh_limiter, monkeypatch):
        """WINDOW_DURATION 経過後は失敗カウントがリセットされる"""
        import backend.core.rate_limiter as rl_module

        for _ in range(4):
            fresh_limiter.check_and_record("90.0.0.1", "window@example.com")

        # WINDOW_DURATION + 1 秒後
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + rl_module.WINDOW_DURATION + 1)

        # ウィンドウ外なのでカウントは1（今回の分のみ）
        allowed, remaining = fresh_limiter.check_and_record("90.0.0.1", "window@example.com")
        assert allowed is True


# ===================================================================
# record_success の追加テスト
# ===================================================================

class TestRecordSuccessEdgeCases:
    """record_success の追加分岐"""

    def test_record_success_inserts_success_entry(self, fresh_limiter):
        """成功記録が success=1 で追加される"""
        fresh_limiter.record_success("100.0.0.1", "success@example.com")
        conn = fresh_limiter._get_conn()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND success = 1",
            ("100.0.0.1",),
        )
        count = cursor.fetchone()[0]
        assert count >= 1
        conn.close()

    def test_record_success_deletes_failures(self, fresh_limiter):
        """成功後に該当 IP/メールの失敗レコードが削除される"""
        for _ in range(3):
            fresh_limiter.check_and_record("110.0.0.1", "delfail@example.com")

        fresh_limiter.record_success("110.0.0.1", "delfail@example.com")

        conn = fresh_limiter._get_conn()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE (ip = ? OR email = ?) AND success = 0",
            ("110.0.0.1", "delfail@example.com"),
        )
        count = cursor.fetchone()[0]
        assert count == 0
        conn.close()

    def test_record_success_no_prior_failures(self, fresh_limiter):
        """失敗記録なしの成功記録もエラーにならない"""
        fresh_limiter.record_success("120.0.0.1", "nofail@example.com")
        locked, _ = fresh_limiter.is_locked("120.0.0.1", "nofail@example.com")
        assert locked is False


# ===================================================================
# モジュールレベル定数テスト
# ===================================================================

class TestModuleConstants:
    """モジュールレベル定数"""

    def test_max_attempts(self):
        from backend.core.rate_limiter import MAX_ATTEMPTS
        assert MAX_ATTEMPTS == 5

    def test_lockout_duration(self):
        from backend.core.rate_limiter import LOCKOUT_DURATION
        assert LOCKOUT_DURATION == 300

    def test_window_duration(self):
        from backend.core.rate_limiter import WINDOW_DURATION
        assert WINDOW_DURATION == 600

    def test_singleton_instance(self):
        from backend.core.rate_limiter import rate_limiter
        assert rate_limiter is not None
