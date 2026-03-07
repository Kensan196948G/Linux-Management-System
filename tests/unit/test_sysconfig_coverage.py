"""
sysconfig.py の追加カバレッジテスト

テスト対象: backend/api/routes/sysconfig.py  (lines 122-508)
目的: 現在 43.62% のカバレッジを向上させる
"""

from unittest.mock import patch

import pytest

# ============================================================================
# サンプルデータ
# ============================================================================

HOSTNAME_SUCCESS = {
    "status": "success",
    "hostname": "testhost",
    "fqdn": "testhost.local",
    "short": "testhost",
    "timestamp": "2026-01-01T00:00:00Z",
}

TIMEZONE_SUCCESS = {
    "status": "success",
    "timezone": "UTC",
    "timezone_file": "UTC",
    "ntp_enabled": "yes",
    "local_rtc": "no",
    "rtc_in_local_tz": "no",
    "timestamp": "2026-01-01T00:00:00Z",
}

LOCALE_SUCCESS = {
    "status": "success",
    "lang": "en_US.UTF-8",
    "lc_ctype": "en_US.UTF-8",
    "lc_messages": "en_US.UTF-8",
    "charmap": "UTF-8",
    "timestamp": "2026-01-01T00:00:00Z",
}

KERNEL_SUCCESS = {
    "status": "success",
    "uname": "Linux testhost 5.15.0 #1 SMP x86_64",
    "kernel_name": "Linux",
    "kernel_release": "5.15.0-generic",
    "kernel_version": "#1 SMP",
    "machine": "x86_64",
    "proc_version": "Linux version 5.15.0",
    "timestamp": "2026-01-01T00:00:00Z",
}

UPTIME_SUCCESS = {
    "status": "success",
    "uptime_string": " 10:00:00 up 2 days,  3:20,  1 user,  load average: 0.05",
    "uptime_seconds": "190000.0",
    "load_1min": "0.05",
    "load_5min": "0.10",
    "load_15min": "0.08",
    "timestamp": "2026-01-01T00:00:00Z",
}

