"""
Filesystem API エンドポイントのユニットテスト

backend/api/routes/filesystem.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetFilesystemUsage:
    """GET /api/filesystem/usage テスト"""

    def test_usage_success(self, test_client, auth_headers):
        """正常系: ファイルシステム使用量取得"""
        fs_data = [
            {"mount": "/", "use_pct": "45%", "size": "50G"},
            {"mount": "/home", "use_pct": "60%", "size": "100G"},
        ]
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_usage.return_value = {
                "stdout": json.dumps(fs_data)
            }
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["filesystems"]) == 2
        assert data["warnings"] == []

    def test_usage_with_warning(self, test_client, auth_headers):
        """使用率85%以上で警告"""
        fs_data = [
            {"mount": "/", "use_pct": "90%", "size": "50G"},
            {"mount": "/home", "use_pct": "40%", "size": "100G"},
        ]
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_usage.return_value = {
                "stdout": json.dumps(fs_data)
            }
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["warnings"]) == 1
        assert data["warnings"][0]["use_percent"] == 90

    def test_usage_empty_stdout(self, test_client, auth_headers):
        """stdoutが空の場合"""
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_usage.return_value = {"stdout": ""}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["filesystems"] == []

    def test_usage_invalid_json(self, test_client, auth_headers):
        """stdoutがJSON解析不可の場合"""
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_usage.return_value = {"stdout": "not json"}
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["filesystems"] == []

    def test_usage_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は500"""
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_usage.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/filesystem/usage", headers=auth_headers)
        assert response.status_code == 500

    def test_usage_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/filesystem/usage")
        assert response.status_code == 403


class TestGetFilesystemMounts:
    """GET /api/filesystem/mounts テスト"""

    def test_mounts_success(self, test_client, auth_headers):
        """正常系: マウントポイント取得"""
        mock_mounts = [
            {"device": "/dev/sda1", "mount": "/", "type": "ext4"},
            {"device": "tmpfs", "mount": "/tmp", "type": "tmpfs"},
        ]
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_mounts.return_value = mock_mounts
            response = test_client.get("/api/filesystem/mounts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["mounts"]) == 2

    def test_mounts_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は500"""
        with patch("backend.api.routes.filesystem.sudo_wrapper") as mock_sw:
            mock_sw.get_filesystem_mounts.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/filesystem/mounts", headers=auth_headers)
        assert response.status_code == 500

    def test_mounts_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/filesystem/mounts")
        assert response.status_code == 403
