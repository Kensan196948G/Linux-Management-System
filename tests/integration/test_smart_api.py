"""
SMART Drive Status モジュール - 統合テスト

テストケース数: 20件
- 正常系: disks/info/health/tests エンドポイント
- unavailable 系: smartctl 未インストール環境
- 異常系: 権限不足、未認証、不正ディスク名
- セキュリティ: SudoWrapperError 処理
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SMART_DISKS_OK = {
    "status": "success",
    "smartctl_available": True,
    "lsblk": {"blockdevices": [{"name": "sda", "size": "500G", "type": "disk", "tran": "sata", "model": "TESTDISK"}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_DISKS_NO_SMARTCTL = {
    "status": "success",
    "smartctl_available": False,
    "lsblk": {"blockdevices": [{"name": "sda", "size": "500G", "type": "disk", "tran": "sata", "model": "TESTDISK"}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_DISKS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "lsblk not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_INFO_OK = {
    "status": "success",
    "disk": "/dev/sda",
    "info_raw": "Device Model: TESTDISK\nSerial Number: 12345\nFirmware Version: 1.0\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_INFO_UNAVAILABLE = {
    "status": "unavailable",
    "message": "smartctl not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_HEALTH_PASSED = {
    "status": "success",
    "disk": "/dev/sda",
    "health": "PASSED",
    "output_raw": "SMART overall-health self-assessment test result: PASSED\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_HEALTH_FAILED = {
    "status": "success",
    "disk": "/dev/sda",
    "health": "FAILED",
    "output_raw": "SMART overall-health self-assessment test result: FAILED!\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_HEALTH_UNAVAILABLE = {
    "status": "unavailable",
    "message": "smartctl not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_TESTS_OK = {
    "status": "success",
    "tests": [{"disk": "/dev/sda", "selftest_raw": "SMART Self-test log structure revision number 1\n"}],
    "timestamp": "2026-03-01T00:00:00Z",
}

SMART_TESTS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "smartctl not found",
    "tests": [],
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストケース
# ===================================================================


class TestSmartDisks:
    """TC_SMT_001〜005: SMART disks エンドポイントテスト"""

    def test_TC_SMT_001_disks_ok(self, test_client, admin_token):
        """TC_SMT_001: ディスク一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks", return_value=SMART_DISKS_OK):
            resp = test_client.get("/api/smart/disks", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["smartctl_available"] is True

    def test_TC_SMT_002_disks_no_smartctl(self, test_client, admin_token):
        """TC_SMT_002: smartctl 未インストール時も成功（smartctl_available=False）"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks", return_value=SMART_DISKS_NO_SMARTCTL):
            resp = test_client.get("/api/smart/disks", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["smartctl_available"] is False

    def test_TC_SMT_003_disks_unavailable(self, test_client, admin_token):
        """TC_SMT_003: lsblk 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks", return_value=SMART_DISKS_UNAVAILABLE):
            resp = test_client.get("/api/smart/disks", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SMT_004_disks_unauthorized(self, test_client):
        """TC_SMT_004: 未認証時の 401 返却"""
        resp = test_client.get("/api/smart/disks")
        assert resp.status_code in (401, 403)

    def test_TC_SMT_005_disks_wrapper_error(self, test_client, admin_token):
        """TC_SMT_005: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/smart/disks", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestSmartInfo:
    """TC_SMT_006〜010: SMART info エンドポイントテスト"""

    def test_TC_SMT_006_info_ok(self, test_client, admin_token):
        """TC_SMT_006: ディスク詳細情報の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_info", return_value=SMART_INFO_OK):
            resp = test_client.get("/api/smart/info/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["disk"] == "/dev/sda"

    def test_TC_SMT_007_info_unavailable(self, test_client, admin_token):
        """TC_SMT_007: smartctl 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_info", return_value=SMART_INFO_UNAVAILABLE):
            resp = test_client.get("/api/smart/info/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SMT_008_info_invalid_disk(self, test_client, admin_token):
        """TC_SMT_008: 不正なディスク名で 400 返却"""
        resp = test_client.get("/api/smart/info/dev/invalid-disk!", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400

    def test_TC_SMT_009_info_unauthorized(self, test_client):
        """TC_SMT_009: 未認証時の 401 返却"""
        resp = test_client.get("/api/smart/info/dev/sda")
        assert resp.status_code in (401, 403)

    def test_TC_SMT_010_info_wrapper_error(self, test_client, admin_token):
        """TC_SMT_010: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_info", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/smart/info/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestSmartHealth:
    """TC_SMT_011〜015: SMART health エンドポイントテスト"""

    def test_TC_SMT_011_health_passed(self, test_client, admin_token):
        """TC_SMT_011: 健全性チェック PASSED"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_health", return_value=SMART_HEALTH_PASSED):
            resp = test_client.get("/api/smart/health/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["health"] == "PASSED"

    def test_TC_SMT_012_health_failed(self, test_client, admin_token):
        """TC_SMT_012: 健全性チェック FAILED"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_health", return_value=SMART_HEALTH_FAILED):
            resp = test_client.get("/api/smart/health/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["health"] == "FAILED"

    def test_TC_SMT_013_health_unavailable(self, test_client, admin_token):
        """TC_SMT_013: smartctl 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_health", return_value=SMART_HEALTH_UNAVAILABLE):
            resp = test_client.get("/api/smart/health/dev/sda", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SMT_014_health_invalid_disk(self, test_client, admin_token):
        """TC_SMT_014: 不正なディスク名で 400 返却"""
        resp = test_client.get("/api/smart/health/dev/sda;rm-rf", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400

    def test_TC_SMT_015_health_viewer_allowed(self, test_client, viewer_token):
        """TC_SMT_015: viewer ロールでも健全性チェック取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_health", return_value=SMART_HEALTH_PASSED):
            resp = test_client.get("/api/smart/health/dev/sda", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200


class TestSmartTests:
    """TC_SMT_016〜020: SMART tests エンドポイントテスト"""

    def test_TC_SMT_016_tests_ok(self, test_client, admin_token):
        """TC_SMT_016: selftest ログの正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests", return_value=SMART_TESTS_OK):
            resp = test_client.get("/api/smart/tests", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["tests"], list)

    def test_TC_SMT_017_tests_unavailable(self, test_client, admin_token):
        """TC_SMT_017: smartctl 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests", return_value=SMART_TESTS_UNAVAILABLE):
            resp = test_client.get("/api/smart/tests", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SMT_018_tests_unauthorized(self, test_client):
        """TC_SMT_018: 未認証時の 401 返却"""
        resp = test_client.get("/api/smart/tests")
        assert resp.status_code in (401, 403)

    def test_TC_SMT_019_tests_viewer_allowed(self, test_client, viewer_token):
        """TC_SMT_019: viewer ロールでも selftest ログ取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests", return_value=SMART_TESTS_OK):
            resp = test_client.get("/api/smart/tests", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_SMT_020_tests_wrapper_error(self, test_client, admin_token):
        """TC_SMT_020: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/smart/tests", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503
