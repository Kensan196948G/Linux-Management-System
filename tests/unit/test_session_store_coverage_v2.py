"""
session_store.py カバレッジ改善テスト v2

対象: backend/core/session_store.py (SessionStore クラス)
全メソッド・分岐を網羅する。

カバー対象:
  - _get_conn: テーブル作成・インデックス作成
  - _cleanup: 期限切れセッション削除、revoke古エントリ削除
  - register_session: 登録・上書き(INSERT OR REPLACE)
  - revoke_session: 存在するセッション→True、存在しないセッション→False
  - revoke_user_sessions: 複数セッションの一括revoke、0件
  - is_revoked: revoked→True、not revoked→False
  - get_active_sessions: 期限内セッションのみ返す、フィールド変換
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def session_store(tmp_path):
    """テスト用SessionStore（一時DBを使用）"""
    from backend.core.session_store import SessionStore

    test_db = tmp_path / "test_sessions.db"
    store = SessionStore()
    with patch("backend.core.session_store.SESSIONS_DB", test_db):
        # テーブル初期化
        store._get_conn()
    # 以降のテストでも同じDBを使用するためパッチを適用し続ける
    return store, test_db


def _patched(store, test_db):
    """パッチされたコンテキストマネージャを返す"""
    return patch("backend.core.session_store.SESSIONS_DB", test_db)


class TestGetConn:
    """_get_conn のテスト"""

    def test_creates_tables(self, tmp_path):
        """テーブルが正しく作成されること"""
        from backend.core.session_store import SessionStore

        test_db = tmp_path / "test_conn.db"
        store = SessionStore()
        with patch("backend.core.session_store.SESSIONS_DB", test_db):
            conn = store._get_conn()
        # テーブル一覧を確認
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "active_sessions" in table_names
        assert "revoked_sessions" in table_names
        conn.close()

    def test_creates_indexes(self, tmp_path):
        """インデックスが正しく作成されること"""
        from backend.core.session_store import SessionStore

        test_db = tmp_path / "test_idx.db"
        store = SessionStore()
        with patch("backend.core.session_store.SESSIONS_DB", test_db):
            conn = store._get_conn()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        idx_names = {i[0] for i in indexes}
        assert "idx_sess_email" in idx_names
        assert "idx_sess_user" in idx_names
        conn.close()

    def test_creates_parent_directory(self, tmp_path):
        """親ディレクトリが存在しない場合に作成されること"""
        from backend.core.session_store import SessionStore

        test_db = tmp_path / "nested" / "deep" / "sessions.db"
        store = SessionStore()
        with patch("backend.core.session_store.SESSIONS_DB", test_db):
            conn = store._get_conn()
        assert test_db.parent.exists()
        conn.close()


class TestRegisterSession:
    """register_session のテスト"""

    def test_register_new_session(self, session_store):
        """新しいセッションが登録されること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="test-jti-001",
                user_id="uid-001",
                username="testuser",
                email="test@example.com",
                role="admin",
                ip_address="127.0.0.1",
                user_agent="TestAgent/1.0",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        assert len(sessions) >= 1
        found = [s for s in sessions if s["session_id"] == "test-jti-001"]
        assert len(found) == 1
        assert found[0]["username"] == "testuser"
        assert found[0]["email"] == "test@example.com"

    def test_register_replaces_existing(self, session_store):
        """同じJTIで上書きされること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="dup-jti",
                user_id="uid-001",
                username="user1",
                email="a@example.com",
                role="viewer",
                ip_address="10.0.0.1",
                user_agent="Agent1",
                expires_at=future,
            )
            store.register_session(
                jti="dup-jti",
                user_id="uid-002",
                username="user2",
                email="b@example.com",
                role="admin",
                ip_address="10.0.0.2",
                user_agent="Agent2",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        dup = [s for s in sessions if s["session_id"] == "dup-jti"]
        assert len(dup) == 1
        assert dup[0]["username"] == "user2"

    def test_register_triggers_cleanup(self, session_store):
        """register 時に期限切れセッションがクリーンアップされること"""
        store, test_db = session_store
        past = time.time() - 3600
        future = time.time() + 3600
        with _patched(store, test_db):
            # 期限切れセッションを手動登録
            conn = store._get_conn()
            conn.execute(
                """INSERT INTO active_sessions
                   (jti, user_id, username, email, role, ip_address, user_agent, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("expired-jti", "uid-x", "old", "old@e.com", "v", "1.1.1.1", "a", time.time() - 7200, past),
            )
            conn.commit()
            conn.close()

            # 新しいセッション登録でクリーンアップ発動
            store.register_session(
                jti="new-jti",
                user_id="uid-new",
                username="new",
                email="new@e.com",
                role="admin",
                ip_address="2.2.2.2",
                user_agent="b",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        expired = [s for s in sessions if s["session_id"] == "expired-jti"]
        assert len(expired) == 0


class TestRevokeSession:
    """revoke_session のテスト"""

    def test_revoke_existing_session(self, session_store):
        """存在するセッションをrevoke → True"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="revoke-me",
                user_id="uid-1",
                username="u",
                email="u@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            result = store.revoke_session("revoke-me")
        assert result is True

    def test_revoke_nonexistent_session(self, session_store):
        """存在しないセッションをrevoke → False"""
        store, test_db = session_store
        with _patched(store, test_db):
            result = store.revoke_session("nonexistent-jti")
        assert result is False

    def test_revoke_removes_from_active(self, session_store):
        """revoke後にアクティブセッション一覧から消えること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="to-remove",
                user_id="uid-1",
                username="u",
                email="u@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            store.revoke_session("to-remove")
            sessions = store.get_active_sessions()
        found = [s for s in sessions if s["session_id"] == "to-remove"]
        assert len(found) == 0

    def test_revoke_adds_to_blocklist(self, session_store):
        """revoke後にブロックリストに追加されること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="blocklist-check",
                user_id="uid-1",
                username="u",
                email="u@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            store.revoke_session("blocklist-check")
            assert store.is_revoked("blocklist-check") is True


class TestRevokeUserSessions:
    """revoke_user_sessions のテスト"""

    def test_revoke_multiple_sessions(self, session_store):
        """ユーザーの複数セッションを一括revoke"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            for i in range(3):
                store.register_session(
                    jti=f"user-jti-{i}",
                    user_id="uid-multi",
                    username="multiuser",
                    email="multi@example.com",
                    role="operator",
                    ip_address="10.0.0.1",
                    user_agent="Agent",
                    expires_at=future,
                )
            count = store.revoke_user_sessions("multi@example.com")
        assert count == 3

    def test_revoke_zero_sessions(self, session_store):
        """セッションが0件のユーザー → 0を返す"""
        store, test_db = session_store
        with _patched(store, test_db):
            count = store.revoke_user_sessions("nobody@example.com")
        assert count == 0

    def test_revoke_only_target_user(self, session_store):
        """他ユーザーのセッションは影響を受けないこと"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="target-jti",
                user_id="uid-t",
                username="target",
                email="target@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            store.register_session(
                jti="other-jti",
                user_id="uid-o",
                username="other",
                email="other@e.com",
                role="v",
                ip_address="2.2.2.2",
                user_agent="b",
                expires_at=future,
            )
            store.revoke_user_sessions("target@e.com")
            sessions = store.get_active_sessions()
        other = [s for s in sessions if s["session_id"] == "other-jti"]
        target = [s for s in sessions if s["session_id"] == "target-jti"]
        assert len(other) == 1
        assert len(target) == 0

    def test_revoke_user_adds_to_blocklist(self, session_store):
        """revoke後に各JTIがブロックリストに追加されること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="bl-check-1",
                user_id="uid-bl",
                username="bluser",
                email="bl@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            store.register_session(
                jti="bl-check-2",
                user_id="uid-bl",
                username="bluser",
                email="bl@e.com",
                role="v",
                ip_address="2.2.2.2",
                user_agent="b",
                expires_at=future,
            )
            store.revoke_user_sessions("bl@e.com")
            assert store.is_revoked("bl-check-1") is True
            assert store.is_revoked("bl-check-2") is True


