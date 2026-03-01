"""
Audit API エンドポイントのユニットテスト

backend/api/routes/audit.py のカバレッジ向上
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestListAuditLogs:
    """GET /api/audit/logs テスト"""

    def test_list_logs_admin(self, test_client, admin_headers):
        """正常系: Admin が全ログを取得"""
        response = test_client.get("/api/audit/logs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_list_logs_with_pagination(self, test_client, admin_headers):
        """ページネーション付きで取得"""
        response = test_client.get(
            "/api/audit/logs?page=1&per_page=10", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 10

    def test_list_logs_with_filters(self, test_client, admin_headers):
        """フィルタ付きで取得"""
        response = test_client.get(
            "/api/audit/logs?operation=hardware_disks&status=success",
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_list_logs_with_date_range(self, test_client, admin_headers):
        """日時範囲指定で取得"""
        response = test_client.get(
            "/api/audit/logs?start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_list_logs_invalid_date_format(self, test_client, admin_headers):
        """不正な日時フォーマット"""
        response = test_client.get(
            "/api/audit/logs?start_date=not-a-date", headers=admin_headers
        )
        assert response.status_code == 400

    def test_list_logs_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/audit/logs")
        assert response.status_code == 403

    def test_list_logs_operator(self, test_client, auth_headers):
        """Operator が自分のログを取得"""
        response = test_client.get("/api/audit/logs", headers=auth_headers)
        assert response.status_code == 200


class TestExportAuditLogs:
    """GET /api/audit/logs/export テスト"""

    def test_export_csv(self, test_client, admin_headers):
        """正常系: CSV形式でエクスポート"""
        response = test_client.get(
            "/api/audit/logs/export?format=csv", headers=admin_headers
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    def test_export_json(self, test_client, admin_headers):
        """正常系: JSON形式でエクスポート"""
        response = test_client.get(
            "/api/audit/logs/export?format=json", headers=admin_headers
        )

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_export_invalid_format(self, test_client, admin_headers):
        """不正なフォーマット指定"""
        response = test_client.get(
            "/api/audit/logs/export?format=xml", headers=admin_headers
        )
        assert response.status_code == 400
        assert "csv" in response.json()["message"]

    def test_export_with_filters(self, test_client, admin_headers):
        """フィルタ付きCSVエクスポート"""
        response = test_client.get(
            "/api/audit/logs/export?format=csv&operation=login&status=success",
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_export_with_date_range(self, test_client, admin_headers):
        """日時範囲指定でエクスポート"""
        response = test_client.get(
            "/api/audit/logs/export?format=json"
            "&start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_export_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/audit/logs/export?format=csv")
        assert response.status_code == 403

    def test_export_content_disposition_csv(self, test_client, admin_headers):
        """CSVレスポンスにContent-Dispositionヘッダがあること"""
        response = test_client.get(
            "/api/audit/logs/export?format=csv", headers=admin_headers
        )
        assert response.status_code == 200
        cd = response.headers.get("content-disposition", "")
        assert "audit_export_" in cd
        assert ".csv" in cd

    def test_export_content_disposition_json(self, test_client, admin_headers):
        """JSONレスポンスにContent-Dispositionヘッダがあること"""
        response = test_client.get(
            "/api/audit/logs/export?format=json", headers=admin_headers
        )
        assert response.status_code == 200
        cd = response.headers.get("content-disposition", "")
        assert "audit_export_" in cd
        assert ".json" in cd
