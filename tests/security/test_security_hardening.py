"""
Security Hardening Tests

Production環境のセキュリティ強化機能をテスト
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.audit_log import AuditLog
from backend.core.config import Settings, load_config


class TestProductionCORS:
    """Production CORS設定のテスト"""

    def test_production_cors_not_wildcard(self, tmp_path):
        """Production設定にワイルドカードCORSが含まれないこと"""
        project_root = Path(__file__).parent.parent.parent
        prod_config_file = project_root / "config" / "prod.json"

        # prod.json が存在することを確認
        assert prod_config_file.exists(), "prod.json not found"

        # 設定を読み込み
        with open(prod_config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # CORS設定が存在することを確認
        assert "cors_origins" in config_data, "cors_origins not defined in prod.json"

        # ワイルドカードが含まれないことを確認
        cors_origins = config_data["cors_origins"]
        assert "*" not in cors_origins, "Wildcard (*) CORS origin found in production config"

        # 明示的なドメインが設定されていることを確認
        assert len(cors_origins) > 0, "No CORS origins configured in prod.json"
        for origin in cors_origins:
            assert origin.startswith("https://"), f"Non-HTTPS origin found: {origin}"

    @patch.dict(os.environ, {"ENVIRONMENT": "development"})
    def test_development_cors_allows_wildcard(self):
        """開発環境ではワイルドカードCORSが許可されること"""
        settings = Settings()
        assert "*" in settings.cors_origins, "Wildcard should be allowed in development"

    @patch.dict(os.environ, {"ENVIRONMENT": "production"})
    def test_production_cors_default_empty(self):
        """Production環境のデフォルトCORS設定が空であること"""
        settings = Settings()
        # デフォルトは空配列（prod.jsonで明示的に設定が必要）
        assert settings.cors_origins == [], "Production CORS default should be empty"


class TestJWTSecretValidation:
    """JWT秘密鍵の起動時検証テスト"""

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    async def test_production_startup_fails_with_default_jwt_secret(self, mock_settings):
        """Production起動時にデフォルトのJWT秘密鍵で失敗すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "change-this-in-production"
        mock_settings.security.require_https = True
        mock_settings.features.debug_mode = False
        mock_settings.features.api_docs_enabled = False
        mock_settings.cors_origins = ["https://example.com"]

        # 起動時検証が失敗することを確認
        with pytest.raises(RuntimeError, match="JWT_SECRET not configured"):
            await validate_production_config()

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    async def test_production_startup_fails_without_https(self, mock_settings):
        """Production起動時にHTTPS無効で失敗すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "secure-production-secret-key"
        mock_settings.security.require_https = False
        mock_settings.features.debug_mode = False
        mock_settings.features.api_docs_enabled = False
        mock_settings.cors_origins = ["https://example.com"]

        # 起動時検証が失敗することを確認
        with pytest.raises(RuntimeError, match="HTTPS must be required"):
            await validate_production_config()

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    async def test_production_startup_fails_with_debug_mode(self, mock_settings):
        """Production起動時にデバッグモード有効で失敗すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "secure-production-secret-key"
        mock_settings.security.require_https = True
        mock_settings.features.debug_mode = True
        mock_settings.features.api_docs_enabled = False
        mock_settings.cors_origins = ["https://example.com"]

        # 起動時検証が失敗することを確認
        with pytest.raises(RuntimeError, match="Debug mode must be disabled"):
            await validate_production_config()

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    async def test_production_startup_fails_with_wildcard_cors(self, mock_settings):
        """Production起動時にワイルドカードCORSで失敗すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "secure-production-secret-key"
        mock_settings.security.require_https = True
        mock_settings.features.debug_mode = False
        mock_settings.features.api_docs_enabled = False
        mock_settings.cors_origins = ["https://example.com", "*"]

        # 起動時検証が失敗することを確認
        with pytest.raises(RuntimeError, match="Wildcard CORS origin"):
            await validate_production_config()

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    @patch("backend.api.main.logger")
    async def test_production_startup_warns_with_api_docs(
        self, mock_logger, mock_settings
    ):
        """Production起動時にAPIドキュメント有効で警告すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "secure-production-secret-key"
        mock_settings.security.require_https = True
        mock_settings.features.debug_mode = False
        mock_settings.features.api_docs_enabled = True
        mock_settings.cors_origins = ["https://example.com"]

        # 警告は出るが起動は成功
        await validate_production_config()

        # 警告ログが出力されていることを確認
        mock_logger.warning.assert_called_once()
        assert "API docs are enabled" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    @patch("backend.api.main.settings")
    async def test_production_startup_success_with_valid_config(self, mock_settings):
        """Production起動時に正しい設定で成功すること"""
        from backend.api.main import validate_production_config

        # Production環境のモック設定
        mock_settings.environment = "production"
        mock_settings.jwt_secret_key = "secure-production-secret-key"
        mock_settings.security.require_https = True
        mock_settings.features.debug_mode = False
        mock_settings.features.api_docs_enabled = False
        mock_settings.cors_origins = ["https://example.com"]

        # 起動時検証が成功することを確認
        await validate_production_config()  # 例外が発生しないことを確認


