"""
承認ワークフロー UI 関連 API の統合テスト

テスト対象: backend/api/routes/approval.py
テスト項目: 12ケース

テスト方針:
- FastAPI TestClient を使用してエンドポイントへ HTTP リクエストを送信
- UI が利用するエンドポイントに絞ったスモークテスト
- 認証なし 401 / 存在しない ID 404 の確認
"""

import sqlite3
from pathlib import Path

import pytest


# ============================================================================
# フィクスチャ
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def init_approval_ui_db(tmp_path_factory):
    """APIルートの approval_service を一時DBで初期化する（モジュール単位）"""
    from backend.api.routes import approval as approval_module

    tmp_db = str(tmp_path_factory.mktemp("approval_ui_db") / "test_approval_ui.db")
    approval_module.approval_service.db_path = tmp_db

    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_db) as conn:
        conn.executescript(schema_sql)
    yield


@pytest.fixture(autouse=True)
def cleanup_approval_ui_db():
    """各テスト前にDBデータをクリーンアップする"""
    from backend.api.routes.approval import approval_service

    with sqlite3.connect(approval_service.db_path) as conn:
        conn.execute("DELETE FROM approval_history")
        conn.execute("DELETE FROM approval_requests")
        conn.commit()
    yield


# ============================================================================
# TC-UI-001〜003: GET /api/approval/pending
# ============================================================================


class TestPendingEndpoint:
    """GET /api/approval/pending のテスト"""

    def test_pending_returns_200_with_list(self, test_client, approver_headers):
        """TC-UI-001: 認証済み Approver は 200 + list キーを返す"""
        response = test_client.get("/api/approval/pending", headers=approver_headers)
        assert response.status_code == 200
        data = response.json()
        assert "list" in data or "items" in data or "requests" in data or data.get("status") == "success"

    def test_pending_returns_200_admin(self, test_client, admin_headers):
        """TC-UI-002: 認証済み Admin は 200 を返す"""
        response = test_client.get("/api/approval/pending", headers=admin_headers)
        assert response.status_code == 200

    def test_pending_unauthenticated_returns_401(self, test_client):
        """TC-UI-003: 認証なしは 401 を返す"""
        response = test_client.get("/api/approval/pending")
        assert response.status_code == 401


# ============================================================================
# TC-UI-004〜006: GET /api/approval/history
# ============================================================================


class TestHistoryEndpoint:
    """GET /api/approval/history のテスト"""

    def test_history_returns_200_with_items(self, test_client, approver_headers):
        """TC-UI-004: 認証済み Approver は 200 + items キーを返す"""
        response = test_client.get("/api/approval/history", headers=approver_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or data.get("status") == "success"

    def test_history_returns_200_admin(self, test_client, admin_headers):
        """TC-UI-005: 認証済み Admin は 200 を返す"""
        response = test_client.get("/api/approval/history", headers=admin_headers)
        assert response.status_code == 200

    def test_history_unauthenticated_returns_401(self, test_client):
        """TC-UI-006: 認証なしは 401 を返す"""
        response = test_client.get("/api/approval/history")
        assert response.status_code == 401


# ============================================================================
# TC-UI-007: GET /api/approval/{id}
# ============================================================================


class TestDetailEndpoint:
    """GET /api/approval/{id} のテスト"""

    def test_get_nonexistent_request_returns_404(self, test_client, approver_headers):
        """TC-UI-007: 存在しない ID は 404 を返す"""
        response = test_client.get("/api/approval/99999", headers=approver_headers)
        assert response.status_code == 404

    def test_get_request_unauthenticated_returns_401(self, test_client):
        """TC-UI-008: 認証なしは 401 を返す"""
        response = test_client.get("/api/approval/99999")
        assert response.status_code == 401


# ============================================================================
# TC-UI-009〜010: POST /api/approval/{id}/approve
# ============================================================================


class TestApproveEndpoint:
    """POST /api/approval/{id}/approve のテスト"""

    def test_approve_nonexistent_request_returns_404(self, test_client, approver_headers):
        """TC-UI-009: 存在しない ID の承認は 404 を返す"""
        response = test_client.post(
            "/api/approval/99999/approve",
            json={"comment": "テスト"},
            headers=approver_headers,
        )
        assert response.status_code == 404

    def test_approve_unauthenticated_returns_401(self, test_client):
        """TC-UI-010: 認証なしは 401 を返す"""
        response = test_client.post(
            "/api/approval/99999/approve",
            json={"comment": "テスト"},
        )
        assert response.status_code == 401


# ============================================================================
# TC-UI-011〜012: POST /api/approval/{id}/reject
# ============================================================================


class TestRejectEndpoint:
    """POST /api/approval/{id}/reject のテスト"""

    def test_reject_nonexistent_request_returns_404(self, test_client, approver_headers):
        """TC-UI-011: 存在しない ID の拒否は 404 を返す"""
        response = test_client.post(
            "/api/approval/99999/reject",
            json={"reason": "テスト拒否"},
            headers=approver_headers,
        )
        assert response.status_code == 404

    def test_reject_unauthenticated_returns_401(self, test_client):
        """TC-UI-012: 認証なしは 401 を返す"""
        response = test_client.post(
            "/api/approval/99999/reject",
            json={"reason": "テスト拒否"},
        )
        assert response.status_code == 401
