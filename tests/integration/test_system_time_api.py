"""
System Time モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）

テスト対象:
    GET  /api/time/status      - 時刻・タイムゾーン情報
    GET  /api/time/timezones   - タイムゾーン一覧
    GET  /api/time/ntp-servers - NTPサーバー一覧
    GET  /api/time/sync-status - 時刻同期状態詳細
    POST /api/time/timezone    - タイムゾーン変更（Admin + 承認フロー）
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError

# ===================================================================
# サンプルレスポンスデータ
# ===================================================================

SAMPLE_TIME_STATUS = {
    "status": "success",
    "system_time": "2026-03-20 14:30:00",
    "utc_time": "2026-03-20 05:30:00",
    "timezone": "Asia/Tokyo",
    "ntp_synchronized": True,
    "ntp_service": "active",
    "rtc_time": "2026-03-20 05:30:00",
}

SAMPLE_TIMEZONES = {
    "status": "success",
    "timezones": [
        "Africa/Abidjan",
        "America/New_York",
        "Asia/Tokyo",
        "Europe/London",
        "UTC",
    ],
    "count": 5,
}

SAMPLE_NTP_SERVERS = {
    "status": "success",
    "output": "^+ ntp1.jst.mfeed.ad.jp  2 10  377  12  +0.123  0.456  0.789",
    "servers": [
        {"name": "ntp1.jst.mfeed.ad.jp", "stratum": 2, "reach": "377"},
    ],
}

SAMPLE_SYNC_STATUS = {
    "status": "success",
    "output": {
        "Timezone": "Asia/Tokyo",
        "NTP": "yes",
        "NTPSynchronized": "yes",
        "TimeUSec": "2026-03-20T14:30:00+09:00",
    },
}


# ===================================================================
# 認証・認可テスト
# ===================================================================


class TestTimeAuth:
    """認証なし / ロール別のアクセス制御テスト"""

    def test_status_no_auth(self, test_client):
        """認証なしで時刻状態取得は拒否される"""
        res = test_client.get("/api/time/status")
        assert res.status_code in (401, 403)

    def test_timezones_no_auth(self, test_client):
        """認証なしでタイムゾーン一覧は拒否される"""
        res = test_client.get("/api/time/timezones")
        assert res.status_code in (401, 403)

    def test_ntp_servers_no_auth(self, test_client):
        """認証なしでNTPサーバー一覧は拒否される"""
        res = test_client.get("/api/time/ntp-servers")
        assert res.status_code in (401, 403)

    def test_sync_status_no_auth(self, test_client):
        """認証なしで同期状態取得は拒否される"""
        res = test_client.get("/api/time/sync-status")
        assert res.status_code in (401, 403)

    def test_set_timezone_no_auth(self, test_client):
        """認証なしでタイムゾーン変更は拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "test"},
        )
        assert res.status_code in (401, 403)

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_status")
    def test_viewer_can_read_status(self, mock_fn, test_client, viewer_headers):
        """Viewerは時刻状態を参照できる"""
        mock_fn.return_value = SAMPLE_TIME_STATUS
        res = test_client.get("/api/time/status", headers=viewer_headers)
        assert res.status_code == 200

    @patch("backend.api.routes.system_time.sudo_wrapper.get_timezones")
    def test_viewer_can_read_timezones(self, mock_fn, test_client, viewer_headers):
        """Viewerはタイムゾーン一覧を参照できる"""
        mock_fn.return_value = SAMPLE_TIMEZONES
        res = test_client.get("/api/time/timezones", headers=viewer_headers)
        assert res.status_code == 200

    def test_viewer_cannot_set_timezone(self, test_client, viewer_headers):
        """Viewerはタイムゾーン変更できない"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "test"},
            headers=viewer_headers,
        )
        assert res.status_code == 403


# ===================================================================
# GET /api/time/status テスト
# ===================================================================


class TestTimeStatus:
    """時刻・タイムゾーン状態取得テスト"""

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_status")
    def test_status_success(self, mock_fn, test_client, auth_headers):
        """正常系: 時刻状態取得"""
        mock_fn.return_value = SAMPLE_TIME_STATUS
        res = test_client.get("/api/time/status", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["timezone"] == "Asia/Tokyo"
        assert data["ntp_synchronized"] is True

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_status")
    def test_status_has_required_fields(self, mock_fn, test_client, auth_headers):
        """レスポンスに必須フィールドが含まれる"""
        mock_fn.return_value = SAMPLE_TIME_STATUS
        res = test_client.get("/api/time/status", headers=auth_headers)
        data = res.json()
        for field in ("system_time", "utc_time", "timezone", "ntp_synchronized"):
            assert field in data, f"Missing field: {field}"

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_status")
    def test_status_wrapper_error(self, mock_fn, test_client, auth_headers):
        """sudo_wrapper エラー時は 500 を返す"""
        mock_fn.side_effect = SudoWrapperError("command failed")
        res = test_client.get("/api/time/status", headers=auth_headers)
        assert res.status_code == 500


# ===================================================================
# GET /api/time/timezones テスト
# ===================================================================


class TestTimezones:
    """タイムゾーン一覧テスト"""

    @patch("backend.api.routes.system_time.sudo_wrapper.get_timezones")
    def test_timezones_success(self, mock_fn, test_client, auth_headers):
        """正常系: タイムゾーン一覧取得"""
        mock_fn.return_value = SAMPLE_TIMEZONES
        res = test_client.get("/api/time/timezones", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "timezones" in data
        assert "Asia/Tokyo" in data["timezones"]

    @patch("backend.api.routes.system_time.sudo_wrapper.get_timezones")
    def test_timezones_count(self, mock_fn, test_client, auth_headers):
        """一覧にカウント情報が含まれる"""
        mock_fn.return_value = SAMPLE_TIMEZONES
        res = test_client.get("/api/time/timezones", headers=auth_headers)
        data = res.json()
        assert data.get("count") == 5

    @patch("backend.api.routes.system_time.sudo_wrapper.get_timezones")
    def test_timezones_wrapper_error(self, mock_fn, test_client, auth_headers):
        """sudo_wrapper エラー時は 500 を返す"""
        mock_fn.side_effect = SudoWrapperError("command failed")
        res = test_client.get("/api/time/timezones", headers=auth_headers)
        assert res.status_code == 500


# ===================================================================
# GET /api/time/ntp-servers テスト
# ===================================================================


class TestNtpServers:
    """NTPサーバー一覧テスト"""

    @patch("backend.api.routes.system_time.sudo_wrapper.get_ntp_servers")
    def test_ntp_servers_success(self, mock_fn, test_client, auth_headers):
        """正常系: NTPサーバー一覧取得"""
        mock_fn.return_value = SAMPLE_NTP_SERVERS
        res = test_client.get("/api/time/ntp-servers", headers=auth_headers)
        assert res.status_code == 200

    @patch("backend.api.routes.system_time.sudo_wrapper.get_ntp_servers")
    def test_ntp_servers_wrapper_error(self, mock_fn, test_client, auth_headers):
        """sudo_wrapper エラー時は 500 を返す"""
        mock_fn.side_effect = SudoWrapperError("chrony not installed")
        res = test_client.get("/api/time/ntp-servers", headers=auth_headers)
        assert res.status_code == 500


# ===================================================================
# GET /api/time/sync-status テスト
# ===================================================================


class TestSyncStatus:
    """時刻同期状態テスト"""

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_sync_status")
    def test_sync_status_success(self, mock_fn, test_client, auth_headers):
        """正常系: 同期状態取得"""
        mock_fn.return_value = SAMPLE_SYNC_STATUS
        res = test_client.get("/api/time/sync-status", headers=auth_headers)
        assert res.status_code == 200

    @patch("backend.api.routes.system_time.sudo_wrapper.get_time_sync_status")
    def test_sync_status_wrapper_error(self, mock_fn, test_client, auth_headers):
        """sudo_wrapper エラー時は 500 を返す"""
        mock_fn.side_effect = SudoWrapperError("timedatectl failed")
        res = test_client.get("/api/time/sync-status", headers=auth_headers)
        assert res.status_code == 500


# ===================================================================
# POST /api/time/timezone テスト
# ===================================================================


class TestSetTimezone:
    """タイムゾーン変更テスト"""

    @patch("backend.api.routes.system_time.sudo_wrapper.set_timezone")
    def test_set_timezone_success(self, mock_fn, test_client, admin_headers):
        """正常系: タイムゾーン変更成功（Admin）"""
        mock_fn.return_value = {"status": "success"}
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/Tokyo", "reason": "Standard timezone"},
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["timezone"] == "Asia/Tokyo"

    @patch("backend.api.routes.system_time.sudo_wrapper.set_timezone")
    def test_set_timezone_utc(self, mock_fn, test_client, admin_headers):
        """UTC タイムゾーン設定"""
        mock_fn.return_value = {"status": "success"}
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "Server standardization"},
            headers=admin_headers,
        )
        assert res.status_code == 200

    @patch("backend.api.routes.system_time.sudo_wrapper.set_timezone")
    def test_set_timezone_wrapper_error(self, mock_fn, test_client, admin_headers):
        """sudo_wrapper エラー時は 500 を返す"""
        mock_fn.side_effect = SudoWrapperError("timedatectl failed")
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/Tokyo", "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 500


# ===================================================================
# 入力バリデーションテスト
# ===================================================================


class TestTimezoneValidation:
    """タイムゾーン変更リクエストのバリデーション"""

    def test_empty_timezone_rejected(self, test_client, admin_headers):
        """空のタイムゾーン名は拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "", "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_missing_reason_rejected(self, test_client, admin_headers):
        """変更理由なしは拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_injection_semicolon_rejected(self, test_client, admin_headers):
        """セミコロンを含むタイムゾーン名は拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC; rm -rf /", "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_injection_pipe_rejected(self, test_client, admin_headers):
        """パイプを含むタイムゾーン名は拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC|cat /etc/passwd", "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_path_traversal_rejected(self, test_client, admin_headers):
        """パストラバーサルは拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "../../../etc/shadow", "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_too_long_timezone_rejected(self, test_client, admin_headers):
        """61文字以上のタイムゾーン名は拒否される"""
        res = test_client.post(
            "/api/time/timezone",
            json={"timezone": "A" * 61, "reason": "test"},
            headers=admin_headers,
        )
        assert res.status_code == 422

    def test_valid_timezone_formats(self, test_client, admin_headers):
        """有効なタイムゾーン形式が受け入れられる"""
        valid_names = ["Asia/Tokyo", "US/Eastern", "UTC", "Etc/GMT+9"]
        for tz in valid_names:
            res = test_client.post(
                "/api/time/timezone",
                json={"timezone": tz, "reason": "format test"},
                headers=admin_headers,
            )
            # 422 (validation error) でなければ OK（403権限エラーや500ラッパーエラーは許容）
            assert res.status_code != 422, f"Valid timezone '{tz}' was rejected"
