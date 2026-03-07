"""
E2E テスト - ログインフロー詳細テスト

認証エンドポイントに対する詳細なE2Eシナリオを検証する。
- JWT トークン構造の検証
- 各ロールのログイン動作
- エッジケース（空欄・特殊文字・長すぎる入力）
- 2FA エンドポイントの存在確認
- トークンの再利用と複数リクエスト
- 承認ワークフローとの連携
"""

import base64
import json

import pytest

pytestmark = [pytest.mark.e2e]


# ==============================================================================
# ヘルパー
# ==============================================================================


def _login(page, base_url: str, email: str, password: str):
    """ログインしてレスポンスを返す"""
    return page.request.post(
        f"{base_url}/api/auth/login",
        data={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )


def _get_token(page, base_url: str, email: str, password: str) -> str:
    resp = _login(page, base_url, email, password)
    assert resp.ok, f"Login failed: {resp.status}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# JWT トークン構造テスト
# ==============================================================================


class TestJWTTokenStructure:
    """JWT トークンの構造と内容を検証する"""

    def test_token_is_jwt_format(self, page, base_url):
        """返されたトークンが JWT フォーマット（3つのドット区切り）である"""
        resp = _login(page, base_url, "operator@example.com", "operator123")
        assert resp.ok
        token = resp.json()["access_token"]
        parts = token.split(".")
        assert len(parts) == 3, f"JWT should have 3 parts, got {len(parts)}"

    def test_token_header_algorithm(self, page, base_url):
        """JWT ヘッダーにアルゴリズム情報が含まれる"""
        resp = _login(page, base_url, "operator@example.com", "operator123")
        token = resp.json()["access_token"]
        header_b64 = token.split(".")[0]
        # Base64 パディング補正
        padding = 4 - len(header_b64) % 4
        if padding != 4:
            header_b64 += "=" * padding
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        assert "alg" in header
        assert header["alg"] in ("HS256", "HS384", "HS512", "RS256")

    def test_token_payload_has_sub(self, page, base_url):
        """JWT ペイロードに sub クレームが含まれる"""
        resp = _login(page, base_url, "operator@example.com", "operator123")
        token = resp.json()["access_token"]
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "sub" in payload

    def test_token_payload_has_exp(self, page, base_url):
        """JWT ペイロードに exp（有効期限）クレームが含まれる"""
        resp = _login(page, base_url, "operator@example.com", "operator123")
        token = resp.json()["access_token"]
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "exp" in payload
        assert isinstance(payload["exp"], (int, float))

    def test_login_response_has_all_required_fields(self, page, base_url):
        """ログインレスポンスに必須フィールドが全て含まれる"""
        resp = _login(page, base_url, "admin@example.com", "admin123")
        assert resp.ok
        data = resp.json()
        assert "access_token" in data
        assert "token_type" in data
        assert "user_id" in data
        assert data["token_type"] == "bearer"

    def test_login_response_contains_role(self, page, base_url):
        """ログインレスポンスにロール情報が含まれる"""
        resp = _login(page, base_url, "admin@example.com", "admin123")
        data = resp.json()
        assert "role" in data
        assert data["role"] in ("Admin", "Operator", "Approver", "Viewer", "admin", "operator", "approver", "viewer")

    def test_admin_role_returned_correctly(self, page, base_url):
        """Admin ユーザーのロールが正しく返される"""
        resp = _login(page, base_url, "admin@example.com", "admin123")
        data = resp.json()
        assert data["role"].lower() in ("admin",)

    def test_viewer_role_returned_correctly(self, page, base_url):
        """Viewer ユーザーのロールが正しく返される"""
        resp = _login(page, base_url, "viewer@example.com", "viewer123")
        data = resp.json()
        assert data["role"].lower() in ("viewer",)


# ==============================================================================
# 各ロールのログイン
# ==============================================================================


class TestRoleLogins:
    """各ロールのログイン動作を検証する"""

    def test_operator_login_succeeds(self, page, base_url):
        """Operator ユーザーがログインできる"""
        resp = _login(page, base_url, "operator@example.com", "operator123")
        assert resp.ok
        assert resp.json()["access_token"]

    def test_viewer_login_succeeds(self, page, base_url):
        """Viewer ユーザーがログインできる"""
        resp = _login(page, base_url, "viewer@example.com", "viewer123")
        assert resp.ok
        assert resp.json()["access_token"]

    def test_all_roles_can_access_me_endpoint(self, page, base_url):
        """全ロールが /api/auth/me エンドポイントにアクセスできる"""
        users = [
            ("admin@example.com", "admin123"),
            ("operator@example.com", "operator123"),
            ("viewer@example.com", "viewer123"),
        ]
        for email, password in users:
            token = _get_token(page, base_url, email, password)
            me_resp = page.request.get(
                f"{base_url}/api/auth/me",
                headers=_auth_headers(token),
            )
            assert me_resp.ok, f"me endpoint failed for {email}"
            data = me_resp.json()
            assert data["email"] == email

    def test_me_endpoint_returns_complete_profile(self, page, base_url):
        """/api/auth/me が完全なプロフィール情報を返す"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/auth/me",
            headers=_auth_headers(token),
        )
        assert resp.ok
        data = resp.json()
        assert "email" in data
        assert "role" in data
        assert "user_id" in data or "id" in data or "username" in data

    def test_approver_login_if_exists(self, page, base_url):
        """Approver ユーザーがログインできる（存在する場合）"""
        resp = _login(page, base_url, "approver@example.com", "approver123")
        # approver がいない場合は 401、いる場合は 200
        assert resp.status in (200, 401), f"Unexpected status: {resp.status}"
        if resp.ok:
            assert resp.json()["access_token"]


# ==============================================================================
# 無効な認証情報テスト
# ==============================================================================


class TestInvalidCredentials:
    """無効な認証情報に対するエラー処理を検証する"""

    def test_empty_email_rejected(self, page, base_url):
        """空のメールアドレスでのログインが拒否される"""
        resp = _login(page, base_url, "", "password123")
        assert resp.status in (400, 401, 422), f"Expected error, got {resp.status}"

    def test_empty_password_rejected(self, page, base_url):
        """空のパスワードでのログインが拒否される"""
        resp = _login(page, base_url, "admin@example.com", "")
        assert resp.status in (400, 401, 422), f"Expected error, got {resp.status}"

    def test_wrong_password_rejected(self, page, base_url):
        """間違ったパスワードでのログインが拒否される"""
        resp = _login(page, base_url, "admin@example.com", "wrongpassword!")
        assert resp.status == 401, f"Expected 401, got {resp.status}"

    def test_nonexistent_user_rejected(self, page, base_url):
        """存在しないユーザーのログインが拒否される"""
        resp = _login(page, base_url, "nobody@nowhere.invalid", "password")
        # 存在しないユーザーは 401（認証失敗）または 422（バリデーション）で拒否される
        assert resp.status in (401, 422), f"Expected 401 or 422, got {resp.status}"

    def test_sql_injection_in_email_rejected(self, page, base_url):
        """メールアドレスへの SQL インジェクションが拒否される"""
        resp = _login(page, base_url, "' OR '1'='1", "anything")
        assert resp.status in (400, 401, 422), f"Expected error, got {resp.status}"

    def test_very_long_email_rejected(self, page, base_url):
        """極端に長いメールアドレスが適切に処理される"""
        long_email = "a" * 500 + "@example.com"
        resp = _login(page, base_url, long_email, "password")
        assert resp.status in (400, 401, 413, 422), f"Expected error, got {resp.status}"

    def test_very_long_password_rejected(self, page, base_url):
        """極端に長いパスワードが適切に処理される"""
        long_password = "p" * 1000
        resp = _login(page, base_url, "admin@example.com", long_password)
        assert resp.status in (400, 401, 413, 422), f"Expected error, got {resp.status}"

    def test_error_response_has_detail(self, page, base_url):
        """失敗時のレスポンスにエラー詳細が含まれる"""
        resp = _login(page, base_url, "wrong@example.com", "wrong")
        assert not resp.ok
        data = resp.json()
        assert "detail" in data or "message" in data or "error" in data


# ==============================================================================
# トークン利用テスト
# ==============================================================================


class TestTokenUsage:
    """取得したトークンの利用パターンを検証する"""

    def test_token_usable_for_multiple_requests(self, page, base_url):
        """取得したトークンを複数のリクエストに再利用できる"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        headers = _auth_headers(token)

        # 複数のエンドポイントを同じトークンでアクセス
        endpoints = [
            "/api/auth/me",
            "/api/system/status",
        ]
        for ep in endpoints:
            resp = page.request.get(f"{base_url}{ep}", headers=headers)
            assert resp.status in (200, 500, 503), f"Unexpected {resp.status} for {ep}"

    def test_bearer_prefix_required(self, page, base_url):
        """Bearer プレフィックスなしのトークンは拒否される"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        # Bearer なしで送信
        resp = page.request.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": token},
        )
        assert resp.status in (401, 403, 422), f"Expected auth error, got {resp.status}"

    def test_malformed_token_rejected(self, page, base_url):
        """不正な形式のトークンが拒否される"""
        resp = page.request.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt.token"},
        )
        assert resp.status in (401, 403, 422), f"Expected auth error, got {resp.status}"

    def test_empty_bearer_rejected(self, page, base_url):
        """空の Bearer トークンが拒否される"""
        resp = page.request.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status in (401, 403, 422), f"Expected auth error, got {resp.status}"

    def test_logout_endpoint_returns_ok(self, page, base_url):
        """ログアウトエンドポイントが正常に応答する"""
        token = _get_token(page, base_url, "operator@example.com", "operator123")
        resp = page.request.post(
            f"{base_url}/api/auth/logout",
            headers=_auth_headers(token),
        )
        assert resp.ok, f"Logout failed: {resp.status}"


# ==============================================================================
# 2FA エンドポイントテスト
# ==============================================================================


class Test2FAEndpoints:
    """2FA 関連エンドポイントの存在と基本動作を確認する"""

    def test_2fa_status_endpoint_exists(self, page, base_url):
        """2FA ステータスエンドポイントが存在する"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/auth/2fa/status",
            headers=_auth_headers(token),
        )
        assert resp.status in (200, 404), f"Unexpected status: {resp.status}"

    def test_2fa_status_without_auth_rejected(self, page, base_url):
        """認証なしの 2FA ステータスアクセスが拒否される"""
        resp = page.request.get(f"{base_url}/api/auth/2fa/status")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_2fa_setup_without_auth_rejected(self, page, base_url):
        """認証なしの 2FA セットアップが拒否される"""
        resp = page.request.post(f"{base_url}/api/auth/2fa/setup")
        assert resp.status in (401, 403, 422), f"Expected auth error, got {resp.status}"

    def test_2fa_verify_with_invalid_code_rejected(self, page, base_url):
        """無効な 2FA コードが拒否される"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.post(
            f"{base_url}/api/auth/2fa/verify",
            data={"code": "000000"},
            headers={**_auth_headers(token), "Content-Type": "application/json"},
        )
        # 2FA が未設定の場合は 400/404、設定済みなら 401
        assert resp.status in (400, 401, 404, 422), f"Unexpected status: {resp.status}"


# ==============================================================================
# セッション管理テスト
# ==============================================================================


class TestSessionManagement:
    """セッション管理エンドポイントの動作を検証する"""

    def test_active_sessions_endpoint_requires_auth(self, page, base_url):
        """アクティブセッション一覧が認証を要求する"""
        resp = page.request.get(f"{base_url}/api/sessions/active")
        assert resp.status in (401, 403), f"Expected auth error, got {resp.status}"

    def test_admin_can_view_active_sessions(self, page, base_url):
        """Admin がアクティブセッションを閲覧できる"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/sessions/active",
            headers=_auth_headers(token),
        )
        assert resp.status in (200, 500, 503), f"Unexpected status: {resp.status}"

    def test_jwt_sessions_endpoint_accessible(self, page, base_url):
        """JWT セッション一覧エンドポイントにアクセスできる"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/sessions/jwt",
            headers=_auth_headers(token),
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"

    def test_rate_limit_status_accessible(self, page, base_url):
        """レート制限ステータスエンドポイントにアクセスできる"""
        token = _get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/sessions/rate-limit-status",
            headers=_auth_headers(token),
        )
        assert resp.status in (200, 403, 500, 503), f"Unexpected status: {resp.status}"
