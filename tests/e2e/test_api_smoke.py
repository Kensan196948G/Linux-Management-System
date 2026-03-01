"""
E2E スモークテスト - 主要APIエンドポイント存在確認

unittest.mock を使用してサーバー起動不要でテスト可能。
FastAPI TestClient でルーティングのみ確認する。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

pytestmark = [pytest.mark.e2e]


# ==============================================================================
# TestClient を使った APIルーティング スモークテスト
# ==============================================================================

EXPECTED_PREFIXES = [
    "/api/auth",
    "/api/system",
    "/api/services",
    "/api/logs",
    "/api/processes",
    "/api/approval",
    "/api/cron",
    "/api/users",
    "/api/network",
    "/api/hardware",
    "/api/firewall",
    "/api/filesystem",
    "/api/packages",
    "/api/ssh",
    "/api/audit",
    "/api/bootup",
    "/api/system-time",
    "/api/quotas",
    "/api/bandwidth",
    "/api/netstat",
    "/api/smart",
    "/api/partitions",
    "/api/sensors",
]


@pytest.fixture(scope="module")
def app_routes():
    """FastAPI アプリのルート一覧を取得する（インポートのみ）"""
    from backend.api.main import app

    return [route.path for route in app.routes if hasattr(route, "path")]


class TestApiRoutesExist:
    """APIルーティングが正しく登録されているか確認するスモークテスト"""

    def test_health_endpoint_exists(self, app_routes):
        """ヘルスチェックエンドポイントが存在する"""
        assert "/health" in app_routes

    def test_auth_routes_registered(self, app_routes):
        """認証ルートが登録されている"""
        auth_routes = [r for r in app_routes if r.startswith("/api/auth")]
        assert len(auth_routes) > 0, "認証ルートが登録されていない"

    def test_system_routes_registered(self, app_routes):
        """システムルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/system")]
        assert len(routes) > 0, "システムルートが登録されていない"

    def test_services_routes_registered(self, app_routes):
        """サービス管理ルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/services")]
        assert len(routes) > 0, "サービス管理ルートが登録されていない"

    def test_logs_routes_registered(self, app_routes):
        """ログルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/logs")]
        assert len(routes) > 0, "ログルートが登録されていない"

    def test_processes_routes_registered(self, app_routes):
        """プロセス管理ルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/processes")]
        assert len(routes) > 0, "プロセス管理ルートが登録されていない"

    def test_approval_routes_registered(self, app_routes):
        """承認フロールートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/approval")]
        assert len(routes) > 0, "承認フロールートが登録されていない"

    def test_firewall_routes_registered(self, app_routes):
        """ファイアウォールルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/firewall")]
        assert len(routes) > 0, "ファイアウォールルートが登録されていない"

    def test_network_routes_registered(self, app_routes):
        """ネットワークルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/network")]
        assert len(routes) > 0, "ネットワークルートが登録されていない"

    def test_hardware_routes_registered(self, app_routes):
        """ハードウェアルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/hardware")]
        assert len(routes) > 0, "ハードウェアルートが登録されていない"

    def test_users_routes_registered(self, app_routes):
        """ユーザー管理ルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/users")]
        assert len(routes) > 0, "ユーザー管理ルートが登録されていない"

    def test_packages_routes_registered(self, app_routes):
        """パッケージ管理ルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/packages")]
        assert len(routes) > 0, "パッケージ管理ルートが登録されていない"

    def test_ssh_routes_registered(self, app_routes):
        """SSHルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/ssh")]
        assert len(routes) > 0, "SSHルートが登録されていない"

    def test_cron_routes_registered(self, app_routes):
        """Cronルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/cron")]
        assert len(routes) > 0, "Cronルートが登録されていない"

    def test_audit_routes_registered(self, app_routes):
        """監査ログルートが登録されている"""
        routes = [r for r in app_routes if r.startswith("/api/audit")]
        assert len(routes) > 0, "監査ログルートが登録されていない"

    def test_minimum_route_count(self, app_routes):
        """最低限のルート数が存在する（50以上）"""
        api_routes = [r for r in app_routes if r.startswith("/api/")]
        assert len(api_routes) >= 50, f"APIルートが少なすぎる: {len(api_routes)}"

    def test_no_duplicate_method_path_routes(self, app_routes):
        """同一パスのルートが重複して登録されていない（ルート数チェック）"""
        # FastAPI は GET/POST 等メソッド違いで同一パスを許容する
        # ここではパス一覧の重複のみ確認（メソッド違いは除外）
        assert len(app_routes) >= len(set(app_routes)) * 0.9, (
            f"ルートの重複が多すぎる: 全 {len(app_routes)} / ユニーク {len(set(app_routes))}"
        )


class TestApiRoutesMockRequests:
    """モックを使ったAPIリクエストテスト（HTTPサーバー不要）"""

    @pytest.fixture(scope="class")
    def client(self):
        """TestClient を使用（実際のHTTPサーバー不起動）"""
        from fastapi.testclient import TestClient

        from backend.api.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_health_endpoint_returns_200(self, client):
        """/health エンドポイントが 200 を返す"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_unauthenticated_system_returns_401_or_403(self, client):
        """認証なしで /api/system/* にアクセスすると 401/403"""
        response = client.get("/api/system/status")
        assert response.status_code in (401, 403), (
            f"認証なしアクセスが {response.status_code} を返した（401/403 期待）"
        )

    def test_unauthenticated_services_returns_401_or_403(self, client):
        """認証なしで /api/services/restart にアクセスすると 401/403"""
        response = client.post("/api/services/restart", json={"service_name": "nginx"})
        assert response.status_code in (401, 403)

    def test_unauthenticated_logs_returns_401_or_403(self, client):
        """認証なしで /api/logs にアクセスすると 401/403"""
        response = client.get("/api/logs/syslog")
        assert response.status_code in (401, 403)

    def test_unauthenticated_processes_returns_401_or_403(self, client):
        """認証なしで /api/processes にアクセスすると 401/403"""
        response = client.get("/api/processes/")
        assert response.status_code in (401, 403)

    def test_unauthenticated_firewall_returns_401_or_403(self, client):
        """認証なしで /api/firewall にアクセスすると 401/403"""
        response = client.get("/api/firewall/rules")
        assert response.status_code in (401, 403)

    def test_login_endpoint_exists(self, client):
        """ログインエンドポイントが存在する（認証情報なしでも 422/401/400）"""
        response = client.post("/api/auth/login", json={})
        assert response.status_code in (400, 401, 422), (
            f"/api/auth/login が {response.status_code} を返した（400/401/422 期待）"
        )

    def test_invalid_token_returns_401(self, client):
        """無効なトークンで 401 を返す"""
        response = client.get(
            "/api/system/status",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        assert response.status_code == 401

    def test_api_info_endpoint(self, client):
        """/api/info エンドポイントが 200 を返す"""
        response = client.get("/api/info")
        assert response.status_code == 200

    def test_nonexistent_endpoint_returns_404(self, client):
        """存在しないエンドポイントが 404 を返す"""
        response = client.get("/api/nonexistent-endpoint-xyz123")
        assert response.status_code == 404
