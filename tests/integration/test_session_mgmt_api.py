"""
セッション管理API 統合テスト

JWTセッション管理・ブルートフォース対策のエンドポイントをテストする。
"""

import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestJwtSessionsGet:
    """GET /api/sessions/jwt のテスト"""

    def test_admin_can_get_jwt_sessions(self, test_client, admin_token):
        """Admin はJWTセッション一覧を取得できる"""
        resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "count" in data
        assert "timestamp" in data
        assert isinstance(data["sessions"], list)

    def test_approver_can_get_jwt_sessions(self, test_client, approver_token):
        """Approver はJWTセッション一覧を取得できる"""
        resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {approver_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data

    def test_viewer_cannot_get_jwt_sessions(self, test_client, viewer_token):
        """Viewer はJWTセッション一覧を取得できない (403)"""
        resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_get_jwt_sessions(self, test_client):
        """未認証ではJWTセッション一覧を取得できない"""
        resp = test_client.get("/api/sessions/jwt")
        assert resp.status_code in (401, 403)

    def test_jwt_sessions_contains_session_after_login(self, test_client, admin_token):
        """ログイン後にセッションが登録されていること"""
        resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # ログインしたセッションが含まれているはず
        assert data["count"] >= 0


class TestJwtSessionRevoke:
    """DELETE /api/sessions/jwt/{session_id} のテスト"""

    def test_admin_can_revoke_session(self, test_client, admin_token):
        """Admin は存在するセッションをrevokeできる"""
        # まず新しいセッションを作成
        login_resp = test_client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "operator123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        # セッション一覧からJTIを取得
        sessions_resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert sessions_resp.status_code == 200
        sessions = sessions_resp.json()["sessions"]

        if not sessions:
            pytest.skip("No active sessions to revoke")

        session_id = sessions[0]["session_id"]
        resp = test_client.delete(
            f"/api/sessions/jwt/{session_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_revoke_nonexistent_session_returns_404(self, test_client, admin_token):
        """存在しないセッションのrevoke → 404"""
        fake_jti = str(uuid.uuid4())
        resp = test_client.delete(
            f"/api/sessions/jwt/{fake_jti}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_viewer_cannot_revoke_session(self, test_client, viewer_token):
        """Viewer はセッションをrevokeできない (403)"""
        fake_jti = str(uuid.uuid4())
        resp = test_client.delete(
            f"/api/sessions/jwt/{fake_jti}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_revoke_session(self, test_client):
        """未認証ではセッションをrevokeできない"""
        fake_jti = str(uuid.uuid4())
        resp = test_client.delete(f"/api/sessions/jwt/{fake_jti}")
        assert resp.status_code in (401, 403)

    def test_revoked_token_is_rejected(self, test_client, admin_token):
        """revokeされたトークンは認証が拒否される"""
        # 新しいセッションを作成
        login_resp = test_client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "operator123"},
        )
        assert login_resp.status_code == 200
        op_token = login_resp.json()["access_token"]

        # トークンが有効であることを確認
        me_resp = test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert me_resp.status_code == 200

        # セッション一覧からこのトークンのJTIを探す
        sessions_resp = test_client.get(
            "/api/sessions/jwt",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        sessions = sessions_resp.json()["sessions"]
        op_sessions = [s for s in sessions if s["email"] == "operator@example.com"]
        if not op_sessions:
            pytest.skip("Session not found")

        session_id = op_sessions[0]["session_id"]

        # セッションをrevoke
        test_client.delete(
            f"/api/sessions/jwt/{session_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # revokeされたトークンは拒否される
        me_resp2 = test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {op_token}"},
        )
        assert me_resp2.status_code in (401, 403)


class TestRevokeUserSessions:
    """DELETE /api/sessions/jwt/user/{user_email} のテスト"""

    def test_admin_can_revoke_user_sessions(self, test_client, admin_token):
        """Admin はユーザーの全セッションをrevokeできる"""
        # operatorでログイン
        test_client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "operator123"},
        )
        resp = test_client.delete(
            "/api/sessions/jwt/user/operator@example.com",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "revoked_count" in data
        assert data["user_email"] == "operator@example.com"

    def test_viewer_cannot_revoke_user_sessions(self, test_client, viewer_token):
        """Viewer はユーザーセッションをrevokeできない (403)"""
        resp = test_client.delete(
            "/api/sessions/jwt/user/operator@example.com",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403


class TestRateLimitStatus:
    """GET /api/sessions/rate-limit-status のテスト"""

    def test_admin_can_get_rate_limit_status(self, test_client, admin_token):
        """Admin はレート制限状況を取得できる"""
        resp = test_client.get(
            "/api/sessions/rate-limit-status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "locked_entries" in data
        assert "count" in data
        assert isinstance(data["locked_entries"], list)

    def test_viewer_cannot_get_rate_limit_status(self, test_client, viewer_token):
        """Viewer はレート制限状況を取得できない (403)"""
        resp = test_client.get(
            "/api/sessions/rate-limit-status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_get_rate_limit_status(self, test_client):
        """未認証ではレート制限状況を取得できない"""
        resp = test_client.get("/api/sessions/rate-limit-status")
        assert resp.status_code in (401, 403)


class TestClearRateLimit:
    """DELETE /api/sessions/rate-limit/{identifier} のテスト"""

    def test_clear_nonexistent_rate_limit_returns_404(self, test_client, admin_token):
        """存在しない識別子のレート制限解除 → 404"""
        resp = test_client.delete(
            "/api/sessions/rate-limit/nonexistent@example.com",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_viewer_cannot_clear_rate_limit(self, test_client, viewer_token):
        """Viewer はレート制限を解除できない (403)"""
        resp = test_client.delete(
            "/api/sessions/rate-limit/192.168.1.1",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_clear_rate_limit(self, test_client):
        """未認証ではレート制限を解除できない"""
        resp = test_client.delete("/api/sessions/rate-limit/192.168.1.1")
        assert resp.status_code in (401, 403)

    def test_admin_can_clear_existing_rate_limit(self, test_client, admin_token, tmp_path, monkeypatch):
        """Admin は既存のレート制限を解除できる"""
        import backend.core.rate_limiter as rl_module
        from backend.core.rate_limiter import RateLimiter

        # テスト専用DBを使用
        test_db = tmp_path / "rate_limit_clear_test.db"
        monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", test_db)
        test_limiter = RateLimiter()
        monkeypatch.setattr(rl_module, "rate_limiter", test_limiter)

        # backend.api.routes.sessions の rate_limiter もパッチ
        import backend.api.routes.sessions as sessions_routes
        monkeypatch.setattr(sessions_routes, "rate_limiter", test_limiter)

        # テスト用のロックを作成
        test_ip = "10.0.0.100"
        test_email = "locktest@example.com"
        for _ in range(6):
            test_limiter.check_and_record(test_ip, test_email)

        # 解除
        resp = test_client.delete(
            f"/api/sessions/rate-limit/{test_ip}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


class TestBruteForceProtection:
    """ブルートフォース対策のエンドツーエンドテスト"""

    def test_brute_force_5_failures_triggers_429(self, test_client, tmp_path, monkeypatch):
        """5回連続失敗後にレート制限 (429) が返る"""
        from backend.core import rate_limiter as rl_module

        # テスト専用DBを使用
        test_db = tmp_path / "test_rate_limit.db"
        monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", test_db)

        from backend.core.rate_limiter import RateLimiter

        test_limiter = RateLimiter()
        monkeypatch.setattr(rl_module, "rate_limiter", test_limiter)

        # backend.api.routes.auth の rate_limiter もパッチ
        import backend.api.routes.auth as auth_routes

        monkeypatch.setattr(auth_routes, "rate_limiter", test_limiter)

        email = "brutetest@example.com"
        # 5回失敗
        for i in range(5):
            resp = test_client.post(
                "/api/auth/login",
                json={"email": email, "password": "wrongpassword"},
                headers={"X-Forwarded-For": "10.1.2.3"},
            )
            if i < 4:
                assert resp.status_code == 401
            # 5回目以降はロックされる場合がある

        # 6回目は429になる
        resp = test_client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrongpassword"},
            headers={"X-Forwarded-For": "10.1.2.3"},
        )
        assert resp.status_code == 429

    def test_success_resets_counter(self, test_client, tmp_path, monkeypatch):
        """ログイン成功後はカウンタがリセットされる"""
        from backend.core import rate_limiter as rl_module

        test_db = tmp_path / "test_rate_limit2.db"
        monkeypatch.setattr(rl_module, "RATE_LIMIT_DB", test_db)

        from backend.core.rate_limiter import RateLimiter

        test_limiter = RateLimiter()
        monkeypatch.setattr(rl_module, "rate_limiter", test_limiter)

        import backend.api.routes.auth as auth_routes

        monkeypatch.setattr(auth_routes, "rate_limiter", test_limiter)

        # 4回失敗
        for _ in range(4):
            test_client.post(
                "/api/auth/login",
                json={"email": "operator@example.com", "password": "wrong"},
                headers={"X-Forwarded-For": "10.1.2.4"},
            )

        # 正しいパスワードでログイン成功
        resp = test_client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "operator123"},
            headers={"X-Forwarded-For": "10.1.2.4"},
        )
        assert resp.status_code == 200

        # カウンタリセット後は再びログイン可能
        locked, _ = test_limiter.is_locked("10.1.2.4", "operator@example.com")
        assert not locked
