"""
Tier 4 小モジュール群 カバレッジ改善テスト

対象:
  - backend/api/routes/dhcp.py
  - backend/api/routes/bind.py
  - backend/api/routes/netstat.py
  - backend/api/routes/mysql.py
  - backend/api/routes/sessions.py
  - backend/api/routes/routing.py
  - backend/api/routes/sensors.py

既存テストで不足しているパス（audit_log, HTTPException reraise,
error detail, parametrize バリエーション等）を網羅する。
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException as FastAPIHTTPException

from backend.core.sudo_wrapper import SudoWrapperError


# ======================================================================
# BIND DNS - 追加カバレッジ
# ======================================================================


class TestBindAuditLogCoverage:
    """BIND エンドポイントの audit_log パスをカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/bind/status", "get_bind_status", "bind_status_view"),
            ("/api/bind/zones", "get_bind_zones", "bind_zones_view"),
            ("/api/bind/config", "get_bind_config", "bind_config_view"),
            ("/api/bind/logs", "get_bind_logs", "bind_logs_view"),
        ],
    )
    def test_audit_log_success(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """正常時に audit_log が success で呼ばれること"""
        mock_data = {"status": "running", "data": "ok"}
        with patch(
            f"backend.api.routes.bind.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.bind.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][0] == audit_op
        assert mock_audit.record.call_args[0][3] == "success"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/bind/status", "get_bind_status", "bind_status_view"),
            ("/api/bind/zones", "get_bind_zones", "bind_zones_view"),
            ("/api/bind/config", "get_bind_config", "bind_config_view"),
            ("/api/bind/logs", "get_bind_logs", "bind_logs_view"),
        ],
    )
    def test_audit_log_failure(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """SudoWrapperError 時に audit_log が failure で呼ばれること"""
        with patch(
            f"backend.api.routes.bind.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("test error"),
        ):
            with patch("backend.api.routes.bind.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][3] == "failure"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/bind/status", "get_bind_status"),
            ("/api/bind/zones", "get_bind_zones"),
            ("/api/bind/config", "get_bind_config"),
            ("/api/bind/logs", "get_bind_logs"),
        ],
    )
    def test_error_detail_contains_message(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError のメッセージが detail/message に含まれること"""
        with patch(
            f"backend.api.routes.bind.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("specific bind error msg"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", "") or body.get("message", "")
        assert "specific bind error msg" in msg


class TestBindLogsValidationExtra:
    """BIND logs lines パラメータの追加バリデーションテスト"""

    @pytest.mark.parametrize("lines_val", [-1, "abc", "50.5", 10000])
    def test_logs_invalid_lines(self, test_client, admin_headers, lines_val):
        """不正な lines 値は 422"""
        resp = test_client.get(
            f"/api/bind/logs?lines={lines_val}", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_logs_lines_min_boundary(self, test_client, admin_headers):
        """lines=1 は正常"""
        mock_data = {"logs": "", "lines": 1}
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get(
                "/api/bind/logs?lines=1", headers=admin_headers
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=1)

    def test_logs_lines_max_boundary(self, test_client, admin_headers):
        """lines=200 は正常"""
        mock_data = {"logs": "", "lines": 200}
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get(
                "/api/bind/logs?lines=200", headers=admin_headers
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=200)

    def test_logs_default_lines_50(self, test_client, admin_headers):
        """デフォルト lines=50 で呼ばれること"""
        mock_data = {"logs": "", "lines": 50}
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get("/api/bind/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=50)


class TestBindAuthExtra:
    """BIND 認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/bind/status",
            "/api/bind/zones",
            "/api/bind/config",
            "/api/bind/logs",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/bind/status",
            "/api/bind/zones",
            "/api/bind/config",
            "/api/bind/logs",
        ],
    )
    def test_missing_bearer_prefix(self, test_client, endpoint):
        """Bearer プレフィックスなしは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "some_token"}
        )
        assert resp.status_code in (401, 403)


# ======================================================================
# Netstat - 追加カバレッジ
# ======================================================================


class TestNetstatAuditLogCoverage:
    """Netstat エンドポイントの audit_log パスをカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/netstat/connections", "get_netstat_connections", "netstat_connections_view"),
            ("/api/netstat/listening", "get_netstat_listening", "netstat_listening_view"),
            ("/api/netstat/stats", "get_netstat_stats", "netstat_stats_view"),
            ("/api/netstat/routes", "get_netstat_routes", "netstat_routes_view"),
        ],
    )
    def test_audit_log_success(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """正常時に audit_log が success で呼ばれること"""
        mock_data = {"data": "ok", "tool": "ss"}
        with patch(
            f"backend.api.routes.netstat.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.netstat.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][0] == audit_op
        assert mock_audit.record.call_args[0][3] == "success"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/netstat/connections", "get_netstat_connections", "netstat_connections_view"),
            ("/api/netstat/listening", "get_netstat_listening", "netstat_listening_view"),
            ("/api/netstat/stats", "get_netstat_stats", "netstat_stats_view"),
            ("/api/netstat/routes", "get_netstat_routes", "netstat_routes_view"),
        ],
    )
    def test_audit_log_failure(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """SudoWrapperError 時に audit_log が failure で呼ばれること"""
        with patch(
            f"backend.api.routes.netstat.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("test error"),
        ):
            with patch("backend.api.routes.netstat.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][3] == "failure"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/netstat/connections", "get_netstat_connections"),
            ("/api/netstat/listening", "get_netstat_listening"),
            ("/api/netstat/stats", "get_netstat_stats"),
            ("/api/netstat/routes", "get_netstat_routes"),
        ],
    )
    def test_error_detail_contains_message(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            f"backend.api.routes.netstat.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("netstat specific error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", "") or body.get("message", "")
        assert "netstat specific error" in msg


class TestNetstatAuthExtra:
    """Netstat 認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/netstat/connections",
            "/api/netstat/listening",
            "/api/netstat/stats",
            "/api/netstat/routes",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.token"}
        )
        assert resp.status_code in (401, 403)


class TestNetstatResponseStructure:
    """Netstat レスポンス構造の追加テスト"""

    def test_connections_response_structure(self, test_client, admin_headers):
        """connections レスポンスに success と data が含まれること"""
        mock_data = {"connections": "tcp 0.0.0.0:22\n", "tool": "ss", "count": 1}
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_connections",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/netstat/connections", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body
        assert body["data"]["tool"] == "ss"

    def test_listening_response_structure(self, test_client, admin_headers):
        """listening レスポンスに success と data が含まれること"""
        mock_data = {"listening": "tcp LISTEN 0.0.0.0:80\n", "tool": "ss"}
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_listening",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/netstat/listening", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_stats_response_structure(self, test_client, admin_headers):
        """stats レスポンスに success と data が含まれること"""
        mock_data = {"stats": "TCP: 10 total\n", "tool": "ss"}
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_stats",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/netstat/stats", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_routes_response_structure(self, test_client, admin_headers):
        """routes レスポンスに success と data が含まれること"""
        mock_data = {"routes": "default via 10.0.0.1\n", "tool": "ip"}
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_routes",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/netstat/routes", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True


# ======================================================================
# MySQL - 追加カバレッジ
# ======================================================================


class TestMysqlAuditLogCoverage:
    """MySQL エンドポイントの audit_log パスをカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/mysql/status", "get_mysql_status", "mysql_status_view"),
            ("/api/mysql/databases", "get_mysql_databases", "mysql_databases_view"),
            ("/api/mysql/users", "get_mysql_users", "mysql_users_view"),
            ("/api/mysql/processes", "get_mysql_processes", "mysql_processes_view"),
            ("/api/mysql/variables", "get_mysql_variables", "mysql_variables_view"),
            ("/api/mysql/logs", "get_mysql_logs", "mysql_logs_view"),
        ],
    )
    def test_audit_log_success(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """正常時に audit_log が success で呼ばれること"""
        mock_data = {"status": "running", "data": "ok"}
        with patch(
            f"backend.api.routes.mysql.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.mysql.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][0] == audit_op
        assert mock_audit.record.call_args[0][3] == "success"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/mysql/status", "get_mysql_status", "mysql_status_view"),
            ("/api/mysql/databases", "get_mysql_databases", "mysql_databases_view"),
            ("/api/mysql/users", "get_mysql_users", "mysql_users_view"),
            ("/api/mysql/processes", "get_mysql_processes", "mysql_processes_view"),
            ("/api/mysql/variables", "get_mysql_variables", "mysql_variables_view"),
            ("/api/mysql/logs", "get_mysql_logs", "mysql_logs_view"),
        ],
    )
    def test_audit_log_failure(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """SudoWrapperError 時に audit_log が failure で呼ばれること"""
        with patch(
            f"backend.api.routes.mysql.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("mysql test error"),
        ):
            with patch("backend.api.routes.mysql.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][3] == "failure"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/mysql/status", "get_mysql_status"),
            ("/api/mysql/databases", "get_mysql_databases"),
            ("/api/mysql/users", "get_mysql_users"),
            ("/api/mysql/processes", "get_mysql_processes"),
            ("/api/mysql/variables", "get_mysql_variables"),
            ("/api/mysql/logs", "get_mysql_logs"),
        ],
    )
    def test_error_detail_contains_message(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            f"backend.api.routes.mysql.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("mysql specific error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", "") or body.get("message", "")
        assert "mysql specific error" in msg


class TestMysqlLogsValidationExtra:
    """MySQL logs lines パラメータの追加バリデーションテスト"""

    @pytest.mark.parametrize("lines_val", [-1, 0, "abc", "50.5", 10000])
    def test_logs_invalid_lines(self, test_client, admin_headers, lines_val):
        """不正な lines 値は 422"""
        resp = test_client.get(
            f"/api/mysql/logs?lines={lines_val}", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_logs_lines_min_boundary(self, test_client, admin_headers):
        """lines=1 は正常"""
        mock_data = {"logs": "", "lines": 1}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get(
                "/api/mysql/logs?lines=1", headers=admin_headers
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=1)

    def test_logs_lines_max_boundary(self, test_client, admin_headers):
        """lines=200 は正常"""
        mock_data = {"logs": "", "lines": 200}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get(
                "/api/mysql/logs?lines=200", headers=admin_headers
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=200)

    def test_logs_default_lines_50(self, test_client, admin_headers):
        """デフォルト lines=50 で呼ばれること"""
        mock_data = {"logs": "", "lines": 50}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get("/api/mysql/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=50)


class TestMysqlAuthExtra:
    """MySQL 認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/mysql/status",
            "/api/mysql/databases",
            "/api/mysql/users",
            "/api/mysql/processes",
            "/api/mysql/variables",
            "/api/mysql/logs",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.token"}
        )
        assert resp.status_code in (401, 403)


class TestMysqlResponseData:
    """MySQL レスポンスデータの追加テスト"""

    def test_databases_empty_list(self, test_client, admin_headers):
        """データベースが空でも正常"""
        mock_data = {"databases": []}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_databases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/mysql/databases", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["databases"] == []

    def test_users_empty_list(self, test_client, admin_headers):
        """ユーザーが空でも正常"""
        mock_data = {"users": []}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_users",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/mysql/users", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["users"] == []

    def test_processes_empty_list(self, test_client, admin_headers):
        """プロセスが空でも正常"""
        mock_data = {"processes": []}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_processes",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/mysql/processes", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["processes"] == []

    def test_variables_complex_data(self, test_client, admin_headers):
        """複雑な変数データも正常に返る"""
        mock_data = {
            "variables": {
                "version": "8.0.33",
                "max_connections": "151",
                "innodb_buffer_pool_size": "134217728",
                "character_set_server": "utf8mb4",
                "collation_server": "utf8mb4_0900_ai_ci",
            }
        }
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_variables",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/mysql/variables", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["variables"]["max_connections"] == "151"

    def test_logs_large_output(self, test_client, admin_headers):
        """大量のログ出力でも正常"""
        large_logs = "\n".join([f"2026-01-01T00:00:{i:02d} MySQL event" for i in range(60)])
        mock_data = {"logs": large_logs, "lines": 200}
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_logs",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/mysql/logs?lines=200", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# Sessions - 追加カバレッジ
# ======================================================================


class TestSessionsJwtExceptionCoverage:
    """JWT セッション管理エンドポイントの例外パスをカバー"""

    def test_jwt_sessions_503_on_exception(self, test_client, admin_headers):
        """GET /api/sessions/jwt で例外時に 503"""
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            side_effect=Exception("session store error"),
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 503

    def test_jwt_sessions_http_exception_passthrough(self, test_client, admin_headers):
        """GET /api/sessions/jwt で HTTPException がそのまま返ること"""
        with patch(
            "backend.api.routes.sessions.session_store.get_active_sessions",
            side_effect=FastAPIHTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 429

    def test_revoke_user_sessions_503_on_exception(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/user/{email} で例外時に 503"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            side_effect=Exception("revoke error"),
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/test@example.com", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_revoke_user_sessions_http_exception_passthrough(
        self, test_client, admin_headers
    ):
        """DELETE /api/sessions/jwt/user/{email} で HTTPException がそのまま返ること"""
        with patch(
            "backend.api.routes.sessions.session_store.revoke_user_sessions",
            side_effect=FastAPIHTTPException(status_code=409, detail="conflict"),
        ):
            resp = test_client.delete(
                "/api/sessions/jwt/user/test@example.com", headers=admin_headers
            )
        assert resp.status_code == 409

    def test_revoke_jwt_session_503_on_exception(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/{id} で例外時に 503"""
        fake_jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            side_effect=Exception("revoke error"),
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{fake_jti}", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_revoke_jwt_session_http_exception_passthrough(
        self, test_client, admin_headers
    ):
        """DELETE /api/sessions/jwt/{id} で HTTPException がそのまま返ること"""
        fake_jti = str(uuid.uuid4())
        with patch(
            "backend.api.routes.sessions.session_store.revoke_session",
            side_effect=FastAPIHTTPException(status_code=400, detail="bad request"),
        ):
            resp = test_client.delete(
                f"/api/sessions/jwt/{fake_jti}", headers=admin_headers
            )
        assert resp.status_code == 400


class TestSessionsRateLimitExceptionCoverage:
    """レート制限エンドポイントの例外パスをカバー"""

    def test_rate_limit_status_503_on_exception(self, test_client, admin_headers):
        """GET /api/sessions/rate-limit-status で例外時に 503"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            side_effect=Exception("db error"),
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_rate_limit_status_http_exception_passthrough(
        self, test_client, admin_headers
    ):
        """GET /api/sessions/rate-limit-status で HTTPException がそのまま返ること"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.get_all_locked",
            side_effect=FastAPIHTTPException(status_code=500, detail="internal"),
        ):
            resp = test_client.get(
                "/api/sessions/rate-limit-status", headers=admin_headers
            )
        assert resp.status_code == 500

    def test_clear_rate_limit_503_on_exception(self, test_client, admin_headers):
        """DELETE /api/sessions/rate-limit/{id} で例外時に 503"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            side_effect=Exception("db error"),
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/10.0.0.1", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_clear_rate_limit_http_exception_passthrough(
        self, test_client, admin_headers
    ):
        """DELETE /api/sessions/rate-limit/{id} で HTTPException がそのまま返ること"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            side_effect=FastAPIHTTPException(status_code=422, detail="invalid"),
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/10.0.0.1", headers=admin_headers
            )
        assert resp.status_code == 422

    def test_clear_rate_limit_success(self, test_client, admin_headers):
        """DELETE /api/sessions/rate-limit/{id} で成功時のレスポンス"""
        with patch(
            "backend.api.routes.sessions.rate_limiter.clear_lock",
            return_value=True,
        ):
            resp = test_client.delete(
                "/api/sessions/rate-limit/10.0.0.1", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["identifier"] == "10.0.0.1"


class TestSessionsOsSessionsExtraCoverage:
    """OS セッションエンドポイント（active/history/failed/wtmp）の追加カバレッジ"""

    @pytest.mark.parametrize(
        "endpoint,response_key",
        [
            ("/api/sessions/active", "sessions"),
            ("/api/sessions/history", "history"),
            ("/api/sessions/failed", "failed_logins"),
            ("/api/sessions/wtmp-summary", "summary"),
        ],
    )
    def test_viewer_role_access(
        self, test_client, viewer_headers, endpoint, response_key
    ):
        """viewer ロールでもOSセッション情報取得可能"""
        mock_result = {"stdout": "user pts/0\n", "stderr": "", "returncode": 0}
        with patch(
            "backend.core.sudo_wrapper.subprocess.run",
            return_value=MagicMock(stdout="user pts/0\n", stderr="", returncode=0),
        ):
            resp = test_client.get(endpoint, headers=viewer_headers)
        # read:sessions 権限がない場合は 403
        assert resp.status_code in (200, 403)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/sessions/active",
            "/api/sessions/history",
            "/api/sessions/failed",
            "/api/sessions/wtmp-summary",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.token"}
        )
        assert resp.status_code in (401, 403)


