"""
E2E セキュリティヘッダーテスト

FastAPI TestClient を使ってセキュリティヘッダーの設定を確認する。
実際のHTTPサーバー起動不要。
"""

import sys
from pathlib import Path

import pytest

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

pytestmark = [pytest.mark.e2e]


@pytest.fixture(scope="module")
def client():
    """TestClient（HTTPサーバー不起動）"""
    from fastapi.testclient import TestClient

    from backend.api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ==============================================================================
# セキュリティヘッダー確認
# ==============================================================================


class TestSecurityHeaders:
    """レスポンスのセキュリティヘッダーを検証する"""

    def _get_headers(self, client, path: str = "/health"):
        response = client.get(path)
        return response.headers

    def test_x_content_type_options_nosniff(self, client):
        """X-Content-Type-Options: nosniff が設定されている"""
        headers = self._get_headers(client)
        assert "x-content-type-options" in headers, "X-Content-Type-Options ヘッダーが欠如"
        assert headers["x-content-type-options"] == "nosniff"

    def test_x_frame_options_set(self, client):
        """X-Frame-Options が設定されている"""
        headers = self._get_headers(client)
        assert "x-frame-options" in headers, "X-Frame-Options ヘッダーが欠如"
        # DENY または SAMEORIGIN が期待値
        assert headers["x-frame-options"] in ("DENY", "SAMEORIGIN")

    def test_x_xss_protection_set(self, client):
        """X-XSS-Protection が設定されている"""
        headers = self._get_headers(client)
        assert "x-xss-protection" in headers, "X-XSS-Protection ヘッダーが欠如"

    def test_referrer_policy_set(self, client):
        """Referrer-Policy が設定されている"""
        headers = self._get_headers(client)
        assert "referrer-policy" in headers, "Referrer-Policy ヘッダーが欠如"

    def test_content_security_policy_set(self, client):
        """Content-Security-Policy が設定されている"""
        headers = self._get_headers(client)
        assert "content-security-policy" in headers, "Content-Security-Policy ヘッダーが欠如"
        csp = headers["content-security-policy"]
        assert "default-src" in csp

    def test_security_headers_on_api_endpoint(self, client):
        """API エンドポイントにもセキュリティヘッダーが付与される"""
        response = client.get("/api/info")
        assert response.status_code == 200
        headers = response.headers
        assert "x-content-type-options" in headers
        assert "x-frame-options" in headers

    def test_security_headers_on_unauthenticated_response(self, client):
        """401/403 レスポンスにもセキュリティヘッダーが付与される"""
        response = client.get("/api/system/status")
        assert response.status_code in (401, 403)
        headers = response.headers
        assert "x-content-type-options" in headers
        assert "x-frame-options" in headers

    def test_no_server_header_leakage(self, client):
        """server ヘッダーが詳細な情報を漏洩しない"""
        headers = self._get_headers(client)
        # server ヘッダーがある場合、バージョン情報を含まないことが望ましい
        server = headers.get("server", "")
        assert "python" not in server.lower(), "server ヘッダーにPythonバージョンが露出している"


# ==============================================================================
# 認証なしアクセスの拒否確認
# ==============================================================================


class TestUnauthenticatedAccess:
    """認証なしアクセスが適切に拒否されることを確認する"""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/system/status"),
        ("POST", "/api/services/restart"),
        ("GET", "/api/logs/syslog"),
        ("GET", "/api/processes/"),
        ("GET", "/api/users/"),
        ("GET", "/api/network/interfaces"),
        ("GET", "/api/hardware/memory"),
        ("GET", "/api/firewall/rules"),
        ("GET", "/api/packages/installed"),
        ("GET", "/api/cron/list"),
        ("GET", "/api/audit/logs"),
    ]

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_unauthenticated_access_rejected(self, client, method, path):
        """認証なしアクセスが 401 または 403 で拒否される"""
        response = getattr(client, method.lower())(path)
        assert response.status_code in (401, 403), (
            f"{method} {path} が {response.status_code} を返した（401/403 期待）"
        )

    def test_invalid_bearer_token_rejected(self, client):
        """不正な Bearer トークンが 401 で拒否される"""
        response = client.get(
            "/api/system/status",
            headers={"Authorization": "Bearer this_is_not_a_valid_jwt_token"},
        )
        assert response.status_code == 401

    def test_malformed_authorization_header(self, client):
        """不正な Authorization ヘッダーが 401 または 403 で拒否される"""
        response = client.get(
            "/api/system/status",
            headers={"Authorization": "NotBearer sometoken"},
        )
        assert response.status_code in (401, 403)

    def test_empty_authorization_header(self, client):
        """空の Authorization ヘッダーが 401 で拒否される"""
        response = client.get(
            "/api/system/status",
            headers={"Authorization": ""},
        )
        assert response.status_code in (401, 403)

    def test_public_health_endpoint_accessible(self, client):
        """/health は認証なしでアクセス可能"""
        response = client.get("/health")
        assert response.status_code == 200

    def test_public_api_info_accessible(self, client):
        """/api/info は認証なしでアクセス可能"""
        response = client.get("/api/info")
        assert response.status_code == 200

    def test_login_endpoint_accessible_without_auth(self, client):
        """ログインエンドポイントは認証なしでアクセス可能（422 は入力エラー）"""
        response = client.post("/api/auth/login", json={})
        # 認証不要でアクセスできる（入力エラーは 422、認証情報不正は 401）
        assert response.status_code in (400, 401, 422)


# ==============================================================================
# レスポンス形式確認
# ==============================================================================


class TestApiResponseFormat:
    """APIレスポンスの形式を確認する"""

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        from backend.api.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    def test_health_response_is_json(self, client):
        """/health が JSON レスポンスを返す"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_error_response_is_json(self, client):
        """エラーレスポンスが JSON 形式"""
        response = client.get("/api/system/status")
        assert response.status_code in (401, 403)
        # JSON パース可能であることを確認
        data = response.json()
        assert isinstance(data, dict)

    def test_404_response_is_json(self, client):
        """404 レスポンスが JSON 形式"""
        response = client.get("/api/this-endpoint-does-not-exist")
        assert response.status_code == 404
        data = response.json()
        assert isinstance(data, dict)

    def test_content_type_is_json_for_api(self, client):
        """API エンドポイントの Content-Type は application/json"""
        response = client.get("/health")
        assert "application/json" in response.headers.get("content-type", "")
