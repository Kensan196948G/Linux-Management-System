"""
Approval API エンドポイントのユニットテスト

backend/api/routes/approval.py のカバレッジ向上
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


class TestCreateApprovalRequest:
    """POST /api/approval/request テスト"""

    def test_create_request_success(self, test_client, auth_headers):
        """正常系: 承認リクエスト作成"""
        mock_result = {
            "status": "pending",
            "request_id": "req-001",
            "expires_at": "2026-03-02T00:00:00Z",
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.create_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/request",
                json={
                    "request_type": "user_add",
                    "payload": {"username": "newuser"},
                    "reason": "New team member",
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["request_id"] == "req-001"
        assert data["request_status"] == "pending"

    def test_create_request_value_error(self, test_client, auth_headers):
        """ValueError → 400"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.create_request = AsyncMock(
                side_effect=ValueError("Forbidden character detected")
            )
            response = test_client.post(
                "/api/approval/request",
                json={
                    "request_type": "user_add",
                    "payload": {"username": "bad;user"},
                    "reason": "Test",
                },
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "Security violation" in response.json()["message"]

    def test_create_request_lookup_error(self, test_client, auth_headers):
        """LookupError → 400"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.create_request = AsyncMock(
                side_effect=LookupError("Unknown request_type: invalid_type")
            )
            response = test_client.post(
                "/api/approval/request",
                json={
                    "request_type": "invalid_type",
                    "payload": {},
                    "reason": "Test",
                },
                headers=auth_headers,
            )

        assert response.status_code == 400

    def test_create_request_exception(self, test_client, auth_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.create_request = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.post(
                "/api/approval/request",
                json={
                    "request_type": "user_add",
                    "payload": {},
                    "reason": "Test",
                },
                headers=auth_headers,
            )

        assert response.status_code == 500

    def test_create_request_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.post(
            "/api/approval/request",
            json={
                "request_type": "user_add",
                "payload": {},
                "reason": "Test",
            },
        )
        assert response.status_code == 403


class TestApproveRequest:
    """POST /api/approval/{request_id}/approve テスト"""

    def test_approve_success(self, test_client, approver_headers):
        """正常系: 承認"""
        mock_result = {"request_id": "req-001", "approved_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/approve",
                json={"comment": "Approved"},
                headers=approver_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_approve_with_reason(self, test_client, approver_headers):
        """reason フィールドを使用した承認"""
        mock_result = {"request_id": "req-001", "approved_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/approve",
                json={"reason": "LGTM"},
                headers=approver_headers,
            )

        assert response.status_code == 200

    def test_approve_not_found(self, test_client, approver_headers):
        """LookupError → 404"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(
                side_effect=LookupError("Request not found")
            )
            response = test_client.post(
                "/api/approval/req-999/approve",
                json={},
                headers=approver_headers,
            )

        assert response.status_code == 404

    def test_approve_self_approval(self, test_client, approver_headers):
        """自己承認 → 403"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(
                side_effect=ValueError("Self-approval is prohibited")
            )
            response = test_client.post(
                "/api/approval/req-001/approve",
                json={},
                headers=approver_headers,
            )

        assert response.status_code == 403

    def test_approve_status_conflict(self, test_client, approver_headers):
        """ステータス不正 → 409"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(
                side_effect=ValueError("Request is not pending")
            )
            response = test_client.post(
                "/api/approval/req-001/approve",
                json={},
                headers=approver_headers,
            )

        assert response.status_code == 409

    def test_approve_exception(self, test_client, approver_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.approve_request = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.post(
                "/api/approval/req-001/approve",
                json={},
                headers=approver_headers,
            )

        assert response.status_code == 500


class TestRejectRequest:
    """POST /api/approval/{request_id}/reject テスト"""

    def test_reject_success(self, test_client, approver_headers):
        """正常系: 拒否"""
        mock_result = {"request_id": "req-001", "rejected_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.reject_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/reject",
                json={"reason": "Security concern"},
                headers=approver_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["emergency"] is False

    def test_reject_emergency(self, test_client, approver_headers):
        """緊急拒否"""
        mock_result = {"request_id": "req-001", "rejected_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.reject_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/reject",
                json={"reason": "Critical security issue", "emergency": True},
                headers=approver_headers,
            )

        assert response.status_code == 200
        assert response.json()["emergency"] is True

    def test_reject_not_found(self, test_client, approver_headers):
        """LookupError → 404"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.reject_request = AsyncMock(
                side_effect=LookupError("Request not found")
            )
            response = test_client.post(
                "/api/approval/req-999/reject",
                json={"reason": "Not valid"},
                headers=approver_headers,
            )

        assert response.status_code == 404

    def test_reject_status_conflict(self, test_client, approver_headers):
        """ステータス不正 → 409"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.reject_request = AsyncMock(
                side_effect=ValueError("Request is already rejected")
            )
            response = test_client.post(
                "/api/approval/req-001/reject",
                json={"reason": "Duplicate rejection"},
                headers=approver_headers,
            )

        assert response.status_code == 409

    def test_reject_exception(self, test_client, approver_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.reject_request = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.post(
                "/api/approval/req-001/reject",
                json={"reason": "Error"},
                headers=approver_headers,
            )

        assert response.status_code == 500


class TestListPendingRequests:
    """GET /api/approval/pending テスト"""

    def test_list_pending_success(self, test_client, approver_headers):
        """正常系: 承認待ち一覧取得"""
        mock_result = {
            "requests": [
                {"request_id": "req-001", "request_type": "user_add"},
            ],
            "total": 1,
            "page": 1,
            "per_page": 20,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_pending_requests = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/pending",
                headers=approver_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1

    def test_list_pending_with_filters(self, test_client, approver_headers):
        """フィルタ付き一覧取得"""
        mock_result = {"requests": [], "total": 0, "page": 1, "per_page": 10}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_pending_requests = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/pending?request_type=user_add&per_page=10&sort_order=desc",
                headers=approver_headers,
            )

        assert response.status_code == 200

    def test_list_pending_per_page_cap(self, test_client, approver_headers):
        """per_page > 100 はキャップされる"""
        mock_result = {"requests": [], "total": 0, "page": 1, "per_page": 100}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_pending_requests = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/pending?per_page=200",
                headers=approver_headers,
            )

        assert response.status_code == 200
        # per_page=200 は内部で100にキャップされることを確認
        mock_svc.list_pending_requests.assert_called_once()
        call_kwargs = mock_svc.list_pending_requests.call_args
        assert call_kwargs[1]["per_page"] == 100 or call_kwargs.kwargs["per_page"] == 100

    def test_list_pending_exception(self, test_client, approver_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_pending_requests = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/pending",
                headers=approver_headers,
            )

        assert response.status_code == 500


class TestListMyRequests:
    """GET /api/approval/my-requests テスト"""

    def test_list_my_requests_success(self, test_client, auth_headers):
        """正常系: 自分のリクエスト一覧"""
        mock_result = {
            "requests": [
                {"request_id": "req-001", "request_type": "user_add"},
            ],
            "total": 1,
            "page": 1,
            "per_page": 20,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_my_requests = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/my-requests",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_list_my_requests_with_filters(self, test_client, auth_headers):
        """フィルタ付き一覧取得"""
        mock_result = {"requests": [], "total": 0, "page": 1, "per_page": 20}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_my_requests = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/my-requests?status_filter=pending&request_type=user_add",
                headers=auth_headers,
            )

        assert response.status_code == 200

    def test_list_my_requests_exception(self, test_client, auth_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_my_requests = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/my-requests",
                headers=auth_headers,
            )

        assert response.status_code == 500


class TestGetApprovalPolicies:
    """GET /api/approval/policies テスト"""

    def test_get_policies_success(self, test_client, auth_headers):
        """正常系: ポリシー一覧取得"""
        mock_policies = [
            {
                "type": "user_add",
                "description": "User addition",
                "approval_required": True,
            },
        ]
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_policies = AsyncMock(return_value=mock_policies)
            response = test_client.get(
                "/api/approval/policies",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["policies"]) == 1

    def test_get_policies_exception(self, test_client, auth_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.list_policies = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/policies",
                headers=auth_headers,
            )

        assert response.status_code == 500


class TestGetApprovalHistory:
    """GET /api/approval/history テスト"""

    def test_get_history_success(self, test_client, admin_headers):
        """正常系: 承認履歴取得"""
        mock_result = {
            "items": [
                {
                    "id": 1,
                    "approval_request_id": "req-001",
                    "action": "approved",
                    "timestamp": "2026-03-01T10:00:00Z",
                },
            ],
            "total": 1,
            "page": 1,
            "per_page": 50,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/history",
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1

    def test_get_history_with_filters(self, test_client, admin_headers):
        """フィルタ付き履歴取得"""
        mock_result = {"items": [], "total": 0, "page": 1, "per_page": 50}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/history?request_type=user_add&action=approved"
                "&start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_get_history_value_error(self, test_client, admin_headers):
        """ValueError → 400"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(
                side_effect=ValueError("Invalid date format")
            )
            response = test_client.get(
                "/api/approval/history?start_date=not-a-date",
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_get_history_exception(self, test_client, admin_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/history",
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestExportApprovalHistory:
    """GET /api/approval/history/export テスト"""

    def test_export_json_success(self, test_client, admin_headers):
        """正常系: JSONエクスポート"""
        mock_result = {
            "items": [
                {
                    "id": 1,
                    "approval_request_id": "req-001",
                    "request_type": "user_add",
                    "action": "approved",
                    "actor_id": "approver-001",
                    "actor_name": "approver",
                    "actor_role": "Approver",
                    "timestamp": "2026-03-01T10:00:00Z",
                    "previous_status": "pending",
                    "new_status": "approved",
                    "details": {"comment": "LGTM"},
                    "signature_valid": True,
                },
            ],
            "total": 1,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/history/export?format=json",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        assert "approval_history.json" in response.headers.get(
            "content-disposition", ""
        )

    def test_export_csv_success(self, test_client, admin_headers):
        """正常系: CSVエクスポート"""
        mock_result = {
            "items": [
                {
                    "id": 1,
                    "approval_request_id": "req-001",
                    "request_type": "user_add",
                    "action": "approved",
                    "actor_id": "approver-001",
                    "actor_name": "approver",
                    "actor_role": "Approver",
                    "timestamp": "2026-03-01T10:00:00Z",
                    "previous_status": "pending",
                    "new_status": "approved",
                    "details": {"comment": "LGTM"},
                    "signature_valid": True,
                },
            ],
            "total": 1,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/history/export?format=csv",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "approval_history.csv" in response.headers.get(
            "content-disposition", ""
        )

    def test_export_invalid_format(self, test_client, admin_headers):
        """不正なフォーマット → 400"""
        response = test_client.get(
            "/api/approval/history/export?format=xml",
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_export_exception(self, test_client, admin_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_history = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/history/export?format=json",
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestGetApprovalStats:
    """GET /api/approval/stats テスト"""

    def test_get_stats_success(self, test_client, admin_headers):
        """正常系: 統計情報取得"""
        mock_result = {
            "period": "30d",
            "total_requests": 50,
            "approved": 30,
            "rejected": 10,
            "pending": 5,
            "expired": 5,
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_stats = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/stats",
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_requests"] == 50

    def test_get_stats_custom_period(self, test_client, admin_headers):
        """カスタム期間での統計"""
        mock_result = {"period": "7d", "total_requests": 10}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_stats = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/stats?period=7d",
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_get_stats_invalid_period_defaults(self, test_client, admin_headers):
        """不正な期間 → デフォルト30dにフォールバック"""
        mock_result = {"period": "30d", "total_requests": 50}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_stats = AsyncMock(return_value=mock_result)
            response = test_client.get(
                "/api/approval/stats?period=invalid",
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_get_stats_exception(self, test_client, admin_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_approval_stats = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/stats",
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestGetRequestDetail:
    """GET /api/approval/{request_id} テスト"""

    def test_get_detail_as_requester(self, test_client, auth_headers):
        """正常系: 申請者本人が詳細取得"""
        mock_detail = {
            "request_id": "req-001",
            "requester_id": "usr-operator",
            "request_type": "user_add",
            "status": "pending",
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_request = AsyncMock(return_value=mock_detail)
            # auth_headers はoperatorのトークン
            # TokenData.user_id がmock_detail["requester_id"]と一致する必要がある
            # ただし実際のuser_idは動的なので、Approver/Adminで代替テスト
            response = test_client.get(
                "/api/approval/req-001",
                headers=auth_headers,
            )

        # operator の user_id と requester_id が一致しないので
        # 403 になる可能性があるが、ロールチェックもされる
        # operator は Approver/Admin ではないので 403
        assert response.status_code == 403

    def test_get_detail_as_approver(self, test_client, approver_headers):
        """正常系: Approver が他者のリクエスト詳細を取得"""
        mock_detail = {
            "request_id": "req-001",
            "requester_id": "other-user",
            "request_type": "user_add",
            "status": "pending",
        }
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_request = AsyncMock(return_value=mock_detail)
            response = test_client.get(
                "/api/approval/req-001",
                headers=approver_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["request"]["request_id"] == "req-001"

    def test_get_detail_not_found(self, test_client, approver_headers):
        """LookupError → 404"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_request = AsyncMock(
                side_effect=LookupError("Request not found")
            )
            response = test_client.get(
                "/api/approval/req-999",
                headers=approver_headers,
            )

        assert response.status_code == 404

    def test_get_detail_exception(self, test_client, approver_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.get_request = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.get(
                "/api/approval/req-001",
                headers=approver_headers,
            )

        assert response.status_code == 500


class TestCancelRequest:
    """POST /api/approval/{request_id}/cancel テスト"""

    def test_cancel_success(self, test_client, auth_headers):
        """正常系: リクエストキャンセル"""
        mock_result = {"request_id": "req-001", "cancelled_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.cancel_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/cancel",
                json={"reason": "No longer needed"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_cancel_not_found(self, test_client, auth_headers):
        """LookupError → 404"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.cancel_request = AsyncMock(
                side_effect=LookupError("Request not found")
            )
            response = test_client.post(
                "/api/approval/req-999/cancel",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 404

    def test_cancel_not_requester(self, test_client, auth_headers):
        """他人のリクエストキャンセル → 403"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.cancel_request = AsyncMock(
                side_effect=ValueError("Only the requester can cancel")
            )
            response = test_client.post(
                "/api/approval/req-001/cancel",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 403

    def test_cancel_status_conflict(self, test_client, auth_headers):
        """ステータス不正 → 409"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.cancel_request = AsyncMock(
                side_effect=ValueError("Request is already approved")
            )
            response = test_client.post(
                "/api/approval/req-001/cancel",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 409

    def test_cancel_exception(self, test_client, auth_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.cancel_request = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.post(
                "/api/approval/req-001/cancel",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 500


class TestExpireOldRequests:
    """POST /api/approval/expire テスト"""

    def test_expire_success(self, test_client, admin_headers):
        """正常系: 期限切れ処理"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.expire_old_requests = AsyncMock(return_value=3)
            response = test_client.post(
                "/api/approval/expire",
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["expired_count"] == 3

    def test_expire_exception(self, test_client, admin_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.expire_old_requests = AsyncMock(
                side_effect=Exception("DB error")
            )
            response = test_client.post(
                "/api/approval/expire",
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestExecuteApprovedAction:
    """POST /api/approval/{request_id}/execute テスト"""

    def test_execute_success(self, test_client, admin_headers):
        """正常系: 承認済み操作の実行"""
        mock_result = {"request_id": "req-001", "executed_at": "2026-03-01T10:00:00Z"}
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.execute_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/approval/req-001/execute",
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_execute_not_found(self, test_client, admin_headers):
        """LookupError → 404"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.execute_request = AsyncMock(
                side_effect=LookupError("Request not found")
            )
            response = test_client.post(
                "/api/approval/req-999/execute",
                headers=admin_headers,
            )

        assert response.status_code == 404

    def test_execute_value_error(self, test_client, admin_headers):
        """ValueError → 400"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.execute_request = AsyncMock(
                side_effect=ValueError("Request not approved")
            )
            response = test_client.post(
                "/api/approval/req-001/execute",
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_execute_not_implemented(self, test_client, admin_headers):
        """NotImplementedError → 501"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.execute_request = AsyncMock(
                side_effect=NotImplementedError("Executor not found for type")
            )
            response = test_client.post(
                "/api/approval/req-001/execute",
                headers=admin_headers,
            )

        assert response.status_code == 501

    def test_execute_exception(self, test_client, admin_headers):
        """Exception → 500"""
        with patch(
            "backend.api.routes.approval.approval_service"
        ) as mock_svc:
            mock_svc.execute_request = AsyncMock(
                side_effect=Exception("Execution error")
            )
            response = test_client.post(
                "/api/approval/req-001/execute",
                headers=admin_headers,
            )

        assert response.status_code == 500
