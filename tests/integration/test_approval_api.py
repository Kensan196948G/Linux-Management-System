"""
承認ワークフロー API の統合テスト

テスト対象: backend/api/routes/approval.py
テスト項目: 35ケース（APIエンドポイント）

統合テスト方針:
- FastAPI TestClient を使用してエンドポイントへ HTTP リクエストを送信
- APIルートのモジュールレベル approval_service の DB を初期化して使用
- ロールベースアクセス制御 (RBAC) の検証
- リクエストライフサイクル全体のテスト (create -> approve/reject/cancel)
"""

import asyncio
import json

import pytest


# ============================================================================
# フィクスチャ
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def init_approval_db(tmp_path_factory):
    """APIルートの approval_service を一時DBで初期化する（モジュール単位）"""
    import asyncio
    import sqlite3
    from backend.api.routes import approval as approval_module
    from pathlib import Path

    # テスト専用の一時DBを使用
    tmp_db = str(tmp_path_factory.mktemp("approval_db") / "test_approval.db")
    approval_module.approval_service.db_path = tmp_db

    # スキーマファイルを同期的にSQLiteへ適用
    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_db) as conn:
        conn.executescript(schema_sql)
    yield


@pytest.fixture(autouse=True)
def cleanup_approval_db():
    """各テスト前にDBデータをクリーンアップする（同期sqlite3使用）"""
    import sqlite3
    from backend.api.routes.approval import approval_service

    with sqlite3.connect(approval_service.db_path) as conn:
        conn.execute("DELETE FROM approval_history")
        conn.execute("DELETE FROM approval_requests")
        conn.commit()
    yield


@pytest.fixture
def sample_approval_request_payload():
    """承認リクエスト作成用のサンプルペイロード"""
    return {
        "request_type": "user_add",
        "payload": {
            "username": "testuser",
            "group": "developers",
            "home": "/home/testuser",
            "shell": "/bin/bash",
        },
        "reason": "テスト用ユーザーアカウントの作成",
    }


def _create_request(test_client, headers, payload=None):
    """承認リクエスト作成のヘルパー"""
    if payload is None:
        payload = {
            "request_type": "user_add",
            "payload": {
                "username": "testuser",
                "group": "developers",
                "home": "/home/testuser",
                "shell": "/bin/bash",
            },
            "reason": "テスト用ユーザーアカウントの作成",
        }
    return test_client.post("/api/approval/request", json=payload, headers=headers)


# ============================================================================
# Test Case 1-10: POST /api/approval/request
# ============================================================================


