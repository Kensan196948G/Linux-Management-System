"""
Filesystemモジュール - 統合テスト（15件以上）

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

import json
from unittest.mock import patch

import pytest

# テスト用データ
SAMPLE_DF_STDOUT = json.dumps([
    {
        "filesystem": "/dev/sda1",
        "type": "ext4",
        "size_kb": 51200000,
        "used_kb": 20480000,
        "avail_kb": 28160000,
        "use_pct": "42%",
        "mount": "/",
    },
    {
        "filesystem": "/dev/sda2",
        "type": "ext4",
        "size_kb": 10240000,
        "used_kb": 8960000,
        "avail_kb": 1024000,
        "use_pct": "88%",
        "mount": "/var",
    },
])

SAMPLE_DF_RESPONSE = {
    "status": "success",
    "stdout": SAMPLE_DF_STDOUT,
}

SAMPLE_MOUNTS_RESPONSE = {
    "status": "success",
    "output": (
        '{"filesystems":[{"target":"/","source":"/dev/sda1","fstype":"ext4","options":"rw"}]}'
    ),
}


# ==============================================================================
# 認証テスト
# ==============================================================================


class TestFilesystemAuthentication:
    """認証・認可テスト"""

    def test_anonymous_usage_rejected(self, test_client):
        """認証なしは 403 を返す"""
        response = test_client.get("/api/filesystem/usage")
        assert response.status_code == 403

    def test_anonymous_mounts_rejected(self, test_client):
        """認証なしは 403 を返す"""
        response = test_client.get("/api/filesystem/mounts")
        assert response.status_code == 403

    def test_viewer_can_read_usage(self, test_client, viewer_headers):
        """Viewer ロールはファイルシステム使用量を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = SAMPLE_DF_RESPONSE
            response = test_client.get("/api/filesystem/usage", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_read_mounts(self, test_client, viewer_headers):
        """Viewer ロールはマウントポイントを読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_mounts") as mock:
            mock.return_value = SAMPLE_MOUNTS_RESPONSE
            response = test_client.get("/api/filesystem/mounts", headers=viewer_headers)
        assert response.status_code == 200

    def test_operator_can_read_usage(self, test_client, operator_headers):
        """Operator ロールはファイルシステム使用量を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = SAMPLE_DF_RESPONSE
            response = test_client.get("/api/filesystem/usage", headers=operator_headers)
        assert response.status_code == 200

    def test_admin_can_read_usage(self, test_client, admin_headers):
        """Admin ロールはファイルシステム使用量を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = SAMPLE_DF_RESPONSE
            response = test_client.get("/api/filesystem/usage", headers=admin_headers)
        assert response.status_code == 200


# ==============================================================================
# /api/filesystem/usage テスト
# ==============================================================================


class TestFilesystemUsage:
    """GET /api/filesystem/usage テスト"""

    def test_usage_success_response_structure(self, test_client, auth_headers):
        """成功レスポンスの構造を確認"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = SAMPLE_DF_RESPONSE
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "filesystems" in data
        assert "warnings" in data

    def test_usage_warning_threshold_detected(self, test_client, auth_headers):
        """85%以上の使用率は warnings に含まれる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = SAMPLE_DF_RESPONSE
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        data = response.json()
        # /var is at 88% which exceeds WARNING_THRESHOLD=85
        assert len(data["warnings"]) >= 1
        warning_mounts = [w["filesystem"] for w in data["warnings"]]
        assert "/var" in warning_mounts

    def test_usage_below_threshold_no_warning(self, test_client, auth_headers):
        """85%未満の使用率は warnings に含まれない"""
        low_usage = json.dumps([
            {
                "filesystem": "/dev/sda1",
                "type": "ext4",
                "size_kb": 51200000,
                "used_kb": 10240000,
                "avail_kb": 40960000,
                "use_pct": "20%",
                "mount": "/",
            }
        ])
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = {"status": "success", "stdout": low_usage}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        data = response.json()
        assert data["warnings"] == []

    def test_usage_wrapper_error_returns_500(self, test_client, auth_headers):
        """SudoWrapperError は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.side_effect = SudoWrapperError("df command failed")
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        assert response.status_code == 500

    def test_usage_empty_filesystem_list(self, test_client, auth_headers):
        """空のファイルシステム一覧を正常処理"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = {"status": "success", "stdout": "[]"}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["filesystems"] == []
        assert data["warnings"] == []

    def test_usage_invalid_json_stdout(self, test_client, auth_headers):
        """不正なJSON出力でも 200 を返す（空リスト扱い）"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = {"status": "success", "stdout": "not-json"}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["filesystems"] == []

    def test_usage_no_stdout_key(self, test_client, auth_headers):
        """stdout キーがない場合でも 200 を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_usage") as mock:
            mock.return_value = {"status": "success"}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["filesystems"] == []


# ==============================================================================
# /api/filesystem/mounts テスト
# ==============================================================================


class TestFilesystemMounts:
    """GET /api/filesystem/mounts テスト"""

    def test_mounts_success_response_structure(self, test_client, auth_headers):
        """成功レスポンスの構造を確認"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_mounts") as mock:
            mock.return_value = SAMPLE_MOUNTS_RESPONSE
            response = test_client.get("/api/filesystem/mounts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "mounts" in data

    def test_mounts_wrapper_error_returns_500(self, test_client, auth_headers):
        """SudoWrapperError は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_mounts") as mock:
            mock.side_effect = SudoWrapperError("findmnt failed")
            response = test_client.get("/api/filesystem/mounts", headers=auth_headers)

        assert response.status_code == 500

    def test_mounts_result_contains_data(self, test_client, auth_headers):
        """mounts フィールドにデータが含まれる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_mounts") as mock:
            mock.return_value = SAMPLE_MOUNTS_RESPONSE
            response = test_client.get("/api/filesystem/mounts", headers=auth_headers)

        data = response.json()
        assert data["mounts"] is not None

    def test_mounts_viewer_can_access(self, test_client, viewer_headers):
        """Viewer はマウントポイント一覧にアクセスできる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_filesystem_mounts") as mock:
            mock.return_value = SAMPLE_MOUNTS_RESPONSE
            response = test_client.get("/api/filesystem/mounts", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# sudo_wrapper メソッド存在確認テスト
# ==============================================================================


class TestSudoWrapperFilesystemMethods:
    """sudo_wrapper にファイルシステムメソッドが追加されていることを確認"""

    def test_get_filesystem_usage_method_exists(self):
        from backend.core.sudo_wrapper import SudoWrapper
        assert hasattr(SudoWrapper, "get_filesystem_usage")

    def test_get_filesystem_du_method_exists(self):
        from backend.core.sudo_wrapper import SudoWrapper
        assert hasattr(SudoWrapper, "get_filesystem_du")

    def test_get_filesystem_mounts_method_exists(self):
        from backend.core.sudo_wrapper import SudoWrapper
        assert hasattr(SudoWrapper, "get_filesystem_mounts")
