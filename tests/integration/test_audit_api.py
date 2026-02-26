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
