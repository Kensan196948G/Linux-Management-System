"""
監査ログ API - 統合テスト

テスト項目:
  - GET /api/audit/logs (12件)
  - GET /api/audit/logs/export (8件)
  合計: 20件
"""

from unittest.mock import patch

import pytest


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_LOG_ENTRIES = [
    {
        "timestamp": "2026-01-01T12:00:00",
        "operation": "service_restart",
        "user_id": "admin@example.com",
        "target": "nginx",
        "status": "success",
        "details": {"return_code": 0},
    },
    {
        "timestamp": "2026-01-01T12:05:00",
        "operation": "firewall_rules_read",
        "user_id": "operator@example.com",
        "target": "firewall",
        "status": "success",
        "details": {},
    },
    {
        "timestamp": "2026-01-01T12:10:00",
        "operation": "ssh_config_read",
        "user_id": "admin@example.com",
        "target": "ssh",
        "status": "success",
        "details": {"warning_count": 2},
    },
]


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def operator_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def viewer_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


# ===================================================================
# GET /api/audit/logs
# ===================================================================


class TestAuditLogsList:
    """監査ログ一覧取得テスト"""

    def test_list_success_admin(self, client, admin_headers):
        """正常系: Adminは全ログを取得できる"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get("/api/audit/logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_list_empty_result(self, client, admin_headers):
        """正常系: ログが0件"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get("/api/audit/logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["total"] == 0

    def test_list_pagination(self, client, admin_headers):
        """正常系: ページネーションパラメータ"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get(
                "/api/audit/logs?page=1&per_page=2", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["per_page"] == 2

    def test_list_filter_by_operation(self, client, admin_headers):
        """正常系: 操作種別フィルタ"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[SAMPLE_LOG_ENTRIES[0]],
        ) as mock_query:
            resp = client.get(
                "/api/audit/logs?operation=service_restart",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        # queryが operation パラメータを受け取ることを確認
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs.get("operation") == "service_restart"

    def test_list_filter_by_status(self, client, admin_headers):
        """正常系: ステータスフィルタ"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ) as mock_query:
            resp = client.get(
                "/api/audit/logs?status=success",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs.get("status") == "success"

    def test_list_viewer_forbidden(self, client, viewer_headers):
        """異常系: ViewerはアクセスできないためPermissionError→403"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=PermissionError("Viewer cannot access"),
        ):
            resp = client.get("/api/audit/logs", headers=viewer_headers)
        # Viewerはread:audit権限を持たないためDeps段階で403
        assert resp.status_code == 403

    def test_list_no_auth(self, client):
        """異常系: 認証なし → 403"""
        resp = client.get("/api/audit/logs")
        assert resp.status_code == 403

    def test_list_operator_allowed(self, client, operator_headers):
        """正常系: Operatorは自分のログのみ閲覧可"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[SAMPLE_LOG_ENTRIES[1]],
        ):
            resp = client.get("/api/audit/logs", headers=operator_headers)
        assert resp.status_code == 200

    def test_list_invalid_date_format(self, client, admin_headers):
        """異常系: 不正な日時形式 → 400"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get(
                "/api/audit/logs?start_date=invalid-date",
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_list_response_entry_fields(self, client, admin_headers):
        """正常系: エントリに必須フィールドが存在"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES[:1],
        ):
            resp = client.get("/api/audit/logs", headers=admin_headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) > 0
        for field in ["timestamp", "operation", "user_id", "target", "status"]:
            assert field in entries[0], f"フィールド '{field}' がエントリに存在しない"

    def test_list_per_page_max_limit(self, client, admin_headers):
        """正常系: per_pageの上限（200）"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get(
                "/api/audit/logs?per_page=200", headers=admin_headers
            )
        assert resp.status_code == 200

    def test_list_per_page_over_limit(self, client, admin_headers):
        """異常系: per_pageが上限超過（201）→ 422 Validation Error"""
        resp = client.get(
            "/api/audit/logs?per_page=201", headers=admin_headers
        )
        assert resp.status_code == 422


# ===================================================================
# GET /api/audit/logs/export
# ===================================================================


