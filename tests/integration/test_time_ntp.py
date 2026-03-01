"""
System Time NTP 管理モジュール - 統合テスト (v0.24)

新規エンドポイントのテスト:
    GET /api/time/ntp-servers   - NTPサーバー一覧
    GET /api/time/sync-status   - 時刻同期状態詳細
    既存エンドポイント後退テスト

テストケース数: 16件
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SAMPLE_NTP = {
    "status": "ok",
    "data": {"output": "^* ntp1.example.com  .GPS.  1 10 377  15  -12.345ms  +0.001ms"},
}
SAMPLE_SYNC = {
    "status": "ok",
    "data": {"output": "NTPSynchronized=yes|Timezone=Asia/Tokyo|LocalRTC=no|"},
}
SAMPLE_TIMEZONES = {
    "status": "ok",
    "data": {"timezones": ["Asia/Tokyo", "UTC", "America/New_York"]},
}
SAMPLE_STATUS = {
    "status": "ok",
    "data": {
        "system_time": "2026-01-01T00:00:00+09:00",
        "utc_time": "2025-12-31T15:00:00+00:00",
        "timezone": "Asia/Tokyo",
        "ntp_synchronized": "yes",
        "ntp_service": "chrony",
        "rtc_time": "",
    },
}


# ===================================================================
# GET /api/time/ntp-servers
# ===================================================================


class TestNtpServersAPI:
    """GET /api/time/ntp-servers のテスト"""

    def test_ntp_servers_viewer_ok(self, test_client, viewer_token):
        """Viewer ロールで NTP サーバー一覧取得成功（200）"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_ntp_servers",
            return_value=SAMPLE_NTP,
        ):
            resp = test_client.get(
                "/api/time/ntp-servers",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_ntp_servers_response_structure(self, test_client, viewer_token):
        """レスポンスに status と data.output キーが存在する"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_ntp_servers",
            return_value=SAMPLE_NTP,
        ):
            resp = test_client.get(
                "/api/time/ntp-servers",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "data" in body
        assert "output" in body["data"]

    def test_ntp_servers_unauthorized(self, test_client):
        """認証なしは 401 を返す"""
        resp = test_client.get("/api/time/ntp-servers")
        assert resp.status_code == 401

    def test_ntp_servers_wrapper_error_returns_500(self, test_client, viewer_token):
        """SudoWrapperError 発生時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_ntp_servers",
            side_effect=SudoWrapperError("chrony not running"),
        ):
            resp = test_client.get(
                "/api/time/ntp-servers",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 500

    def test_ntp_servers_admin_ok(self, test_client, admin_token):
        """Admin ロールでも 200 を返す"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_ntp_servers",
            return_value=SAMPLE_NTP,
        ):
            resp = test_client.get(
                "/api/time/ntp-servers",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200


# ===================================================================
# GET /api/time/sync-status
# ===================================================================


class TestSyncStatusAPI:
    """GET /api/time/sync-status のテスト"""

    def test_sync_status_viewer_ok(self, test_client, viewer_token):
        """Viewer ロールで時刻同期状態取得成功（200）"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_sync_status",
            return_value=SAMPLE_SYNC,
        ):
            resp = test_client.get(
                "/api/time/sync-status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_sync_status_response_structure(self, test_client, viewer_token):
        """レスポンスに status と data.output キーが存在する"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_sync_status",
            return_value=SAMPLE_SYNC,
        ):
            resp = test_client.get(
                "/api/time/sync-status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "data" in body
        assert "output" in body["data"]

    def test_sync_status_unauthorized(self, test_client):
        """認証なしは 401 を返す"""
        resp = test_client.get("/api/time/sync-status")
        assert resp.status_code == 401

    def test_sync_status_wrapper_error_returns_500(self, test_client, viewer_token):
        """SudoWrapperError 発生時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_sync_status",
            side_effect=SudoWrapperError("timedatectl failed"),
        ):
            resp = test_client.get(
                "/api/time/sync-status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 500

    def test_sync_status_admin_ok(self, test_client, admin_token):
        """Admin ロールでも 200 を返す"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_sync_status",
            return_value=SAMPLE_SYNC,
        ):
            resp = test_client.get(
                "/api/time/sync-status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200


# ===================================================================
# 既存エンドポイント後退テスト
# ===================================================================


class TestExistingEndpointsRegression:
    """既存エンドポイントへの後退テスト"""

    def test_existing_status_ok(self, test_client, viewer_token):
        """既存 GET /api/time/status が引き続き 200 を返す"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_STATUS,
        ):
            resp = test_client.get(
                "/api/time/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_existing_status_response_structure(self, test_client, viewer_token):
        """既存 status レスポンスに ntp_synchronized キーが存在する"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_STATUS,
        ):
            resp = test_client.get(
                "/api/time/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "ntp_synchronized" in body["data"]

    def test_existing_timezones_ok(self, test_client, viewer_token):
        """既存 GET /api/time/timezones が引き続き 200 を返す"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_timezones",
            return_value=SAMPLE_TIMEZONES,
        ):
            resp = test_client.get(
                "/api/time/timezones",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_existing_timezones_response_structure(self, test_client, viewer_token):
        """既存 timezones レスポンスに data.timezones リストが存在する"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_timezones",
            return_value=SAMPLE_TIMEZONES,
        ):
            resp = test_client.get(
                "/api/time/timezones",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "timezones" in body["data"]

    def test_existing_status_unauthorized(self, test_client):
        """既存 status エンドポイントも認証なしは 401 を返す"""
        resp = test_client.get("/api/time/status")
        assert resp.status_code == 401

    def test_existing_timezones_unauthorized(self, test_client):
        """既存 timezones エンドポイントも認証なしは 401 を返す"""
        resp = test_client.get("/api/time/timezones")
        assert resp.status_code == 401
