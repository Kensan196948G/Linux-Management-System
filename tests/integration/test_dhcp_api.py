"""DHCP Server API テスト (TC_DHP_001〜020)"""

import pytest
from unittest.mock import patch

from backend.core.sudo_wrapper import SudoWrapperError


class TestDhcpStatus:
    """DHCP ステータス取得テスト"""

    def test_TC_DHP_001_status_success_admin(self, test_client, admin_token):
        """TC_DHP_001: ステータス取得成功（admin）"""
        mock_data = {"status": "running", "version": "isc-dhcpd-4.4.3", "service": "isc-dhcp-server"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "running"

    def test_TC_DHP_002_status_viewer(self, test_client, viewer_token):
        """TC_DHP_002: viewer でもステータス取得可能"""
        mock_data = {"status": "stopped", "version": "isc-dhcpd-4.4.3", "service": "isc-dhcp-server"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_DHP_003_status_unauthenticated(self, test_client):
        """TC_DHP_003: 未認証は拒否"""
        resp = test_client.get("/api/dhcp/status")
        assert resp.status_code in (401, 403)

    def test_TC_DHP_004_status_wrapper_error(self, test_client, admin_token):
        """TC_DHP_004: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/dhcp/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_DHP_005_status_stopped(self, test_client, admin_token):
        """TC_DHP_005: サービス停止状態を正常取得"""
        mock_data = {"status": "stopped", "version": "isc-dhcpd-4.4.3", "service": "isc-dhcp-server"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "stopped"


class TestDhcpUnavailable:
    """DHCP 未インストール時 503 テスト"""

    def test_TC_DHP_006_status_unavailable(self, test_client, admin_token):
        """TC_DHP_006: status - DHCP未インストール時 503"""
        mock_data = {"status": "unavailable", "message": "isc-dhcp-server is not installed"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_DHP_007_leases_unavailable(self, test_client, admin_token):
        """TC_DHP_007: leases - DHCP未インストール時 503"""
        mock_data = {"status": "unavailable", "message": "isc-dhcp-server is not installed"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/leases",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_DHP_008_config_unavailable(self, test_client, admin_token):
        """TC_DHP_008: config - DHCP未インストール時 503"""
        mock_data = {"status": "unavailable", "message": "isc-dhcp-server is not installed"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/config",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_DHP_009_pools_unavailable(self, test_client, admin_token):
        """TC_DHP_009: pools - DHCP未インストール時 503"""
        mock_data = {"status": "unavailable", "message": "isc-dhcp-server is not installed"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/pools",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_DHP_010_logs_unavailable(self, test_client, admin_token):
        """TC_DHP_010: logs - DHCP未インストール時 503"""
        mock_data = {"status": "unavailable", "message": "isc-dhcp-server is not installed"}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestDhcpAuthErrors:
    """認証エラーテスト"""

    def test_TC_DHP_011_leases_unauthenticated(self, test_client):
        """TC_DHP_011: leases - 未認証は拒否"""
        resp = test_client.get("/api/dhcp/leases")
        assert resp.status_code in (401, 403)

    def test_TC_DHP_012_config_unauthenticated(self, test_client):
        """TC_DHP_012: config - 未認証は拒否"""
        resp = test_client.get("/api/dhcp/config")
        assert resp.status_code in (401, 403)

    def test_TC_DHP_013_pools_unauthenticated(self, test_client):
        """TC_DHP_013: pools - 未認証は拒否"""
        resp = test_client.get("/api/dhcp/pools")
        assert resp.status_code in (401, 403)

    def test_TC_DHP_014_logs_unauthenticated(self, test_client):
        """TC_DHP_014: logs - 未認証は拒否"""
        resp = test_client.get("/api/dhcp/logs")
        assert resp.status_code in (401, 403)

    def test_TC_DHP_015_status_invalid_token(self, test_client):
        """TC_DHP_015: 無効なトークンは拒否"""
        resp = test_client.get(
            "/api/dhcp/status",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )
        assert resp.status_code in (401, 403)


class TestDhcpEndpoints:
    """正常系エンドポイントテスト"""

    def test_TC_DHP_016_leases_success(self, test_client, admin_token):
        """TC_DHP_016: リース一覧取得成功"""
        mock_data = {
            "leases": [
                {"ip": "192.168.1.100", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "host1", "expires": "2025-01-01 12:00:00", "state": "active"}
            ],
            "total": 1,
        }
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/leases",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "leases" in body["data"]
        assert body["data"]["total"] == 1

    def test_TC_DHP_017_config_success(self, test_client, admin_token):
        """TC_DHP_017: 設定サマリ取得成功"""
        mock_data = {
            "subnets": [
                {"subnet": "192.168.1.0", "netmask": "255.255.255.0", "ranges": [{"start": "192.168.1.100", "end": "192.168.1.200"}]}
            ],
            "total": 1,
        }
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/config",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "subnets" in body["data"]

    def test_TC_DHP_018_pools_success(self, test_client, admin_token):
        """TC_DHP_018: アドレスプール取得成功"""
        mock_data = {
            "pools": [
                {"subnet": "192.168.1.0/255.255.255.0", "ranges": [{"start": "192.168.1.100", "end": "192.168.1.200"}], "allow": [], "deny": []}
            ],
            "total": 1,
        }
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/pools",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "pools" in body["data"]

    def test_TC_DHP_019_logs_success(self, test_client, admin_token):
        """TC_DHP_019: ログ取得成功"""
        mock_data = {"logs": "Jan  1 00:00:00 host dhcpd: DHCPACK on 192.168.1.100\n", "lines": 50}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "logs" in body["data"]

    def test_TC_DHP_020_logs_lines_param(self, test_client, admin_token):
        """TC_DHP_020: logs lines パラメータ（100行指定）"""
        mock_data = {"logs": "line1\nline2\n", "lines": 100}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data) as mock_fn:
            resp = test_client.get(
                "/api/dhcp/logs?lines=100",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=100)


class TestDhcpLogsValidation:
    """ログ lines パラメータバリデーションテスト"""

    def test_TC_DHP_021_logs_lines_too_large(self, test_client, admin_token):
        """TC_DHP_021: lines=201 は 422"""
        resp = test_client.get(
            "/api/dhcp/logs?lines=201",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_DHP_022_logs_lines_zero(self, test_client, admin_token):
        """TC_DHP_022: lines=0 は 422"""
        resp = test_client.get(
            "/api/dhcp/logs?lines=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_DHP_023_logs_lines_min(self, test_client, admin_token):
        """TC_DHP_023: lines=1 は正常"""
        mock_data = {"logs": "", "lines": 1}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/logs?lines=1",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200

    def test_TC_DHP_024_logs_lines_max(self, test_client, admin_token):
        """TC_DHP_024: lines=200 は正常"""
        mock_data = {"logs": "", "lines": 200}
        with patch("backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/dhcp/logs?lines=200",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200

    def test_TC_DHP_025_wrapper_error_leases(self, test_client, admin_token):
        """TC_DHP_025: leases SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/dhcp/leases",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
