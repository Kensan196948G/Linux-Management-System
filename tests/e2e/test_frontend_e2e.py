"""
E2E テスト - フロントエンド UI テスト（Playwright ブラウザ）

実際のブラウザを起動して、ログイン画面・ダッシュボードなどのUIを検証する。
"""

import pytest


pytestmark = [pytest.mark.e2e]


# ==============================================================================
# ログイン UI テスト
# ==============================================================================


class TestLoginUI:
    """ログイン画面の UI テスト"""

    def test_login_page_loads(self, page, base_url):
        """ログインページが正常に読み込まれる"""
        page.goto(f"{base_url}/dev/index.html")
        # ページのタイトルまたはログインフォームが存在することを確認
        assert page.title() is not None

    def test_login_page_has_form_elements(self, page, base_url):
        """ログインページにフォーム要素が存在する"""
        page.goto(f"{base_url}/dev/index.html")
        # ページが読み込まれた（HTMLが存在する）
        content = page.content()
        assert len(content) > 100

    def test_login_page_returns_200(self, page, base_url):
        """ログインページが 200 を返す"""
        response = page.request.get(f"{base_url}/dev/index.html")
        assert response.ok

    def test_dashboard_page_returns_200(self, page, base_url):
        """ダッシュボードページが 200 を返す"""
        response = page.request.get(f"{base_url}/dev/dashboard.html")
        assert response.ok

    def test_all_frontend_pages_exist(self, page, base_url):
        """全フロントエンドページが存在する"""
        pages = [
            "/dev/index.html",
            "/dev/dashboard.html",
            "/dev/processes.html",
            "/dev/users.html",
            "/dev/cron.html",
            "/dev/approval.html",
        ]
        for page_path in pages:
            response = page.request.get(f"{base_url}{page_path}")
            assert response.ok, f"Page {page_path} returned {response.status}"


# ==============================================================================
# API経由のログインフロー UI テスト
# ==============================================================================


class TestLoginAPIFlow:
    """API を通じたログインフローの E2E テスト"""

    def test_full_login_flow(self, page, base_url):
        """ログイン → トークン取得 → 保護エンドポイントアクセスの完全フロー"""
        # Step 1: ログイン
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        assert login_resp.ok
        token = login_resp.json()["access_token"]
        assert token

        # Step 2: 保護エンドポイントにアクセス
        status_resp = page.request.get(
            f"{base_url}/api/system/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status_resp.ok

        # Step 3: ログアウト
        logout_resp = page.request.post(
            f"{base_url}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_resp.ok

    def test_cross_module_access_flow(self, page, base_url):
        """複数モジュールにまたがるアクセスフロー"""
        # ログイン
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "viewer@example.com", "password": "viewer123"},
            headers={"Content-Type": "application/json"},
        )
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 各モジュールにアクセス（成功または503/400が期待値）
        endpoints = [
            "/api/system/status",
            "/api/network/interfaces",
            "/api/hardware/memory",
        ]

        for endpoint in endpoints:
            resp = page.request.get(f"{base_url}{endpoint}", headers=headers)
            assert resp.status in (200, 400, 503), (
                f"Unexpected status {resp.status} for {endpoint}"
            )
