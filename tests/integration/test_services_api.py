"""
Services API - 統合テスト

POST /api/services/restart エンドポイントの統合テスト
（sudo_wrapper をモックして、本番環境依存なしに実行）
"""

from unittest.mock import patch

import pytest


# ===================================================================
# テスト用サンプルデータ
# ===================================================================

RESTART_SUCCESS = {
    "status": "success",
    "service": "nginx",
    "before": "active",
    "after": "active",
}

RESTART_DENIED = {
    "status": "error",
    "message": "Service 'unknown-service' is not in the allowed list",
}

RESTART_ERROR = {
    "status": "error",
    "message": "systemctl restart failed: exit code 1",
}


# ===================================================================
# 正常系テスト
# ===================================================================


class TestServiceRestartSuccess:
    """POST /api/services/restart - 正常系テスト"""

    def test_restart_nginx_as_operator(self, test_client, operator_headers):
        """operator権限でnginxを再起動できる"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_SUCCESS
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "nginx"

    def test_restart_nginx_as_admin(self, test_client, admin_headers):
        """admin権限でnginxを再起動できる"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_SUCCESS
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_restart_returns_before_after_status(self, test_client, admin_headers):
        """再起動前後のサービス状態を返す"""
        mock_result = {"status": "success", "service": "postgresql", "before": "active", "after": "active"}
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = mock_result
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "postgresql"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "before" in data
        assert "after" in data
        assert data["service"] == "postgresql"

    def test_restart_allowed_services(self, test_client, admin_headers):
        """許可されたサービス名（英数字・ハイフン・アンダースコア）で再起動できる"""
        for service_name in ["nginx", "apache2", "postgresql", "redis-server", "my_service"]:
            with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
                mock_result = {"status": "success", "service": service_name, "before": "active", "after": "active"}
                mock_wrapper.restart_service.return_value = mock_result
                resp = test_client.post(
                    "/api/services/restart",
                    json={"service_name": service_name},
                    headers=admin_headers,
                )
            assert resp.status_code == 200, f"Failed for service: {service_name}"


# ===================================================================
# 権限テスト
# ===================================================================


class TestServiceRestartPermissions:
    """POST /api/services/restart - 権限テスト"""

    def test_restart_requires_auth(self, test_client):
        """認証なしは 403 を返す（本システムはHTTP403で未認証を表現）"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx"},
        )
        assert resp.status_code == 403
        assert resp.json()["status"] == "error"

    def test_viewer_cannot_restart(self, test_client, viewer_headers):
        """viewer権限では再起動できない（403）"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_operator_can_restart(self, test_client, operator_headers):
        """operator権限では再起動できる"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_SUCCESS
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=operator_headers,
            )
        assert resp.status_code == 200

    def test_admin_can_restart(self, test_client, admin_headers):
        """admin権限では再起動できる"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_SUCCESS
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# 入力バリデーションテスト
# ===================================================================


class TestServiceRestartValidation:
    """POST /api/services/restart - 入力バリデーションテスト"""

    def test_reject_empty_service_name(self, test_client, admin_headers):
        """空のサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_missing_service_name(self, test_client, admin_headers):
        """service_name フィールドなしは 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_with_semicolon(self, test_client, admin_headers):
        """セミコロン含むサービス名は 422 を返す（シェルインジェクション防止）"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx; rm -rf /"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_with_pipe(self, test_client, admin_headers):
        """パイプ含むサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx | cat /etc/passwd"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_with_ampersand(self, test_client, admin_headers):
        """アンパサンド含むサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx & id"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_with_dollar(self, test_client, admin_headers):
        """ドル記号含むサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx${IFS}restart"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_too_long(self, test_client, admin_headers):
        """65文字を超えるサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "a" * 65},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_reject_service_name_with_space(self, test_client, admin_headers):
        """スペース含むサービス名は 422 を返す"""
        resp = test_client.post(
            "/api/services/restart",
            json={"service_name": "nginx restart"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_accept_max_length_service_name(self, test_client, admin_headers):
        """64文字のサービス名は受け付ける"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            service_name = "a" * 64
            mock_wrapper.restart_service.return_value = {
                "status": "success",
                "service": service_name,
                "before": "active",
                "after": "active",
            }
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": service_name},
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# エラー処理テスト
# ===================================================================


class TestServiceRestartError:
    """POST /api/services/restart - エラー処理テスト"""

    def test_returns_403_when_wrapper_denies(self, test_client, admin_headers):
        """allowlist外のサービスはwrapperがエラーを返し 403 になる"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_DENIED
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "unknown-service"},
                headers=admin_headers,
            )
        assert resp.status_code == 403
        assert "not in the allowed list" in resp.json()["message"]

    def test_returns_500_on_wrapper_exception(self, test_client, admin_headers):
        """sudoラッパー例外時は 500 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.side_effect = SudoWrapperError("systemctl failed")
            resp = test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=admin_headers,
            )
        assert resp.status_code == 500
        assert "Service restart failed" in resp.json()["message"]

    def test_wrapper_called_with_correct_service(self, test_client, admin_headers):
        """wrapperが正しいサービス名で呼び出されることを確認"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            mock_wrapper.restart_service.return_value = RESTART_SUCCESS
            test_client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=admin_headers,
            )
        mock_wrapper.restart_service.assert_called_once_with("nginx")

    def test_audit_log_recorded_on_success(self, test_client, admin_headers):
        """成功時に監査ログが記録される（副作用確認）"""
        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            with patch("backend.api.routes.services.audit_log") as mock_audit:
                mock_wrapper.restart_service.return_value = RESTART_SUCCESS
                test_client.post(
                    "/api/services/restart",
                    json={"service_name": "nginx"},
                    headers=admin_headers,
                )
        # 少なくとも2回呼ばれる（attempt + success）
        assert mock_audit.record.call_count >= 2

    def test_audit_log_recorded_on_failure(self, test_client, admin_headers):
        """失敗時に監査ログが記録される"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.services.sudo_wrapper") as mock_wrapper:
            with patch("backend.api.routes.services.audit_log") as mock_audit:
                mock_wrapper.restart_service.side_effect = SudoWrapperError("failed")
                test_client.post(
                    "/api/services/restart",
                    json={"service_name": "nginx"},
                    headers=admin_headers,
                )
        assert mock_audit.record.call_count >= 2  # attempt + failure
