"""
Network API エンドポイントのユニットテスト

backend/api/routes/network.py のカバレッジ向上
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetInterfaces:
    """GET /api/network/interfaces テスト"""

    def test_get_interfaces_success(self, test_client, auth_headers):
        """正常系: インターフェース一覧取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "interfaces": [
                    {"ifname": "eth0", "operstate": "UP", "address": "00:11:22:33:44:55"}
                ],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_interfaces.return_value = mock_result
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["interfaces"]) == 1

    def test_get_interfaces_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/network/interfaces")
        assert response.status_code == 403

    def test_get_interfaces_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "ip command not found"}
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_interfaces.return_value = mock_result
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 503

    def test_get_interfaces_wrapper_error_with_fallback(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → ip コマンドフォールバック"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps([{"ifname": "lo", "operstate": "UNKNOWN"}])

        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_interfaces.side_effect = SudoWrapperError("NoNewPrivileges")
            with patch("subprocess.run", return_value=mock_proc):
                response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_interfaces_wrapper_error_fallback_fails(self, test_client, auth_headers):
        """SudoWrapperError + フォールバックも失敗"""
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_interfaces.side_effect = SudoWrapperError("Permission denied")
            with patch("subprocess.run", side_effect=OSError("ip not found")):
                response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 500


class TestGetStats:
    """GET /api/network/stats テスト"""

    def test_get_stats_success(self, test_client, auth_headers):
        """正常系: ネットワーク統計取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "stats": [{"interface": "eth0", "rx_bytes": 1000, "tx_bytes": 2000}],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_stats.return_value = mock_result
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_stats_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "stats unavailable"}
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_stats.return_value = mock_result
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 503

    def test_get_stats_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_stats.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 500


class TestGetConnections:
    """GET /api/network/connections テスト"""

    def test_get_connections_success(self, test_client, auth_headers):
        """正常系: 接続一覧取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "connections": [
                    {"protocol": "tcp", "local": "0.0.0.0:80", "remote": "192.168.1.1:12345"}
                ],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_connections.return_value = mock_result
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_connections_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "ss command failed"}
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_connections.return_value = mock_result
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 503

    def test_get_connections_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_connections.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 500


class TestGetRoutes:
    """GET /api/network/routes テスト"""

    def test_get_routes_success(self, test_client, auth_headers):
        """正常系: ルーティングテーブル取得"""
        mock_result = {
            "status": "success",
            "output": json.dumps({
                "status": "success",
                "routes": [
                    {"destination": "0.0.0.0/0", "gateway": "192.168.1.1", "interface": "eth0"}
                ],
                "timestamp": "2026-03-01T00:00:00Z",
            }),
        }
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_routes.return_value = mock_result
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_routes_error_status(self, test_client, auth_headers):
        """エラーステータス"""
        mock_result = {"status": "error", "message": "routes unavailable"}
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_routes.return_value = mock_result
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 503

    def test_get_routes_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.network.sudo_wrapper") as mock_sw:
            mock_sw.get_network_routes.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 500


class TestGetDns:
    """GET /api/network/dns テスト"""

    def test_get_dns_success(self, test_client, auth_headers):
        """正常系: DNS設定取得"""
        response = test_client.get("/api/network/dns", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "dns" in data
        assert "nameservers" in data["dns"]

    def test_get_dns_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/network/dns")
        assert response.status_code == 403