class TestSessionsJwtAuditLogCoverage:
    """JWT セッション操作の audit_log パスをカバー"""

    def test_list_jwt_sessions_audit_log(self, test_client, admin_headers):
        """GET /api/sessions/jwt で audit_log が記録されること"""
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.get_active_sessions",
                return_value=[],
            ):
                resp = test_client.get("/api/sessions/jwt", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "list_jwt_sessions"
        assert call_kwargs["status"] == "success"

    def test_revoke_user_sessions_audit_log(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/user/{email} で audit_log が記録されること"""
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.revoke_user_sessions",
                return_value=2,
            ):
                resp = test_client.delete(
                    "/api/sessions/jwt/user/test@example.com",
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "revoke_user_sessions"
        assert call_kwargs["target"] == "test@example.com"

    def test_revoke_jwt_session_audit_log(self, test_client, admin_headers):
        """DELETE /api/sessions/jwt/{id} で audit_log が記録されること"""
        fake_jti = str(uuid.uuid4())
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.session_store.revoke_session",
                return_value=True,
            ):
                resp = test_client.delete(
                    f"/api/sessions/jwt/{fake_jti}",
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "revoke_jwt_session"

    def test_clear_rate_limit_audit_log(self, test_client, admin_headers):
        """DELETE /api/sessions/rate-limit/{id} で audit_log が記録されること"""
        with patch("backend.api.routes.sessions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.sessions.rate_limiter.clear_lock",
                return_value=True,
            ):
                resp = test_client.delete(
                    "/api/sessions/rate-limit/10.0.0.1",
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "clear_rate_limit"


# ======================================================================
# Routing - 追加カバレッジ
# ======================================================================


class TestRoutingAuditLogCoverage:
    """Routing エンドポイントの audit_log パスをカバー（attempt/success/denied/failure）"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op,data_key",
        [
            ("/api/routing/routes", "get_routing_routes", "routing_routes", "routes"),
            ("/api/routing/gateways", "get_routing_gateways", "routing_gateways", "gateways"),
            ("/api/routing/arp", "get_routing_arp", "routing_arp", "arp"),
            ("/api/routing/interfaces", "get_routing_interfaces", "routing_interfaces", "interfaces"),
        ],
    )
    def test_audit_log_attempt_and_success(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op, data_key
    ):
        """正常時に audit_log が attempt -> success の順で呼ばれること"""
        mock_output = json.dumps({
            "status": "success",
            data_key: [{"item": "test"}],
            "timestamp": "2026-01-01T00:00:00Z",
        })
        mock_result = {"status": "success", "output": mock_output}
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            return_value=mock_result,
        ):
            with patch("backend.api.routes.routing.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        calls = mock_audit.record.call_args_list
        # attempt が最初
        assert calls[0][1]["status"] == "attempt"
        assert calls[0][1]["operation"] == audit_op
        # success が最後
        assert calls[-1][1]["status"] == "success"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/routing/routes", "get_routing_routes", "routing_routes"),
            ("/api/routing/gateways", "get_routing_gateways", "routing_gateways"),
            ("/api/routing/arp", "get_routing_arp", "routing_arp"),
            ("/api/routing/interfaces", "get_routing_interfaces", "routing_interfaces"),
        ],
    )
    def test_audit_log_attempt_and_failure(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """SudoWrapperError 時に audit_log が attempt -> failure の順で呼ばれること"""
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("routing error"),
        ):
            with patch("backend.api.routes.routing.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 500
        calls = mock_audit.record.call_args_list
        assert calls[0][1]["status"] == "attempt"
        assert calls[-1][1]["status"] == "failure"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/routing/routes", "get_routing_routes", "routing_routes"),
            ("/api/routing/gateways", "get_routing_gateways", "routing_gateways"),
            ("/api/routing/arp", "get_routing_arp", "routing_arp"),
            ("/api/routing/interfaces", "get_routing_interfaces", "routing_interfaces"),
        ],
    )
    def test_audit_log_attempt_and_denied(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """status=error 時に audit_log が attempt -> denied の順で呼ばれること"""
        mock_output = json.dumps({
            "status": "error",
            "message": "command failed",
        })
        mock_result = {"status": "error", "output": mock_output, "message": "command failed"}
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            return_value=mock_result,
        ):
            with patch("backend.api.routes.routing.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        calls = mock_audit.record.call_args_list
        assert calls[0][1]["status"] == "attempt"
        assert calls[-1][1]["status"] == "denied"


class TestRoutingErrorDetails:
    """Routing エンドポイントのエラー詳細をカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/routing/routes", "get_routing_routes"),
            ("/api/routing/gateways", "get_routing_gateways"),
            ("/api/routing/arp", "get_routing_arp"),
            ("/api/routing/interfaces", "get_routing_interfaces"),
        ],
    )
    def test_wrapper_error_detail(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("specific routing error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 500
        body = resp.json()
        msg = body.get("detail", "") or body.get("message", "")
        assert "specific routing error" in msg

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/routing/routes", "get_routing_routes"),
            ("/api/routing/gateways", "get_routing_gateways"),
            ("/api/routing/arp", "get_routing_arp"),
            ("/api/routing/interfaces", "get_routing_interfaces"),
        ],
    )
    def test_service_error_detail(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """status=error 時の detail メッセージが正しいこと"""
        mock_result = {"status": "error", "message": "service unavailable message"}
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            return_value=mock_result,
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503


class TestRoutingAuthExtra:
    """Routing 認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/routing/routes",
            "/api/routing/gateways",
            "/api/routing/arp",
            "/api/routing/interfaces",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.tok.en"}
        )
        assert resp.status_code in (401, 403)

    def test_admin_can_read_gateways(self, test_client, admin_headers):
        """admin でゲートウェイ取得可能"""
        mock_output = json.dumps({
            "status": "success",
            "gateways": [],
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_routing_gateways",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/routing/gateways", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_read_arp(self, test_client, admin_headers):
        """admin で ARP テーブル取得可能"""
        mock_output = json.dumps({
            "status": "success",
            "arp": [],
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_routing_arp",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/routing/arp", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# Sensors - 追加カバレッジ
# ======================================================================


class TestSensorsAuditLogCoverage:
    """Sensors エンドポイントの audit_log パスをカバー（attempt/success/denied/failure）"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op,data_key",
        [
            ("/api/sensors/all", "get_sensors_all", "sensors_all", "sensors"),
            ("/api/sensors/temperature", "get_sensors_temperature", "sensors_temperature", "temperature"),
            ("/api/sensors/fans", "get_sensors_fans", "sensors_fans", "fans"),
            ("/api/sensors/voltage", "get_sensors_voltage", "sensors_voltage", "voltage"),
        ],
    )
    def test_audit_log_attempt_and_success(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op, data_key
    ):
        """正常時に audit_log が attempt -> success の順で呼ばれること"""
        mock_output = json.dumps({
            "status": "success",
            "source": "lm-sensors",
            data_key: {"chip": {"temp": 45.0}},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        mock_result = {"status": "success", "output": mock_output}
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            return_value=mock_result,
        ):
            with patch("backend.api.routes.sensors.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        calls = mock_audit.record.call_args_list
        assert calls[0][1]["status"] == "attempt"
        assert calls[-1][1]["status"] == "success"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/sensors/all", "get_sensors_all", "sensors_all"),
            ("/api/sensors/temperature", "get_sensors_temperature", "sensors_temperature"),
            ("/api/sensors/fans", "get_sensors_fans", "sensors_fans"),
            ("/api/sensors/voltage", "get_sensors_voltage", "sensors_voltage"),
        ],
    )
    def test_audit_log_attempt_and_failure(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """SudoWrapperError 時に audit_log が attempt -> failure の順で呼ばれること"""
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("sensor error"),
        ):
            with patch("backend.api.routes.sensors.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 500
        calls = mock_audit.record.call_args_list
        assert calls[0][1]["status"] == "attempt"
        assert calls[-1][1]["status"] == "failure"

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,audit_op",
        [
            ("/api/sensors/all", "get_sensors_all", "sensors_all"),
            ("/api/sensors/temperature", "get_sensors_temperature", "sensors_temperature"),
            ("/api/sensors/fans", "get_sensors_fans", "sensors_fans"),
            ("/api/sensors/voltage", "get_sensors_voltage", "sensors_voltage"),
        ],
    )
    def test_audit_log_attempt_and_denied(
        self, test_client, admin_headers, endpoint, wrapper_method, audit_op
    ):
        """status=error 時に audit_log が attempt -> denied の順で呼ばれること"""
        mock_output = json.dumps({
            "status": "error",
            "message": "sensors command failed",
        })
        mock_result = {"status": "error", "output": mock_output, "message": "sensors command failed"}
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            return_value=mock_result,
        ):
            with patch("backend.api.routes.sensors.audit_log") as mock_audit:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        calls = mock_audit.record.call_args_list
        assert calls[0][1]["status"] == "attempt"
        assert calls[-1][1]["status"] == "denied"


class TestSensorsErrorDetails:
    """Sensors エンドポイントのエラー詳細をカバー"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/sensors/all", "get_sensors_all"),
            ("/api/sensors/temperature", "get_sensors_temperature"),
            ("/api/sensors/fans", "get_sensors_fans"),
            ("/api/sensors/voltage", "get_sensors_voltage"),
        ],
    )
    def test_wrapper_error_detail(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            f"backend.core.sudo_wrapper.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("sensor specific error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 500
        body = resp.json()
        msg = body.get("detail", "") or body.get("message", "")
        assert "sensor specific error" in msg


class TestSensorsAuthExtra:
    """Sensors 認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/sensors/all",
            "/api/sensors/temperature",
            "/api/sensors/fans",
            "/api/sensors/voltage",
        ],
    )
    def test_invalid_token_rejected(self, test_client, endpoint):
        """無効なトークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer invalid.tok.en"}
        )
        assert resp.status_code in (401, 403)

    def test_admin_can_read_fans(self, test_client, admin_headers):
        """admin でファン情報取得可能"""
        mock_output = json.dumps({
            "status": "success",
            "source": "lm-sensors",
            "fans": {"chip": {"fan1": 1200}},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sensors_fans",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/sensors/fans", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_read_voltage(self, test_client, admin_headers):
        """admin で電圧情報取得可能"""
        mock_output = json.dumps({
            "status": "success",
            "source": "lm-sensors",
            "voltage": {"chip": {"in0": 0.836}},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sensors_voltage",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/sensors/voltage", headers=admin_headers)
        assert resp.status_code == 200


class TestSensorsResponseStructure:
    """Sensors レスポンス構造の追加テスト"""

    def test_all_response_has_source(self, test_client, admin_headers):
        """all レスポンスに source が含まれること"""
        mock_output = json.dumps({
            "status": "success",
            "source": "lm-sensors",
            "sensors": {},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sensors_all",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/sensors/all", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "lm-sensors"

    def test_temperature_response_has_source(self, test_client, admin_headers):
        """temperature レスポンスに source が含まれること"""
        mock_output = json.dumps({
            "status": "success",
            "source": "thermal_zone",
            "temperature": {},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sensors_temperature",
            return_value={"status": "success", "output": mock_output},
        ):
            resp = test_client.get("/api/sensors/temperature", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "thermal_zone"


# ======================================================================
# _utils.py parse_wrapper_result - カバレッジ
# ======================================================================


class TestParseWrapperResult:
    """parse_wrapper_result ユーティリティのカバレッジ"""

    def test_valid_json_output(self):
        """output が有効な JSON 文字列の場合パースされること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "output": '{"key": "value"}'}
        parsed = parse_wrapper_result(result)
        assert parsed == {"key": "value"}

    def test_invalid_json_output(self):
        """output が無効な JSON の場合 result がそのまま返ること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "output": "not json"}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_no_output_field(self):
        """output フィールドがない場合 result がそのまま返ること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "data": "something"}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_empty_string_output(self):
        """output が空文字列の場合 result がそのまま返ること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "output": ""}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_none_output(self):
        """output が None の場合 result がそのまま返ること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "output": None}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_non_string_output(self):
        """output が文字列でない場合 result がそのまま返ること"""
        from backend.api.routes._utils import parse_wrapper_result

        result = {"status": "success", "output": 42}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_nested_json_output(self):
        """ネストされた JSON が正しくパースされること"""
        from backend.api.routes._utils import parse_wrapper_result

        nested = {"status": "success", "routes": [{"dst": "default", "via": "10.0.0.1"}], "timestamp": "2026-01-01T00:00:00Z"}
        result = {"status": "success", "output": json.dumps(nested)}
        parsed = parse_wrapper_result(result)
        assert parsed["routes"][0]["via"] == "10.0.0.1"
