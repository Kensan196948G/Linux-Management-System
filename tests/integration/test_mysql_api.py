"""MySQL/MariaDB API テスト (TC_MYS_001〜015)"""

import pytest
from unittest.mock import patch

from backend.core.sudo_wrapper import SudoWrapperError


class TestMysqlStatus:
    """MySQL ステータス取得テスト"""

    def test_TC_MYS_001_status_success(self, test_client, admin_token):
        """TC_MYS_001: ステータス取得成功（admin）"""
        mock_data = {"status": "running", "version": "mysql  Ver 8.0.33"}
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_status", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "running"

    def test_TC_MYS_002_status_viewer(self, test_client, viewer_token):
        """TC_MYS_002: viewer でもステータス取得可能"""
        mock_data = {"status": "running", "version": "mysql  Ver 8.0.33"}
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_status", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_MYS_003_databases_success(self, test_client, admin_token):
        """TC_MYS_003: データベース一覧取得成功"""
        mock_data = {"databases": ["information_schema", "mysql", "myapp"]}
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_databases", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/databases",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "databases" in body["data"]
        assert len(body["data"]["databases"]) == 3

    def test_TC_MYS_004_users_success(self, test_client, admin_token):
        """TC_MYS_004: ユーザー一覧取得成功（パスワードハッシュなし）"""
        mock_data = {
            "users": [
                {"user": "root", "host": "localhost", "account_locked": "N"},
                {"user": "appuser", "host": "%", "account_locked": "N"},
            ]
        }
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_users", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/users",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "users" in body["data"]
        # パスワードハッシュが含まれないことを確認
        for user in body["data"]["users"]:
            assert "password" not in user
            assert "authentication_string" not in user

    def test_TC_MYS_005_processes_success(self, test_client, admin_token):
        """TC_MYS_005: プロセスリスト取得成功"""
        mock_data = {
            "processes": [
                {"Id": "1", "User": "root", "Host": "localhost", "db": "None",
                 "Command": "Query", "Time": "0", "State": "", "Info": "SHOW PROCESSLIST"}
            ]
        }
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_processes", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/processes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "processes" in body["data"]


class TestMysqlUnavailable:
    """MySQL 未インストール時のテスト"""

    def test_TC_MYS_006_status_unavailable(self, test_client, admin_token):
        """TC_MYS_006: mysql 未インストール - status は 200 + unavailable"""
        mock_data = {"status": "unavailable", "message": "mysql/mariadb is not installed"}
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_status", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "unavailable"

    def test_TC_MYS_007_databases_wrapper_error(self, test_client, admin_token):
        """TC_MYS_007: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_databases",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/mysql/databases",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_MYS_008_users_wrapper_error(self, test_client, admin_token):
        """TC_MYS_008: users エンドポイント - SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_users",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/mysql/users",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_MYS_009_processes_wrapper_error(self, test_client, admin_token):
        """TC_MYS_009: processes エンドポイント - SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_processes",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/mysql/processes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_MYS_010_status_wrapper_error(self, test_client, admin_token):
        """TC_MYS_010: status エンドポイント - SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_status",
            side_effect=SudoWrapperError("connection refused"),
        ):
            resp = test_client.get(
                "/api/mysql/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestMysqlAuth:
    """認証・認可テスト"""

    def test_TC_MYS_011_status_unauthenticated(self, test_client):
        """TC_MYS_011: 未認証は拒否（status）"""
        resp = test_client.get("/api/mysql/status")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_012_databases_unauthenticated(self, test_client):
        """TC_MYS_012: 未認証は拒否（databases）"""
        resp = test_client.get("/api/mysql/databases")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_013_users_unauthenticated(self, test_client):
        """TC_MYS_013: 未認証は拒否（users）"""
        resp = test_client.get("/api/mysql/users")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_014_processes_unauthenticated(self, test_client):
        """TC_MYS_014: 未認証は拒否（processes）"""
        resp = test_client.get("/api/mysql/processes")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_015_logs_success_and_lines_param(self, test_client, admin_token):
        """TC_MYS_015: logs エンドポイント - lines パラメータ付きで取得成功"""
        mock_data = {"logs": "2024-01-01T00:00:00 MySQL started\n", "lines": 100}
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/logs?lines=100",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["lines"] == 100

    def test_TC_MYS_016_logs_unauthenticated(self, test_client):
        """TC_MYS_016: 未認証は拒否（logs）"""
        resp = test_client.get("/api/mysql/logs")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_017_variables_success(self, test_client, admin_token):
        """TC_MYS_017: variables エンドポイント取得成功"""
        mock_data = {
            "variables": {
                "version": "8.0.33",
                "max_connections": "151",
                "innodb_buffer_pool_size": "134217728",
            }
        }
        with patch("backend.api.routes.mysql.sudo_wrapper.get_mysql_variables", return_value=mock_data):
            resp = test_client.get(
                "/api/mysql/variables",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "variables" in body["data"]

    def test_TC_MYS_018_variables_unauthenticated(self, test_client):
        """TC_MYS_018: 未認証は拒否（variables）"""
        resp = test_client.get("/api/mysql/variables")
        assert resp.status_code in (401, 403)

    def test_TC_MYS_019_logs_lines_limit(self, test_client, admin_token):
        """TC_MYS_019: lines=201 は 422 バリデーションエラー"""
        resp = test_client.get(
            "/api/mysql/logs?lines=201",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_MYS_020_variables_wrapper_error(self, test_client, admin_token):
        """TC_MYS_020: variables エンドポイント - SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.mysql.sudo_wrapper.get_mysql_variables",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/mysql/variables",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
