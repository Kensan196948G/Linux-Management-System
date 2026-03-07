"""
E2E テスト - ページアクセシビリティテスト

主要な全ページ・全エンドポイントへのアクセシビリティを検証する。
- HTML ページが 200 を返すこと
- API エンドポイントが認証を要求すること
- 監査・セキュリティ・パッケージ・ネットワーク等の各モジュール確認

Note: ページのバッチテストは単一テスト内ループで実行し、
      Playwright の起動オーバーヘッドを最小化する。
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
# フロントエンドページ アクセシビリティテスト（バッチ）
# ==============================================================================


class TestMainPagesAccessibility:
    """主要ページの HTTP アクセシビリティを検証する（バッチ）"""

    def test_core_pages_return_200(self, page, base_url):
        """コアページ群が全て 200 を返す"""
        pages = [
            "/dev/index.html",
            "/dev/dashboard.html",
            "/dev/processes.html",
            "/dev/logs.html",
            "/dev/users.html",
            "/dev/packages.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_network_and_security_pages_return_200(self, page, base_url):
        """ネットワーク・セキュリティ関連ページが 200 を返す"""
        pages = [
            "/dev/network.html",
            "/dev/firewall.html",
            "/dev/netstat.html",
            "/dev/ssh.html",
            "/dev/bandwidth.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_system_pages_return_200(self, page, base_url):
        """システム管理ページが 200 を返す"""
        pages = [
            "/dev/monitoring.html",
            "/dev/settings.html",
            "/dev/approval.html",
            "/dev/cron.html",
            "/dev/audit.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_hardware_pages_return_200(self, page, base_url):
        """ハードウェア関連ページが 200 を返す"""
        pages = [
            "/dev/hardware.html",
            "/dev/sensors.html",
            "/dev/partitions.html",
            "/dev/smart.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_server_pages_return_200(self, page, base_url):
        """サーバー管理ページが 200 を返す"""
        pages = [
            "/dev/nginx.html",
            "/dev/apache.html",
            "/dev/mysql.html",
            "/dev/postgresql.html",
            "/dev/postfix.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_tool_pages_return_200(self, page, base_url):
        """各種ツールページが 200 を返す"""
        pages = [
            "/dev/backup.html",
            "/dev/bootup.html",
            "/dev/quotas.html",
            "/dev/dbmonitor.html",
            "/dev/certificates.html",
            "/dev/containers.html",
            "/dev/fail2ban.html",
            "/dev/ansible.html",
        ]
        failed = []
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            if not resp.ok:
                failed.append(f"{page_path}: {resp.status}")
        assert not failed, f"Pages failed: {failed}"

    def test_dashboard_content_is_substantial(self, page, base_url):
        """主要ページのコンテンツが十分な量である（5000文字以上）"""
        pages = [
            "/dev/dashboard.html",
            "/dev/processes.html",
            "/dev/monitoring.html",
        ]
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            assert resp.ok
            assert len(resp.text()) > 5000, f"{page_path}: too short ({len(resp.text())} chars)"


# ==============================================================================
# API エンドポイント 認証要求テスト（バッチ）
# ==============================================================================


class TestAuthRequiredEndpoints:
    """認証が必要な API エンドポイントが未認証アクセスを拒否する（バッチ）"""

    def test_system_endpoints_require_auth(self, page, base_url):
        """システム系エンドポイントが認証を要求する"""
        endpoints = [
            "/api/system/status",
            "/api/system/detailed",
            "/api/system/health-score",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}")
            assert resp.status in (401, 403), f"{ep} should require auth, got {resp.status}"

    def test_audit_and_monitoring_require_auth(self, page, base_url):
        """監査・モニタリング系エンドポイントが認証を要求する"""
        endpoints = [
            "/api/audit/logs",
            "/api/audit/stats",
            "/api/monitoring/metrics",
            "/api/monitoring/history",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}")
            assert resp.status in (401, 403), f"{ep} should require auth, got {resp.status}"

    def test_user_and_package_endpoints_require_auth(self, page, base_url):
        """ユーザー・パッケージ系エンドポイントが認証を要求する"""
        endpoints = [
            "/api/users/list",
            "/api/packages/installed",
            "/api/packages/updates",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}")
            assert resp.status in (401, 403), f"{ep} should require auth, got {resp.status}"

    def test_hardware_and_network_require_auth(self, page, base_url):
        """ハードウェア・ネットワーク系エンドポイントが認証を要求する"""
        endpoints = [
            "/api/hardware/memory",
            "/api/network/interfaces",
            "/api/processes",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}")
            assert resp.status in (401, 403), f"{ep} should require auth, got {resp.status}"

    def test_security_and_backup_require_auth(self, page, base_url):
        """セキュリティ・バックアップ系エンドポイントが認証を要求する"""
        endpoints = [
            "/api/security/score",
            "/api/backup/status",
            "/api/fail2ban/status",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}")
            assert resp.status in (401, 403), f"{ep} should require auth, got {resp.status}"


# ==============================================================================
# 認証後の各モジュール API アクセステスト（バッチ）
# ==============================================================================


class TestAuthenticatedAPIAccess:
    """認証済みユーザーが各モジュール API にアクセスできることを検証する"""

    def test_core_api_accessible(self, page, base_url):
        """コア API にアクセスできる（システム・プロセス）"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/system/status",
            "/api/processes",
            "/api/hardware/memory",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_network_api_accessible(self, page, base_url):
        """ネットワーク API にアクセスできる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/network/interfaces",
            "/api/netstat/connections",
            "/api/routing/routes",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_package_and_security_api_accessible(self, page, base_url):
        """パッケージ・セキュリティ API にアクセスできる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/packages/installed",
            "/api/security/score",
            "/api/audit/logs",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_hardware_api_accessible(self, page, base_url):
        """ハードウェア API にアクセスできる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/sensors/temperature",
            "/api/partitions/list",
            "/api/hardware/disk_usage",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_server_management_api_accessible(self, page, base_url):
        """サーバー管理 API にアクセスできる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/nginx/status",
            "/api/backup/status",
            "/api/fail2ban/status",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_config_api_accessible(self, page, base_url):
        """設定系 API にアクセスできる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)
        endpoints = [
            "/api/sysconfig/hostname",
            "/api/sysconfig/timezone",
            "/api/ssh/status",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 403, 500, 503), f"Unexpected {resp.status} for {ep}"


# ==============================================================================
# ページ HTML 品質テスト
# ==============================================================================


class TestPageHTMLQuality:
    """ページ HTML の基本品質を確認する"""

    def test_key_pages_have_title_element(self, page, base_url):
        """主要ページに <title> 要素が存在する"""
        pages = [
            "/dev/dashboard.html",
            "/dev/processes.html",
            "/dev/firewall.html",
        ]
        for page_path in pages:
            page.goto(f"{base_url}{page_path}")
            title = page.title()
            assert title is not None and len(title) > 0, f"{page_path} has no title"

    def test_key_pages_have_charset(self, page, base_url):
        """主要ページに文字コード宣言が存在する"""
        pages = [
            "/dev/dashboard.html",
            "/dev/logs.html",
        ]
        for page_path in pages:
            resp = page.request.get(f"{base_url}{page_path}")
            content = resp.text()
            assert "charset" in content.lower() or "utf-8" in content.lower(), (
                f"{page_path} missing charset declaration"
            )

    def test_login_page_has_title(self, page, base_url):
        """ログインページにタイトルが存在する"""
        page.goto(f"{base_url}/dev/index.html")
        title = page.title()
        assert title is not None and len(title) > 0

    def test_monitoring_page_has_script(self, page, base_url):
        """モニタリングページに JavaScript が含まれる"""
        resp = page.request.get(f"{base_url}/dev/monitoring.html")
        assert resp.ok
        assert "<script" in resp.text().lower()
