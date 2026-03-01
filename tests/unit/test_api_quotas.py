"""
Quotas API エンドポイントのユニットテスト

backend/api/routes/quotas.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _mock_output(**kwargs):
    """テスト用モックデータ生成ヘルパー"""
    defaults = {"status": "ok", "timestamp": "2026-03-01T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


class TestGetQuotaStatus:
    """GET /api/quotas/status テスト"""

    def test_status_success(self, test_client, auth_headers):
        """正常系: クォータ状態取得"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_status.return_value = _mock_output(
                quotas_enabled=True, filesystems=["/dev/sda1"]
            )
            response = test_client.get("/api/quotas/status", headers=auth_headers)
        assert response.status_code == 200

    def test_status_with_filesystem(self, test_client, auth_headers):
        """正常系: ファイルシステム指定"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_status.return_value = _mock_output(quotas_enabled=True)
            response = test_client.get(
                "/api/quotas/status?filesystem=/dev/sda1", headers=auth_headers
            )
        assert response.status_code == 200

    def test_status_invalid_filesystem(self, test_client, auth_headers):
        """不正なファイルシステム"""
        response = test_client.get(
            "/api/quotas/status?filesystem=;rm+-rf+/", headers=auth_headers
        )
        assert response.status_code == 422

    def test_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/quotas/status", headers=auth_headers)
        assert response.status_code == 503

    def test_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/quotas/status")
        assert response.status_code == 403


class TestGetAllUserQuotas:
    """GET /api/quotas/users テスト"""

    def test_users_success(self, test_client, auth_headers):
        """正常系: 全ユーザークォータ取得"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_all_user_quotas.return_value = _mock_output(
                users=[{"username": "testuser", "used_kb": 1024}]
            )
            response = test_client.get("/api/quotas/users", headers=auth_headers)
        assert response.status_code == 200

    def test_users_with_filesystem(self, test_client, auth_headers):
        """正常系: ファイルシステム指定"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_all_user_quotas.return_value = _mock_output(users=[])
            response = test_client.get(
                "/api/quotas/users?filesystem=/dev/sda1", headers=auth_headers
            )
        assert response.status_code == 200

    def test_users_invalid_filesystem(self, test_client, auth_headers):
        """不正なファイルシステム"""
        response = test_client.get(
            "/api/quotas/users?filesystem=|cat+/etc/passwd", headers=auth_headers
        )
        assert response.status_code == 422

    def test_users_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_all_user_quotas.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/quotas/users", headers=auth_headers)
        assert response.status_code == 503


class TestGetUserQuota:
    """GET /api/quotas/user/{username} テスト"""

    def test_user_quota_success(self, test_client, auth_headers):
        """正常系: 特定ユーザークォータ取得"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_user_quota.return_value = _mock_output(
                username="testuser", used_kb=512
            )
            response = test_client.get(
                "/api/quotas/user/testuser", headers=auth_headers
            )
        assert response.status_code == 200

    def test_user_quota_invalid_name(self, test_client, auth_headers):
        """不正なユーザー名"""
        response = test_client.get(
            "/api/quotas/user/test;rm+-rf", headers=auth_headers
        )
        assert response.status_code == 422

    def test_user_quota_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_user_quota.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/quotas/user/testuser", headers=auth_headers
            )
        assert response.status_code == 503


