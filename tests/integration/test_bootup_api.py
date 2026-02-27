"""
Bootup/Shutdown 管理モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）

テストケース数: 20件
- 正常系: 起動状態取得、サービス一覧、有効化/無効化、シャットダウン/再起動
- 異常系: 権限不足、未認証、allowlist外サービス、無効な遅延値
- セキュリティ: インジェクション攻撃、allowlist外拒否
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SAMPLE_BOOTUP_STATUS = {
    "status": "ok",
    "data": {
        "default_target": "multi-user.target",
        "uptime": "up 5 days, 3 hours, 42 minutes",
        "last_boot": "2026-02-22 09:15",
        "failed_units": 0,
    },
}

SAMPLE_BOOTUP_SERVICES = {
    "status": "ok",
    "data": {
        "services": [
            {"unit": "nginx", "state": "enabled", "vendor_preset": "enabled"},
            {"unit": "postgresql", "state": "enabled", "vendor_preset": "disabled"},
            {"unit": "redis", "state": "disabled", "vendor_preset": "disabled"},
            {"unit": "ssh", "state": "enabled", "vendor_preset": "enabled"},
        ]
    },
}

SAMPLE_ENABLE_RESULT = {
    "status": "ok",
    "data": "Service 'nginx' enabled at boot",
}

SAMPLE_DISABLE_RESULT = {
    "status": "ok",
    "data": "Service 'redis' disabled at boot",
}

SAMPLE_SHUTDOWN_RESULT = {
    "status": "ok",
    "data": "System shutdown scheduled at +1",
}

SAMPLE_REBOOT_RESULT = {
    "status": "ok",
    "data": "System reboot scheduled at +5",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestBootupStatusAPI:
    """GET /api/bootup/status のテスト"""

    def test_get_bootup_status_viewer(self, test_client, viewer_token):
        """TC001: Viewer ロールで起動状態取得成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_status",
            return_value=SAMPLE_BOOTUP_STATUS,
        ):
            resp = test_client.get(
                "/api/bootup/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "data" in data

    def test_get_bootup_status_operator(self, test_client, auth_headers):
        """TC002: Operator ロールで起動状態取得成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_status",
            return_value=SAMPLE_BOOTUP_STATUS,
        ):
            resp = test_client.get("/api/bootup/status", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_bootup_status_admin(self, test_client, admin_token):
        """TC003: Admin ロールで起動状態取得成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_status",
            return_value=SAMPLE_BOOTUP_STATUS,
        ):
            resp = test_client.get(
                "/api/bootup/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200

    def test_get_bootup_status_unauthorized(self, test_client):
        """TC004: 未認証でアクセス拒否"""
        resp = test_client.get("/api/bootup/status")
        assert resp.status_code in (401, 403)

    def test_get_bootup_status_response_structure(self, test_client, auth_headers):
        """TC005: レスポンス構造確認"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_status",
            return_value=SAMPLE_BOOTUP_STATUS,
        ):
            resp = test_client.get("/api/bootup/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "default_target" in data["data"]
        assert "uptime" in data["data"]


class TestBootupServicesAPI:
    """GET /api/bootup/services のテスト"""

    def test_get_bootup_services_success(self, test_client, auth_headers):
        """TC006: 起動時サービス一覧取得成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_services",
            return_value=SAMPLE_BOOTUP_SERVICES,
        ):
            resp = test_client.get("/api/bootup/services", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "services" in data["data"]

    def test_get_bootup_services_viewer(self, test_client, viewer_token):
        """TC007: Viewer ロールでサービス一覧取得可能"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_services",
            return_value=SAMPLE_BOOTUP_SERVICES,
        ):
            resp = test_client.get(
                "/api/bootup/services",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_get_bootup_services_unauthorized(self, test_client):
        """TC008: 未認証でアクセス拒否"""
        resp = test_client.get("/api/bootup/services")
        assert resp.status_code in (401, 403)


class TestBootupEnableAPI:
    """POST /api/bootup/enable のテスト"""

    def test_enable_service_admin_success(self, test_client, admin_token):
        """TC009: Admin ロールでサービス有効化成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.enable_service_at_boot",
            return_value=SAMPLE_ENABLE_RESULT,
        ):
            resp = test_client.post(
                "/api/bootup/enable",
                json={"service": "nginx", "reason": "nginx を起動時に有効化する"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "message" in data

    def test_enable_service_forbidden_operator(self, test_client, auth_headers):
        """TC010: Operator ロールはサービス有効化不可（write:bootup 権限なし）"""
        resp = test_client.post(
            "/api/bootup/enable",
            json={"service": "nginx", "reason": "テスト"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_enable_service_forbidden_viewer(self, test_client, viewer_token):
        """TC011: Viewer ロールはサービス有効化不可"""
        resp = test_client.post(
            "/api/bootup/enable",
            json={"service": "nginx", "reason": "テスト"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_enable_service_not_in_allowlist(self, test_client, admin_token):
        """TC012: allowlist 外のサービスは拒否"""
        resp = test_client.post(
            "/api/bootup/enable",
            json={"service": "unknown-service", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "許可リスト" in data["message"]

    def test_enable_service_injection_rejected(self, test_client, admin_token):
        """TC013: インジェクション攻撃は拒否"""
        resp = test_client.post(
            "/api/bootup/enable",
            json={"service": "nginx; rm -rf /", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (400, 422)

    def test_enable_service_unauthorized(self, test_client):
        """TC014: 未認証は拒否"""
        resp = test_client.post(
            "/api/bootup/enable",
            json={"service": "nginx", "reason": "テスト"},
        )
        assert resp.status_code in (401, 403)


class TestBootupActionAPI:
    """POST /api/bootup/action のテスト"""

    def test_schedule_shutdown_admin_success(self, test_client, admin_token):
        """TC015: Admin ロールでシャットダウンスケジュール成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.schedule_shutdown",
            return_value=SAMPLE_SHUTDOWN_RESULT,
        ):
            resp = test_client.post(
                "/api/bootup/action",
                json={"action": "shutdown", "delay": "+1", "reason": "定期メンテナンスのためシャットダウン"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["action"] == "shutdown"
        assert data["delay"] == "+1"

    def test_schedule_reboot_admin_success(self, test_client, admin_token):
        """TC016: Admin ロールで再起動スケジュール成功"""
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.schedule_reboot",
            return_value=SAMPLE_REBOOT_RESULT,
        ):
            resp = test_client.post(
                "/api/bootup/action",
                json={"action": "reboot", "delay": "+5", "reason": "カーネルアップデート適用のため再起動"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["action"] == "reboot"

    def test_schedule_shutdown_forbidden_operator(self, test_client, auth_headers):
        """TC017: Operator ロールはシャットダウン不可"""
        resp = test_client.post(
            "/api/bootup/action",
            json={"action": "shutdown", "delay": "+1", "reason": "テスト"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_schedule_shutdown_invalid_delay(self, test_client, admin_token):
        """TC018: 無効な遅延値は拒否"""
        resp = test_client.post(
            "/api/bootup/action",
            json={"action": "shutdown", "delay": "+999999", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "遅延指定" in data["message"]

    def test_schedule_shutdown_injection_in_delay(self, test_client, admin_token):
        """TC019: 遅延指定へのインジェクション攻撃は拒否"""
        resp = test_client.post(
            "/api/bootup/action",
            json={"action": "shutdown", "delay": "+1; rm -rf /", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_schedule_action_unauthorized(self, test_client):
        """TC020: 未認証は拒否"""
        resp = test_client.post(
            "/api/bootup/action",
            json={"action": "shutdown", "delay": "+1", "reason": "テスト"},
        )
        assert resp.status_code in (401, 403)


class TestBootupDisableAPI:
    """bootup disable エンドポイントの追加テスト（カバレッジ向上）"""

    def test_disable_service_admin_success(self, test_client, admin_token):
        """TC021: Admin がサービス無効化を実行"""
        from backend.api.routes.bootup import ALLOWED_BOOTUP_SERVICES
        service = next(iter(ALLOWED_BOOTUP_SERVICES))
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.disable_service_at_boot",
            return_value={"status": "ok", "service": service},
        ):
            resp = test_client.post(
                "/api/bootup/disable",
                json={"service": service, "reason": "テスト"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert service in data.get("message", "")

    def test_disable_service_not_in_allowlist(self, test_client, admin_token):
        """TC022: allowlist 外のサービスを無効化しようとすると 400"""
        resp = test_client.post(
            "/api/bootup/disable",
            json={"service": "unknown-service-xyz", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_disable_service_injection_rejected(self, test_client, admin_token):
        """TC023: サービス名にインジェクション文字列を拒否"""
        resp = test_client.post(
            "/api/bootup/disable",
            json={"service": "nginx; rm -rf /", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_disable_service_wrapper_error(self, test_client, admin_token):
        """TC024: SudoWrapperError 発生時 500"""
        from backend.api.routes.bootup import ALLOWED_BOOTUP_SERVICES
        from backend.core.sudo_wrapper import SudoWrapperError
        service = next(iter(ALLOWED_BOOTUP_SERVICES))
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.disable_service_at_boot",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.post(
                "/api/bootup/disable",
                json={"service": service, "reason": "テスト"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_disable_service_forbidden_operator(self, test_client, auth_headers):
        """TC025: Operator ロールはサービス無効化不可"""
        resp = test_client.post(
            "/api/bootup/disable",
            json={"service": "nginx", "reason": "テスト"},
            headers=auth_headers,
        )
        assert resp.status_code == 403


class TestBootupStatusWrapperError:
    """bootup status のエラーパステスト"""

    def test_get_bootup_status_wrapper_error(self, test_client, admin_token):
        """TC026: ステータス取得で SudoWrapperError 発生時 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_status",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/bootup/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_get_bootup_services_wrapper_error(self, test_client, admin_token):
        """TC027: サービス一覧で SudoWrapperError 発生時 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.get_bootup_services",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/bootup/services",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_enable_service_wrapper_error(self, test_client, admin_token):
        """TC028: サービス有効化で SudoWrapperError 発生時 500"""
        from backend.api.routes.bootup import ALLOWED_BOOTUP_SERVICES
        from backend.core.sudo_wrapper import SudoWrapperError
        service = next(iter(ALLOWED_BOOTUP_SERVICES))
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.enable_service_at_boot",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.post(
                "/api/bootup/enable",
                json={"service": service, "reason": "テスト"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_schedule_action_wrapper_error(self, test_client, admin_token):
        """TC029: シャットダウンスケジュールで SudoWrapperError 発生時 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.bootup.sudo_wrapper.schedule_shutdown",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.post(
                "/api/bootup/action",
                json={"action": "shutdown", "delay": "+1", "reason": "テスト"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500
