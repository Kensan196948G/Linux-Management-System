"""
Serversモジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest


# テスト用サーバーデータ
SAMPLE_ALL_STATUS_RESPONSE = {
    "status": "success",
    "servers": [
        {
            "service": "nginx",
            "active_state": "active",
            "sub_state": "running",
            "load_state": "loaded",
            "main_pid": 1234,
            "enabled": "enabled",
        },
        {
            "service": "apache2",
            "active_state": "inactive",
            "sub_state": "dead",
            "load_state": "loaded",
            "main_pid": 0,
            "enabled": "disabled",
        },
        {
            "service": "mysql",
            "active_state": "active",
            "sub_state": "running",
            "load_state": "loaded",
            "main_pid": 2345,
            "enabled": "enabled",
        },
        {
            "service": "postgresql",
            "active_state": "active",
            "sub_state": "running",
            "load_state": "loaded",
            "main_pid": 3456,
            "enabled": "enabled",
        },
        {
            "service": "redis",
            "active_state": "inactive",
            "sub_state": "dead",
            "load_state": "not-found",
            "main_pid": 0,
            "enabled": "unknown",
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SERVER_STATUS_RESPONSE = {
    "status": "success",
    "server": {
        "service": "nginx",
        "active_state": "active",
        "sub_state": "running",
        "load_state": "loaded",
        "main_pid": 1234,
        "enabled": "enabled",
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_VERSION_RESPONSE = {
    "status": "success",
    "server": "nginx",
    "version": "1.24.0",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_CONFIG_INFO_RESPONSE = {
    "status": "success",
    "server": "nginx",
    "config_path": "/etc/nginx/nginx.conf",
    "exists": True,
    "type": "file",
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# 認証テスト
# ==============================================================================


class TestServersAuthentication:
    """認証・認可テスト"""

    def test_anonymous_user_rejected_status(self, test_client):
        response = test_client.get("/api/servers/status")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_server_status(self, test_client):
        response = test_client.get("/api/servers/nginx/status")
        assert response.status_code == 403

    def test_anonymous_user_rejected_version(self, test_client):
        response = test_client.get("/api/servers/nginx/version")
        assert response.status_code == 403

    def test_anonymous_user_rejected_config(self, test_client):
        response = test_client.get("/api/servers/nginx/config")
        assert response.status_code == 403

    def test_viewer_can_read_server_status(self, test_client, viewer_headers):
        """Viewer ロールはサーバー情報を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.return_value = SAMPLE_ALL_STATUS_RESPONSE
            response = test_client.get("/api/servers/status", headers=viewer_headers)
            assert response.status_code == 200

    def test_invalid_server_name_returns_422(self, test_client, auth_headers):
        """allowlist外のサーバー名は 422 を返す"""
        response = test_client.get("/api/servers/malicious/status", headers=auth_headers)
        assert response.status_code == 422


# ==============================================================================
# 全サーバー状態テスト
# ==============================================================================


class TestAllServerStatus:
    """GET /api/servers/status テスト"""

    def test_get_all_status_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.return_value = SAMPLE_ALL_STATUS_RESPONSE
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "servers" in data
        assert len(data["servers"]) == 5
        assert "timestamp" in data

    def test_get_all_status_contains_nginx(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.return_value = SAMPLE_ALL_STATUS_RESPONSE
            response = test_client.get("/api/servers/status", headers=auth_headers)

        data = response.json()
        services = [s.get("service") for s in data["servers"]]
        assert "nginx" in services

    def test_get_all_status_empty_list(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "servers": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["servers"] == []

    def test_get_all_status_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 500

    def test_get_all_status_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_all_server_status") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "systemctl not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/status", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# 個別サーバー状態テスト
# ==============================================================================


class TestSingleServerStatus:
    """GET /api/servers/{server}/status テスト"""

    @pytest.mark.parametrize("server", ["nginx", "apache2", "mysql", "postgresql", "redis"])
    def test_get_server_status_all_allowed(self, test_client, auth_headers, server):
        """許可サーバー全てで 200 が返る"""
        resp = dict(SAMPLE_SERVER_STATUS_RESPONSE)
        resp["server"] = dict(SAMPLE_SERVER_STATUS_RESPONSE["server"])
        resp["server"]["service"] = server

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_status") as mock_get:
            mock_get.return_value = resp
            response = test_client.get(
                f"/api/servers/{server}/status", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_get_server_status_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_status") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 500

    def test_get_server_status_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_status") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "systemctl not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/nginx/status", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# バージョンテスト
# ==============================================================================


class TestServerVersion:
    """GET /api/servers/{server}/version テスト"""

    def test_get_nginx_version_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_version") as mock_get:
            mock_get.return_value = SAMPLE_VERSION_RESPONSE
            response = test_client.get("/api/servers/nginx/version", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["server"] == "nginx"
        assert "version" in data
        assert "timestamp" in data

    def test_get_version_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_version") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/servers/mysql/version", headers=auth_headers)

        assert response.status_code == 500

    def test_get_version_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_version") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "mysql not found",
                "server": "mysql",
                "version": "unknown",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/mysql/version", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# 設定ファイル情報テスト
# ==============================================================================


class TestServerConfigInfo:
    """GET /api/servers/{server}/config テスト"""

    def test_get_nginx_config_exists(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_config_info") as mock_get:
            mock_get.return_value = SAMPLE_CONFIG_INFO_RESPONSE
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["server"] == "nginx"
        assert "config_path" in data
        assert data["exists"] is True

    def test_get_config_not_exists(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_config_info") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "server": "redis",
                "config_path": "/etc/redis/redis.conf",
                "exists": False,
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/redis/config", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["exists"] is False

    def test_get_config_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_config_info") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 500

    def test_get_config_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_server_config_info") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "Permission denied",
                "server": "nginx",
                "config_path": "",
                "exists": False,
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/servers/nginx/config", headers=auth_headers)

        assert response.status_code == 503
