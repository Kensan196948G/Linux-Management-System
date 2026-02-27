"""
API エンドポイントの統合テスト
"""

import pytest
from unittest.mock import patch


class TestHealthCheck:
    """ヘルスチェックエンドポイント"""

    def test_health_endpoint(self, test_client):
        """ヘルスチェック"""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["environment"] == "development"


class TestAuthEndpoints:
    """認証エンドポイント"""

    def test_login_endpoint(self, test_client):
        """ログインエンドポイント"""
        response = test_client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "operator123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_me_endpoint(self, test_client, auth_headers):
        """現在のユーザー情報取得"""
        response = test_client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "operator"

    def test_logout_endpoint(self, test_client, auth_headers):
        """ログアウト"""
        response = test_client.post("/api/auth/logout", headers=auth_headers)

        assert response.status_code == 200


class TestSystemEndpoints:
    """システムエンドポイント"""

    def test_system_status_authenticated(self, test_client, auth_headers):
        """システム状態取得（認証済み）"""
        response = test_client.get("/api/system/status", headers=auth_headers)

        # 権限チェックは通過（sudo ラッパーの結果は問わない）
        assert response.status_code in [200, 500]

    def test_system_status_unauthenticated(self, test_client):
        """システム状態取得（認証なし）"""
        response = test_client.get("/api/system/status")

        assert response.status_code == 403  # Forbidden


class TestServiceEndpoints:
    """サービスエンドポイント"""

    def test_service_restart_with_permission(self, test_client, auth_headers):
        """サービス再起動（権限あり）"""
        response = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx"},
            headers=auth_headers,
        )

        # 権限チェックは通過
        assert response.status_code != 403

    def test_service_restart_without_permission(self, test_client, viewer_token):
        """サービス再起動（権限なし）"""
        headers = {"Authorization": f"Bearer {viewer_token}"}

        response = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx"},
            headers=headers,
        )

        assert response.status_code == 403  # Forbidden

    def test_service_restart_invalid_name(self, test_client, auth_headers):
        """サービス再起動（不正なサービス名）"""
        response = test_client.post(
            "/api/services/restart",
            json={"service_name": "invalid; rm -rf /"},
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error


class TestLogsEndpoints:
    """ログエンドポイント"""

    def test_logs_with_permission(self, test_client, auth_headers):
        """ログ取得（権限あり）"""
        response = test_client.get("/api/logs/nginx?lines=10", headers=auth_headers)

        # 権限チェックは通過
        assert response.status_code != 403

    def test_logs_without_permission(self, test_client):
        """ログ取得（認証なし）"""
        response = test_client.get("/api/logs/nginx?lines=10")

        assert response.status_code == 403

    def test_logs_invalid_lines(self, test_client, auth_headers):
        """ログ取得（不正な行数）"""
        response = test_client.get("/api/logs/nginx?lines=999999", headers=auth_headers)

        # lines は 1-1000 に制限されている
        assert response.status_code == 422


class TestSystemStatusError:
    """system.py エラーパスカバレッジ向上"""

    def test_system_status_exception(self, admin_token):
        """system status が例外で失敗した場合 (raise_server_exceptions=False で 500 を確認)"""
        from backend.api.main import app
        from fastapi.testclient import TestClient
        no_raise_client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "backend.api.routes.system.sudo_wrapper.get_system_status",
            side_effect=Exception("unexpected system error"),
        ):
            resp = no_raise_client.get(
                "/api/system/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500
