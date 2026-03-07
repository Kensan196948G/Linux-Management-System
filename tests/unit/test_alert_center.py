"""
アラートセンター API ユニットテスト

新規エンドポイント:
  GET  /api/alerts/unread-count
  POST /api/alerts/{id}/mark-read
  POST /api/alerts/mark-all-read

既存エンドポイントのスモークテスト:
  GET  /api/alerts/rules
  GET  /api/alerts/active
  GET  /api/alerts/summary
"""

import pytest

import backend.api.routes.alerts as alerts_module


@pytest.fixture(autouse=True)
def reset_read_alerts():
    """テスト間で既読セットをリセットする"""
    alerts_module._read_alerts.clear()
    yield
    alerts_module._read_alerts.clear()


# ===================================================================
# GET /api/alerts/unread-count
# ===================================================================

class TestGetUnreadCount:
    """GET /api/alerts/unread-count テスト"""

    def test_unread_count_authenticated(self, test_client, auth_headers):
        """正常系: 認証済みで unread-count を取得できる"""
        response = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        assert data["count"] >= 0

    def test_unread_count_unauthenticated(self, test_client):
        """未認証は 403"""
        response = test_client.get("/api/alerts/unread-count")
        assert response.status_code == 403

    def test_unread_count_invalid_token(self, test_client):
        """不正トークンは 401 または 403"""
        response = test_client.get(
            "/api/alerts/unread-count",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code in (401, 403)

    def test_unread_count_decreases_after_mark_read(self, test_client, auth_headers):
        """既読にすると unread-count が減少する"""
        # まず unread-count を取得
        r1 = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert r1.status_code == 200
        before = r1.json()["count"]

        if before > 0:
            # 最初のアラートルール ID を既読にする
            alert_id = alerts_module.DEFAULT_RULES[0]["id"]
            mr = test_client.post(f"/api/alerts/{alert_id}/mark-read", headers=auth_headers)
            assert mr.status_code == 200

            r2 = test_client.get("/api/alerts/unread-count", headers=auth_headers)
            assert r2.status_code == 200
            # unread-count は増加しない
            assert r2.json()["count"] <= before

    def test_unread_count_zero_after_mark_all_read(self, test_client, auth_headers):
        """全既読後は unread-count が 0"""
        mar = test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        assert mar.status_code == 200

        r = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_unread_count_returns_integer(self, test_client, auth_headers):
        """count フィールドは整数"""
        response = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json()["count"], int)

    def test_unread_count_viewer_can_access(self, test_client):
        """viewer ロールでもアクセス可能（read:alerts 権限）"""
        login = test_client.post(
            "/api/auth/login",
            json={"email": "viewer@example.com", "password": "viewer123"},
        )
        if login.status_code != 200:
            pytest.skip("viewer ユーザーが未作成のためスキップ")
        token = login.json()["access_token"]
        response = test_client.get(
            "/api/alerts/unread-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


# ===================================================================
# POST /api/alerts/{alert_id}/mark-read
# ===================================================================

class TestMarkAlertRead:
    """POST /api/alerts/{alert_id}/mark-read テスト"""

    def test_mark_read_success(self, test_client, auth_headers):
        """正常系: 既知 ID を既読にできる"""
        alert_id = alerts_module.DEFAULT_RULES[0]["id"]
        response = test_client.post(f"/api/alerts/{alert_id}/mark-read", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["alert_id"] == alert_id
        assert data["read"] is True

    def test_mark_read_unknown_id_returns_404(self, test_client, auth_headers):
        """存在しない ID は 404"""
        response = test_client.post(
            "/api/alerts/unknown-nonexistent-id/mark-read",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_mark_read_unauthenticated(self, test_client):
        """未認証は 403"""
        alert_id = alerts_module.DEFAULT_RULES[0]["id"]
        response = test_client.post(f"/api/alerts/{alert_id}/mark-read")
        assert response.status_code == 403

    def test_mark_read_idempotent(self, test_client, auth_headers):
        """同じ ID を複数回既読にしても 200 が返る"""
        alert_id = alerts_module.DEFAULT_RULES[0]["id"]
        for _ in range(3):
            r = test_client.post(f"/api/alerts/{alert_id}/mark-read", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["read"] is True

    def test_mark_read_persists_in_module_state(self, test_client, auth_headers):
        """既読状態がモジュールの _read_alerts セットに保存される"""
        alert_id = alerts_module.DEFAULT_RULES[1]["id"]
        assert alert_id not in alerts_module._read_alerts

        test_client.post(f"/api/alerts/{alert_id}/mark-read", headers=auth_headers)
        assert alert_id in alerts_module._read_alerts

    def test_mark_read_all_valid_ids(self, test_client, auth_headers):
        """全有効アラート ID を一つずつ既読にできる"""
        for rule in alerts_module.DEFAULT_RULES:
            r = test_client.post(f"/api/alerts/{rule['id']}/mark-read", headers=auth_headers)
            assert r.status_code == 200

    def test_mark_read_invalid_token(self, test_client):
        """不正トークンは 401 または 403"""
        alert_id = alerts_module.DEFAULT_RULES[0]["id"]
        response = test_client.post(
            f"/api/alerts/{alert_id}/mark-read",
            headers={"Authorization": "Bearer bad.token"},
        )
        assert response.status_code in (401, 403)

    def test_mark_read_empty_id_returns_404(self, test_client, auth_headers):
        """空文字列相当の ID は 404 または 422"""
        response = test_client.post("/api/alerts/   /mark-read", headers=auth_headers)
        assert response.status_code in (404, 422)


# ===================================================================
# POST /api/alerts/mark-all-read
# ===================================================================

class TestMarkAllRead:
    """POST /api/alerts/mark-all-read テスト"""

    def test_mark_all_read_success(self, test_client, auth_headers):
        """正常系: 全件既読になる"""
        response = test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["read"] is True
        assert data["marked"] == len(alerts_module.DEFAULT_RULES)

    def test_mark_all_read_makes_unread_count_zero(self, test_client, auth_headers):
        """全件既読後は unread-count が 0"""
        test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        r = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_mark_all_read_unauthenticated(self, test_client):
        """未認証は 403"""
        response = test_client.post("/api/alerts/mark-all-read")
        assert response.status_code == 403

    def test_mark_all_read_idempotent(self, test_client, auth_headers):
        """複数回呼んでも 200 が返る"""
        for _ in range(2):
            r = test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
            assert r.status_code == 200

    def test_mark_all_read_updates_module_state(self, test_client, auth_headers):
        """全件既読後、全 ID が _read_alerts に含まれる"""
        test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        all_ids = {r["id"] for r in alerts_module.DEFAULT_RULES}
        assert all_ids.issubset(alerts_module._read_alerts)


# ===================================================================
# 既存エンドポイントのスモークテスト
# ===================================================================

class TestExistingEndpointsSmoke:
    """既存エンドポイントが壊れていないことを確認するスモークテスト"""

    def test_get_rules_returns_200(self, test_client, auth_headers):
        """GET /api/alerts/rules — 200 と rules リスト"""
        r = test_client.get("/api/alerts/rules", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
        assert isinstance(data["rules"], list)
        assert len(data["rules"]) > 0

    def test_get_active_returns_200(self, test_client, auth_headers):
        """GET /api/alerts/active — 200 と active_alerts リスト"""
        r = test_client.get("/api/alerts/active", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "active_alerts" in data
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_get_summary_returns_200(self, test_client, auth_headers):
        """GET /api/alerts/summary — 200 と total_rules"""
        r = test_client.get("/api/alerts/summary", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_rules" in data
        assert data["total_rules"] == len(alerts_module.DEFAULT_RULES)

    def test_rules_unauthenticated(self, test_client):
        """GET /api/alerts/rules — 未認証は 403"""
        r = test_client.get("/api/alerts/rules")
        assert r.status_code == 403

    def test_active_unauthenticated(self, test_client):
        """GET /api/alerts/active — 未認証は 403"""
        r = test_client.get("/api/alerts/active")
        assert r.status_code == 403