class TestAuditLogsExport:
    """監査ログエクスポートテスト"""

    def test_export_csv_admin(self, client, admin_headers):
        """正常系: AdminはCSVエクスポート可能"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get(
                "/api/audit/logs/export?format=csv", headers=admin_headers
            )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        content = resp.text
        assert "timestamp" in content
        assert "operation" in content

    def test_export_json_admin(self, client, admin_headers):
        """正常系: AdminはJSONエクスポート可能"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get(
                "/api/audit/logs/export?format=json", headers=admin_headers
            )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]

    def test_export_operator_forbidden(self, client, operator_headers):
        """異常系: OperatorはエクスポートできないためDepsで403"""
        resp = client.get(
            "/api/audit/logs/export?format=csv", headers=operator_headers
        )
        assert resp.status_code == 403

    def test_export_viewer_forbidden(self, client, viewer_headers):
        """異常系: Viewerはエクスポート不可"""
        resp = client.get(
            "/api/audit/logs/export?format=csv", headers=viewer_headers
        )
        assert resp.status_code == 403

    def test_export_no_auth(self, client):
        """異常系: 認証なし → 403"""
        resp = client.get("/api/audit/logs/export?format=csv")
        assert resp.status_code == 403

    def test_export_invalid_format(self, client, admin_headers):
        """異常系: 不正なフォーマット → 400"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get(
                "/api/audit/logs/export?format=xml", headers=admin_headers
            )
        assert resp.status_code == 400

    def test_export_csv_empty(self, client, admin_headers):
        """正常系: データ0件のCSVエクスポート（ヘッダーのみ）"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get(
                "/api/audit/logs/export?format=csv", headers=admin_headers
            )
        assert resp.status_code == 200
        # CSVヘッダー行が含まれること
        assert "timestamp" in resp.text

    def test_export_json_empty(self, client, admin_headers):
        """正常系: データ0件のJSONエクスポート（空配列）"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get(
                "/api/audit/logs/export?format=json", headers=admin_headers
            )
        assert resp.status_code == 200
        import json
        data = json.loads(resp.text)
        assert data == []


# ===================================================================
# GET /api/audit/operations
# ===================================================================


class TestAuditOperations:
    """監査ログ操作種別一覧テスト"""

    def test_list_operations_admin(self, client, admin_headers):
        """正常系: Adminは操作種別一覧を取得できる"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "operations" in data
        assert isinstance(data["operations"], list)

    def test_list_operations_contains_unique_sorted(self, client, admin_headers):
        """正常系: 操作種別が重複なし・ソート済みで返る"""
        entries = SAMPLE_LOG_ENTRIES + [
            {
                "timestamp": "2026-01-01T12:15:00",
                "operation": "service_restart",
                "user_id": "admin@example.com",
                "target": "postgresql",
                "status": "success",
                "details": {},
            }
        ]
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=entries,
        ):
            resp = client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 200
        ops = resp.json()["operations"]
        assert ops == sorted(set(ops))  # ソート済み・重複なし
        assert ops.count("service_restart") == 1

    def test_list_operations_empty(self, client, admin_headers):
        """正常系: ログが0件のとき空リストを返す"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["operations"] == []

    def test_list_operations_no_auth(self, client):
        """異常系: 認証なし → 403"""
        resp = client.get("/api/audit/operations")
        assert resp.status_code == 403

    def test_list_operations_viewer_forbidden(self, client, viewer_headers):
        """異常系: ViewerはアクセスできないためDeps段階で403"""
        resp = client.get("/api/audit/operations", headers=viewer_headers)
        assert resp.status_code == 403

    def test_list_operations_operator_allowed(self, client, operator_headers):
        """正常系: Operatorは自分のログ内の操作種別を取得できる"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[SAMPLE_LOG_ENTRIES[1]],
        ):
            resp = client.get("/api/audit/operations", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "firewall_rules_read" in data["operations"]

    def test_list_operations_internal_error(self, client, admin_headers):
        """異常系: 内部エラー → 500"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=Exception("DB connection failed"),
        ):
            resp = client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 500


# ===================================================================
# GET /api/audit/stats
# ===================================================================


class TestAuditStats:
    """監査ログ統計テスト"""

    def test_get_stats_admin(self, client, admin_headers):
        """正常系: Admin は統計情報を取得できる"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "total" in data
        assert "by_operation" in data
        assert "by_status" in data
        assert "by_user" in data

    def test_get_stats_total_count(self, client, admin_headers):
        """正常系: 総件数が正しい"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=SAMPLE_LOG_ENTRIES,
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        assert resp.json()["total"] == len(SAMPLE_LOG_ENTRIES)

    def test_get_stats_operation_counts(self, client, admin_headers):
        """正常系: 操作別件数が正しい"""
        entries = [
            {"operation": "login", "user_id": "admin@example.com", "status": "success",
             "timestamp": "2026-01-01T00:00:00", "target": "system", "details": {}},
            {"operation": "login", "user_id": "user1@example.com", "status": "success",
             "timestamp": "2026-01-01T01:00:00", "target": "system", "details": {}},
            {"operation": "service_restart", "user_id": "admin@example.com", "status": "success",
             "timestamp": "2026-01-01T02:00:00", "target": "nginx", "details": {}},
        ]
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=entries,
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        data = resp.json()
        assert data["by_operation"]["login"] == 2
        assert data["by_operation"]["service_restart"] == 1

    def test_get_stats_status_counts(self, client, admin_headers):
        """正常系: ステータス別件数が返る"""
        entries = [
            {"operation": "service_restart", "user_id": "admin@example.com", "status": "success",
             "timestamp": "2026-01-01T00:00:00", "target": "nginx", "details": {}},
            {"operation": "service_restart", "user_id": "admin@example.com", "status": "failure",
             "timestamp": "2026-01-01T01:00:00", "target": "nginx", "details": {}},
        ]
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=entries,
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        data = resp.json()
        assert "by_status" in data
        assert data["by_status"].get("success", 0) == 1
        assert data["by_status"].get("failure", 0) == 1

    def test_get_stats_no_auth(self, client):
        """異常系: 認証なし → 403"""
        resp = client.get("/api/audit/stats")
        assert resp.status_code == 403

    def test_get_stats_viewer_forbidden(self, client, viewer_headers):
        """異常系: Viewerはアクセス不可 → 403"""
        resp = client.get("/api/audit/stats", headers=viewer_headers)
        assert resp.status_code == 403

    def test_get_stats_operator_allowed(self, client, operator_headers):
        """正常系: Operatorは自分のログの統計を取得できる"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[SAMPLE_LOG_ENTRIES[1]],
        ):
            resp = client.get("/api/audit/stats", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_get_stats_empty(self, client, admin_headers):
        """正常系: ログが0件のとき total=0"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            return_value=[],
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_get_stats_internal_error(self, client, admin_headers):
        """異常系: 内部エラー → 500"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=Exception("DB connection failed"),
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 500


# ==============================================================================
# エクスポート例外パス（lines 296-303）
# ==============================================================================


class TestAuditExportExceptions:
    """エクスポートエンドポイントの PermissionError / Exception パス"""

    def test_export_permission_error_returns_403(self, client, admin_headers):
        """PermissionError 発生時に 403 を返す (lines 296-300)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=PermissionError("access denied"),
        ):
            resp = client.get(
                "/api/audit/logs/export?format=json",
                headers=admin_headers,
            )
        assert resp.status_code == 403

    def test_export_generic_exception_returns_500(self, client, admin_headers):
        """予期せぬ例外発生時に 500 を返す (lines 301-305)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=RuntimeError("DB connection lost"),
        ):
            resp = client.get(
                "/api/audit/logs/export?format=csv",
                headers=admin_headers,
            )
        assert resp.status_code == 500