class TestGetGroupQuota:
    """GET /api/quotas/group/{groupname} テスト"""

    def test_group_quota_success(self, test_client, auth_headers):
        """正常系: グループクォータ取得"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_group_quota.return_value = _mock_output(
                groupname="devteam", used_kb=2048
            )
            response = test_client.get(
                "/api/quotas/group/devteam", headers=auth_headers
            )
        assert response.status_code == 200

    def test_group_quota_invalid_name(self, test_client, auth_headers):
        """不正なグループ名"""
        response = test_client.get(
            "/api/quotas/group/dev;ls", headers=auth_headers
        )
        assert response.status_code == 422

    def test_group_quota_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_group_quota.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/quotas/group/devteam", headers=auth_headers
            )
        assert response.status_code == 503


class TestGetQuotaReport:
    """GET /api/quotas/report テスト"""

    def test_report_success(self, test_client, auth_headers):
        """正常系: レポート取得"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_report.return_value = _mock_output(
                report={"total_users": 10}
            )
            response = test_client.get("/api/quotas/report", headers=auth_headers)
        assert response.status_code == 200

    def test_report_with_filesystem(self, test_client, auth_headers):
        """正常系: ファイルシステム指定"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_report.return_value = _mock_output(report={})
            response = test_client.get(
                "/api/quotas/report?filesystem=/dev/sda1", headers=auth_headers
            )
        assert response.status_code == 200

    def test_report_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.get_quota_report.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/quotas/report", headers=auth_headers)
        assert response.status_code == 503


class TestSetQuota:
    """POST /api/quotas/set テスト"""

    def test_set_user_quota_success(self, test_client, admin_headers):
        """正常系: ユーザークォータ設定（Admin）"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.set_user_quota.return_value = _mock_output(
                message="Quota set for user testuser"
            )
            response = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/dev/sda1",
                    "soft_kb": 1024,
                    "hard_kb": 2048,
                },
                headers=admin_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "user"
        assert data["name"] == "testuser"

    def test_set_group_quota_success(self, test_client, admin_headers):
        """正常系: グループクォータ設定（Admin）"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.set_group_quota.return_value = _mock_output(
                message="Quota set for group devteam"
            )
            response = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "group",
                    "name": "devteam",
                    "filesystem": "/dev/sda1",
                    "soft_kb": 4096,
                    "hard_kb": 8192,
                },
                headers=admin_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "group"

    def test_set_quota_approver(self, test_client, approver_headers):
        """正常系: Approverも設定可能"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.set_user_quota.return_value = _mock_output(
                message="Quota set"
            )
            response = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/dev/sda1",
                    "soft_kb": 512,
                    "hard_kb": 1024,
                },
                headers=approver_headers,
            )
        assert response.status_code == 200

    def test_set_quota_invalid_type(self, test_client, admin_headers):
        """不正なタイプ"""
        response = test_client.post(
            "/api/quotas/set",
            json={
                "type": "other",
                "name": "testuser",
                "filesystem": "/dev/sda1",
                "soft_kb": 1024,
                "hard_kb": 2048,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_quota_invalid_name(self, test_client, admin_headers):
        """不正な名前"""
        response = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "test;rm -rf /",
                "filesystem": "/dev/sda1",
                "soft_kb": 1024,
                "hard_kb": 2048,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_quota_invalid_filesystem(self, test_client, admin_headers):
        """不正なファイルシステム"""
        response = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": ";rm -rf /",
                "soft_kb": 1024,
                "hard_kb": 2048,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_quota_hard_less_than_soft(self, test_client, admin_headers):
        """hard_kb < soft_kb"""
        response = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/dev/sda1",
                "soft_kb": 2048,
                "hard_kb": 1024,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_set_quota_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.set_user_quota.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/dev/sda1",
                    "soft_kb": 1024,
                    "hard_kb": 2048,
                },
                headers=admin_headers,
            )
        assert response.status_code == 503

    def test_set_quota_operator_forbidden(self, test_client, auth_headers):
        """Operator権限不足"""
        response = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/dev/sda1",
                "soft_kb": 1024,
                "hard_kb": 2048,
            },
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_set_quota_uuid_filesystem(self, test_client, admin_headers):
        """正常系: UUID形式ファイルシステム"""
        with patch("backend.api.routes.quotas.sudo_wrapper") as mock_sw:
            mock_sw.set_user_quota.return_value = _mock_output(message="OK")
            response = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "UUID=abcd1234-5678-90ab-cdef-1234567890ab",
                    "soft_kb": 1024,
                    "hard_kb": 2048,
                },
                headers=admin_headers,
            )
        assert response.status_code == 200
