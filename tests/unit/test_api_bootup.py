"""
Bootup API エンドポイントのユニットテスト

backend/api/routes/bootup.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetBootupStatus:
    """GET /api/bootup/status テスト"""

    def test_get_status_success(self, test_client, auth_headers):
        """正常系: 起動状態取得"""
        mock_result = {
            "status": "success",
            "default_target": "multi-user.target",
            "uptime": "5 days",
            "last_boot": "2026-02-24T10:00:00Z",
            "failed_units": [],
        }
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.get_bootup_status.return_value = mock_result
            response = test_client.get("/api/bootup/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/bootup/status")
        assert response.status_code == 403

    def test_get_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.get_bootup_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bootup/status", headers=auth_headers)

        assert response.status_code == 500


class TestGetBootupServices:
    """GET /api/bootup/services テスト"""

    def test_get_services_success(self, test_client, auth_headers):
        """正常系: 起動時サービス一覧取得"""
        mock_result = {
            "status": "success",
            "services": [
                {"unit": "nginx.service", "state": "enabled", "vendor_preset": "enabled"},
                {"unit": "ssh.service", "state": "enabled", "vendor_preset": "enabled"},
            ],
        }
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.get_bootup_services.return_value = mock_result
            response = test_client.get("/api/bootup/services", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_services_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.get_bootup_services.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bootup/services", headers=auth_headers)

        assert response.status_code == 500


class TestEnableServiceAtBoot:
    """POST /api/bootup/enable テスト"""

    def test_enable_success(self, test_client, admin_headers):
        """正常系: サービス起動時有効化"""
        mock_result = {"status": "success", "message": "Service enabled"}
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.enable_service_at_boot.return_value = mock_result
            response = test_client.post(
                "/api/bootup/enable",
                json={"service": "nginx", "reason": "Enable nginx on boot"},
                headers=admin_headers,
            )

        assert response.status_code == 202

    def test_enable_not_in_allowlist(self, test_client, admin_headers):
        """allowlist外のサービス"""
        response = test_client.post(
            "/api/bootup/enable",
            json={"service": "malicious-svc", "reason": "Try to enable"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "許可リスト" in response.json()["message"]

    def test_enable_forbidden_chars(self, test_client, admin_headers):
        """特殊文字を含むサービス名"""
        response = test_client.post(
            "/api/bootup/enable",
            json={"service": "nginx; rm -rf /", "reason": "Attack"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_enable_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.enable_service_at_boot.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/bootup/enable",
                json={"service": "nginx", "reason": "Enable on boot"},
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestDisableServiceAtBoot:
    """POST /api/bootup/disable テスト"""

    def test_disable_success(self, test_client, admin_headers):
        """正常系: サービス起動時無効化"""
        mock_result = {"status": "success", "message": "Service disabled"}
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.disable_service_at_boot.return_value = mock_result
            response = test_client.post(
                "/api/bootup/disable",
                json={"service": "redis", "reason": "Disable redis on boot"},
                headers=admin_headers,
            )

        assert response.status_code == 202

    def test_disable_not_in_allowlist(self, test_client, admin_headers):
        """allowlist外のサービス"""
        response = test_client.post(
            "/api/bootup/disable",
            json={"service": "unknown-service", "reason": "Try to disable"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_disable_forbidden_chars(self, test_client, admin_headers):
        """特殊文字を含むサービス名"""
        response = test_client.post(
            "/api/bootup/disable",
            json={"service": "nginx|cat /etc/passwd", "reason": "Attack"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_disable_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.disable_service_at_boot.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/bootup/disable",
                json={"service": "redis", "reason": "Disable on boot"},
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestScheduleSystemAction:
    """POST /api/bootup/action テスト"""

    def test_schedule_shutdown_success(self, test_client, admin_headers):
        """正常系: シャットダウンスケジュール"""
        mock_result = {"status": "success", "message": "Shutdown scheduled"}
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.schedule_shutdown.return_value = mock_result
            response = test_client.post(
                "/api/bootup/action",
                json={"action": "shutdown", "delay": "+5", "reason": "Maintenance"},
                headers=admin_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["action"] == "shutdown"

    def test_schedule_reboot_success(self, test_client, admin_headers):
        """正常系: 再起動スケジュール"""
        mock_result = {"status": "success", "message": "Reboot scheduled"}
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.schedule_reboot.return_value = mock_result
            response = test_client.post(
                "/api/bootup/action",
                json={"action": "reboot", "delay": "+10", "reason": "Kernel update"},
                headers=admin_headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["action"] == "reboot"

    def test_schedule_invalid_delay(self, test_client, admin_headers):
        """不正な遅延値"""
        response = test_client.post(
            "/api/bootup/action",
            json={"action": "shutdown", "delay": "+999", "reason": "Test"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "許可されていません" in response.json()["message"]

    def test_schedule_shutdown_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時（shutdown）"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.schedule_shutdown.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/bootup/action",
                json={"action": "shutdown", "delay": "now", "reason": "Emergency"},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_schedule_reboot_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時（reboot）"""
        with patch("backend.api.routes.bootup.sudo_wrapper") as mock_sw:
            mock_sw.schedule_reboot.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/bootup/action",
                json={"action": "reboot", "delay": "now", "reason": "Emergency"},
                headers=admin_headers,
            )

        assert response.status_code == 500
