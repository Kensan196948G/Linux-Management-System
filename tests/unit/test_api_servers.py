"""
Servers API エンドポイントのユニットテスト

backend/api/routes/servers.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetAllServerStatus:
    """GET /api/servers/status テスト"""

    def test_get_all_status_success(self, test_client, auth_headers):
        """正常系: 全サーバー状態取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "servers": [
                    {"service": "nginx", "active_state": "active", "sub_state": "running"},
                    {"service": "redis", "active_state": "inactive", "sub_state": "dead"},
                ],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_all_server_status.return_value = mock_result
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["servers"]) == 2

    def test_get_all_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/servers/status")
        assert response.status_code == 403

    def test_get_all_status_error(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "systemctl not found"}
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_all_server_status.return_value = mock_result
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 503

    def test_get_all_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_all_server_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 500


class TestGetServerStatus:
    """GET /api/servers/{server}/status テスト"""

    def test_get_nginx_status_success(self, test_client, auth_headers):
        """正常系: nginx 状態取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "server": {"service": "nginx", "active_state": "active"},
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_status.return_value = mock_result
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 200

    def test_get_server_status_not_allowed(self, test_client, auth_headers):
        """allowlist外のサーバー名"""
        response = test_client.get("/api/servers/malicious/status", headers=auth_headers)
        assert response.status_code == 422  # FastAPI path validation

    def test_get_server_status_error(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "Service not found"}
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_status.return_value = mock_result
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 503

    def test_get_server_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 500

    def test_get_server_status_value_error(self, test_client, auth_headers):
        """ValueError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_status.side_effect = ValueError("Invalid server")
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 400


class TestGetServerVersion:
    """GET /api/servers/{server}/version テスト"""

    def test_get_version_success(self, test_client, auth_headers):
        """正常系: バージョン取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "server": "nginx",
                "version": "1.24.0",
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_version.return_value = mock_result
            response = test_client.get("/api/servers/nginx/version", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.24.0"

    def test_get_version_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "Version unknown"}
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_version.return_value = mock_result
            response = test_client.get("/api/servers/nginx/version", headers=auth_headers)

        assert response.status_code == 503

    def test_get_version_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_version.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/servers/nginx/version", headers=auth_headers)

        assert response.status_code == 500

    def test_get_version_value_error(self, test_client, auth_headers):
        """ValueError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_version.side_effect = ValueError("Bad server")
            response = test_client.get("/api/servers/nginx/version", headers=auth_headers)

        assert response.status_code == 400


class TestGetServerConfig:
    """GET /api/servers/{server}/config テスト"""

    def test_get_config_success(self, test_client, auth_headers):
        """正常系: 設定情報取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "server": "nginx",
                "config_path": "/etc/nginx/nginx.conf",
                "exists": True,
                "type": "file",
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_config_info.return_value = mock_result
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["server"] == "nginx"
        assert data["exists"] is True

    def test_get_config_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "Config not found"}
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_config_info.return_value = mock_result
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 503

    def test_get_config_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_config_info.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 500

    def test_get_config_value_error(self, test_client, auth_headers):
        """ValueError 発生時"""
        with patch("backend.api.routes.servers.sudo_wrapper") as mock_sw:
            mock_sw.get_server_config_info.side_effect = ValueError("Bad server")
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 400
