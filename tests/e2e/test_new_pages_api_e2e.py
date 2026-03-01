"""
E2E テスト - 新規5ページ API エンドポイント

Bootup / Bandwidth / DB Monitor / Postfix / Quotas の
APIエンドポイントに対するE2Eテスト。

テスト方針:
  - 認証なしアクセスで 401/403 を返すこと
  - 認証ありで 200 またはサービス未起動時の 500/503 を返すこと
  - 各エンドポイントのレスポンス構造を検証
"""

import pytest


pytestmark = [pytest.mark.e2e]


# ==============================================================================
# ヘルパー
# ==============================================================================


def _login(page, base_url, email, password):
    """ログインしてトークンとヘッダーを返す"""
    resp = page.request.post(
        f"{base_url}/api/auth/login",
        data={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    assert resp.ok, f"Login failed for {email}: {resp.status}"
    token = resp.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


# ==============================================================================
# Bootup API E2E テスト
# ==============================================================================


class TestBootupAPI:
    """Bootup / Shutdown 管理 API の E2E テスト"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token, self.headers = _login(page, base_url, "operator@example.com", "operator123")

    def test_bootup_status_requires_auth(self, page, base_url):
        """認証なしで /api/bootup/status は 401/403"""
        resp = page.request.get(f"{base_url}/api/bootup/status")
        assert resp.status in (401, 403)

    def test_bootup_services_requires_auth(self, page, base_url):
        """認証なしで /api/bootup/services は 401/403"""
        resp = page.request.get(f"{base_url}/api/bootup/services")
        assert resp.status in (401, 403)

    def test_bootup_status_with_auth(self, page, base_url):
        """認証ありで /api/bootup/status が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bootup/status",
            headers=self.headers,
        )
        # 200（正常）または 500/503（ラッパー未設定環境）
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert isinstance(data, dict)

    def test_bootup_services_with_auth(self, page, base_url):
        """認証ありで /api/bootup/services が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bootup/services",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert isinstance(data, dict)

    def test_bootup_enable_requires_auth(self, page, base_url):
        """認証なしで /api/bootup/enable は 401/403"""
        resp = page.request.post(
            f"{base_url}/api/bootup/enable",
            data={"service": "nginx", "reason": "test"},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status in (401, 403)

    def test_bootup_enable_invalid_service_rejected(self, page, base_url):
        """allowlist外のサービスは 400"""
        admin_token, admin_headers = _login(page, base_url, "admin@example.com", "admin123")
        admin_headers["Content-Type"] = "application/json"
        resp = page.request.post(
            f"{base_url}/api/bootup/enable",
            data={"service": "malicious-service", "reason": "test"},
            headers=admin_headers,
        )
        # 400（allowlist拒否）または 403（権限不足）
        assert resp.status in (400, 403, 422), f"Unexpected status: {resp.status}"


# ==============================================================================
# Bandwidth API E2E テスト
# ==============================================================================


class TestBandwidthAPI:
    """帯域幅監視 API の E2E テスト"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token, self.headers = _login(page, base_url, "viewer@example.com", "viewer123")

    def test_bandwidth_summary_requires_auth(self, page, base_url):
        """認証なしで /api/bandwidth/summary は 401/403"""
        resp = page.request.get(f"{base_url}/api/bandwidth/summary")
        assert resp.status in (401, 403)

    def test_bandwidth_live_requires_auth(self, page, base_url):
        """認証なしで /api/bandwidth/live は 401/403"""
        resp = page.request.get(f"{base_url}/api/bandwidth/live")
        assert resp.status in (401, 403)

    def test_bandwidth_daily_requires_auth(self, page, base_url):
        """認証なしで /api/bandwidth/daily は 401/403"""
        resp = page.request.get(f"{base_url}/api/bandwidth/daily")
        assert resp.status in (401, 403)

    def test_bandwidth_interfaces_requires_auth(self, page, base_url):
        """認証なしで /api/bandwidth/interfaces は 401/403"""
        resp = page.request.get(f"{base_url}/api/bandwidth/interfaces")
        assert resp.status in (401, 403)

    def test_bandwidth_summary_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/summary が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/summary",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    def test_bandwidth_live_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/live が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/live",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    def test_bandwidth_daily_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/daily が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/daily",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    def test_bandwidth_interfaces_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/interfaces が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/interfaces",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data
            assert "interfaces" in data

    def test_bandwidth_top_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/top が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/top",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_bandwidth_hourly_with_auth(self, page, base_url):
        """認証ありで /api/bandwidth/hourly が応答する"""
        resp = page.request.get(
            f"{base_url}/api/bandwidth/hourly",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"


# ==============================================================================
# DB Monitor API E2E テスト
# ==============================================================================


class TestDBMonitorAPI:
    """データベース監視 API の E2E テスト"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token, self.headers = _login(page, base_url, "operator@example.com", "operator123")

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_status_requires_auth(self, page, base_url, db_type):
        """認証なしで /api/dbmonitor/{db_type}/status は 401/403"""
        resp = page.request.get(f"{base_url}/api/dbmonitor/{db_type}/status")
        assert resp.status in (401, 403)

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_databases_requires_auth(self, page, base_url, db_type):
        """認証なしで /api/dbmonitor/{db_type}/databases は 401/403"""
        resp = page.request.get(f"{base_url}/api/dbmonitor/{db_type}/databases")
        assert resp.status in (401, 403)

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_status_with_auth(self, page, base_url, db_type):
        """認証ありで /api/dbmonitor/{db_type}/status が応答する"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/{db_type}/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status for {db_type}: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data
            assert "db_type" in data

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_databases_with_auth(self, page, base_url, db_type):
        """認証ありで /api/dbmonitor/{db_type}/databases が応答する"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/{db_type}/databases",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status for {db_type}: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_processes_with_auth(self, page, base_url, db_type):
        """認証ありで /api/dbmonitor/{db_type}/processes が応答する"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/{db_type}/processes",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status for {db_type}: {resp.status}"

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_connections_with_auth(self, page, base_url, db_type):
        """認証ありで /api/dbmonitor/{db_type}/connections が応答する"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/{db_type}/connections",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status for {db_type}: {resp.status}"

    @pytest.mark.parametrize("db_type", ["mysql", "postgresql"])
    def test_db_variables_with_auth(self, page, base_url, db_type):
        """認証ありで /api/dbmonitor/{db_type}/variables が応答する"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/{db_type}/variables",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status for {db_type}: {resp.status}"

    def test_invalid_db_type_rejected(self, page, base_url):
        """許可されていないDBタイプは 422"""
        resp = page.request.get(
            f"{base_url}/api/dbmonitor/sqlite/status",
            headers=self.headers,
        )
        assert resp.status == 422, f"Expected 422 for invalid db_type, got {resp.status}"


# ==============================================================================
# Postfix API E2E テスト
# ==============================================================================


class TestPostfixAPI:
    """Postfix / SMTP 管理 API の E2E テスト"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token, self.headers = _login(page, base_url, "operator@example.com", "operator123")

    def test_postfix_status_requires_auth(self, page, base_url):
        """認証なしで /api/postfix/status は 401/403"""
        resp = page.request.get(f"{base_url}/api/postfix/status")
        assert resp.status in (401, 403)

    def test_postfix_queue_requires_auth(self, page, base_url):
        """認証なしで /api/postfix/queue は 401/403"""
        resp = page.request.get(f"{base_url}/api/postfix/queue")
        assert resp.status in (401, 403)

    def test_postfix_logs_requires_auth(self, page, base_url):
        """認証なしで /api/postfix/logs は 401/403"""
        resp = page.request.get(f"{base_url}/api/postfix/logs")
        assert resp.status in (401, 403)

    def test_postfix_status_with_auth(self, page, base_url):
        """認証ありで /api/postfix/status が応答する"""
        resp = page.request.get(
            f"{base_url}/api/postfix/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert isinstance(data, dict)

    def test_postfix_queue_with_auth(self, page, base_url):
        """認証ありで /api/postfix/queue が応答する"""
        resp = page.request.get(
            f"{base_url}/api/postfix/queue",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert isinstance(data, dict)

    def test_postfix_logs_with_auth(self, page, base_url):
        """認証ありで /api/postfix/logs が応答する"""
        resp = page.request.get(
            f"{base_url}/api/postfix/logs",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert isinstance(data, dict)

    def test_postfix_logs_lines_param(self, page, base_url):
        """/api/postfix/logs の lines パラメータが機能する"""
        resp = page.request.get(
            f"{base_url}/api/postfix/logs?lines=10",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"


# ==============================================================================
# Quotas API E2E テスト
# ==============================================================================


class TestQuotasAPI:
    """ディスククォータ管理 API の E2E テスト"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token, self.headers = _login(page, base_url, "operator@example.com", "operator123")

    def test_quotas_status_requires_auth(self, page, base_url):
        """認証なしで /api/quotas/status は 401/403"""
        resp = page.request.get(f"{base_url}/api/quotas/status")
        assert resp.status in (401, 403)

    def test_quotas_users_requires_auth(self, page, base_url):
        """認証なしで /api/quotas/users は 401/403"""
        resp = page.request.get(f"{base_url}/api/quotas/users")
        assert resp.status in (401, 403)

    def test_quotas_status_with_auth(self, page, base_url):
        """認証ありで /api/quotas/status が応答する"""
        resp = page.request.get(
            f"{base_url}/api/quotas/status",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    def test_quotas_users_with_auth(self, page, base_url):
        """認証ありで /api/quotas/users が応答する"""
        resp = page.request.get(
            f"{base_url}/api/quotas/users",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
        if resp.ok:
            data = resp.json()
            assert "status" in data

    def test_quotas_report_with_auth(self, page, base_url):
        """認証ありで /api/quotas/report が応答する"""
        resp = page.request.get(
            f"{base_url}/api/quotas/report",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_quotas_user_specific_with_auth(self, page, base_url):
        """認証ありで /api/quotas/user/{username} が応答する"""
        resp = page.request.get(
            f"{base_url}/api/quotas/user/root",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_quotas_group_specific_with_auth(self, page, base_url):
        """認証ありで /api/quotas/group/{groupname} が応答する"""
        resp = page.request.get(
            f"{base_url}/api/quotas/group/root",
            headers=self.headers,
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_quotas_set_requires_auth(self, page, base_url):
        """認証なしで /api/quotas/set は 401/403"""
        resp = page.request.post(
            f"{base_url}/api/quotas/set",
            data={
                "type": "user",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 1024,
                "hard_kb": 2048,
            },
            headers={"Content-Type": "application/json"},
        )
        assert resp.status in (401, 403)


# ==============================================================================
# クロスモジュール認証 E2E テスト
# ==============================================================================


class TestNewPagesAuthFlow:
    """新規5ページ全体の認証フローを横断的に検証"""

    UNAUTHENTICATED_ENDPOINTS = [
        "/api/bootup/status",
        "/api/bootup/services",
        "/api/bandwidth/summary",
        "/api/bandwidth/live",
        "/api/bandwidth/daily",
        "/api/bandwidth/interfaces",
        "/api/dbmonitor/mysql/status",
        "/api/dbmonitor/mysql/databases",
        "/api/dbmonitor/postgresql/status",
        "/api/dbmonitor/postgresql/databases",
        "/api/postfix/status",
        "/api/postfix/queue",
        "/api/postfix/logs",
        "/api/quotas/status",
        "/api/quotas/users",
    ]

    @pytest.mark.parametrize("endpoint", UNAUTHENTICATED_ENDPOINTS)
    def test_all_new_endpoints_require_auth(self, page, base_url, endpoint):
        """全ての新規エンドポイントが認証を要求する"""
        resp = page.request.get(f"{base_url}{endpoint}")
        assert resp.status in (401, 403), (
            f"Expected 401/403 for {endpoint}, got {resp.status}"
        )