MODULES_SUCCESS = {
    "status": "success",
    "modules": [
        {"name": "ext4", "size": "786432", "used": "3"},
        {"name": "nf_conntrack", "size": "172032", "used": "2"},
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}


# ============================================================================
# locale エンドポイントテスト
# ============================================================================


class TestSysconfigLocale:
    """GET /api/sysconfig/locale テスト"""

    def test_get_locale_success(self, test_client, auth_headers):
        """正常なロケール情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = LOCALE_SUCCESS
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "lang" in data
        assert "charmap" in data

    def test_get_locale_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.side_effect = SudoWrapperError("locale failed")
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 500

    def test_get_locale_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = {"status": "error", "message": "localectl failed"}
        response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        # wrapper returns error dict, parsed → 503
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock2:
            mock2.return_value = {"status": "error", "message": "localectl failed"}
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 503

    def test_get_locale_unauthenticated(self, test_client):
        """認証なしは 403"""
        response = test_client.get("/api/sysconfig/locale")
        assert response.status_code == 403

    def test_get_locale_response_fields(self, test_client, auth_headers):
        """レスポンスに必須フィールドが含まれる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = LOCALE_SUCCESS
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "lang" in data
        assert "lc_ctype" in data
        assert "lc_messages" in data
        assert "charmap" in data
        assert "timestamp" in data


# ============================================================================
# kernel エンドポイントテスト
# ============================================================================


class TestSysconfigKernelAdditional:
    """GET /api/sysconfig/kernel 追加テスト"""

    def test_get_kernel_success(self, test_client, auth_headers):
        """正常なカーネル情報取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = KERNEL_SUCCESS
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "kernel_name" in data
        assert "machine" in data

    def test_get_kernel_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.side_effect = SudoWrapperError("uname failed")
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 500

    def test_get_kernel_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = {"status": "error", "message": "uname failed"}
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 503

    def test_get_kernel_unauthenticated(self, test_client):
        """認証なしは 403"""
        response = test_client.get("/api/sysconfig/kernel")
        assert response.status_code == 403

    def test_get_kernel_all_fields(self, test_client, auth_headers):
        """全フィールドが返る"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = KERNEL_SUCCESS
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        data = response.json()
        assert "uname" in data
        assert "kernel_release" in data
        assert "kernel_version" in data
        assert "proc_version" in data


# ============================================================================
# uptime エンドポイントテスト
# ============================================================================


class TestSysconfigUptimeAdditional:
    """GET /api/sysconfig/uptime 追加テスト"""

    def test_get_uptime_success(self, test_client, auth_headers):
        """正常な稼働時間取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = UPTIME_SUCCESS
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "uptime_string" in data
        assert "load_1min" in data

    def test_get_uptime_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.side_effect = SudoWrapperError("uptime failed")
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 500

    def test_get_uptime_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = {"status": "error", "message": "uptime unavailable"}
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 503

    def test_get_uptime_unauthenticated(self, test_client):
        """認証なしは 403"""
        response = test_client.get("/api/sysconfig/uptime")
        assert response.status_code == 403

    def test_get_uptime_load_fields(self, test_client, auth_headers):
        """load_1min / load_5min / load_15min が返る"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = UPTIME_SUCCESS
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        data = response.json()
        assert "load_1min" in data
        assert "load_5min" in data
        assert "load_15min" in data
        assert "uptime_seconds" in data


# ============================================================================
# modules エンドポイントテスト
# ============================================================================


class TestSysconfigModulesAdditional:
    """GET /api/sysconfig/modules 追加テスト"""

    def test_get_modules_success(self, test_client, auth_headers):
        """正常なモジュール一覧取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = MODULES_SUCCESS
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "modules" in data

    def test_get_modules_wrapper_error(self, test_client, auth_headers):
        """ラッパーエラー時は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.side_effect = SudoWrapperError("lsmod failed")
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 500

    def test_get_modules_service_error(self, test_client, auth_headers):
        """サービスエラー時は 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = {"status": "error", "message": "lsmod unavailable"}
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 503

    def test_get_modules_unauthenticated(self, test_client):
        """認証なしは 403"""
        response = test_client.get("/api/sysconfig/modules")
        assert response.status_code == 403

    def test_get_modules_returns_list(self, test_client, auth_headers):
        """modules フィールドはリスト"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = MODULES_SUCCESS
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        data = response.json()
        assert isinstance(data["modules"], list)

    def test_get_modules_empty_list(self, test_client, auth_headers):
        """モジュールが空の場合も 200"""
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


# ============================================================================
# viewer ロールのアクセステスト
# ============================================================================


class TestSysconfigViewerAccess:
    """viewer ロールによるアクセステスト"""

    def test_viewer_can_access_locale(self, test_client, viewer_headers):
        """viewer は locale にアクセスできる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.return_value = LOCALE_SUCCESS
            response = test_client.get("/api/sysconfig/locale", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_access_uptime(self, test_client, viewer_headers):
        """viewer は uptime にアクセスできる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.return_value = UPTIME_SUCCESS
            response = test_client.get("/api/sysconfig/uptime", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_access_modules(self, test_client, viewer_headers):
        """viewer は modules にアクセスできる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.return_value = MODULES_SUCCESS
            response = test_client.get("/api/sysconfig/modules", headers=viewer_headers)
        assert response.status_code == 200


# ============================================================================
# エラーメッセージ内容確認テスト
# ============================================================================


class TestSysconfigErrorMessages:
    """エラーレスポンスの内容確認"""

    def test_hostname_500_contains_detail(self, test_client, auth_headers):
        """hostname 500 レスポンスに message が含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_hostname") as mock:
            mock.side_effect = SudoWrapperError("hostname script error")
            response = test_client.get("/api/sysconfig/hostname", headers=auth_headers)
        assert response.status_code == 500
        data = response.json()
        assert "message" in data

    def test_timezone_503_contains_detail(self, test_client, auth_headers):
        """timezone 503 レスポンスに message が含まれる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_timezone") as mock:
            mock.return_value = {"status": "error", "message": "timedatectl not found"}
            response = test_client.get("/api/sysconfig/timezone", headers=auth_headers)
        assert response.status_code == 503
        data = response.json()
        assert "message" in data

    def test_locale_500_message(self, test_client, auth_headers):
        """locale 500 に error メッセージ含む"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_locale") as mock:
            mock.side_effect = SudoWrapperError("locale error detail")
            response = test_client.get("/api/sysconfig/locale", headers=auth_headers)
        assert response.status_code == 500
        data = response.json()
        assert "locale error detail" in data.get("message", "")

    def test_kernel_503_message(self, test_client, auth_headers):
        """kernel 503 のメッセージ確認"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_kernel") as mock:
            mock.return_value = {"status": "error", "message": "kernel info unavailable"}
            response = test_client.get("/api/sysconfig/kernel", headers=auth_headers)
        assert response.status_code == 503

    def test_uptime_500_message(self, test_client, auth_headers):
        """uptime 500 のメッセージ確認"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_uptime") as mock:
            mock.side_effect = SudoWrapperError("uptime error detail")
            response = test_client.get("/api/sysconfig/uptime", headers=auth_headers)
        assert response.status_code == 500
        data = response.json()
        assert "uptime error detail" in data.get("message", "")

    def test_modules_500_message(self, test_client, auth_headers):
        """modules 500 のメッセージ確認"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sysconfig_modules") as mock:
            mock.side_effect = SudoWrapperError("modules error detail")
            response = test_client.get("/api/sysconfig/modules", headers=auth_headers)
        assert response.status_code == 500
        data = response.json()
        assert "modules error detail" in data.get("message", "")
