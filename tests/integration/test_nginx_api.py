"""
Nginx モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
テストケース数: 25件以上
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

NGINX_STATUS_OK = {
    "status": "success",
    "service": "nginx",
    "active": "active",
    "enabled": "enabled",
    "version": "nginx/1.24.0",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_STATUS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "nginx not installed",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_CONFIG_OK = {
    "status": "success",
    "config": "# nginx configuration\nworker_processes auto;\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_CONFIG_UNAVAILABLE = {
    "status": "unavailable",
    "message": "nginx not installed",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_VHOSTS_OK = {
    "status": "success",
    "vhosts": [
        {"name": "default", "path": "/etc/nginx/sites-enabled/default", "is_symlink": True}
    ],
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_VHOSTS_EMPTY = {
    "status": "success",
    "vhosts": [],
    "message": "sites-enabled directory not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_CONNECTIONS_OK = {
    "status": "success",
    "connections_raw": "ESTAB  0  0  0.0.0.0:80  0.0.0.0:*  users:((\"nginx\",pid=1234,fd=6))",
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_LOGS_OK = {
    "status": "success",
    "logs": '127.0.0.1 - - [01/Mar/2026:00:00:00 +0000] "GET / HTTP/1.1" 200 612\n',
    "lines": 1,
    "timestamp": "2026-03-01T00:00:00Z",
}

NGINX_LOGS_EMPTY = {
    "status": "success",
    "logs": "",
    "message": "Log file not found: /var/log/nginx/access.log",
    "lines": 0,
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# 認証・権限テスト（5件）
# ===================================================================


class TestNginxAuth:
    """認証・権限テスト"""

    def test_anonymous_user_rejected_status(self, test_client):
        response = test_client.get("/api/nginx/status")
        assert response.status_code == 403

    def test_anonymous_user_rejected_config(self, test_client):
        response = test_client.get("/api/nginx/config")
        assert response.status_code == 403

    def test_anonymous_user_rejected_vhosts(self, test_client):
        response = test_client.get("/api/nginx/vhosts")
        assert response.status_code == 403

    def test_anonymous_user_rejected_connections(self, test_client):
        response = test_client.get("/api/nginx/connections")
        assert response.status_code == 403

    def test_anonymous_user_rejected_logs(self, test_client):
        response = test_client.get("/api/nginx/logs")
        assert response.status_code == 403

    def test_viewer_can_read_nginx_status(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_status") as mock:
            mock.return_value = NGINX_STATUS_OK
            response = test_client.get("/api/nginx/status", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_read_nginx_config(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_config") as mock:
            mock.return_value = NGINX_CONFIG_OK
            response = test_client.get("/api/nginx/config", headers=viewer_headers)
        assert response.status_code == 200


# ===================================================================
# GET /api/nginx/status テスト
# ===================================================================


class TestNginxStatus:
    """GET /api/nginx/status テスト"""

    def test_get_status_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_status") as mock:
            mock.return_value = NGINX_STATUS_OK
            response = test_client.get("/api/nginx/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["service"] == "nginx"
        assert data["active"] == "active"
        assert "version" in data

    def test_get_status_unavailable(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_status") as mock:
            mock.return_value = NGINX_STATUS_UNAVAILABLE
            response = test_client.get("/api/nginx/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"
        assert "nginx not installed" in data["message"]

    def test_get_status_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_status") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/nginx/status", headers=auth_headers)
        assert response.status_code == 503


# ===================================================================
# GET /api/nginx/config テスト
# ===================================================================


class TestNginxConfig:
    """GET /api/nginx/config テスト"""

    def test_get_config_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_config") as mock:
            mock.return_value = NGINX_CONFIG_OK
            response = test_client.get("/api/nginx/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "config" in data

    def test_get_config_unavailable(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_config") as mock:
            mock.return_value = NGINX_CONFIG_UNAVAILABLE
            response = test_client.get("/api/nginx/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"

    def test_get_config_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_config") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/nginx/config", headers=auth_headers)
        assert response.status_code == 503


# ===================================================================
# GET /api/nginx/vhosts テスト
# ===================================================================


class TestNginxVhosts:
    """GET /api/nginx/vhosts テスト"""

    def test_get_vhosts_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_vhosts") as mock:
            mock.return_value = NGINX_VHOSTS_OK
            response = test_client.get("/api/nginx/vhosts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["vhosts"], list)
        assert len(data["vhosts"]) == 1

    def test_get_vhosts_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_vhosts") as mock:
            mock.return_value = NGINX_VHOSTS_EMPTY
            response = test_client.get("/api/nginx/vhosts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_vhosts_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_vhosts") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/nginx/vhosts", headers=auth_headers)
        assert response.status_code == 503


# ===================================================================
# GET /api/nginx/connections テスト
# ===================================================================


class TestNginxConnections:
    """GET /api/nginx/connections テスト"""

    def test_get_connections_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_connections") as mock:
            mock.return_value = NGINX_CONNECTIONS_OK
            response = test_client.get("/api/nginx/connections", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "connections_raw" in data

    def test_get_connections_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_connections") as mock:
            mock.return_value = {
                "status": "success",
                "connections_raw": "",
                "timestamp": "2026-03-01T00:00:00Z",
            }
            response = test_client.get("/api/nginx/connections", headers=auth_headers)
        assert response.status_code == 200

    def test_get_connections_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_connections") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/nginx/connections", headers=auth_headers)
        assert response.status_code == 503


# ===================================================================
# GET /api/nginx/logs テスト
# ===================================================================


class TestNginxLogs:
    """GET /api/nginx/logs テスト"""

    def test_get_logs_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_OK
            response = test_client.get("/api/nginx/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "logs" in data

    def test_get_logs_custom_lines(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_OK
            response = test_client.get("/api/nginx/logs?lines=100", headers=auth_headers)
        assert response.status_code == 200
        mock.assert_called_once_with(lines=100)

    def test_get_logs_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_EMPTY
            response = test_client.get("/api/nginx/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_logs_lines_min_boundary(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_OK
            response = test_client.get("/api/nginx/logs?lines=1", headers=auth_headers)
        assert response.status_code == 200

    def test_get_logs_lines_max_boundary(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_OK
            response = test_client.get("/api/nginx/logs?lines=200", headers=auth_headers)
        assert response.status_code == 200

    def test_get_logs_lines_out_of_range(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = NGINX_LOGS_OK
            response = test_client.get("/api/nginx/logs?lines=201", headers=auth_headers)
        assert response.status_code == 422  # Validation error

    def test_get_logs_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/nginx/logs", headers=auth_headers)
        assert response.status_code == 503

    def test_get_logs_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_nginx_logs") as mock:
            mock.return_value = {"status": "error", "message": "permission denied"}
            response = test_client.get("/api/nginx/logs", headers=auth_headers)
        assert response.status_code == 503
