"""
DB Monitor API エンドポイントのユニットテスト

backend/api/routes/dbmonitor.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _mock_output(**kwargs):
    """テスト用モックデータ生成ヘルパー"""
    defaults = {"status": "ok", "timestamp": "2026-03-01T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


class TestGetDBStatus:
    """GET /api/dbmonitor/{db_type}/status テスト"""

    def test_mysql_status_success(self, test_client, auth_headers):
        """正常系: MySQL ステータス取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_status.return_value = _mock_output(
                db_type="mysql", running=True, version="8.0.35"
            )
            response = test_client.get(
                "/api/dbmonitor/mysql/status", headers=auth_headers
            )
        assert response.status_code == 200
        data = response.json()
        assert data["db_type"] == "mysql"

    def test_postgresql_status_success(self, test_client, auth_headers):
        """正常系: PostgreSQL ステータス取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_status.return_value = _mock_output(
                db_type="postgresql", running=True, version="15.4"
            )
            response = test_client.get(
                "/api/dbmonitor/postgresql/status", headers=auth_headers
            )
        assert response.status_code == 200
        data = response.json()
        assert data["db_type"] == "postgresql"

    def test_invalid_db_type(self, test_client, auth_headers):
        """不正なDBタイプ"""
        response = test_client.get(
            "/api/dbmonitor/oracle/status", headers=auth_headers
        )
        assert response.status_code == 422

    def test_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/dbmonitor/mysql/status", headers=auth_headers
            )
        assert response.status_code == 503

    def test_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/dbmonitor/mysql/status")
        assert response.status_code == 403


class TestGetDBProcesses:
    """GET /api/dbmonitor/{db_type}/processes テスト"""

    def test_mysql_processes_success(self, test_client, auth_headers):
        """正常系: MySQL プロセス一覧取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_processlist.return_value = _mock_output(
                processes=[{"id": 1, "user": "root", "db": "test"}], count=1
            )
            response = test_client.get(
                "/api/dbmonitor/mysql/processes", headers=auth_headers
            )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_postgresql_processes_success(self, test_client, auth_headers):
        """正常系: PostgreSQL プロセス一覧取得（activity キー）"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_processlist.return_value = _mock_output(
                activity=[{"pid": 1, "state": "active"}], count=1
            )
            response = test_client.get(
                "/api/dbmonitor/postgresql/processes", headers=auth_headers
            )
        assert response.status_code == 200

    def test_processes_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_processlist.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/dbmonitor/mysql/processes", headers=auth_headers
            )
        assert response.status_code == 503


class TestGetDBDatabases:
    """GET /api/dbmonitor/{db_type}/databases テスト"""

    def test_mysql_databases_success(self, test_client, auth_headers):
        """正常系: MySQL データベース一覧取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_databases.return_value = _mock_output(
                databases=["mysql", "information_schema", "test_db"], count=3
            )
            response = test_client.get(
                "/api/dbmonitor/mysql/databases", headers=auth_headers
            )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3

    def test_postgresql_databases_success(self, test_client, auth_headers):
        """正常系: PostgreSQL データベース一覧取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_databases.return_value = _mock_output(
                databases=["postgres", "mydb"], count=2
            )
            response = test_client.get(
                "/api/dbmonitor/postgresql/databases", headers=auth_headers
            )
        assert response.status_code == 200

    def test_databases_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_databases.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/dbmonitor/mysql/databases", headers=auth_headers
            )
        assert response.status_code == 503


class TestGetDBConnections:
    """GET /api/dbmonitor/{db_type}/connections テスト"""

    def test_postgresql_connections_success(self, test_client, auth_headers):
        """正常系: PostgreSQL 接続一覧取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_connections.return_value = _mock_output(
                connections=[{"pid": 1, "state": "idle"}], count=1
            )
            response = test_client.get(
                "/api/dbmonitor/postgresql/connections", headers=auth_headers
            )
        assert response.status_code == 200

    def test_mysql_connections_success(self, test_client, auth_headers):
        """正常系: MySQL 接続一覧取得（processes フォールバック）"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_connections.return_value = _mock_output(
                processes=[{"id": 1, "user": "root"}], count=1
            )
            response = test_client.get(
                "/api/dbmonitor/mysql/connections", headers=auth_headers
            )
        assert response.status_code == 200

    def test_connections_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_connections.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/dbmonitor/postgresql/connections", headers=auth_headers
            )
        assert response.status_code == 503


class TestGetDBVariables:
    """GET /api/dbmonitor/{db_type}/variables テスト"""

    def test_mysql_variables_success(self, test_client, auth_headers):
        """正常系: MySQL 変数取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_variables.return_value = _mock_output(
                variables={"max_connections": "151"}
            )
            response = test_client.get(
                "/api/dbmonitor/mysql/variables", headers=auth_headers
            )
        assert response.status_code == 200

    def test_postgresql_variables_success(self, test_client, auth_headers):
        """正常系: PostgreSQL 変数取得"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_variables.return_value = _mock_output(
                variables={"max_connections": "100"}
            )
            response = test_client.get(
                "/api/dbmonitor/postgresql/variables", headers=auth_headers
            )
        assert response.status_code == 200

    def test_variables_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.dbmonitor.sudo_wrapper") as mock_sw:
            mock_sw.get_db_variables.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/dbmonitor/mysql/variables", headers=auth_headers
            )
        assert response.status_code == 503
