"""
Disk Quota 管理モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）

テストケース数: 22件
- 正常系: 状態取得、ユーザー一覧、ユーザー/グループ情報、レポート、クォータ設定
- 異常系: 権限不足、未認証、不正入力（インジェクション、無効パス）
- セキュリティ: インジェクション攻撃拒否、allowlist外拒否
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SAMPLE_QUOTA_STATUS = {
    "status": "unavailable",
    "message": "quota tools not installed",
    "filesystems": [],
}

SAMPLE_QUOTA_STATUS_OK = {
    "status": "ok",
    "data": {
        "filesystems": [
            {
                "device": "/dev/sda1",
                "mountpoint": "/",
                "quota_enabled": True,
                "users_over_limit": 2,
            }
        ]
    },
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_USER_QUOTA = {
    "status": "ok",
    "data": {
        "user": "testuser",
        "filesystem": "/",
        "used_kb": 102400,
        "soft_limit_kb": 512000,
        "hard_limit_kb": 1024000,
        "grace_period": "-",
        "inodes_used": 100,
        "inode_soft": 0,
        "inode_hard": 0,
    },
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_GROUP_QUOTA = {
    "status": "ok",
    "data": {
        "group": "developers",
        "filesystem": "/",
        "used_kb": 204800,
        "soft_limit_kb": 1024000,
        "hard_limit_kb": 2048000,
    },
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_ALL_USERS_QUOTA = {
    "status": "ok",
    "data": {
        "users": [
            {"username": "user1", "used_kb": 102400, "soft_limit_kb": 512000},
            {"username": "user2", "used_kb": 30720, "soft_limit_kb": 512000},
        ]
    },
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_QUOTA_REPORT = {
    "status": "ok",
    "data": {"report": "User disk space usage:\nuser1: 100M / 500M"},
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_QUOTA_SET_RESULT = {
    "status": "success",
    "message": "Quota set for user testuser",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestQuotaStatusAPI:
    """GET /api/quotas/status のテスト"""

    def test_get_quota_status_viewer(self, test_client, viewer_token):
        """TC001: Viewer ロールでクォータ状態取得成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value=SAMPLE_QUOTA_STATUS,
        ):
            resp = test_client.get(
                "/api/quotas/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_get_quota_status_with_filesystem(self, test_client, viewer_token):
        """TC002: ファイルシステム指定でクォータ状態取得"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value=SAMPLE_QUOTA_STATUS_OK,
        ) as mock:
            resp = test_client.get(
                "/api/quotas/status?filesystem=/",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("/")

    def test_get_quota_status_unauthorized(self, test_client):
        """TC003: 未認証でクォータ状態取得失敗"""
        resp = test_client.get("/api/quotas/status")
        assert resp.status_code in (401, 403)

    def test_get_quota_status_invalid_filesystem(self, test_client, viewer_token):
        """TC004: 無効なファイルシステムパスで拒否"""
        resp = test_client.get(
            "/api/quotas/status?filesystem=/invalid;ls",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_get_quota_status_injection_filesystem(self, test_client, viewer_token):
        """TC005: ファイルシステムパスへのインジェクション攻撃拒否"""
        resp = test_client.get(
            "/api/quotas/status?filesystem=/;ls",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


class TestQuotaUsersAPI:
    """GET /api/quotas/users のテスト"""

    def test_get_all_user_quotas_viewer(self, test_client, viewer_token):
        """TC006: Viewer ロールで全ユーザークォータ一覧取得成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_QUOTA,
        ):
            resp = test_client.get(
                "/api/quotas/users",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_get_all_user_quotas_with_filesystem(self, test_client, viewer_token):
        """TC007: ファイルシステム指定で全ユーザークォータ一覧取得"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_QUOTA,
        ) as mock:
            resp = test_client.get(
                "/api/quotas/users?filesystem=/home",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("/home")

    def test_get_all_user_quotas_unauthorized(self, test_client):
        """TC008: 未認証で全ユーザークォータ一覧取得失敗"""
        resp = test_client.get("/api/quotas/users")
        assert resp.status_code in (401, 403)


class TestQuotaUserDetailAPI:
    """GET /api/quotas/user/{username} のテスト"""

    def test_get_user_quota_viewer(self, test_client, viewer_token):
        """TC009: Viewer ロールでユーザークォータ情報取得成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_user_quota",
            return_value=SAMPLE_USER_QUOTA,
        ):
            resp = test_client.get(
                "/api/quotas/user/testuser",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_get_user_quota_invalid_username(self, test_client, viewer_token):
        """TC010: 無効なユーザー名で拒否"""
        resp = test_client.get(
            "/api/quotas/user/test;rm -rf",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code in (404, 422)

    def test_get_user_quota_injection_attack(self, test_client, viewer_token):
        """TC011: ユーザー名へのシェルインジェクション攻撃拒否"""
        resp = test_client.get(
            "/api/quotas/user/$(whoami)",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code in (404, 422)

    def test_get_user_quota_long_name(self, test_client, viewer_token):
        """TC012: 長すぎるユーザー名で拒否"""
        long_name = "a" * 65
        resp = test_client.get(
            f"/api/quotas/user/{long_name}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_get_user_quota_unauthorized(self, test_client):
        """TC013: 未認証でユーザークォータ情報取得失敗"""
        resp = test_client.get("/api/quotas/user/testuser")
        assert resp.status_code in (401, 403)


class TestQuotaGroupDetailAPI:
    """GET /api/quotas/group/{groupname} のテスト"""

    def test_get_group_quota_viewer(self, test_client, viewer_token):
        """TC014: Viewer ロールでグループクォータ情報取得成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_group_quota",
            return_value=SAMPLE_GROUP_QUOTA,
        ):
            resp = test_client.get(
                "/api/quotas/group/developers",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_get_group_quota_injection(self, test_client, viewer_token):
        """TC015: グループ名へのインジェクション攻撃拒否"""
        resp = test_client.get(
            "/api/quotas/group/dev|ls",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code in (404, 422)


class TestQuotaReportAPI:
    """GET /api/quotas/report のテスト"""

    def test_get_quota_report_viewer(self, test_client, viewer_token):
        """TC016: Viewer ロールでクォータレポート取得成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_report",
            return_value=SAMPLE_QUOTA_REPORT,
        ):
            resp = test_client.get(
                "/api/quotas/report",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_get_quota_report_unauthorized(self, test_client):
        """TC017: 未認証でレポート取得失敗"""
        resp = test_client.get("/api/quotas/report")
        assert resp.status_code in (401, 403)


class TestQuotaSetAPI:
    """POST /api/quotas/set のテスト"""

    def test_set_user_quota_admin(self, test_client, admin_token):
        """TC018: Admin ロールでユーザークォータ設定成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_user_quota",
            return_value=SAMPLE_QUOTA_SET_RESULT,
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/",
                    "soft_kb": 512000,
                    "hard_kb": 1024000,
                    "isoft": 0,
                    "ihard": 0,
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["name"] == "testuser"
        assert data["soft_kb"] == 512000
        assert data["hard_kb"] == 1024000

    def test_set_group_quota_admin(self, test_client, admin_token):
        """TC019: Admin ロールでグループクォータ設定成功"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_group_quota",
            return_value=SAMPLE_QUOTA_SET_RESULT,
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "group",
                    "name": "developers",
                    "filesystem": "/home",
                    "soft_kb": 1024000,
                    "hard_kb": 2048000,
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "group"
        assert data["name"] == "developers"

    def test_set_quota_viewer_forbidden(self, test_client, viewer_token):
        """TC020: Viewer ロールでクォータ設定は403 Forbidden"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 512000,
                "hard_kb": 1024000,
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_set_quota_unauthorized(self, test_client):
        """TC021: 未認証でクォータ設定失敗"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 512000,
                "hard_kb": 1024000,
            },
        )
        assert resp.status_code in (401, 403)

    def test_set_quota_invalid_type(self, test_client, admin_token):
        """TC022: 無効なタイプでクォータ設定拒否"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "root",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 512000,
                "hard_kb": 1024000,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_quota_invalid_name(self, test_client, admin_token):
        """TC023: 無効なユーザー名でクォータ設定拒否（インジェクション攻撃）"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "test; rm -rf /",
                "filesystem": "/",
                "soft_kb": 512000,
                "hard_kb": 1024000,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_quota_invalid_filesystem(self, test_client, admin_token):
        """TC024: 無効なファイルシステムパスでクォータ設定拒否"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "../../etc",
                "soft_kb": 512000,
                "hard_kb": 1024000,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_quota_negative_values(self, test_client, admin_token):
        """TC025: 負のクォータ値で設定拒否"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": -1,
                "hard_kb": 1024000,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422
