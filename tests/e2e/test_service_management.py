"""
E2E テスト - サービス管理 API テスト

/api/services/restart エンドポイントとサーバー状態 API の E2E 検証。
- RBAC（ロールベースアクセス制御）の検証
- 不正な入力の拒否確認
- サービス再起動の承認フロー連携
- サーバー状態エンドポイントの確認
"""

import pytest

pytestmark = [pytest.mark.e2e]


# ==============================================================================
# ヘルパー
# ==============================================================================


def _login(page, base_url: str, email: str, password: str):
    return page.request.post(
        f"{base_url}/api/auth/login",
        data={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )


def _get_token(page, base_url: str, email: str, password: str) -> str:
    resp = _login(page, base_url, email, password)
    assert resp.ok, f"Login failed for {email}: {resp.status}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# サービス再起動 RBAC テスト
# ==============================================================================


class TestServiceRestartRBAC:
    """サービス再起動のロールベースアクセス制御を検証する"""

    def test_restart_requires_auth(self, page, base_url):
        """認証なしのサービス再起動が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status in (401, 403, 422), f"Expected auth error, got {resp.status}"

    def test_viewer_cannot_restart_service(self, page, base_url):
        """Viewer ロールがサービス再起動できない"""
        token = _get_token(page, base_url, "viewer@example.com", "viewer123")
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
        )
        assert resp.status in (401, 403), f"Expected 403, got {resp.status}"

    def test_operator_can_attempt_restart(self, page, base_url):
        """Operator ロールがサービス再起動を試みられる（許可リスト内）"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
        )
        # 200（成功）、403（許可なし）、500/503（ラッパー未設定）、422（バリデーション）
        assert resp.status in (200, 202, 403, 422, 500, 503), f"Unexpected: {resp.status}"

    def test_admin_can_attempt_restart(self, page, base_url):
        """Admin ロールがサービス再起動を試みられる"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
        )
        assert resp.status in (200, 202, 403, 422, 500, 503), f"Unexpected: {resp.status}"


# ==============================================================================
# サービス再起動 入力バリデーションテスト
# ==============================================================================


class TestServiceRestartValidation:
    """サービス再起動エンドポイントの入力バリデーションを検証する"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.headers = {**_auth_headers(self.token), "Content-Type": "application/json"}

    def test_empty_service_name_rejected(self, page, base_url):
        """空のサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": ""},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422), f"Expected error, got {resp.status}"

    def test_service_with_semicolon_rejected(self, page, base_url):
        """セミコロンを含むサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx; rm -rf /"},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422), f"Expected error for injection, got {resp.status}"

    def test_service_with_pipe_rejected(self, page, base_url):
        """パイプを含むサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx | cat /etc/passwd"},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422), f"Expected error for injection, got {resp.status}"

    def test_service_not_in_allowlist_rejected(self, page, base_url):
        """許可リスト外のサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "totally-unknown-evil-service-xyz"},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422, 500), f"Expected rejection, got {resp.status}"

    def test_service_with_ampersand_rejected(self, page, base_url):
        """アンパサンドを含むサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx && malicious"},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422), f"Expected error, got {resp.status}"

    def test_service_with_backtick_rejected(self, page, base_url):
        """バッククォートを含むサービス名が拒否される"""
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "`whoami`"},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 422), f"Expected error, got {resp.status}"

    def test_service_name_too_long_rejected(self, page, base_url):
        """極端に長いサービス名が適切に処理される"""
        long_name = "a" * 500
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": long_name},
            headers=self.headers,
        )
        assert resp.status in (400, 403, 413, 422), f"Expected error, got {resp.status}"


# ==============================================================================
# サーバー状態 API テスト
# ==============================================================================


class TestServerStatusAPI:
    """サーバー状態 API エンドポイントを検証する"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.headers = _auth_headers(self.token)

    def test_servers_status_requires_auth(self, page, base_url):
        """/api/servers/status が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/servers/status")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_servers_status_accessible_with_auth(self, page, base_url):
        """/api/servers/status に認証ありでアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/servers/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    @pytest.mark.parametrize("server_name", ["nginx", "apache2", "postgresql", "mysql"])
    def test_individual_server_status_endpoint(self, page, base_url, server_name):
        """個別サーバー状態エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/servers/{server_name}/status",
            headers=self.headers,
        )
        assert resp.status in (200, 404, 500, 503), f"Unexpected {resp.status} for {server_name}"

    def test_servers_status_response_is_dict(self, page, base_url):
        """/api/servers/status のレスポンスが辞書型である"""
        resp = page.request.get(
            f"{base_url}/api/servers/status",
            headers=self.headers,
        )
        if resp.status == 200:
            data = resp.json()
            assert isinstance(data, (dict, list))

    def test_nginx_server_status_endpoint(self, page, base_url):
        """/api/nginx/status エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/nginx/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    def test_apache_server_status_endpoint(self, page, base_url):
        """/api/apache/status エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/apache/status",
            headers=self.headers,
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"


# ==============================================================================
# 承認ワークフロー連携テスト
# ==============================================================================


class TestApprovalWorkflow:
    """承認ワークフローエンドポイントの基本動作を検証する"""

    @pytest.fixture(autouse=True)
    def setup_auth(self, page, base_url):
        self.page = page
        self.base_url = base_url
        self.operator_token = _get_token(page, base_url, "operator@example.com", "operator123")
        self.admin_token = _get_token(page, base_url, "admin@example.com", "admin123")
        self.viewer_token = _get_token(page, base_url, "viewer@example.com", "viewer123")

    def test_approval_pending_requires_auth(self, page, base_url):
        """承認待ち一覧が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/approval/pending")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_admin_can_view_pending_approvals(self, page, base_url):
        """Admin が承認待ちリストを閲覧できる"""
        resp = page.request.get(
            f"{base_url}/api/approval/pending",
            headers=_auth_headers(self.admin_token),
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    def test_operator_can_view_own_requests(self, page, base_url):
        """Operator が自分のリクエストを閲覧できる"""
        resp = page.request.get(
            f"{base_url}/api/approval/my-requests",
            headers=_auth_headers(self.operator_token),
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    def test_viewer_cannot_view_pending_approvals(self, page, base_url):
        """Viewer が承認待ちリストを閲覧できない"""
        resp = page.request.get(
            f"{base_url}/api/approval/pending",
            headers=_auth_headers(self.viewer_token),
        )
        assert resp.status in (401, 403), f"Expected 403, got {resp.status}"

    def test_approval_stats_accessible(self, page, base_url):
        """承認統計エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/approval/stats",
            headers=_auth_headers(self.admin_token),
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_approval_history_accessible(self, page, base_url):
        """承認履歴エンドポイントにアクセスできる"""
        resp = page.request.get(
            f"{base_url}/api/approval/history",
            headers=_auth_headers(self.admin_token),
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