class TestIsRevoked:
    """is_revoked のテスト"""

    def test_not_revoked(self, session_store):
        """revokeされていないJTI → False"""
        store, test_db = session_store
        with _patched(store, test_db):
            assert store.is_revoked("never-revoked") is False

    def test_is_revoked_after_revoke(self, session_store):
        """revoke後 → True"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="check-rev",
                user_id="uid-1",
                username="u",
                email="u@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            store.revoke_session("check-rev")
            assert store.is_revoked("check-rev") is True


class TestGetActiveSessions:
    """get_active_sessions のテスト"""

    def test_empty_sessions(self, session_store):
        """セッションが0件 → 空リスト"""
        store, test_db = session_store
        with _patched(store, test_db):
            sessions = store.get_active_sessions()
        assert sessions == []

    def test_excludes_expired(self, session_store):
        """期限切れセッションは含まれないこと"""
        store, test_db = session_store
        past = time.time() - 100
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="expired",
                user_id="uid-exp",
                username="exp",
                email="exp@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=past,
            )
            store.register_session(
                jti="valid",
                user_id="uid-val",
                username="val",
                email="val@e.com",
                role="v",
                ip_address="2.2.2.2",
                user_agent="b",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        jti_list = [s["session_id"] for s in sessions]
        assert "valid" in jti_list
        assert "expired" not in jti_list

    def test_session_fields(self, session_store):
        """セッション辞書のフィールドが正しいこと"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="field-check",
                user_id="uid-fc",
                username="fielduser",
                email="fc@e.com",
                role="admin",
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        s = [x for x in sessions if x["session_id"] == "field-check"][0]
        assert s["user_id"] == "uid-fc"
        assert s["username"] == "fielduser"
        assert s["email"] == "fc@e.com"
        assert s["role"] == "admin"
        assert s["ip_address"] == "192.168.1.1"
        assert s["user_agent"] == "Mozilla/5.0"
        assert "created_at" in s
        assert "expires_at" in s

    def test_null_ip_and_user_agent(self, session_store):
        """ip_address/user_agent が None の場合 'unknown' に変換されること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="null-fields",
                user_id="uid-nf",
                username="nfuser",
                email="nf@e.com",
                role="viewer",
                ip_address=None,
                user_agent=None,
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        s = [x for x in sessions if x["session_id"] == "null-fields"][0]
        assert s["ip_address"] == "unknown"
        assert s["user_agent"] == "unknown"

    def test_ordered_by_created_at_desc(self, session_store):
        """created_at の降順でソートされること"""
        store, test_db = session_store
        future = time.time() + 3600
        with _patched(store, test_db):
            store.register_session(
                jti="old",
                user_id="uid-o",
                username="old",
                email="o@e.com",
                role="v",
                ip_address="1.1.1.1",
                user_agent="a",
                expires_at=future,
            )
            # 少し待ってから2番目を登録（created_atが異なるように）
            import time as t
            t.sleep(0.01)
            store.register_session(
                jti="new",
                user_id="uid-n",
                username="new",
                email="n@e.com",
                role="v",
                ip_address="2.2.2.2",
                user_agent="b",
                expires_at=future,
            )
            sessions = store.get_active_sessions()
        jti_list = [s["session_id"] for s in sessions]
        if "old" in jti_list and "new" in jti_list:
            assert jti_list.index("new") < jti_list.index("old")


class TestCleanup:
    """_cleanup のテスト"""

    def test_cleanup_removes_expired_active(self, session_store):
        """_cleanup で期限切れアクティブセッションが削除されること"""
        store, test_db = session_store
        past = time.time() - 100
        with _patched(store, test_db):
            conn = store._get_conn()
            conn.execute(
                """INSERT INTO active_sessions
                   (jti, user_id, username, email, role, ip_address, user_agent, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("cleanup-exp", "uid-c", "c", "c@e.com", "v", "1.1.1.1", "a", time.time() - 200, past),
            )
            conn.commit()
            store._cleanup(conn)
            cursor = conn.execute("SELECT jti FROM active_sessions WHERE jti = ?", ("cleanup-exp",))
            assert cursor.fetchone() is None
            conn.close()

    def test_cleanup_removes_old_revoked(self, session_store):
        """_cleanup で24時間以上経過したrevokedエントリが削除されること"""
        store, test_db = session_store
        old_revoked_at = time.time() - 90000  # 25時間前
        with _patched(store, test_db):
            conn = store._get_conn()
            conn.execute(
                "INSERT INTO revoked_sessions (jti, revoked_at) VALUES (?, ?)",
                ("old-revoked", old_revoked_at),
            )
            conn.commit()
            store._cleanup(conn)
            cursor = conn.execute("SELECT jti FROM revoked_sessions WHERE jti = ?", ("old-revoked",))
            assert cursor.fetchone() is None
            conn.close()

    def test_cleanup_keeps_recent_revoked(self, session_store):
        """_cleanup で24時間以内のrevokedエントリは残ること"""
        store, test_db = session_store
        recent_revoked_at = time.time() - 3600  # 1時間前
        with _patched(store, test_db):
            conn = store._get_conn()
            conn.execute(
                "INSERT INTO revoked_sessions (jti, revoked_at) VALUES (?, ?)",
                ("recent-revoked", recent_revoked_at),
            )
            conn.commit()
            store._cleanup(conn)
            cursor = conn.execute("SELECT jti FROM revoked_sessions WHERE jti = ?", ("recent-revoked",))
            assert cursor.fetchone() is not None
            conn.close()