class TestAuditLogRBAC:
    """監査ログRBACのテスト"""

    def test_admin_can_view_all_logs(self, tmp_path):
        """管理者は全ての監査ログを閲覧可能"""
        # テスト用監査ログを作成
        audit_log = AuditLog(log_dir=tmp_path)
        audit_log.record("service_restart", "user1@example.com", "nginx", "success")
        audit_log.record("service_restart", "user2@example.com", "postgresql", "success")

        # Admin は全てのログを閲覧可能
        logs = audit_log.query(user_role="Admin", requesting_user_id="admin@example.com")

        assert len(logs) == 2
        assert logs[0]["user_id"] == "user1@example.com"
        assert logs[1]["user_id"] == "user2@example.com"

    def test_operator_can_only_view_own_logs(self, tmp_path):
        """オペレーターは自分のログのみ閲覧可能"""
        # テスト用監査ログを作成
        audit_log = AuditLog(log_dir=tmp_path)
        audit_log.record("service_restart", "user1@example.com", "nginx", "success")
        audit_log.record("service_restart", "user2@example.com", "postgresql", "success")

        # Operator は自分のログのみ閲覧可能
        logs = audit_log.query(
            user_role="Operator", requesting_user_id="user1@example.com"
        )

        assert len(logs) == 1
        assert logs[0]["user_id"] == "user1@example.com"

    def test_approver_can_only_view_own_logs(self, tmp_path):
        """承認者は自分のログのみ閲覧可能"""
        # テスト用監査ログを作成
        audit_log = AuditLog(log_dir=tmp_path)
        audit_log.record("service_restart", "user1@example.com", "nginx", "success")
        audit_log.record("approval_action", "approver@example.com", "request123", "approved")

        # Approver は自分のログのみ閲覧可能
        logs = audit_log.query(
            user_role="Approver", requesting_user_id="approver@example.com"
        )

        assert len(logs) == 1
        assert logs[0]["user_id"] == "approver@example.com"

    def test_viewer_cannot_access_audit_logs(self, tmp_path):
        """閲覧者は監査ログにアクセス不可"""
        # テスト用監査ログを作成
        audit_log = AuditLog(log_dir=tmp_path)
        audit_log.record("service_restart", "user1@example.com", "nginx", "success")

        # Viewer は監査ログにアクセス不可
        with pytest.raises(PermissionError, match="Viewer role cannot access"):
            audit_log.query(user_role="Viewer", requesting_user_id="viewer@example.com")


# ===================================================================
# セキュリティヘッダーテスト
# ===================================================================


class TestSecurityHeaders:
    """セキュリティヘッダーの付与テスト"""

    def test_x_content_type_options_header(self, test_client, auth_headers):
        """X-Content-Type-Options: nosniff ヘッダーが付与される"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert "x-content-type-options" in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_x_frame_options_header(self, test_client, auth_headers):
        """X-Frame-Options: DENY ヘッダーが付与される"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert "x-frame-options" in response.headers
        assert response.headers["x-frame-options"] == "DENY"

    def test_x_xss_protection_header(self, test_client, auth_headers):
        """X-XSS-Protection ヘッダーが付与される"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert "x-xss-protection" in response.headers
        assert response.headers["x-xss-protection"] == "1; mode=block"

    def test_referrer_policy_header(self, test_client, auth_headers):
        """Referrer-Policy ヘッダーが付与される"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert "referrer-policy" in response.headers
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    def test_content_security_policy_header(self, test_client, auth_headers):
        """Content-Security-Policy ヘッダーが付与される"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert "content-security-policy" in response.headers
        csp = response.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "connect-src 'self'" in csp

    def test_security_headers_on_error_response(self, test_client):
        """エラーレスポンスにもセキュリティヘッダーが付与される"""
        response = test_client.get("/api/system/status")  # 認証なし
        # 403/401 でもセキュリティヘッダーは付与されること
        assert "x-frame-options" in response.headers


# ===================================================================
# レート制限テスト
# ===================================================================


class TestRateLimiting:
    """APIレート制限テスト"""

    @pytest.fixture(autouse=True)
    def clear_rate_limits(self):
        """各テスト前にレート制限ストレージをリセット"""
        from backend.api.main import _clear_rate_limit_state
        _clear_rate_limit_state()
        yield
        _clear_rate_limit_state()

    def test_normal_requests_pass(self, test_client, auth_headers):
        """通常のリクエスト数（60以下）は通過する"""
        response = test_client.get("/api/system/status", headers=auth_headers)
        assert response.status_code != 429

    def test_login_endpoint_accepts_normal_attempts(self, test_client):
        """通常回数のログイン試行は通過する"""
        resp = test_client.post(
            "/api/auth/login",
            json={"username": "admin@example.com", "password": "admin"},
        )
        # 認証成功/失敗にかかわらず 429 でないこと
        assert resp.status_code != 429
