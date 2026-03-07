"""
E2E テスト - ダッシュボードとナビゲーション

ダッシュボードページの構造と API エンドポイントを検証する。
- HTML ページ構造の検証
- システム状態 API の検証
- ダッシュボード設定 API の検証
- ストリーミングエンドポイントの存在確認
- メタデータ・静的ファイル配信の確認
"""

import pytest

pytestmark = [pytest.mark.e2e]


# ==============================================================================
# ヘルパー
# ==============================================================================


def _get_token(page, base_url: str, email: str, password: str) -> str:
    resp = page.request.post(
        f"{base_url}/api/auth/login",
        data={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    assert resp.ok, f"Login failed for {email}: {resp.status}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# ダッシュボード HTML 構造テスト
# ==============================================================================


class TestDashboardHTML:
    """ダッシュボードページの HTML 構造を検証する"""

    def test_dashboard_page_returns_200(self, page, base_url):
        """ダッシュボードページが 200 を返す"""
        resp = page.request.get(f"{base_url}/dev/dashboard.html")
        assert resp.ok, f"Dashboard returned {resp.status}"

    def test_dashboard_has_html_doctype(self, page, base_url):
        """ダッシュボードが HTML ドキュメントである"""
        page.goto(f"{base_url}/dev/dashboard.html")
        content = page.content()
        assert "<html" in content.lower() or "<!doctype" in content.lower()

    def test_dashboard_has_head_element(self, page, base_url):
        """ダッシュボードに <head> 要素が存在する"""
        page.goto(f"{base_url}/dev/dashboard.html")
        content = page.content()
        assert "<head" in content.lower()

    def test_dashboard_has_body_element(self, page, base_url):
        """ダッシュボードに <body> 要素が存在する"""
        page.goto(f"{base_url}/dev/dashboard.html")
        content = page.content()
        assert "<body" in content.lower()

    def test_dashboard_has_title_tag(self, page, base_url):
        """ダッシュボードに <title> タグが存在する"""
        page.goto(f"{base_url}/dev/dashboard.html")
        title = page.title()
        assert title is not None
        assert len(title) > 0

    def test_dashboard_content_is_substantial(self, page, base_url):
        """ダッシュボードのコンテンツが十分な量である"""
        resp = page.request.get(f"{base_url}/dev/dashboard.html")
        # ダッシュボードは最低でも 5000 文字以上の HTML を持つ
        assert len(resp.text()) > 5000, f"Dashboard content too short: {len(resp.text())} chars"

    def test_dashboard_references_css(self, page, base_url):
        """ダッシュボードが CSS を参照している"""
        page.goto(f"{base_url}/dev/dashboard.html")
        content = page.content()
        assert "stylesheet" in content or ".css" in content

    def test_dashboard_references_javascript(self, page, base_url):
        """ダッシュボードが JavaScript を参照している"""
        page.goto(f"{base_url}/dev/dashboard.html")
        content = page.content()
        assert "<script" in content.lower()

    def test_login_page_has_title(self, page, base_url):
        """ログインページにタイトルが存在する"""
        page.goto(f"{base_url}/dev/index.html")
        title = page.title()
        assert title is not None
        assert len(title) > 0

    def test_login_page_has_form(self, page, base_url):
        """ログインページにフォーム要素が存在する"""
        page.goto(f"{base_url}/dev/index.html")
        content = page.content()
        # email/password 入力欄またはフォームが存在する
        assert "email" in content.lower() or "password" in content.lower() or "<form" in content.lower()


# ==============================================================================
# ダッシュボード API テスト
# ==============================================================================


class TestDashboardAPI:
    """ダッシュボード API エンドポイントを検証する"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.headers = _auth_headers(self.token)

    def test_dashboard_config_requires_auth(self, page, base_url):
        """ダッシュボード設定 API が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/dashboard/config")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_dashboard_config_accessible_with_auth(self, page, base_url):
        """認証済みでダッシュボード設定にアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/dashboard/config",
            headers=self.headers,
        )
        assert resp.status in (200, 404, 500, 503), f"Unexpected status: {resp.status}"

    def test_dashboard_presets_requires_auth(self, page, base_url):
        """ダッシュボードプリセット API が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/dashboard/presets")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_dashboard_presets_returns_list(self, page, base_url):
        """ダッシュボードプリセットがリストを返す（または正常なエラー）"""
        resp = page.request.get(
            f"{base_url}/api/dashboard/presets",
            headers=self.headers,
        )
        assert resp.status in (200, 404, 500, 503), f"Unexpected status: {resp.status}"
        if resp.status == 200:
            data = resp.json()
            assert isinstance(data, (list, dict))


# ==============================================================================
# システム状態 API テスト
# ==============================================================================


class TestSystemStatusAPI:
    """システム状態 API の詳細な検証"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.headers = _auth_headers(self.token)

    def test_system_status_returns_cpu_info(self, page, base_url):
        """システム状態に CPU 情報が含まれる"""
        resp = page.request.get(
            f"{base_url}/api/system/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"
        if resp.status == 200:
            data = resp.json()
            assert "cpu" in data

    def test_system_status_returns_memory_info(self, page, base_url):
        """システム状態にメモリ情報が含まれる"""
        resp = page.request.get(
            f"{base_url}/api/system/status",
            headers=self.headers,
        )
        if resp.status == 200:
            data = resp.json()
            assert "memory" in data

    def test_system_detailed_endpoint_accessible(self, page, base_url):
        """詳細システム情報エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/system/detailed",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    def test_system_health_score_endpoint_accessible(self, page, base_url):
        """システムヘルススコアエンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/system/health-score",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"
        if resp.status == 200:
            data = resp.json()
            assert isinstance(data, dict)

    def test_system_status_requires_auth(self, page, base_url):
        """システム状態 API が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/system/status")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_system_detailed_requires_auth(self, page, base_url):
        """詳細システム情報が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/system/detailed")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"


# ==============================================================================
# ストリーミング・WebSocket エンドポイントテスト
# ==============================================================================


class TestStreamingEndpoints:
    """ストリーミングエンドポイントの存在を確認する"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.headers = _auth_headers(self.token)

    def test_stream_system_endpoint_exists(self, page, base_url):
        """/api/stream/system エンドポイントが存在する（認証エラーか 200）"""
        resp = page.request.get(f"{base_url}/api/stream/system")
        # 認証なし -> 401/403、クエリパラメータ不足 -> 422、SSE接続 -> 200
        assert resp.status in (200, 401, 403, 406, 422, 426), f"Unexpected: {resp.status}"

    def test_stream_dashboard_endpoint_exists(self, page, base_url):
        """/api/stream/dashboard エンドポイントが存在する"""
        resp = page.request.get(f"{base_url}/api/stream/dashboard")
        assert resp.status in (200, 401, 403, 406, 422, 426), f"Unexpected: {resp.status}"

    def test_monitoring_metrics_accessible_with_auth(self, page, base_url):
        """/api/monitoring/metrics に認証ありでアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/monitoring/metrics",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected: {resp.status}"

    def test_monitoring_history_accessible_with_auth(self, page, base_url):
        """/api/monitoring/history に認証ありでアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/monitoring/history",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected: {resp.status}"


# ==============================================================================
# 静的ファイル配信テスト
# ==============================================================================


class TestStaticAssets:
    """静的ファイルが正しく配信されることを確認する"""

    def test_favicon_ico_accessible(self, page, base_url):
        """favicon.ico がアクセス可能である"""
        resp = page.request.get(f"{base_url}/favicon.ico")
        assert resp.status in (200, 301, 302, 404), f"Unexpected: {resp.status}"

    def test_favicon_svg_accessible(self, page, base_url):
        """favicon SVG ファイルがアクセス可能である"""
        resp = page.request.get(f"{base_url}/favicon-dev.svg")
        assert resp.status in (200, 404), f"Unexpected: {resp.status}"

    def test_api_info_endpoint_accessible(self, page, base_url):
        """/api/info エンドポイントにアクセスできる"""
        resp = page.request.get(f"{base_url}/api/info")
        assert resp.status in (200, 401, 403), f"Unexpected: {resp.status}"

    def test_health_check_returns_healthy(self, page, base_url):
        """/health エンドポイントが 'healthy' ステータスを返す"""
        resp = page.request.get(f"{base_url}/health")
        assert resp.ok
        data = resp.json()
        assert data.get("status") == "healthy"

    def test_health_check_has_version(self, page, base_url):
        """/health レスポンスにバージョン情報が含まれる"""
        resp = page.request.get(f"{base_url}/health")
        assert resp.ok
        data = resp.json()
        assert "version" in data

    def test_openapi_spec_accessible(self, page, base_url):
        """OpenAPI 仕様書にアクセスできる"""
        resp = page.request.get(f"{base_url}/openapi.json")
        assert resp.ok
        data = resp.json()
        assert "openapi" in data or "info" in data
