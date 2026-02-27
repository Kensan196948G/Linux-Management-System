"""
データベース監視モジュール - 統合テスト

テストケース数: 20件
- 正常系: MySQL/PostgreSQL の各エンドポイント（status/processes/databases/connections/variables）
- 異常系: 権限不足、未認証、不正DBタイプ
- セキュリティ: allowlist外拒否
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

MYSQL_STATUS = {
    "status": "ok",
    "db_type": "mysql",
    "running": True,
    "version": "8.0.33-MySQL Community Server - GPL",
    "uptime": 3600,
    "connections": 5,
    "timestamp": "2026-03-01T00:00:00",
}

PG_STATUS = {
    "status": "ok",
    "db_type": "postgresql",
    "running": True,
    "version": "PostgreSQL 15.2",
    "connections": 3,
    "timestamp": "2026-03-01T00:00:00",
}

MYSQL_PROCESSLIST = {
    "status": "ok",
    "db_type": "mysql",
    "processes": [
        {"Id": 1, "User": "root", "Host": "localhost", "Command": "Query", "Info": "SHOW PROCESSLIST"},
    ],
    "count": 1,
    "timestamp": "2026-03-01T00:00:00",
}

PG_ACTIVITY = {
    "status": "ok",
    "db_type": "postgresql",
    "activity": [
        {"pid": 1234, "usename": "postgres", "state": "active", "query": "SELECT 1"},
    ],
    "count": 1,
    "timestamp": "2026-03-01T00:00:00",
}

MYSQL_DATABASES = {
    "status": "ok",
    "db_type": "mysql",
    "databases": ["mysql", "information_schema", "performance_schema", "mydb"],
    "count": 4,
    "timestamp": "2026-03-01T00:00:00",
}

PG_DATABASES = {
    "status": "ok",
    "db_type": "postgresql",
    "databases": ["postgres", "template0", "template1", "mydb"],
    "count": 4,
    "timestamp": "2026-03-01T00:00:00",
}

PG_CONNECTIONS = {
    "status": "ok",
    "db_type": "postgresql",
    "connections": [
        {"pid": 111, "usename": "appuser", "datname": "mydb", "state": "idle"},
    ],
    "count": 1,
    "timestamp": "2026-03-01T00:00:00",
}

MYSQL_VARIABLES = {
    "status": "ok",
    "db_type": "mysql",
    "variables": {"max_connections": "151", "innodb_buffer_pool_size": "134217728"},
    "timestamp": "2026-03-01T00:00:00",
}

DB_UNAVAILABLE = {
    "status": "unavailable",
    "message": "MySQL client not installed",
    "db_type": "mysql",
    "timestamp": "2026-03-01T00:00:00",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestDBMonitorStatus:
    """GET /api/dbmonitor/{db_type}/status のテスト"""

    def test_mysql_status_viewer(self, test_client, viewer_token):
        """TC_DBM_001: Viewer ロールで MySQL 状態取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_status",
            return_value=MYSQL_STATUS,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_postgresql_status_viewer(self, test_client, viewer_token):
        """TC_DBM_002: Viewer ロールで PostgreSQL 状態取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_status",
            return_value=PG_STATUS,
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_db_status_unavailable(self, test_client, viewer_token):
        """TC_DBM_003: DB クライアント未インストール時に unavailable を返す"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_status",
            return_value=DB_UNAVAILABLE,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_db_status_unauthenticated(self, test_client):
        """TC_DBM_004: 未認証で状態取得を拒否"""
        resp = test_client.get("/api/dbmonitor/mysql/status")
        assert resp.status_code in (401, 403)

    def test_invalid_db_type_status(self, test_client, viewer_token):
        """TC_DBM_005: 不正なDBタイプで 422 を返す"""
        resp = test_client.get(
            "/api/dbmonitor/oracle/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


class TestDBMonitorProcesses:
    """GET /api/dbmonitor/{db_type}/processes のテスト"""

    def test_mysql_processlist(self, test_client, viewer_token):
        """TC_DBM_006: MySQL プロセス一覧取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_processlist",
            return_value=MYSQL_PROCESSLIST,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/processes",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["data"], list)

    def test_postgresql_activity(self, test_client, viewer_token):
        """TC_DBM_007: PostgreSQL アクティビティ取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_processlist",
            return_value=PG_ACTIVITY,
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/processes",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_processes_no_auth(self, test_client):
        """TC_DBM_008: 未認証でプロセス一覧拒否"""
        resp = test_client.get("/api/dbmonitor/mysql/processes")
        assert resp.status_code in (401, 403)

    def test_invalid_db_processes(self, test_client, viewer_token):
        """TC_DBM_009: 不正なDBタイプで 422 を返す"""
        resp = test_client.get(
            "/api/dbmonitor/mssql/processes",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


class TestDBMonitorDatabases:
    """GET /api/dbmonitor/{db_type}/databases のテスト"""

    def test_mysql_databases(self, test_client, viewer_token):
        """TC_DBM_010: MySQL データベース一覧取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_databases",
            return_value=MYSQL_DATABASES,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/databases",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["data"], list)

    def test_postgresql_databases(self, test_client, viewer_token):
        """TC_DBM_011: PostgreSQL データベース一覧取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_databases",
            return_value=PG_DATABASES,
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/databases",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_databases_no_auth(self, test_client):
        """TC_DBM_012: 未認証でデータベース一覧拒否"""
        resp = test_client.get("/api/dbmonitor/mysql/databases")
        assert resp.status_code in (401, 403)


class TestDBMonitorConnections:
    """GET /api/dbmonitor/{db_type}/connections のテスト"""

    def test_postgresql_connections(self, test_client, viewer_token):
        """TC_DBM_013: PostgreSQL 接続一覧取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_connections",
            return_value=PG_CONNECTIONS,
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/connections",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_mysql_connections_fallback(self, test_client, viewer_token):
        """TC_DBM_014: MySQL 接続一覧（processlist フォールバック）"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_connections",
            return_value=MYSQL_PROCESSLIST,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/connections",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_connections_no_auth(self, test_client):
        """TC_DBM_015: 未認証で接続一覧拒否"""
        resp = test_client.get("/api/dbmonitor/postgresql/connections")
        assert resp.status_code in (401, 403)


class TestDBMonitorVariables:
    """GET /api/dbmonitor/{db_type}/variables のテスト"""

    def test_mysql_variables(self, test_client, viewer_token):
        """TC_DBM_016: MySQL 変数一覧取得成功"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_variables",
            return_value=MYSQL_VARIABLES,
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/variables",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_postgresql_variables_fallback(self, test_client, viewer_token):
        """TC_DBM_017: PostgreSQL 変数取得（statusフォールバック）"""
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_variables",
            return_value=PG_STATUS,
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/variables",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_variables_no_auth(self, test_client):
        """TC_DBM_018: 未認証で変数一覧拒否"""
        resp = test_client.get("/api/dbmonitor/mysql/variables")
        assert resp.status_code in (401, 403)


class TestDBMonitorSecurity:
    """セキュリティテスト"""

    def test_injection_db_type(self, test_client, viewer_token):
        """TC_DBM_019: DBタイプにインジェクション文字を含む場合 422 を返す"""
        resp = test_client.get(
            "/api/dbmonitor/mysql;DROP TABLE users/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code in (404, 422)

    def test_allowlist_enforcement(self, test_client, viewer_token):
        """TC_DBM_020: allowlist 外のDBタイプは 422 を返す"""
        for invalid_db in ["sqlite", "redis", "mongo", "mssql", "oracle"]:
            resp = test_client.get(
                f"/api/dbmonitor/{invalid_db}/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            assert resp.status_code == 422, f"Expected 422 for db_type={invalid_db}"


class TestDBMonitorErrorPaths:
    """DBモニター エラーパスカバレッジ向上"""

    def test_status_wrapper_error(self, test_client, viewer_token):
        """TC_DBM_021: status SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_status",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_processlist_wrapper_error(self, test_client, viewer_token):
        """TC_DBM_022: processlist SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_processlist",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/processes",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_databases_wrapper_error(self, test_client, viewer_token):
        """TC_DBM_023: databases SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_databases",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/dbmonitor/postgresql/databases",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_connections_wrapper_error(self, test_client, viewer_token):
        """TC_DBM_024: connections SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_connections",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/connections",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_variables_wrapper_error(self, test_client, viewer_token):
        """TC_DBM_025: variables SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.dbmonitor.sudo_wrapper.get_db_variables",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/dbmonitor/mysql/variables",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503
