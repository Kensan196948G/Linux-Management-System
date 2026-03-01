"""
PostgreSQL 管理モジュール - 統合テスト

テストケース数: 18件
- 正常系: status/databases/users/activity/config/logs エンドポイント
- unavailable 系: PostgreSQL 未インストール環境
- 異常系: 権限不足、未認証、SudoWrapperError
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

PG_STATUS_OK = {
    "status": "success",
    "service": "postgresql",
    "active": "active",
    "enabled": "enabled",
    "version": "PostgreSQL 15.3 (Ubuntu 15.3-1.pgdg22.04+1) on x86_64",
    "ready": "accepting connections",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_STATUS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "PostgreSQL is not installed",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_DATABASES_OK = {
    "status": "success",
    "databases_raw": "postgres|8192 bytes|en_US.UTF-8|en_US.UTF-8\ntemplate0|8192 bytes|en_US.UTF-8|en_US.UTF-8",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_DATABASES_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Cannot connect to PostgreSQL",
    "databases_raw": "",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_USERS_OK = {
    "status": "success",
    "users_raw": "postgres|t|t|t|t|-1\npg_monitor|f|f|f|f|-1",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_USERS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Cannot connect to PostgreSQL",
    "users_raw": "",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_ACTIVITY_OK = {
    "status": "success",
    "activity_raw": "12345|postgres|psql|127.0.0.1|idle|SELECT 1",
    "connection_count": 3,
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_ACTIVITY_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Cannot connect to PostgreSQL",
    "activity_raw": "",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_CONFIG_OK = {
    "status": "success",
    "config_raw": "max_connections|100||Sets the maximum number of concurrent connections.\nlisten_addresses|localhost||Sets the host name or IP address(es) to listen to.",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_CONFIG_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Cannot connect to PostgreSQL",
    "config_raw": "",
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_LOGS_OK = {
    "status": "success",
    "logs": "2026-03-01 00:00:00 UTC [1234]: LOG: database system is ready to accept connections",
    "lines": 50,
    "timestamp": "2026-03-01T00:00:00Z",
}

PG_LOGS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "PostgreSQL is not installed",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestPostgreSQLStatus:
    """TC_PGS_001〜003: PostgreSQL status エンドポイントテスト"""

    def test_TC_PGS_001_status_ok(self, test_client, admin_token):
        """TC_PGS_001: PostgreSQL 正常稼働時のステータス取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_status", return_value=PG_STATUS_OK):
            resp = test_client.get("/api/postgresql/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "postgresql"
        assert data["active"] == "active"
        assert data["ready"] == "accepting connections"

    def test_TC_PGS_002_status_unavailable(self, test_client, admin_token):
        """TC_PGS_002: PostgreSQL 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_status", return_value=PG_STATUS_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"
        assert "message" in data

    def test_TC_PGS_003_status_unauthorized(self, test_client):
        """TC_PGS_003: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/status")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_003b_status_viewer_allowed(self, test_client, viewer_token):
        """TC_PGS_003b: viewer ロールは read:postgresql 権限で取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_status", return_value=PG_STATUS_OK):
            resp = test_client.get("/api/postgresql/status", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_PGS_003c_status_wrapper_error(self, test_client, admin_token):
        """TC_PGS_003c: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_status", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestPostgreSQLDatabases:
    """TC_PGS_004〜006: PostgreSQL databases エンドポイントテスト"""

    def test_TC_PGS_004_databases_ok(self, test_client, admin_token):
        """TC_PGS_004: データベース一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_databases", return_value=PG_DATABASES_OK):
            resp = test_client.get("/api/postgresql/databases", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "databases_raw" in data

    def test_TC_PGS_005_databases_unavailable(self, test_client, admin_token):
        """TC_PGS_005: PostgreSQL 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_databases", return_value=PG_DATABASES_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/databases", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PGS_006_databases_unauthorized(self, test_client):
        """TC_PGS_006: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/databases")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_006b_databases_wrapper_error(self, test_client, admin_token):
        """TC_PGS_006b: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_databases", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/databases", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestPostgreSQLUsers:
    """TC_PGS_007〜009: PostgreSQL users エンドポイントテスト"""

    def test_TC_PGS_007_users_ok(self, test_client, admin_token):
        """TC_PGS_007: ユーザー/ロール一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_users", return_value=PG_USERS_OK):
            resp = test_client.get("/api/postgresql/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "users_raw" in data

    def test_TC_PGS_008_users_unavailable(self, test_client, admin_token):
        """TC_PGS_008: PostgreSQL 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_users", return_value=PG_USERS_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PGS_009_users_unauthorized(self, test_client):
        """TC_PGS_009: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/users")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_009b_users_wrapper_error(self, test_client, admin_token):
        """TC_PGS_009b: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_users", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestPostgreSQLActivity:
    """TC_PGS_010〜012: PostgreSQL activity エンドポイントテスト"""

    def test_TC_PGS_010_activity_ok(self, test_client, admin_token):
        """TC_PGS_010: 接続・クエリ状況の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_activity", return_value=PG_ACTIVITY_OK):
            resp = test_client.get("/api/postgresql/activity", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "activity_raw" in data
        assert data["connection_count"] == 3

    def test_TC_PGS_011_activity_unavailable(self, test_client, admin_token):
        """TC_PGS_011: PostgreSQL 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_activity", return_value=PG_ACTIVITY_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/activity", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PGS_012_activity_unauthorized(self, test_client):
        """TC_PGS_012: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/activity")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_012b_activity_wrapper_error(self, test_client, admin_token):
        """TC_PGS_012b: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_activity", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/activity", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestPostgreSQLConfig:
    """TC_PGS_013〜015: PostgreSQL config エンドポイントテスト"""

    def test_TC_PGS_013_config_ok(self, test_client, admin_token):
        """TC_PGS_013: 設定パラメータの正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_config", return_value=PG_CONFIG_OK):
            resp = test_client.get("/api/postgresql/config", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "config_raw" in data

    def test_TC_PGS_014_config_unavailable(self, test_client, admin_token):
        """TC_PGS_014: PostgreSQL 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_config", return_value=PG_CONFIG_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/config", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PGS_015_config_unauthorized(self, test_client):
        """TC_PGS_015: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/config")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_015b_config_wrapper_error(self, test_client, admin_token):
        """TC_PGS_015b: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_config", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/config", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestPostgreSQLLogs:
    """TC_PGS_016〜018: PostgreSQL logs エンドポイントテスト"""

    def test_TC_PGS_016_logs_ok(self, test_client, admin_token):
        """TC_PGS_016: ログの正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_logs", return_value=PG_LOGS_OK):
            resp = test_client.get("/api/postgresql/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "logs" in data
        assert data["lines"] == 50

    def test_TC_PGS_016b_logs_custom_lines(self, test_client, admin_token):
        """TC_PGS_016b: lines パラメータ指定でのログ取得"""
        custom_logs = {**PG_LOGS_OK, "lines": 100}
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_logs", return_value=custom_logs):
            resp = test_client.get("/api/postgresql/logs?lines=100", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 100

    def test_TC_PGS_017_logs_unavailable(self, test_client, admin_token):
        """TC_PGS_017: PostgreSQL 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_logs", return_value=PG_LOGS_UNAVAILABLE):
            resp = test_client.get("/api/postgresql/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PGS_018_logs_unauthorized(self, test_client):
        """TC_PGS_018: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/postgresql/logs")
        assert resp.status_code in (401, 403)

    def test_TC_PGS_018b_logs_invalid_lines(self, test_client, admin_token):
        """TC_PGS_018b: lines パラメータが範囲外の場合 422 返却"""
        resp = test_client.get("/api/postgresql/logs?lines=999", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 422

    def test_TC_PGS_018c_logs_wrapper_error(self, test_client, admin_token):
        """TC_PGS_018c: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_postgresql_logs", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/postgresql/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503
