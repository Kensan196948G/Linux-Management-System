"""
System Time API エンドポイントのユニットテスト

backend/api/routes/system_time.py のカバレッジ向上
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetTimeStatus:
    """GET /api/time/status テスト"""

    def test_get_time_status_success(self, test_client, auth_headers):
        """正常系: 時刻状態取得"""
        mock_result = {
            "status": "success",
            "system_time": "2026-03-01 10:00:00",
            "utc_time": "2026-03-01 01:00:00",
            "timezone": "Asia/Tokyo",
            "ntp_synchronized": True,
            "ntp_service": "active",
            "rtc_time": "2026-03-01 01:00:00",
        }
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.get_time_status.return_value = mock_result
            response = test_client.get("/api/time/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Asia/Tokyo"

    def test_get_time_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/time/status")
        assert response.status_code == 403

    def test_get_time_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.get_time_status.side_effect = SudoWrapperError("timedatectl failed")
            response = test_client.get("/api/time/status", headers=auth_headers)

        assert response.status_code == 500


class TestListTimezones:
    """GET /api/time/timezones テスト"""

    def test_list_timezones_success(self, test_client, auth_headers):
        """正常系: タイムゾーン一覧取得"""
        mock_result = {
            "status": "success",
            "timezones": ["Asia/Tokyo", "UTC", "US/Eastern", "Europe/London"],
        }
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.get_timezones.return_value = mock_result
            response = test_client.get("/api/time/timezones", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "Asia/Tokyo" in data["timezones"]

    def test_list_timezones_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.get_timezones.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/time/timezones", headers=auth_headers)

        assert response.status_code == 500


class TestSetTimezone:
    """POST /api/time/timezone テスト"""

    def test_set_timezone_success(self, test_client, admin_headers):
        """正常系: タイムゾーン変更"""
        mock_result = {"status": "success"}
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.set_timezone.return_value = mock_result
            response = test_client.post(
                "/api/time/timezone",
                json={"timezone": "Asia/Tokyo", "reason": "Standard timezone change"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "Asia/Tokyo" in data["message"]

    def test_set_timezone_invalid_format(self, test_client, admin_headers):
        """不正なタイムゾーン名形式"""
        response = test_client.post(
            "/api/time/timezone",
            json={"timezone": "../../../etc/passwd", "reason": "Path traversal attempt"},
            headers=admin_headers,
        )
        assert response.status_code == 422  # Pydantic validation

    def test_set_timezone_path_traversal(self, test_client, admin_headers):
        """パストラバーサル"""
        response = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/..Tokyo", "reason": "Traversal"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_timezone_special_chars(self, test_client, admin_headers):
        """特殊文字を含むタイムゾーン"""
        response = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia;rm -rf /", "reason": "Injection attempt"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_timezone_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時"""
        with patch("backend.api.routes.system_time.sudo_wrapper") as mock_sw:
            mock_sw.set_timezone.side_effect = SudoWrapperError("timedatectl failed")
            response = test_client.post(
                "/api/time/timezone",
                json={"timezone": "Asia/Tokyo", "reason": "Change timezone"},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_set_timezone_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/Tokyo", "reason": "Change timezone"},
        )
        assert response.status_code == 403
