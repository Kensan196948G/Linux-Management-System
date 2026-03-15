"""
postgresql.py カバレッジ改善テスト v2

対象: backend/api/routes/postgresql.py (全6エンドポイント)
既存テストで不足している分岐を網羅する。

カバー対象:
  - 全エンドポイントの audit_log 呼び出し検証（operation/target/status）
  - parse_wrapper_result の JSON パース成功・失敗分岐
  - SudoWrapperError 例外パス（全エンドポイント）
  - レスポンスモデルの全フィールド検証
  - logs の lines パラメータ境界値
  - viewer/operator ロールアクセス検証
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ======================================================================
# ヘルパー
# ======================================================================


def _mock_output(**kwargs):
    """sudo_wrapper 形式のモック出力 (output フィールドに JSON 文字列)"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


def _raw_output(**kwargs):
    """parse不要な直接返却形式"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return defaults


# ======================================================================
# status エンドポイント
# ======================================================================


class TestPostgreSQLStatusCoverageV2:
    """GET /api/postgresql/status の追加カバレッジ"""

    def test_status_audit_log(self, test_client, admin_headers):
        """audit_log が正しい引数で呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_status.return_value = _raw_output(
                    service="postgresql", active="active"
                )
                resp = test_client.get("/api/postgresql/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_status"
        assert call_kwargs["target"] == "postgresql"
        assert call_kwargs["status"] == "success"

    def test_status_all_fields(self, test_client, admin_headers):
        """全レスポンスフィールドの確認"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_status.return_value = _raw_output(
                service="postgresql",
                active="active",
                enabled="enabled",
                version="PostgreSQL 15.3",
                ready="accepting connections",
                message=None,
            )
            resp = test_client.get("/api/postgresql/status", headers=admin_headers)
        data = resp.json()
        assert data["service"] == "postgresql"
        assert data["active"] == "active"
        assert data["enabled"] == "enabled"
        assert data["version"] == "PostgreSQL 15.3"
        assert data["ready"] == "accepting connections"

    def test_status_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未インストール時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_status.return_value = _raw_output(
                status="unavailable", message="PostgreSQL not installed"
            )
            resp = test_client.get("/api/postgresql/status", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"
        assert resp.json()["message"] == "PostgreSQL not installed"

    def test_status_json_output_parsed(self, test_client, admin_headers):
        """output フィールドの JSON が正しくパースされること"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_status.return_value = _mock_output(
                service="postgresql", active="active"
            )
            resp = test_client.get("/api/postgresql/status", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["service"] == "postgresql"


# ======================================================================
# databases エンドポイント
# ======================================================================


class TestPostgreSQLDatabasesCoverageV2:
    """GET /api/postgresql/databases の追加カバレッジ"""

    def test_databases_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_databases.return_value = _raw_output(
                    databases_raw="postgres|8192"
                )
                resp = test_client.get("/api/postgresql/databases", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_databases"

    def test_databases_response_fields(self, test_client, admin_headers):
        """レスポンスフィールドの確認"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_databases.return_value = _raw_output(
                databases_raw="postgres|8192\ntemplate0|8192",
                databases=[{"name": "postgres"}, {"name": "template0"}],
            )
            resp = test_client.get("/api/postgresql/databases", headers=admin_headers)
        data = resp.json()
        assert "databases_raw" in data
        assert "databases" in data

    def test_databases_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未接続時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_databases.return_value = _raw_output(
                status="unavailable", message="Cannot connect"
            )
            resp = test_client.get("/api/postgresql/databases", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_databases_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_databases.return_value = _mock_output(
                databases_raw="db1|1024"
            )
            resp = test_client.get("/api/postgresql/databases", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# users エンドポイント
# ======================================================================


class TestPostgreSQLUsersCoverageV2:
    """GET /api/postgresql/users の追加カバレッジ"""

    def test_users_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_users.return_value = _raw_output(
                    users_raw="postgres|t|t"
                )
                resp = test_client.get("/api/postgresql/users", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_users"

    def test_users_response_fields(self, test_client, admin_headers):
        """レスポンスフィールド"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_users.return_value = _raw_output(
                users_raw="postgres|t|t\npg_monitor|f|f",
                users=[{"name": "postgres"}, {"name": "pg_monitor"}],
            )
            resp = test_client.get("/api/postgresql/users", headers=admin_headers)
        data = resp.json()
        assert "users_raw" in data
        assert "users" in data

    def test_users_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未接続時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_users.return_value = _raw_output(
                status="unavailable", message="Cannot connect"
            )
            resp = test_client.get("/api/postgresql/users", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_users_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_users.return_value = _mock_output(
                users_raw="user1|t"
            )
            resp = test_client.get("/api/postgresql/users", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# activity エンドポイント
# ======================================================================


class TestPostgreSQLActivityCoverageV2:
    """GET /api/postgresql/activity の追加カバレッジ"""

    def test_activity_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_activity.return_value = _raw_output(
                    activity_raw="1234|postgres|idle", connection_count=1
                )
                resp = test_client.get("/api/postgresql/activity", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_activity"

    def test_activity_response_fields(self, test_client, admin_headers):
        """レスポンスフィールド"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_activity.return_value = _raw_output(
                activity_raw="1234|postgres|psql|127.0.0.1|idle",
                connection_count=5,
            )
            resp = test_client.get("/api/postgresql/activity", headers=admin_headers)
        data = resp.json()
        assert "activity_raw" in data
        assert data["connection_count"] == 5

    def test_activity_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未接続時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_activity.return_value = _raw_output(
                status="unavailable", message="Cannot connect"
            )
            resp = test_client.get("/api/postgresql/activity", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_activity_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_activity.return_value = _mock_output(
                activity_raw="data", connection_count=2
            )
            resp = test_client.get("/api/postgresql/activity", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# config エンドポイント
# ======================================================================


class TestPostgreSQLConfigCoverageV2:
    """GET /api/postgresql/config の追加カバレッジ"""

    def test_config_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_config.return_value = _raw_output(
                    config_raw="max_connections|100"
                )
                resp = test_client.get("/api/postgresql/config", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_config"

    def test_config_response_fields(self, test_client, admin_headers):
        """レスポンスフィールド"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_config.return_value = _raw_output(
                config_raw="max_connections|100\nlisten_addresses|localhost"
            )
            resp = test_client.get("/api/postgresql/config", headers=admin_headers)
        data = resp.json()
        assert "config_raw" in data
        assert "max_connections" in data["config_raw"]

    def test_config_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未接続時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_config.return_value = _raw_output(
                status="unavailable", message="Cannot connect"
            )
            resp = test_client.get("/api/postgresql/config", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_config_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_config.return_value = _mock_output(
                config_raw="setting1|val1"
            )
            resp = test_client.get("/api/postgresql/config", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# logs エンドポイント
# ======================================================================


class TestPostgreSQLLogsCoverageV2:
    """GET /api/postgresql/logs の追加カバレッジ"""

    def test_logs_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.postgresql.audit_log") as mock_audit:
            with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
                mock_sw.get_postgresql_logs.return_value = _raw_output(
                    logs="LOG: ready", lines=50
                )
                resp = test_client.get("/api/postgresql/logs", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "postgresql_logs"

    def test_logs_response_fields(self, test_client, admin_headers):
        """レスポンスフィールド"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_logs.return_value = _raw_output(
                logs="2026-03-15 LOG: started\n2026-03-15 LOG: ready",
                lines=2,
            )
            resp = test_client.get("/api/postgresql/logs?lines=2", headers=admin_headers)
        data = resp.json()
        assert "logs" in data
        assert data["lines"] == 2

    @pytest.mark.parametrize("lines", [1, 50, 100, 200])
    def test_logs_valid_lines(self, test_client, admin_headers, lines):
        """有効な lines パラメータ"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_logs.return_value = _raw_output(
                logs="log data", lines=lines
            )
            resp = test_client.get(
                f"/api/postgresql/logs?lines={lines}", headers=admin_headers
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize("lines", [0, -1, 201, 999])
    def test_logs_invalid_lines(self, test_client, admin_headers, lines):
        """無効な lines パラメータ → 422"""
        resp = test_client.get(
            f"/api/postgresql/logs?lines={lines}", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_logs_default_lines(self, test_client, admin_headers):
        """デフォルト lines=50"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_logs.return_value = _raw_output(
                logs="log", lines=50
            )
            resp = test_client.get("/api/postgresql/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_sw.get_postgresql_logs.assert_called_once_with(lines=50)

    def test_logs_unavailable(self, test_client, admin_headers):
        """PostgreSQL 未インストール時"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_logs.return_value = _raw_output(
                status="unavailable", message="PostgreSQL not installed"
            )
            resp = test_client.get("/api/postgresql/logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_logs_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            mock_sw.get_postgresql_logs.return_value = _mock_output(
                logs="log line", lines=1
            )
            resp = test_client.get("/api/postgresql/logs?lines=1", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# パラメトライズ: 全エンドポイントの SudoWrapperError テスト
# ======================================================================


class TestPostgreSQLAllEndpointErrors:
    """全エンドポイントの SudoWrapperError テスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/postgresql/status", "get_postgresql_status"),
            ("/api/postgresql/databases", "get_postgresql_databases"),
            ("/api/postgresql/users", "get_postgresql_users"),
            ("/api/postgresql/activity", "get_postgresql_activity"),
            ("/api/postgresql/config", "get_postgresql_config"),
            ("/api/postgresql/logs", "get_postgresql_logs"),
        ],
    )
    def test_sudo_wrapper_error_returns_503(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).side_effect = SudoWrapperError("fail")
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/postgresql/status",
            "/api/postgresql/databases",
            "/api/postgresql/users",
            "/api/postgresql/activity",
            "/api/postgresql/config",
            "/api/postgresql/logs",
        ],
    )
    def test_unauthenticated(self, test_client, endpoint):
        """未認証で拒否"""
        resp = test_client.get(endpoint)
        assert resp.status_code in (401, 403)


# ======================================================================
# viewer ロールアクセス
# ======================================================================


class TestPostgreSQLViewerAccess:
    """viewer ロールのアクセス確認"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/postgresql/status", "get_postgresql_status"),
            ("/api/postgresql/databases", "get_postgresql_databases"),
            ("/api/postgresql/users", "get_postgresql_users"),
            ("/api/postgresql/activity", "get_postgresql_activity"),
            ("/api/postgresql/config", "get_postgresql_config"),
            ("/api/postgresql/logs", "get_postgresql_logs"),
        ],
    )
    def test_viewer_can_access(
        self, test_client, viewer_headers, endpoint, wrapper_method
    ):
        """viewer ロールは read:postgresql 権限で全エンドポイントにアクセス可能"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).return_value = _raw_output()
            resp = test_client.get(endpoint, headers=viewer_headers)
        assert resp.status_code == 200


# ======================================================================
# operator ロールアクセス
# ======================================================================


class TestPostgreSQLOperatorAccess:
    """operator ロールのアクセス確認"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/postgresql/status", "get_postgresql_status"),
            ("/api/postgresql/databases", "get_postgresql_databases"),
            ("/api/postgresql/users", "get_postgresql_users"),
            ("/api/postgresql/activity", "get_postgresql_activity"),
            ("/api/postgresql/config", "get_postgresql_config"),
            ("/api/postgresql/logs", "get_postgresql_logs"),
        ],
    )
    def test_operator_can_access(
        self, test_client, auth_headers, endpoint, wrapper_method
    ):
        """operator ロールは read:postgresql 権限で全エンドポイントにアクセス可能"""
        with patch("backend.api.routes.postgresql.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).return_value = _raw_output()
            resp = test_client.get(endpoint, headers=auth_headers)
        assert resp.status_code == 200
