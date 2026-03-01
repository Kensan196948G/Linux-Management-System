"""
E2E テスト - Approval History / Stats API エンドポイント

承認履歴・統計APIの E2E シナリオを検証する。
エンドポイント:
  GET /api/approval/history              - 承認履歴一覧
  GET /api/approval/history/export       - 承認履歴エクスポート（CSV/JSON）
  GET /api/approval/stats                - 承認統計情報
"""

import pytest


pytestmark = [pytest.mark.e2e]


class TestApprovalHistoryE2E:
    """Approval History API の E2E テスト"""

    # ------------------------------------------------------------------
    # GET /api/approval/history - 承認履歴一覧
    # ------------------------------------------------------------------

    def test_get_approval_history(self, api_client, admin_token):
        """GET /api/approval/history -> 200, 基本フィールド確認"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get("/api/approval/history", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert isinstance(data["items"], list)

    def test_get_approval_history_filter_by_action(self, api_client, admin_token):
        """GET /api/approval/history?action=approved -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history?action=approved", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "items" in data

    def test_get_approval_history_filter_invalid_action(
        self, api_client, admin_token
    ):
        """GET /api/approval/history?action=invalid -> 200 or 400"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history?action=invalid_action_xyz", headers=headers
        )
        # サービスがフィルタを無視して空結果を返すか、400 で拒否するかは実装依存
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            data = response.json()
            assert "items" in data

    def test_get_approval_history_pagination(self, api_client, admin_token):
        """GET /api/approval/history?page=1&per_page=5 -> items <= 5"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history?page=1&per_page=5", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["items"]) <= 5
        assert data["page"] == 1
        assert data["per_page"] == 5

    def test_get_approval_history_large_per_page_capped(
        self, api_client, admin_token
    ):
        """GET /api/approval/history?per_page=200 -> per_page は 100 に制限"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history?per_page=200", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # サーバー側で per_page > 100 は 100 に切り詰められる
        assert data["per_page"] <= 100

    def test_get_approval_history_filter_by_request_type(
        self, api_client, admin_token
    ):
        """GET /api/approval/history?request_type=firewall_modify -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history?request_type=firewall_modify", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    # ------------------------------------------------------------------
    # GET /api/approval/history/export - エクスポート
    # ------------------------------------------------------------------

    def test_export_history_csv(self, api_client, admin_token):
        """GET /api/approval/history/export?format=csv -> 200, text/csv"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history/export?format=csv", headers=headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type

    def test_export_history_json(self, api_client, admin_token):
        """GET /api/approval/history/export?format=json -> 200, application/json"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history/export?format=json", headers=headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "json" in content_type

    def test_export_history_invalid_format(self, api_client, admin_token):
        """GET /api/approval/history/export?format=xml -> 400"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/history/export?format=xml", headers=headers
        )
        assert response.status_code == 400

    # ------------------------------------------------------------------
    # GET /api/approval/stats - 統計情報
    # ------------------------------------------------------------------

    def test_get_approval_stats(self, api_client, admin_token):
        """GET /api/approval/stats -> 200, 基本フィールド確認"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get("/api/approval/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_approval_stats_period_7d(self, api_client, admin_token):
        """GET /api/approval/stats?period=7d -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/stats?period=7d", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_approval_stats_period_30d(self, api_client, admin_token):
        """GET /api/approval/stats?period=30d -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/stats?period=30d", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_approval_stats_period_90d(self, api_client, admin_token):
        """GET /api/approval/stats?period=90d -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/stats?period=90d", headers=headers
        )
        assert response.status_code == 200

    def test_get_approval_stats_period_all(self, api_client, admin_token):
        """GET /api/approval/stats?period=all -> 200"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/stats?period=all", headers=headers
        )
        assert response.status_code == 200

    def test_get_approval_stats_period_invalid(self, api_client, admin_token):
        """GET /api/approval/stats?period=invalid -> 200（デフォルト 30d にフォールバック）"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get(
            "/api/approval/stats?period=invalid", headers=headers
        )
        # 実装上、不正な period は "30d" にフォールバックするので 200
        assert response.status_code == 200

    # ------------------------------------------------------------------
    # 権限テスト
    # ------------------------------------------------------------------

    def test_history_requires_auth(self, api_client):
        """認証なしで history -> 403"""
        response = api_client.get("/api/approval/history")
        assert response.status_code == 403

    def test_export_requires_auth(self, api_client):
        """認証なしで export -> 403"""
        response = api_client.get("/api/approval/history/export?format=json")
        assert response.status_code == 403

    def test_stats_requires_auth(self, api_client):
        """認証なしで stats -> 403"""
        response = api_client.get("/api/approval/stats")
        assert response.status_code == 403

    def test_viewer_cannot_access_history(self, api_client, viewer_token):
        """Viewer ロールは承認履歴にアクセス不可"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = api_client.get("/api/approval/history", headers=headers)
        assert response.status_code == 403

    def test_operator_cannot_access_history(self, api_client, auth_token):
        """Operator ロールは承認履歴にアクセス不可"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = api_client.get("/api/approval/history", headers=headers)
        assert response.status_code == 403

    def test_viewer_cannot_access_stats(self, api_client, viewer_token):
        """Viewer ロールは統計にアクセス不可"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = api_client.get("/api/approval/stats", headers=headers)
        assert response.status_code == 403

    def test_viewer_cannot_export(self, api_client, viewer_token):
        """Viewer ロールはエクスポート不可"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = api_client.get(
            "/api/approval/history/export?format=json", headers=headers
        )
        assert response.status_code == 403

    def test_operator_cannot_export(self, api_client, auth_token):
        """Operator ロールはエクスポート不可"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = api_client.get(
            "/api/approval/history/export?format=json", headers=headers
        )
        assert response.status_code == 403