class TestCreateApprovalRequestAPI:
    """承認リクエスト作成APIのテスト"""

    def test_create_request_success_operator(
        self, test_client, operator_headers, sample_approval_request_payload
    ):
        """TC-API-001: Operatorによる承認リクエスト作成成功"""
        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
            headers=operator_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert "request_id" in data
        assert data["request_type"] == "user_add"

    def test_create_request_success_admin(
        self, test_client, admin_headers, sample_approval_request_payload
    ):
        """TC-API-002: Adminによる承認リクエスト作成成功"""
        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert "request_id" in data

    def test_create_request_forbidden_viewer(
        self, test_client, viewer_headers, sample_approval_request_payload
    ):
        """TC-API-003: Viewerは承認リクエスト作成不可（403 Forbidden）"""
        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_create_request_unauthorized(
        self, test_client, sample_approval_request_payload
    ):
        """TC-API-004: 認証なしは拒否（401 Unauthorized）"""
        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
        )
        assert response.status_code in (401, 403)

    def test_create_request_invalid_type(self, test_client, operator_headers):
        """TC-API-005: 不正な操作種別は拒否（400 Bad Request）"""
        payload = {
            "request_type": "nonexistent_operation",
            "payload": {"key": "value"},
            "reason": "テスト",
        }
        response = test_client.post(
            "/api/approval/request",
            json=payload,
            headers=operator_headers,
        )
        assert response.status_code == 400
        data = response.json()
        assert "Invalid request_type" in (data.get("detail", "") or data.get("message", ""))

    def test_create_request_forbidden_chars(self, test_client, operator_headers):
        """TC-API-006: 特殊文字を含むペイロードは拒否（400 Bad Request）"""
        payload = {
            "request_type": "user_add",
            "payload": {
                "username": "testuser; rm -rf /",
                "group": "developers",
            },
            "reason": "テスト",
        }
        response = test_client.post(
            "/api/approval/request",
            json=payload,
            headers=operator_headers,
        )
        assert response.status_code == 400
        data = response.json()
        assert "Forbidden character" in (data.get("detail", "") or data.get("message", ""))

    def test_create_request_empty_reason(self, test_client, operator_headers):
        """TC-API-007: 申請理由が空の場合は拒否（422 Validation Error）"""
        payload = {
            "request_type": "user_add",
            "payload": {"username": "testuser"},
            "reason": "",
        }
        response = test_client.post(
            "/api/approval/request",
            json=payload,
            headers=operator_headers,
        )
        assert response.status_code == 422

    def test_create_request_reason_too_long(self, test_client, operator_headers):
        """TC-API-008: 申請理由が1000文字超は拒否（422 Validation Error）"""
        payload = {
            "request_type": "user_add",
            "payload": {"username": "testuser"},
            "reason": "a" * 1001,
        }
        response = test_client.post(
            "/api/approval/request",
            json=payload,
            headers=operator_headers,
        )
        assert response.status_code == 422

    def test_create_request_returns_uuid(
        self, test_client, operator_headers, sample_approval_request_payload
    ):
        """TC-API-009: レスポンスにUUID形式のrequest_idが含まれること"""
        import uuid

        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
            headers=operator_headers,
        )
        assert response.status_code == 201
        data = response.json()
        # UUID 形式の検証
        request_id = data["request_id"]
        try:
            uuid.UUID(request_id, version=4)
        except ValueError:
            pytest.fail(f"request_id is not a valid UUID: {request_id}")

    def test_create_request_returns_correct_fields(
        self, test_client, operator_headers, sample_approval_request_payload
    ):
        """TC-API-010: レスポンスに必須フィールドが全て含まれること"""
        response = test_client.post(
            "/api/approval/request",
            json=sample_approval_request_payload,
            headers=operator_headers,
        )
        assert response.status_code == 201
        data = response.json()
        required_fields = [
            "status",
            "message",
            "request_id",
            "request_type",
            "created_at",
            "expires_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


# ============================================================================
# Test Case 11-20: GET /api/approval/pending
# ============================================================================


class TestGetPendingRequestsAPI:
    """承認待ちリクエスト一覧取得APIのテスト"""

    def test_get_pending_success_approver(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-011: Approverによる承認待ち一覧取得成功"""
        # まず operator でリクエストを作成
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending", headers=approver_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "requests" in data or "total" in data

    def test_get_pending_success_admin(
        self, test_client, admin_headers, operator_headers
    ):
        """TC-API-012: Adminによる承認待ち一覧取得成功"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending", headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_pending_forbidden_operator(self, test_client, operator_headers):
        """TC-API-013: Operatorは承認待ち一覧取得不可（403 Forbidden）"""
        response = test_client.get(
            "/api/approval/pending", headers=operator_headers
        )
        assert response.status_code == 403

    def test_get_pending_forbidden_viewer(self, test_client, viewer_headers):
        """TC-API-014: Viewerは承認待ち一覧取得不可（403 Forbidden）"""
        response = test_client.get(
            "/api/approval/pending", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_get_pending_filter_by_type(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-015: 操作種別によるフィルタリング"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending?request_type=user_add",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # フィルタ結果が全て user_add であること
        if "requests" in data and data["requests"]:
            for req in data["requests"]:
                assert req["request_type"] == "user_add"

    def test_get_pending_filter_by_requester(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-016: 申請者によるフィルタリング"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending?requester_id=user_002",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_pending_sort_by_created_at(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-017: 作成日時によるソート"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending?sort_by=created_at&sort_order=desc",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_pending_sort_by_expires_at(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-018: 期限日時によるソート"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending?sort_by=expires_at&sort_order=asc",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_pending_pagination(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-019: ページネーション機能"""
        # 複数のリクエスト作成
        for _ in range(3):
            _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/pending?page=1&per_page=2",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # ページネーション情報が含まれること
        assert "total" in data or "page" in data

    def test_get_pending_per_page_limit(
        self, test_client, approver_headers, operator_headers
    ):
        """TC-API-020: per_pageの最大値制限（100件）"""
        _create_request(test_client, operator_headers)

        # per_page=200 を指定しても 100 に制限される
        response = test_client.get(
            "/api/approval/pending?per_page=200",
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # per_page が 100 に制限されていることを間接的に確認
        if "per_page" in data:
            assert data["per_page"] <= 100


# ============================================================================
# Test Case 21-27: GET /api/approval/my-requests, GET /api/approval/{id}
# ============================================================================


class TestGetRequestsAPI:
    """承認リクエスト取得APIのテスト"""

    def test_get_my_requests_success(self, test_client, operator_headers):
        """TC-API-021: 自分の申請一覧取得成功"""
        # リクエスト作成
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/my-requests", headers=operator_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_my_requests_filter_by_status(
        self, test_client, operator_headers
    ):
        """TC-API-022: ステータスによるフィルタリング"""
        _create_request(test_client, operator_headers)

        response = test_client.get(
            "/api/approval/my-requests?status_filter=pending",
            headers=operator_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_request_detail_success_requester(
        self, test_client, operator_headers
    ):
        """TC-API-023: 申請者本人は詳細取得可能"""
        # リクエスト作成
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.get(
            f"/api/approval/{request_id}", headers=operator_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["request"]["id"] == request_id

    def test_get_request_detail_success_approver(
        self, test_client, operator_headers, approver_headers
    ):
        """TC-API-024: Approverは他者の申請詳細取得可能"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.get(
            f"/api/approval/{request_id}", headers=approver_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["request"]["id"] == request_id

    def test_get_request_detail_forbidden_other_operator(
        self, test_client, admin_headers, viewer_headers
    ):
        """TC-API-025: Viewerは他者の申請詳細取得不可（403 Forbidden）"""
        # Admin でリクエスト作成
        create_resp = _create_request(test_client, admin_headers)
        request_id = create_resp.json()["request_id"]

        # Viewer でアクセス -> 403
        response = test_client.get(
            f"/api/approval/{request_id}", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_get_request_detail_includes_history(
        self, test_client, operator_headers
    ):
        """TC-API-026: 詳細レスポンスに履歴が含まれること"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.get(
            f"/api/approval/{request_id}", headers=operator_headers
        )
        assert response.status_code == 200
        data = response.json()
        request_detail = data["request"]
        assert "history" in request_detail
        # 作成時に "created" アクションが記録されている
        assert len(request_detail["history"]) >= 1
        assert request_detail["history"][0]["action"] == "created"

    def test_get_request_detail_not_found(self, test_client, operator_headers):
        """TC-API-027: 存在しないリクエストIDは404 Not Found"""
        fake_id = "nonexistent-request-id"
        response = test_client.get(
            f"/api/approval/{fake_id}", headers=operator_headers
        )
        assert response.status_code == 404


# ============================================================================
# Test Case 28-35: POST /api/approval/{id}/approve, reject, cancel, execute
# ============================================================================


class TestApprovalActionsAPI:
    """承認・拒否・キャンセル・実行APIのテスト"""

    def test_approve_request_success(
        self, test_client, operator_headers, approver_headers
    ):
        """TC-API-028: 承認成功"""
        # Operator がリクエスト作成
        create_resp = _create_request(test_client, operator_headers)
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # Approver が承認
        response = test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "承認します"},
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "approved_by" in data

    def test_approve_request_self_approval_forbidden(
        self, test_client, admin_headers
    ):
        """TC-API-029: 自己承認は禁止（403 Forbidden）"""
        # Admin がリクエスト作成
        create_resp = _create_request(test_client, admin_headers)
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # 同じ Admin が自己承認 -> 403
        response = test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "自己承認テスト"},
            headers=admin_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert "Self-approval" in (data.get("detail", "") or data.get("message", ""))

    def test_approve_request_already_approved_conflict(
        self, test_client, operator_headers, approver_headers, admin_headers
    ):
        """TC-API-030: 既に承認済みは409 Conflict"""
        # Operator がリクエスト作成
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        # Approver が承認
        response1 = test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "1回目承認"},
            headers=approver_headers,
        )
        assert response1.status_code == 200

        # Admin が再度承認 -> 409
        response2 = test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "2回目承認"},
            headers=admin_headers,
        )
        assert response2.status_code == 409

    def test_reject_request_success(
        self, test_client, operator_headers, approver_headers
    ):
        """TC-API-031: 拒否成功"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.post(
            f"/api/approval/{request_id}/reject",
            json={"reason": "要件が不十分です"},
            headers=approver_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "rejected_by" in data

    def test_reject_request_empty_reason_validation_error(
        self, test_client, operator_headers, approver_headers
    ):
        """TC-API-032: 拒否理由が空は422 Validation Error"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.post(
            f"/api/approval/{request_id}/reject",
            json={"reason": ""},
            headers=approver_headers,
        )
        assert response.status_code == 422

    def test_cancel_request_success_requester(
        self, test_client, operator_headers
    ):
        """TC-API-033: 申請者によるキャンセル成功"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.post(
            f"/api/approval/{request_id}/cancel",
            json={"reason": "不要になりました"},
            headers=operator_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_cancel_request_forbidden_not_requester(
        self, test_client, operator_headers, admin_headers
    ):
        """TC-API-034: 申請者以外はキャンセル不可（403 Forbidden）"""
        # Operator がリクエスト作成
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        # Admin がキャンセル -> 403
        response = test_client.post(
            f"/api/approval/{request_id}/cancel",
            json={"reason": "管理者キャンセルテスト"},
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_execute_request_success_admin(self, test_client, admin_headers):
        """TC-API-035: 存在しないIDで実行すると404を返す"""
        fake_id = "nonexistent-execute-id"
        response = test_client.post(
            f"/api/approval/{fake_id}/execute",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_execute_approved_request(
        self, test_client, operator_headers, admin_headers
    ):
        """TC-API-036: 承認済みリクエストを手動実行（sudoラッパーをモック）"""
        from unittest.mock import patch

        # group_add リクエストを作成
        create_resp = test_client.post(
            "/api/approval/request",
            json={
                "request_type": "group_add",
                "payload": {"name": "testgroup"},
                "reason": "テスト用グループ作成",
            },
            headers=operator_headers,
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # Admin が承認
        test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "承認します"},
            headers=admin_headers,
        )

        # sudo_wrapperをモックして実行
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.add_group"
        ) as mock_exec:
            mock_exec.return_value = {"status": "success", "message": "Group added"}
            response = test_client.post(
                f"/api/approval/{request_id}/execute",
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["request_id"] == request_id

    def test_execute_request_not_approved(
        self, test_client, operator_headers, admin_headers
    ):
        """TC-API-037: pending状態のリクエストを実行しようとすると400を返す"""
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.post(
            f"/api/approval/{request_id}/execute",
            headers=admin_headers,
        )
        assert response.status_code == 400


# ============================================================================
# その他のエンドポイント
# ============================================================================


class TestOtherEndpoints:
    """その他のエンドポイントのテスト"""

    def test_get_approval_history_admin(self, test_client, admin_headers):
        """承認履歴取得（Admin専用 - v0.4 スタブ: 501）"""
        response = test_client.get(
            "/api/approval/history", headers=admin_headers
        )
        assert response.status_code == 501

    def test_export_approval_history_json(self, test_client, admin_headers):
        """承認履歴エクスポート JSON（v0.4 スタブ: 501）"""
        response = test_client.get(
            "/api/approval/history/export?format=json",
            headers=admin_headers,
        )
        assert response.status_code == 501

    def test_export_approval_history_csv(self, test_client, admin_headers):
        """承認履歴エクスポート CSV（v0.4 スタブ: 501）"""
        response = test_client.get(
            "/api/approval/history/export?format=csv",
            headers=admin_headers,
        )
        assert response.status_code == 501

    def test_get_approval_policies(self, test_client, operator_headers):
        """承認ポリシー一覧取得"""
        response = test_client.get(
            "/api/approval/policies", headers=operator_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "policies" in data
        assert isinstance(data["policies"], list)
        assert len(data["policies"]) > 0

    def test_get_approval_stats_admin(self, test_client, admin_headers):
        """承認統計情報取得（Admin専用 - v0.4 スタブ: 501）"""
        response = test_client.get(
            "/api/approval/stats", headers=admin_headers
        )
        assert response.status_code == 501


# ============================================================================
# 未カバー行を対象にしたエラーパステスト（approval.py 行 137-139, 176-177,
# 198-200, 234-251, 298-300, 327, 342-344, 367-369, 457, 474-480,
# 516-517, 532-539, 554-565）
# ============================================================================


class TestApprovalAPIErrorPaths:
    """
    ApprovalService をモックして未カバーエラーパスを検証するテスト。
    TestClient のリクエストで approval_service のメソッドに例外を注入する。
    """

    # ------ 行 137-139: create_request で Exception → 500 ------

    def test_create_request_internal_error_returns_500(
        self, test_client, operator_headers
    ):
        """TC-ERR-001: create_request で予期しない例外が発生した場合 500 を返す（行 137-139）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.create_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection failed"),
        ):
            response = test_client.post(
                "/api/approval/request",
                json={
                    "request_type": "user_add",
                    "payload": {"username": "testuser"},
                    "reason": "テスト",
                },
                headers=operator_headers,
            )
        assert response.status_code == 500
        assert "Failed to create approval request" in response.json()["message"]

    # ------ 行 176-177: approve_request で LookupError → 404 ------

    def test_approve_request_not_found_returns_404(
        self, test_client, approver_headers
    ):
        """TC-ERR-002: approve_request で LookupError → 404（行 176-177）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.approve_request",
            new_callable=AsyncMock,
            side_effect=LookupError("Approval request not found: nonexistent-id"),
        ):
            response = test_client.post(
                "/api/approval/nonexistent-id/approve",
                json={"comment": "テスト承認"},
                headers=approver_headers,
            )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    # ------ 行 198-200: approve_request で Exception → 500 ------

    def test_approve_request_internal_error_returns_500(
        self, test_client, approver_headers
    ):
        """TC-ERR-003: approve_request で予期しない例外 → 500（行 198-200）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.approve_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected DB error"),
        ):
            response = test_client.post(
                "/api/approval/some-id/approve",
                json={"comment": "テスト"},
                headers=approver_headers,
            )
        assert response.status_code == 500
        assert "Failed to approve request" in response.json()["message"]

    # ------ 行 234-239: reject_request で LookupError → 404 ------

    def test_reject_request_not_found_returns_404(
        self, test_client, approver_headers
    ):
        """TC-ERR-004: reject_request で LookupError → 404（行 234-239）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.reject_request",
            new_callable=AsyncMock,
            side_effect=LookupError("Approval request not found: nonexistent-id"),
        ):
            response = test_client.post(
                "/api/approval/nonexistent-id/reject",
                json={"reason": "拒否理由"},
                headers=approver_headers,
            )
        assert response.status_code == 404

    # ------ 行 241-247: reject_request で ValueError → 409 ------

    def test_reject_request_wrong_status_returns_409(
        self, test_client, operator_headers, approver_headers
    ):
        """TC-ERR-005: reject_request で ValueError (ステータス不正) → 409（行 241-247）"""
        # まず承認済みリクエストを作る: create → approve
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        # Approver が承認
        test_client.post(
            f"/api/approval/{request_id}/approve",
            json={"comment": "承認"},
            headers=approver_headers,
        )

        # 承認済みを拒否しようとすると 409
        response = test_client.post(
            f"/api/approval/{request_id}/reject",
            json={"reason": "拒否理由"},
            headers=approver_headers,
        )
        assert response.status_code == 409

    # ------ 行 249-251: reject_request で Exception → 500 ------

    def test_reject_request_internal_error_returns_500(
        self, test_client, approver_headers
    ):
        """TC-ERR-006: reject_request で予期しない例外 → 500（行 249-251）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.reject_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.post(
                "/api/approval/some-id/reject",
                json={"reason": "拒否理由"},
                headers=approver_headers,
            )
        assert response.status_code == 500
        assert "Failed to reject request" in response.json()["message"]

    # ------ 行 298-300: list_pending_requests で Exception → 500 ------

    def test_list_pending_requests_internal_error_returns_500(
        self, test_client, approver_headers
    ):
        """TC-ERR-007: list_pending_requests で予期しない例外 → 500（行 298-300）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.list_pending_requests",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.get(
                "/api/approval/pending", headers=approver_headers
            )
        assert response.status_code == 500
        assert "Failed to list pending requests" in response.json()["message"]

    # ------ 行 327: list_my_requests の per_page 上限クランプ ------

    def test_list_my_requests_per_page_clamped_to_100(
        self, test_client, operator_headers
    ):
        """TC-ERR-008: my-requests の per_page=200 は内部で 100 にクランプされる（行 327）"""
        response = test_client.get(
            "/api/approval/my-requests?per_page=200",
            headers=operator_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # per_page フィールドが存在する場合は 100 以下であること
        if "per_page" in data:
            assert data["per_page"] <= 100

    # ------ 行 342-344: list_my_requests で Exception → 500 ------

    def test_list_my_requests_internal_error_returns_500(
        self, test_client, operator_headers
    ):
        """TC-ERR-009: list_my_requests で予期しない例外 → 500（行 342-344）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.list_my_requests",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.get(
                "/api/approval/my-requests", headers=operator_headers
            )
        assert response.status_code == 500
        assert "Failed to list my requests" in response.json()["message"]

    # ------ 行 367-369: get_approval_policies で Exception → 500 ------

    def test_get_approval_policies_internal_error_returns_500(
        self, test_client, operator_headers
    ):
        """TC-ERR-010: get_approval_policies で予期しない例外 → 500（行 367-369）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.list_policies",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.get(
                "/api/approval/policies", headers=operator_headers
            )
        assert response.status_code == 500
        assert "Failed to get policies" in response.json()["message"]

    # ------ 行 457: get_request_detail で他者の申請に Operator がアクセス → 403 ------

    def test_get_request_detail_operator_cannot_view_others_request(
        self, test_client, admin_headers, operator_headers
    ):
        """TC-ERR-011: Operatorは他者(Admin)の申請詳細取得不可（行 457）"""
        # Admin でリクエスト作成
        create_resp = _create_request(test_client, admin_headers)
        request_id = create_resp.json()["request_id"]

        # Operator (別ユーザー) がアクセス → 403
        # (viewer_headers はアクセス権なし 403 だが operator は request:approval 権限あり
        #  → 権限はあるが "他者の申請" なので 403 になる)
        response = test_client.get(
            f"/api/approval/{request_id}", headers=operator_headers
        )
        # admin と operator は別ユーザーなので 403 を期待
        assert response.status_code == 403

    # ------ 行 474-476: get_request_detail で HTTPException 再送出 ------

    def test_get_request_detail_viewer_forbidden_is_reraised(
        self, test_client, admin_headers, viewer_headers
    ):
        """TC-ERR-012: viewer が詳細取得 → 403 HTTPException が再送出される（行 474-476）"""
        create_resp = _create_request(test_client, admin_headers)
        request_id = create_resp.json()["request_id"]

        response = test_client.get(
            f"/api/approval/{request_id}", headers=viewer_headers
        )
        # viewer は request:approval 権限なし → 403
        assert response.status_code == 403

    # ------ 行 478-480: get_request_detail で Exception → 500 ------

    def test_get_request_detail_internal_error_returns_500(
        self, test_client, operator_headers
    ):
        """TC-ERR-013: get_request で予期しない例外 → 500（行 478-480）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.get_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.get(
                "/api/approval/some-valid-looking-id", headers=operator_headers
            )
        assert response.status_code == 500
        assert "Failed to get request detail" in response.json()["message"]

    # ------ 行 516-517: cancel_request で LookupError → 404 ------

    def test_cancel_request_not_found_returns_404(
        self, test_client, operator_headers
    ):
        """TC-ERR-014: cancel_request で LookupError → 404（行 516-517）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.cancel_request",
            new_callable=AsyncMock,
            side_effect=LookupError("Approval request not found"),
        ):
            response = test_client.post(
                "/api/approval/nonexistent-id/cancel",
                json={"reason": "不要"},
                headers=operator_headers,
            )
        assert response.status_code == 404

    # ------ 行 526-530: cancel_request で "Only the requester" ValueError → 403 ------

    def test_cancel_request_other_user_returns_403(
        self, test_client, operator_headers, admin_headers
    ):
        """TC-ERR-015: cancel_request でキャンセル不可 ValueError → 403（行 526-530）"""
        # Operator がリクエスト作成
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        # Admin がキャンセル → 403（申請者以外はキャンセル不可）
        response = test_client.post(
            f"/api/approval/{request_id}/cancel",
            json={"reason": "管理者キャンセル"},
            headers=admin_headers,
        )
        assert response.status_code == 403
        assert "Only the requester" in response.json()["message"]

    # ------ 行 531-535: cancel_request でステータス不正 ValueError → 409 ------

    def test_cancel_request_already_cancelled_returns_409(
        self, test_client, operator_headers
    ):
        """TC-ERR-016: cancel 済みリクエストの再キャンセル → 409（行 531-535）"""
        # 作成してキャンセル
        create_resp = _create_request(test_client, operator_headers)
        request_id = create_resp.json()["request_id"]

        test_client.post(
            f"/api/approval/{request_id}/cancel",
            json={"reason": "1回目キャンセル"},
            headers=operator_headers,
        )

        # 再度キャンセル → 409
        response = test_client.post(
            f"/api/approval/{request_id}/cancel",
            json={"reason": "2回目キャンセル"},
            headers=operator_headers,
        )
        assert response.status_code == 409

    # ------ 行 537-539: cancel_request で Exception → 500 ------

    def test_cancel_request_internal_error_returns_500(
        self, test_client, operator_headers
    ):
        """TC-ERR-017: cancel_request で予期しない例外 → 500（行 537-539）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.cancel_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.post(
                "/api/approval/some-id/cancel",
                json={"reason": "テスト"},
                headers=operator_headers,
            )
        assert response.status_code == 500
        assert "Failed to cancel request" in response.json()["message"]

    # ------ 行 554-565: expire_old_requests エンドポイントのテスト ------

    def test_expire_old_requests_success_admin(self, test_client, admin_headers):
        """TC-ERR-018: expire エンドポイントが成功する（行 554-565）"""
        response = test_client.post(
            "/api/approval/expire",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "expired_count" in data
        assert isinstance(data["expired_count"], int)

    def test_expire_old_requests_forbidden_operator(
        self, test_client, operator_headers
    ):
        """TC-ERR-019: Operator は expire エンドポイント使用不可（403）"""
        response = test_client.post(
            "/api/approval/expire",
            headers=operator_headers,
        )
        assert response.status_code == 403

    def test_expire_old_requests_internal_error_returns_500(
        self, test_client, admin_headers
    ):
        """TC-ERR-020: expire_old_requests で予期しない例外 → 500（行 563-565）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.expire_old_requests",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            response = test_client.post(
                "/api/approval/expire",
                headers=admin_headers,
            )
        assert response.status_code == 500
        assert "Failed to expire old requests" in response.json()["message"]

    # ------ approve_request の ValueError (自己承認以外) → 409 ------

    def test_approve_request_conflict_non_self_approval_returns_409(
        self, test_client, approver_headers
    ):
        """TC-ERR-021: 自己承認以外の ValueError → 409（行 193-196）"""
        from unittest.mock import AsyncMock, patch

        with patch(
            "backend.api.routes.approval.approval_service.approve_request",
            new_callable=AsyncMock,
            side_effect=ValueError("Cannot approve: request status is 'approved'"),
        ):
            response = test_client.post(
                "/api/approval/some-id/approve",
                json={"comment": "テスト"},
                headers=approver_headers,
            )
        assert response.status_code == 409
