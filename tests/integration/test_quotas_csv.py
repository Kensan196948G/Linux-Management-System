"""
Disk Quota CSV エクスポート + アラート機能 統合テスト

テストケース数: 12件
- CSV エクスポート: 正常系、認証なし、ファイルシステム指定
- アラート: 正常系、全件0件(100%)、閾値バリデーション422、認証なし
- セキュリティ: インジェクション拒否
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SAMPLE_ALL_USERS_WITH_LIMITS = {
    "status": "ok",
    "data": {
        "users": [
            {
                "username": "user1",
                "filesystem": "/",
                "used_kb": 460800,
                "soft_limit_kb": 512000,
                "hard_limit_kb": 1024000,
                "grace_period": "-",
                "inodes_used": 100,
                "inode_soft": 0,
                "inode_hard": 0,
            },
            {
                "username": "user2",
                "filesystem": "/",
                "used_kb": 30720,
                "soft_limit_kb": 512000,
                "hard_limit_kb": 1024000,
                "grace_period": "-",
                "inodes_used": 20,
                "inode_soft": 0,
                "inode_hard": 0,
            },
        ]
    },
    "timestamp": "2026-02-27T10:00:00",
}

SAMPLE_NO_LIMITS = {
    "status": "ok",
    "data": {
        "users": [
            {
                "username": "user1",
                "filesystem": "/",
                "used_kb": 100000,
                "soft_limit_kb": 0,
                "hard_limit_kb": 0,
            }
        ]
    },
    "timestamp": "2026-02-27T10:00:00",
}


# ===================================================================
# CSV エクスポートテスト
# ===================================================================


class TestQuotaCSVExport:
    """GET /api/quotas/export/csv のテスト"""

    def test_export_csv_success(self, test_client, viewer_token):
        """正常系: CSV を取得でき Content-Type が text/csv であること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/export/csv",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_contains_header_row(self, test_client, viewer_token):
        """CSV にヘッダー行が含まれること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/export/csv",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        assert lines[0].startswith("username")
        assert "used_kb" in lines[0]

    def test_export_csv_contains_user_data(self, test_client, viewer_token):
        """CSV にユーザーデータが含まれること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/export/csv",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        assert "user1" in resp.text
        assert "user2" in resp.text

    def test_export_csv_with_filesystem(self, test_client, viewer_token):
        """ファイルシステム指定でも CSV を取得できること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/export/csv?filesystem=/",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_unauthorized(self, test_client):
        """認証なしは 401 または 403 を返すこと"""
        resp = test_client.get("/api/quotas/export/csv")
        assert resp.status_code in (401, 403)

    def test_export_csv_invalid_filesystem(self, test_client, viewer_token):
        """不正なファイルシステムは 422 を返すこと"""
        resp = test_client.get(
            "/api/quotas/export/csv?filesystem=../etc/passwd",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


# ===================================================================
# アラートテスト
# ===================================================================


class TestQuotaAlerts:
    """GET /api/quotas/alerts のテスト"""

    def test_alerts_default_threshold(self, test_client, viewer_token):
        """デフォルト閾値 80% でアラートを取得できること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/alerts",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert data["threshold"] == 80

    def test_alerts_returns_over_threshold_users(self, test_client, viewer_token):
        """80% 超のユーザーが alerts に含まれること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/alerts?threshold=40",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        usernames = [a["username"] for a in data["alerts"]]
        # user1 は 460800/1024000 ≈ 45% > 40%, user2 は 30720/1024000 ≈ 3% <= 40%
        assert "user1" in usernames
        assert "user2" not in usernames

    def test_alerts_threshold_100_returns_empty(self, test_client, viewer_token):
        """閾値 100% では誰も超えられないため 0 件であること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_ALL_USERS_WITH_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/alerts?threshold=100",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_count"] == 0
        assert data["alerts"] == []

    def test_alerts_threshold_0_validation_error(self, test_client, viewer_token):
        """閾値 0 はバリデーションエラー 422 を返すこと"""
        resp = test_client.get(
            "/api/quotas/alerts?threshold=0",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_alerts_threshold_101_validation_error(self, test_client, viewer_token):
        """閾値 101 はバリデーションエラー 422 を返すこと"""
        resp = test_client.get(
            "/api/quotas/alerts?threshold=101",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_alerts_unauthorized(self, test_client):
        """認証なしは 401 または 403 を返すこと"""
        resp = test_client.get("/api/quotas/alerts")
        assert resp.status_code in (401, 403)

    def test_alerts_no_limit_users_excluded(self, test_client, viewer_token):
        """リミットが 0 のユーザーはアラート対象外であること"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=SAMPLE_NO_LIMITS,
        ):
            resp = test_client.get(
                "/api/quotas/alerts?threshold=1",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_count"] == 0