class TestAuditExceptionPaths:
    """例外パスのカバレッジ向上テスト（lines 88, 121, 130-132, 156, 206, 250, 252）"""

    def test_list_logs_permission_error_returns_403(self, client, admin_headers):
        """audit_log.query() が PermissionError → 403 (line 121)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=PermissionError("access denied"),
        ):
            resp = client.get("/api/audit/logs", headers=admin_headers)
        assert resp.status_code == 403

    def test_list_logs_generic_exception_returns_500(self, client, admin_headers):
        """audit_log.query() が Exception → 500 (lines 130-132)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=RuntimeError("DB error"),
        ):
            resp = client.get("/api/audit/logs", headers=admin_headers)
        assert resp.status_code == 500

    def test_list_logs_invalid_date_returns_400(self, client, admin_headers):
        """不正な日時フォーマットで 400 (line 88 + ValueError path)"""
        resp = client.get("/api/audit/logs?start_date=not-a-date", headers=admin_headers)
        assert resp.status_code == 400

    def test_list_operations_permission_error_returns_403(self, client, admin_headers):
        """list_audit_operations の PermissionError → 403 (line 156)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=PermissionError("access denied"),
        ):
            resp = client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 403

    def test_get_stats_permission_error_returns_403(self, client, admin_headers):
        """get_audit_stats の PermissionError → 403 (line 206)"""
        with patch(
            "backend.api.routes.audit.audit_log.query",
            side_effect=PermissionError("access denied"),
        ):
            resp = client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 403

    def test_export_with_start_date(self, client, admin_headers):
        """export で start_date パラメータを指定 (lines 250, 252)"""
        resp = client.get(
            "/api/audit/logs/export?format=json&start_date=2025-01-01T00:00:00Z",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    def test_export_with_end_date(self, client, admin_headers):
        """export で end_date パラメータを指定"""
        resp = client.get(
            "/api/audit/logs/export?format=json&end_date=2099-12-31T23:59:59Z",
            headers=admin_headers,
        )
        assert resp.status_code == 200


class TestUserActivityReport:
    """GET /api/audit/report/user-activity のテスト"""

    def test_admin_can_access_report(self, test_client, admin_headers):
        """Admin はレポートを閲覧できる"""
        resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200

    def test_report_response_structure(self, test_client, admin_headers):
        """レスポンス構造確認"""
        resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        data = resp.json()
        assert data["status"] == "success"
        assert "total_operations" in data
        assert "by_user" in data
        assert "by_operation" in data
        assert "by_status" in data
        assert "by_hour" in data

    def test_report_default_7_days(self, test_client, admin_headers):
        """デフォルト7日集計"""
        resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        data = resp.json()
        assert data["period_days"] == 7

    def test_report_custom_days(self, test_client, admin_headers):
        """日数指定が機能する"""
        resp = test_client.get("/api/audit/report/user-activity?days=30", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30

    def test_report_days_too_large_rejected(self, test_client, admin_headers):
        """91日以上は拒否"""
        resp = test_client.get("/api/audit/report/user-activity?days=91", headers=admin_headers)
        assert resp.status_code == 422

    def test_viewer_cannot_access_report(self, test_client, viewer_headers):
        """Viewer はレポート閲覧不可（Approver以上専用）"""
        resp = test_client.get("/api/audit/report/user-activity", headers=viewer_headers)
        assert resp.status_code in (401, 403)

    def test_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/audit/report/user-activity")
        assert resp.status_code in (401, 403)

    def test_by_hour_has_24_entries(self, test_client, admin_headers):
        """時間帯別集計は24件（0〜23時）"""
        resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        data = resp.json()
        assert len(data["by_hour"]) == 24


class TestAuditSummary:
    """GET /api/audit/report/summary のテスト"""

    def test_summary_returns_200(self, test_client, admin_headers):
        """サマリーレポート取得が成功"""
        resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200

    def test_summary_response_structure(self, test_client, admin_headers):
        """レスポンス構造確認"""
        resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        data = resp.json()
        assert data["status"] == "success"
        assert "total" in data
        assert "success_rate" in data
        assert "top_operations" in data

    def test_summary_viewer_can_access(self, test_client, viewer_headers):
        """Viewer は read:audit がないため 403 (Operator以上が必要)"""
        resp = test_client.get("/api/audit/report/summary", headers=viewer_headers)
        assert resp.status_code in (401, 403)

    def test_summary_custom_hours(self, test_client, admin_headers):
        """時間指定が機能する"""
        resp = test_client.get("/api/audit/report/summary?hours=48", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_hours"] == 48

    def test_summary_hours_too_large_rejected(self, test_client, admin_headers):
        """720時間超は拒否"""
        resp = test_client.get("/api/audit/report/summary?hours=721", headers=admin_headers)
        assert resp.status_code == 422

    def test_summary_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/audit/report/summary")
        assert resp.status_code in (401, 403)

    def test_success_rate_is_valid_percent(self, test_client, admin_headers):
        """success_rate は 0.0〜100.0 の範囲"""
        resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        data = resp.json()
        assert 0.0 <= data["success_rate"] <= 100.0
