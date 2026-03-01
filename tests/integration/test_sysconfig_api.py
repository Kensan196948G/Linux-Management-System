"""
Sysconfig モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest

# ==============================================================================
# テスト用サンプルデータ
# ==============================================================================

SAMPLE_HOSTNAME_RESPONSE = {
    "status": "success",
    "hostname": "myserver",
    "fqdn": "myserver.example.com",
    "short": "myserver",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_TIMEZONE_RESPONSE = {
    "status": "success",
    "timezone": "Asia/Tokyo",
    "timezone_file": "Asia/Tokyo",
    "ntp_enabled": "yes",
    "local_rtc": "no",
    "rtc_in_local_tz": "no",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_LOCALE_RESPONSE = {
    "status": "success",
    "lang": "ja_JP.UTF-8",
    "lc_ctype": "ja_JP.UTF-8",
    "lc_messages": "ja_JP.UTF-8",
    "charmap": "UTF-8",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_KERNEL_RESPONSE = {
    "status": "success",
    "uname": "Linux myserver 5.15.0 #1 SMP x86_64 GNU/Linux",
    "kernel_name": "Linux",
    "kernel_release": "5.15.0-generic",
    "kernel_version": "#1 SMP",
    "machine": "x86_64",
    "proc_version": "Linux version 5.15.0",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_UPTIME_RESPONSE = {
    "status": "success",
    "uptime_string": " 12:00:00 up 5 days,  3:20,  2 users,  load average: 0.10, 0.15, 0.12",
    "uptime_seconds": "455999.12",
    "load_1min": "0.10",
    "load_5min": "0.15",
    "load_15min": "0.12",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_MODULES_RESPONSE = {
    "status": "success",
    "modules": [
        {"name": "nf_conntrack", "size": "172032", "used": "2"},
        {"name": "nft_compat", "size": "20480", "used": "1"},
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# 認証テスト
# ==============================================================================


class TestSysconfigAuth:
    """認証なしアクセスのテスト（6件）"""

    def test_anonymous_hostname_rejected(self, test_client):
        """認証なしで /hostname は拒否される"""
        response = test_client.get("/api/sysconfig/hostname")
        assert response.status_code == 403

    def test_anonymous_timezone_rejected(self, test_client):
        """認証なしで /timezone は拒否される"""
        response = test_client.get("/api/sysconfig/timezone")
        assert response.status_code == 403

    def test_anonymous_locale_rejected(self, test_client):
        """認証なしで /locale は拒否される"""
        response = test_client.get("/api/sysconfig/locale")
        assert response.status_code == 403

    def test_anonymous_kernel_rejected(self, test_client):
        """認証なしで /kernel は拒否される"""
        response = test_client.get("/api/sysconfig/kernel")
        assert response.status_code == 403

    def test_anonymous_uptime_rejected(self, test_client):
        """認証なしで /uptime は拒否される"""
        response = test_client.get("/api/sysconfig/uptime")
        assert response.status_code == 403

    def test_anonymous_modules_rejected(self, test_client):
        """認証なしで /modules は拒否される"""
        response = test_client.get("/api/sysconfig/modules")
        assert response.status_code == 403

    def test_viewer_can_read_hostname(self, test_client, viewer_headers):
        """viewer ロールは hostname を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_hostname") as mock:
            mock.return_value = SAMPLE_HOSTNAME_RESPONSE
            response = test_client.get("/api/sysconfig/hostname", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_read_kernel(self, test_client, viewer_headers):
        """viewer ロールは kernel を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = SAMPLE_KERNEL_RESPONSE
            response = test_client.get("/api/sysconfig/kernel", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# hostname エンドポイントテスト
# ==============================================================================


class TestSysconfigHostname:
    """GET /api/sysconfig/hostname テスト"""

    def test_get_hostname_success(self, test_client, auth_headers):
        """正常なホスト名情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_hostname") as mock:
            mock.return_value = SAMPLE_HOSTNAME_RESPONSE
            response = test_client.get("/api/sysconfig/hostname", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "hostname" in data
        assert "fqdn" in data
        assert "timestamp" in data

    def test_get_hostname_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_hostname") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/hostname", headers=auth_headers)
        assert response.status_code == 500

    def test_get_hostname_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_hostname") as mock:
            mock.return_value = {"status": "error", "message": "command failed"}
            response = test_client.get("/api/sysconfig/hostname", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# timezone エンドポイントテスト
# ==============================================================================


class TestSysconfigTimezone:
    """GET /api/sysconfig/timezone テスト"""

    def test_get_timezone_success(self, test_client, auth_headers):
        """正常なタイムゾーン情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_timezone") as mock:
            mock.return_value = SAMPLE_TIMEZONE_RESPONSE
            response = test_client.get("/api/sysconfig/timezone", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "timezone" in data
        assert "ntp_enabled" in data
        assert "timestamp" in data

    def test_get_timezone_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_timezone") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/timezone", headers=auth_headers)
        assert response.status_code == 500

    def test_get_timezone_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_timezone") as mock:
            mock.return_value = {"status": "error", "message": "timedatectl failed"}
            response = test_client.get("/api/sysconfig/timezone", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# locale エンドポイントテスト
# ==============================================================================


class TestSysconfigLocale:
    """GET /api/sysconfig/locale テスト"""

    def test_get_locale_success(self, test_client, auth_headers):
        """正常なロケール情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = SAMPLE_LOCALE_RESPONSE
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "lang" in data
        assert "charmap" in data
        assert "timestamp" in data

    def test_get_locale_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 500

    def test_get_locale_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = {"status": "error", "message": "localectl failed"}
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# kernel エンドポイントテスト
# ==============================================================================


class TestSysconfigKernel:
    """GET /api/sysconfig/kernel テスト"""

    def test_get_kernel_success(self, test_client, auth_headers):
        """正常なカーネル情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = SAMPLE_KERNEL_RESPONSE
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "kernel_release" in data
        assert "machine" in data
        assert "uname" in data
        assert "timestamp" in data

    def test_get_kernel_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 500

    def test_get_kernel_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = {"status": "error", "message": "uname failed"}
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# uptime エンドポイントテスト
# ==============================================================================


class TestSysconfigUptime:
    """GET /api/sysconfig/uptime テスト"""

    def test_get_uptime_success(self, test_client, auth_headers):
        """正常な稼働時間情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = SAMPLE_UPTIME_RESPONSE
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "uptime_string" in data
        assert "load_1min" in data
        assert "timestamp" in data

    def test_get_uptime_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 500

    def test_get_uptime_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = {"status": "error", "message": "uptime failed"}
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# modules エンドポイントテスト
# ==============================================================================


class TestSysconfigModules:
    """GET /api/sysconfig/modules テスト"""

    def test_get_modules_success(self, test_client, auth_headers):
        """正常なモジュール一覧取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = SAMPLE_MODULES_RESPONSE
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "modules" in data
        assert isinstance(data["modules"], list)
        assert "timestamp" in data

    def test_get_modules_empty_list(self, test_client, auth_headers):
        """空のモジュール一覧も正常に返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = {
                "status": "success",
                "modules": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["modules"] == []

    def test_get_modules_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 500

    def test_get_modules_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = {"status": "error", "message": "lsmod failed"}
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 503
