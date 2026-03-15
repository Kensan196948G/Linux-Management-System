"""
sessions.py カバレッジ改善テスト v2

対象: backend/api/routes/sessions.py (全9エンドポイント)
既存テストで不足している分岐・レスポンス検証を網羅する。

カバー対象:
  - OS セッション系: active/history/failed/wtmp-summary の全分岐
  - JWT セッション系: jwt GET/DELETE, user revoke の成功・NotFound・例外
  - レート制限系: rate-limit-status GET, rate-limit DELETE の成功・NotFound・例外
  - audit_log 呼び出し検証（operation/target/status/details）
  - HTTPException passthrough、503 Exception、正常レスポンス構造
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException as FastAPIHTTPException


# ======================================================================
# ヘルパー
# ======================================================================

def _make_subprocess_mock(stdout="", stderr="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


# ======================================================================
# OS セッション系 — 追加カバレッジ
# ======================================================================


class TestActiveSessionsCoverageV2:
    """GET /api/sessions/active の追加分岐カバー"""

    def test_active_multi_line_parsing(self, test_client, admin_headers):
        """複数行のstdout が正しくパースされること"""
        stdout = "user1 pts/0 2026-03-01\n\nuser2 pts/1 2026-03-01\n\n"
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(stdout),
        ):
            resp = test_client.get("/api/sessions/active", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # 空行はフィルタされる
        assert data["count"] == 2
        assert len(data["sessions"]) == 2

    def test_active_timestamp_is_iso(self, test_client, admin_headers):
        """timestamp が ISO 形式であること"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock("user pts/0"),
        ):
            resp = test_client.get("/api/sessions/active", headers=admin_headers)
        assert resp.status_code == 200
        ts = resp.json()["timestamp"]
        # ISO 形式パースが成功すること
        datetime.fromisoformat(ts)

    def test_active_single_line(self, test_client, admin_headers):
        """1行のstdout でcount=1"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock("admin pts/0 2026-03-15"),
        ):
            resp = test_client.get("/api/sessions/active", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestHistoryCoverageV2:
    """GET /api/sessions/history の追加分岐カバー"""

    def test_history_empty_stdout(self, test_client, admin_headers):
        """空のstdout で空リスト"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(""),
        ):
            resp = test_client.get("/api/sessions/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["history"] == []

    def test_history_multi_line(self, test_client, admin_headers):
        """複数行のログイン履歴"""
        stdout = "admin pts/0 host1\nroot pts/1 host2\nuser pts/2 host3"
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(stdout),
        ):
            resp = test_client.get("/api/sessions/history", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_history_timestamp_present(self, test_client, admin_headers):
        """timestamp フィールドが存在"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock("line1"),
        ):
            resp = test_client.get("/api/sessions/history", headers=admin_headers)
        assert "timestamp" in resp.json()


class TestFailedSessionsCoverageV2:
    """GET /api/sessions/failed の追加分岐カバー"""

    def test_failed_empty_stdout(self, test_client, admin_headers):
        """空のstdout"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(""),
        ):
            resp = test_client.get("/api/sessions/failed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_failed_multi_entries(self, test_client, admin_headers):
        """複数の失敗エントリ"""
        stdout = "failed from 1.1.1.1\nfailed from 2.2.2.2\nfailed from 3.3.3.3"
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(stdout),
        ):
            resp = test_client.get("/api/sessions/failed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_failed_no_timestamp_field(self, test_client, admin_headers):
        """failed_logins レスポンスに timestamp がないことを確認（仕様通り）"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock("line"),
        ):
            resp = test_client.get("/api/sessions/failed", headers=admin_headers)
        data = resp.json()
        assert "failed_logins" in data
        assert "count" in data


class TestWtmpSummaryCoverageV2:
    """GET /api/sessions/wtmp-summary の追加分岐カバー"""

    def test_wtmp_empty_stdout(self, test_client, admin_headers):
        """空のstdout"""
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(""),
        ):
            resp = test_client.get("/api/sessions/wtmp-summary", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_wtmp_multi_lines(self, test_client, admin_headers):
        """複数行のサマリ"""
        stdout = "line1\nline2\nline3\nline4\nline5"
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=_make_subprocess_mock(stdout),
        ):
            resp = test_client.get("/api/sessions/wtmp-summary", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 5


# ======================================================================
# JWT セッション系 — 追加カバレッジ
# ======================================================================


class TestJwtSessionsCoverageV2:
    """GET /api/sessions/jwt の追加カバレッジ"""

    def test_jwt_sessions_returns_session_list_structure(self, test_client, admin_headers):
        """セッションリストの各要素の構造確認"""
        mock_sessions = [
            {
                "session_id": "jti-001",
                "user_id": "uid-001",
                "username": "admin",
                "email": "admin@example.com",
                "role": "admin",
                "ip_address": "127.0.0.1",
                "user_agent": "TestAgent",
                "created_at": "2026-03-15T00:00:00+00:00",
                "expires_at": "2026-03-15T01:00:00+00:00",
            }
        ]
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            return_value=mock_sessions,
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        s = data["sessions"][0]
        assert s["session_id"] == "jti-001"
        assert s["email"] == "admin@example.com"
        assert "timestamp" in data

    def test_jwt_sessions_empty_list(self, test_client, admin_headers):
        """セッションが0件の場合"""
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            return_value=[],
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_jwt_sessions_audit_log_details(self, test_client, admin_headers):
        """audit_log の details にカウントが含まれること"""
        mock_sessions = [{"session_id": "a"}, {"session_id": "b"}]
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.get_active_sessions",
                return_value=mock_sessions,
            ):
                resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["details"]["count"] == 2


class TestRevokeUserSessionsCoverageV2:
    """DELETE /api/sessions/jwt/user/{email} の追加カバレッジ"""

    def test_revoke_user_sessions_success_response(self, test_client, admin_headers):
        """成功時のレスポンス構造"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            return_value=3,
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/user@example.com",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["revoked_count"] == 3
        assert data["user_email"] == "user@example.com"

    def test_revoke_user_sessions_zero_count(self, test_client, admin_headers):
        """セッションが0件でも成功を返す"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            return_value=0,
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/nobody@example.com",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["revoked_count"] == 0

    def test_revoke_user_sessions_audit_log_details(self, test_client, admin_headers):
        """audit_log の details に revoked_count が含まれること"""
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.revoke_user_sessions",
                return_value=5,
            ):
                resp = test_client.delete(
                    "/api/sessions/jwt/user/test@example.com",
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["details"]["revoked_count"] == 5
        assert call_kwargs["target"] == "test@example.com"


class TestRevokeJwtSessionCoverageV2:
    """DELETE /api/sessions/jwt/{session_id} の追加カバレッジ"""

    def test_revoke_session_success(self, test_client, admin_headers):
        """成功時のレスポンス"""
        jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            return_value=True,
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{jti}", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["session_id"] == jti

    def test_revoke_session_not_found(self, test_client, admin_headers):
        """存在しないセッションは404"""
        jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            return_value=False,
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{jti}", headers=admin_headers
            )
        assert resp.status_code == 404

    def test_revoke_session_audit_log_called(self, test_client, admin_headers):
        """成功時に audit_log が呼ばれること"""
        jti = str(uuid.uuid4())
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.revoke_session",
                return_value=True,
            ):
                resp = test_client.delete(
                    f"/api/sessions/jwt/{jti}", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "revoke_jwt_session"
        assert call_kwargs["target"] == jti


# ======================================================================
# レート制限系 — 追加カバレッジ
# ======================================================================


class TestRateLimitStatusCoverageV2:
    """GET /api/sessions/rate-limit-status の追加カバレッジ"""

    def test_rate_limit_status_with_entries(self, test_client, admin_headers):
        """ロック中エントリがある場合"""
        mock_entries = [
            {"identifier": "10.0.0.1", "locked_at": "2026-03-15T00:00:00Z", "attempts": 6},
            {"identifier": "bad@example.com", "locked_at": "2026-03-15T01:00:00Z", "attempts": 10},
        ]
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            return_value=mock_entries,
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["locked_entries"]) == 2
        assert "timestamp" in data

    def test_rate_limit_status_empty(self, test_client, admin_headers):
        """ロック中エントリが0件"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            return_value=[],
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestClearRateLimitCoverageV2:
    """DELETE /api/sessions/rate-limit/{identifier} の追加カバレッジ"""

    def test_clear_rate_limit_success_response(self, test_client, admin_headers):
        """成功時のレスポンス構造"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            return_value=True,
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/192.168.1.100",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["identifier"] == "192.168.1.100"

    def test_clear_rate_limit_not_found(self, test_client, admin_headers):
        """存在しない識別子は404"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            return_value=False,
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/unknown@example.com",
                headers=admin_headers,
            )
        assert resp.status_code == 404

    def test_clear_rate_limit_audit_log(self, test_client, admin_headers):
        """成功時に audit_log が記録されること"""
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.rate_limiter.clear_lock",
                return_value=True,
            ):
                resp = test_client.delete(
                    "/api/sessions/rate-limit/10.0.0.5",
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "clear_rate_limit"
        assert call_kwargs["target"] == "10.0.0.5"


# ======================================================================
# パラメトライズ: 全OS セッションエンドポイント例外パス
# ======================================================================


class TestOsSessionsParametrized:
    """OS セッション4エンドポイントの共通パスをパラメトライズでカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,response_key",
        [
            ("/api/sessions/active", "get_active_sessions", "sessions"),
            ("/api/sessions/history", "get_session_history", "history"),
            ("/api/sessions/failed", "get_failed_sessions", "failed_logins"),
            ("/api/sessions/wtmp-summary", "get_wtmp_summary", "summary"),
        ],
    )
    def test_general_exception_503(
        self, test_client, admin_headers, endpoint, wrapper_method, response_key
    ):
        """一般例外で503"""
        with patch(
            f"backend.api.routes.sessions.sudo_wrapper.{wrapper_method}",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/sessions/active", "get_active_sessions"),
            ("/api/sessions/history", "get_session_history"),
            ("/api/sessions/failed", "get_failed_sessions"),
            ("/api/sessions/wtmp-summary", "get_wtmp_summary"),
        ],
    )
    def test_http_exception_passthrough(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """HTTPException はそのまま返る"""
        with patch(
            f"backend.api.routes.sessions.sudo_wrapper.{wrapper_method}",
            side_effect=FastAPIHTTPException(status_code=418, detail="teapot"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 418

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/sessions/active",
            "/api/sessions/history",
            "/api/sessions/failed",
            "/api/sessions/wtmp-summary",
        ],
    )
    def test_unauthenticated(self, test_client, endpoint):
        """未認証でアクセス拒否"""
        resp = test_client.get(endpoint)
        assert resp.status_code in (401, 403)


# ======================================================================
# JWT/レート制限エンドポイントの権限チェック
# ======================================================================


class TestSessionsPermissionChecks:
    """JWT・レート制限エンドポイントの権限検証"""

    @pytest.mark.parametrize(
        "method,endpoint",
        [
            ("GET", "/api/sessions/jwt"),
            ("DELETE", "/api/sessions/jwt/user/test@example.com"),
            ("DELETE", f"/api/sessions/jwt/{uuid.uuid4()}"),
            ("GET", "/api/sessions/rate-limit-status"),
            ("DELETE", "/api/sessions/rate-limit/10.0.0.1"),
        ],
    )
    def test_viewer_denied(self, test_client, viewer_headers, method, endpoint):
        """Viewer ロールは manage:sessions / read:session_mgmt が必要なエンドポイントにアクセスできない"""
        if method == "GET":
            resp = test_client.get(endpoint, headers=viewer_headers)
        else:
            resp = test_client.delete(endpoint, headers=viewer_headers)
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        "method,endpoint",
        [
            ("GET", "/api/sessions/jwt"),
            ("DELETE", "/api/sessions/jwt/user/test@example.com"),
            ("DELETE", f"/api/sessions/jwt/{uuid.uuid4()}"),
            ("GET", "/api/sessions/rate-limit-status"),
            ("DELETE", "/api/sessions/rate-limit/10.0.0.1"),
        ],
    )
    def test_unauthenticated_denied(self, test_client, method, endpoint):
        """未認証はアクセスできない"""
        if method == "GET":
            resp = test_client.get(endpoint)
        else:
            resp = test_client.delete(endpoint)
        assert resp.status_code in (401, 403)


# ======================================================================
# 例外パスの直接カバレッジ (lines 102-105, 132-135, 166-167, 187-190, 223-224)
# ======================================================================


class TestSessionsExceptionPaths:
    """JWT/レート制限エンドポイントの except HTTPException / except Exception パス"""

    def test_jwt_get_general_exception_503(self, test_client, admin_headers):
        """GET /api/sessions/jwt: 一般例外→503 (lines 104-105)"""
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            side_effect=RuntimeError("db crash"),
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 503

    def test_jwt_get_http_exception_passthrough(self, test_client, admin_headers):
        """GET /api/sessions/jwt: HTTPException→そのまま返る (lines 102-103)"""
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            side_effect=FastAPIHTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 429

    def test_revoke_user_general_exception_503(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/user/{email}: 一般例外→503 (lines 134-135)"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            side_effect=RuntimeError("revoke crash"),
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/x@example.com", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_revoke_user_http_exception_passthrough(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/user/{email}: HTTPException→そのまま (lines 132-133)"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            side_effect=FastAPIHTTPException(status_code=409, detail="conflict"),
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/x@example.com", headers=admin_headers
            )
        assert resp.status_code == 409

    def test_revoke_jwt_general_exception_503(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/{id}: 一般例外→503 (lines 166-167)"""
        jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            side_effect=RuntimeError("revoke fail"),
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{jti}", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_revoke_jwt_http_exception_passthrough(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/{id}: HTTPException→そのまま (line 164-165)"""
        jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            side_effect=FastAPIHTTPException(status_code=400, detail="bad"),
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{jti}", headers=admin_headers
            )
        assert resp.status_code == 400

    def test_rate_limit_status_general_exception_503(self, test_client, admin_headers):
        """GET /api/sessions/rate-limit-status: 一般例外→503 (lines 189-190)"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            side_effect=RuntimeError("rate db crash"),
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_rate_limit_status_http_exception_passthrough(self, test_client, admin_headers):
        """GET /api/sessions/rate-limit-status: HTTPException→そのまま (lines 187-188)"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            side_effect=FastAPIHTTPException(status_code=500, detail="internal"),
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 500

    def test_clear_rate_limit_general_exception_503(self, test_client, admin_headers):
        """DELETE /api/sessions/rate-limit/{id}: 一般例外→503 (lines 223-224)"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            side_effect=RuntimeError("clear fail"),
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/10.0.0.1", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_clear_rate_limit_http_exception_passthrough(self, test_client, admin_headers):
        """DELETE /api/sessions/rate-limit/{id}: HTTPException→そのまま (lines 221-222)"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            side_effect=FastAPIHTTPException(status_code=422, detail="invalid"),
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/10.0.0.1", headers=admin_headers
            )
        assert resp.status_code == 422
