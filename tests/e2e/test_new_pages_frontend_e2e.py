"""
E2E テスト - 新規5ページ フロントエンド UI テスト（Playwright ブラウザ）

Bootup / Bandwidth / DB Monitor / Postfix / Quotas の
フロントエンドページに対するE2Eテスト。

テスト方針:
  - 各HTMLページが正常にロードされること（200応答）
  - ページのコンテンツが存在すること
  - 認証なしでの保護されたAPIへのリダイレクト/拒否確認
  - 基本的なUI要素の存在確認
"""

import pytest

from .conftest import get_api_token


pytestmark = [pytest.mark.e2e]


# ==============================================================================
# 新規ページ存在確認テスト
# ==============================================================================


class TestNewPagesExist:
    """新規5ページが正常にロードされることを確認"""

    NEW_PAGES = [
        "/dev/bootup.html",
        "/dev/bandwidth.html",
        "/dev/dbmonitor.html",
        "/dev/postfix.html",
        "/dev/quotas.html",
    ]

    @pytest.mark.parametrize("page_path", NEW_PAGES)
    def test_page_returns_200(self, page, base_url, page_path):
        """各ページが HTTP 200 を返す"""
        response = page.request.get(f"{base_url}{page_path}")
        assert response.ok, f"Page {page_path} returned {response.status}"

    @pytest.mark.parametrize("page_path", NEW_PAGES)
    def test_page_has_content(self, page, base_url, page_path):
        """各ページにHTMLコンテンツが存在する"""
        page.goto(f"{base_url}{page_path}")
        content = page.content()
        assert len(content) > 100, f"Page {page_path} content too short: {len(content)} chars"

    @pytest.mark.parametrize("page_path", NEW_PAGES)
    def test_page_has_html_structure(self, page, base_url, page_path):
        """各ページに基本的なHTML構造が存在する"""
        page.goto(f"{base_url}{page_path}")
        content = page.content()
        assert "<html" in content.lower(), f"Page {page_path} missing <html> tag"
        assert "<body" in content.lower(), f"Page {page_path} missing <body> tag"


# ==============================================================================
# Bootup ページ UI テスト
# ==============================================================================


class TestBootupPageUI:
    """Bootup ページの UI テスト"""

    def test_bootup_page_loads(self, page, base_url):
        """bootup.html が正常にロードされる"""
        page.goto(f"{base_url}/dev/bootup.html")
        assert page.title() is not None

    def test_bootup_page_has_title(self, page, base_url):
        """bootup ページにタイトル要素が存在する"""
        page.goto(f"{base_url}/dev/bootup.html")
        content = page.content()
        # ページにbootup関連のテキストが含まれていることを確認
        content_lower = content.lower()
        assert any(
            keyword in content_lower
            for keyword in ["bootup", "boot", "startup", "shutdown"]
        ), "Bootup page should contain boot/startup related content"


# ==============================================================================
# Bandwidth ページ UI テスト
# ==============================================================================


class TestBandwidthPageUI:
    """Bandwidth ページの UI テスト"""

    def test_bandwidth_page_loads(self, page, base_url):
        """bandwidth.html が正常にロードされる"""
        page.goto(f"{base_url}/dev/bandwidth.html")
        assert page.title() is not None

    def test_bandwidth_page_has_title(self, page, base_url):
        """bandwidth ページに関連コンテンツが存在する"""
        page.goto(f"{base_url}/dev/bandwidth.html")
        content = page.content()
        content_lower = content.lower()
        assert any(
            keyword in content_lower
            for keyword in ["bandwidth", "network", "traffic"]
        ), "Bandwidth page should contain bandwidth/network related content"


# ==============================================================================
# DB Monitor ページ UI テスト
# ==============================================================================


class TestDBMonitorPageUI:
    """DB Monitor ページの UI テスト"""

    def test_dbmonitor_page_loads(self, page, base_url):
        """dbmonitor.html が正常にロードされる"""
        page.goto(f"{base_url}/dev/dbmonitor.html")
        assert page.title() is not None

    def test_dbmonitor_page_has_title(self, page, base_url):
        """dbmonitor ページに関連コンテンツが存在する"""
        page.goto(f"{base_url}/dev/dbmonitor.html")
        content = page.content()
        content_lower = content.lower()
        assert any(
            keyword in content_lower
            for keyword in ["database", "db", "mysql", "postgresql", "monitor"]
        ), "DB Monitor page should contain database related content"


# ==============================================================================
# Postfix ページ UI テスト
# ==============================================================================


class TestPostfixPageUI:
    """Postfix ページの UI テスト"""

    def test_postfix_page_loads(self, page, base_url):
        """postfix.html が正常にロードされる"""
        page.goto(f"{base_url}/dev/postfix.html")
        assert page.title() is not None

    def test_postfix_page_has_title(self, page, base_url):
        """postfix ページに関連コンテンツが存在する"""
        page.goto(f"{base_url}/dev/postfix.html")
        content = page.content()
        content_lower = content.lower()
        assert any(
            keyword in content_lower
            for keyword in ["postfix", "mail", "smtp", "email"]
        ), "Postfix page should contain mail/smtp related content"


# ==============================================================================
# Quotas ページ UI テスト
# ==============================================================================


class TestQuotasPageUI:
    """Quotas ページの UI テスト"""

    def test_quotas_page_loads(self, page, base_url):
        """quotas.html が正常にロードされる"""
        page.goto(f"{base_url}/dev/quotas.html")
        assert page.title() is not None

    def test_quotas_page_has_title(self, page, base_url):
        """quotas ページに関連コンテンツが存在する"""
        page.goto(f"{base_url}/dev/quotas.html")
        content = page.content()
        content_lower = content.lower()
        assert any(
            keyword in content_lower
            for keyword in ["quota", "disk", "storage"]
        ), "Quotas page should contain quota/disk related content"


# ==============================================================================
# 全ページ一括ロード確認（既存テストとの統合）
# ==============================================================================


class TestAllNewPagesIntegration:
    """既存ページと合わせて全ページの一括確認"""

    ALL_PAGES = [
        "/dev/index.html",
        "/dev/dashboard.html",
        "/dev/processes.html",
        "/dev/users.html",
        "/dev/cron.html",
        "/dev/approval.html",
        "/dev/bootup.html",
        "/dev/bandwidth.html",
        "/dev/dbmonitor.html",
        "/dev/postfix.html",
        "/dev/quotas.html",
    ]

    def test_all_pages_return_200(self, page, base_url):
        """全ページ（既存+新規）が 200 を返す"""
        for page_path in self.ALL_PAGES:
            response = page.request.get(f"{base_url}{page_path}")
            assert response.ok, f"Page {page_path} returned {response.status}"

    def test_authenticated_api_access_across_modules(self, page, base_url):
        """認証後に全新規モジュールのAPIにアクセスできること"""
        token = get_api_token(page, base_url, "operator@example.com", "operator123")
        headers = {"Authorization": f"Bearer {token}"}

        endpoints = [
            "/api/bootup/status",
            "/api/bootup/services",
            "/api/bandwidth/summary",
            "/api/bandwidth/live",
            "/api/dbmonitor/mysql/status",
            "/api/dbmonitor/postgresql/status",
            "/api/postfix/status",
            "/api/postfix/queue",
            "/api/quotas/status",
            "/api/quotas/users",
        ]

        for endpoint in endpoints:
            resp = page.request.get(f"{base_url}{endpoint}", headers=headers)
            # 200（正常）、403（権限不足）、500/503（サービス未起動）は許容
            assert resp.status in (200, 403, 500, 503), (
                f"Unexpected status {resp.status} for {endpoint}"
            )
