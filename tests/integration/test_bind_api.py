"""BIND DNS API テスト (TC_BND_001〜020)"""

import pytest
from unittest.mock import patch

from backend.core.sudo_wrapper import SudoWrapperError


class TestBindStatus:
    """BIND ステータス取得テスト"""

    def test_TC_BND_001_status_success_admin(self, test_client, admin_token):
        """TC_BND_001: ステータス取得成功（admin）"""
        mock_data = {"status": "running", "version": "BIND 9.18.1", "service": "named"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_status", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "running"

    def test_TC_BND_002_status_viewer(self, test_client, viewer_token):
        """TC_BND_002: viewer でもステータス取得可能"""
        mock_data = {"status": "stopped", "version": "unknown", "service": "bind9"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_status", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_BND_003_status_unavailable(self, test_client, admin_token):
        """TC_BND_003: BIND 未インストール環境"""
        mock_data = {"status": "unavailable", "message": "BIND (named) is not installed"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_status", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "unavailable"

    def test_TC_BND_004_status_unauthenticated(self, test_client):
        """TC_BND_004: 未認証は拒否"""
        resp = test_client.get("/api/bind/status")
        assert resp.status_code in (401, 403)

    def test_TC_BND_005_status_wrapper_error(self, test_client, admin_token):
        """TC_BND_005: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_status",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/bind/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestBindZones:
    """BIND ゾーン取得テスト"""

    def test_TC_BND_006_zones_success(self, test_client, admin_token):
        """TC_BND_006: ゾーン一覧取得成功"""
        mock_data = {"zones": "example.com\nlocalhost\n"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_zones", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/zones",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "zones" in body["data"]

    def test_TC_BND_007_zones_empty(self, test_client, admin_token):
        """TC_BND_007: ゾーンが空の場合"""
        mock_data = {"zones": ""}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_zones", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/zones",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["zones"] == ""

    def test_TC_BND_008_zones_unauthenticated(self, test_client):
        """TC_BND_008: 未認証は拒否"""
        resp = test_client.get("/api/bind/zones")
        assert resp.status_code in (401, 403)

    def test_TC_BND_009_zones_wrapper_error(self, test_client, admin_token):
        """TC_BND_009: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_zones",
            side_effect=SudoWrapperError("zones error"),
        ):
            resp = test_client.get(
                "/api/bind/zones",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_BND_010_zones_viewer(self, test_client, viewer_token):
        """TC_BND_010: viewer でもゾーン取得可能"""
        mock_data = {"zones": "example.com\n"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_zones", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/zones",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200


class TestBindConfig:
    """BIND 設定確認テスト"""

    def test_TC_BND_011_config_valid(self, test_client, admin_token):
        """TC_BND_011: 設定確認 - valid"""
        mock_data = {"valid": True, "output": ""}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_config", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/config",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["valid"] is True

    def test_TC_BND_012_config_invalid(self, test_client, admin_token):
        """TC_BND_012: 設定確認 - invalid"""
        mock_data = {"valid": False, "output": "/etc/named.conf:10: syntax error"}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_config", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/config",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid"] is False

    def test_TC_BND_013_config_unauthenticated(self, test_client):
        """TC_BND_013: 未認証は拒否"""
        resp = test_client.get("/api/bind/config")
        assert resp.status_code in (401, 403)

    def test_TC_BND_014_config_wrapper_error(self, test_client, admin_token):
        """TC_BND_014: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_config",
            side_effect=SudoWrapperError("config error"),
        ):
            resp = test_client.get(
                "/api/bind/config",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestBindLogs:
    """BIND ログ取得テスト"""

    def test_TC_BND_015_logs_default(self, test_client, admin_token):
        """TC_BND_015: デフォルト50行取得"""
        mock_data = {"logs": "Feb 27 12:00:00 server named[1234]: starting...\n", "lines": 50}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/bind/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "logs" in body["data"]

    def test_TC_BND_016_logs_custom_lines(self, test_client, admin_token):
        """TC_BND_016: 行数指定"""
        mock_data = {"logs": "log content\n", "lines": 100}
        with patch("backend.api.routes.bind.sudo_wrapper.get_bind_logs", return_value=mock_data) as mock:
            resp = test_client.get(
                "/api/bind/logs?lines=100",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(lines=100)

    def test_TC_BND_017_logs_max_limit(self, test_client, admin_token):
        """TC_BND_017: 200行上限の検証"""
        resp = test_client.get(
            "/api/bind/logs?lines=201",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_BND_018_logs_min_limit(self, test_client, admin_token):
        """TC_BND_018: 最小1行の検証"""
        resp = test_client.get(
            "/api/bind/logs?lines=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_BND_019_logs_unauthenticated(self, test_client):
        """TC_BND_019: 未認証は拒否"""
        resp = test_client.get("/api/bind/logs")
        assert resp.status_code in (401, 403)

    def test_TC_BND_020_logs_wrapper_error(self, test_client, admin_token):
        """TC_BND_020: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.bind.sudo_wrapper.get_bind_logs",
            side_effect=SudoWrapperError("logs error"),
        ):
            resp = test_client.get(
                "/api/bind/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
