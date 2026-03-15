"""
通知管理 API - 統合テスト

/api/notifications エンドポイントの統合テスト（20件以上）
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ==============================================================================
# 認証なし 403 テスト (3件)
# ==============================================================================


class TestNotificationsUnauthorized:
    """認証なしアクセスは 403 を返すこと"""

    def test_settings_no_auth(self, test_client):
        """GET /api/notifications/settings — 認証なしは 403"""
        response = test_client.get("/api/notifications/settings")
        assert response.status_code == 403

    def test_webhooks_no_auth(self, test_client):
        """GET /api/notifications/webhooks — 認証なしは 403"""
        response = test_client.get("/api/notifications/webhooks")
        assert response.status_code == 403

    def test_history_no_auth(self, test_client):
        """GET /api/notifications/history — 認証なしは 403"""
        response = test_client.get("/api/notifications/history")
        assert response.status_code == 403


# ==============================================================================
# GET /api/notifications/settings テスト (4件)
# ==============================================================================


class TestGetNotificationSettings:
    """GET /api/notifications/settings"""

    @staticmethod
    def _patch_notification_service(monkeypatch, tmp_path):
        """通知サービスをテスト用に差し替えるヘルパー"""
        from backend.core import notification_service as ns_module
        import backend.api.routes.notifications as notif_routes

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        monkeypatch.setattr(notif_routes, "notification_service", svc)
        return svc

    def test_viewer_can_read_settings(self, test_client, viewer_headers, tmp_path, monkeypatch):
        """viewer ロールは設定を取得できること"""
        self._patch_notification_service(monkeypatch, tmp_path)
        response = test_client.get("/api/notifications/settings", headers=viewer_headers)
        assert response.status_code == 200

    def test_admin_can_read_settings(self, test_client, admin_headers, tmp_path, monkeypatch):
        """admin ロールは設定を取得できること"""
        self._patch_notification_service(monkeypatch, tmp_path)
        response = test_client.get("/api/notifications/settings", headers=admin_headers)
        assert response.status_code == 200

    def test_settings_structure(self, test_client, admin_headers, tmp_path, monkeypatch):
        """設定レスポンスに必須キーが含まれること"""
        self._patch_notification_service(monkeypatch, tmp_path)
        response = test_client.get("/api/notifications/settings", headers=admin_headers)
        data = response.json()
        assert data["status"] == "success"
        assert "settings" in data
        s = data["settings"]
        assert "enabled" in s
        assert "slack_webhooks" in s
        assert "discord_webhooks" in s
        assert "generic_webhooks" in s
        assert "notification_levels" in s
        assert "event_types" in s

    def test_settings_no_smtp_password(self, test_client, admin_headers, tmp_path, monkeypatch):
        """smtp_password がレスポンスに含まれないこと（機密情報マスク）"""
        self._patch_notification_service(monkeypatch, tmp_path)
        response = test_client.get("/api/notifications/settings", headers=admin_headers)
        data = response.json()
        assert "smtp_password" not in data.get("settings", {})


# ==============================================================================
# PUT /api/notifications/settings テスト (5件)
# ==============================================================================


class TestUpdateNotificationSettings:
    """PUT /api/notifications/settings"""

    def test_admin_can_update_settings(self, test_client, admin_headers, tmp_path, monkeypatch):
        """admin ロールは設定を更新できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        # routes モジュールのインポート済みインスタンスも差し替える
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {"enabled": False, "notification_levels": ["critical"]}
        response = test_client.put("/api/notifications/settings", json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["settings"]["enabled"] is False
        assert data["settings"]["notification_levels"] == ["critical"]

    def test_viewer_cannot_update_settings(self, test_client, viewer_headers):
        """viewer ロールは設定を更新できないこと (403)"""
        payload = {"enabled": False}
        response = test_client.put("/api/notifications/settings", json=payload, headers=viewer_headers)
        assert response.status_code == 403

    def test_operator_cannot_update_settings(self, test_client, operator_headers):
        """operator ロールは設定を更新できないこと (403)"""
        payload = {"enabled": False}
        response = test_client.put("/api/notifications/settings", json=payload, headers=operator_headers)
        assert response.status_code == 403

    def test_invalid_notification_level_rejected(self, test_client, admin_headers):
        """不正な通知レベルは拒否されること (422)"""
        payload = {"notification_levels": ["invalid_level"]}
        response = test_client.put("/api/notifications/settings", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_invalid_event_type_rejected(self, test_client, admin_headers):
        """不正なイベント種別は拒否されること (422)"""
        payload = {"event_types": ["nonexistent_event"]}
        response = test_client.put("/api/notifications/settings", json=payload, headers=admin_headers)
        assert response.status_code == 422


# ==============================================================================
# POST /api/notifications/test テスト (4件)
# ==============================================================================


class TestSendTestNotification:
    """POST /api/notifications/test"""

    def test_admin_can_send_test(self, test_client, admin_headers, tmp_path, monkeypatch):
        """admin ロールはテスト通知を送信できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {"message": "テスト通知です", "severity": "info", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "channels_notified" in data

    def test_viewer_cannot_send_test(self, test_client, viewer_headers):
        """viewer ロールはテスト通知を送信できないこと (403)"""
        payload = {"message": "テスト", "severity": "info", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload, headers=viewer_headers)
        assert response.status_code == 403

    def test_invalid_severity_rejected(self, test_client, admin_headers):
        """不正な重大度は拒否されること (422)"""
        payload = {"message": "テスト", "severity": "unknown", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_forbidden_chars_in_message_rejected(self, test_client, admin_headers, tmp_path, monkeypatch):
        """禁止文字を含むメッセージは拒否されること (422)"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {"message": "テスト; rm -rf /", "severity": "info", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload, headers=admin_headers)
        assert response.status_code == 422


# ==============================================================================
# GET /api/notifications/webhooks テスト (2件)
# ==============================================================================


class TestListWebhooks:
    """GET /api/notifications/webhooks"""

    def test_admin_can_list_webhooks(self, test_client, admin_headers, tmp_path, monkeypatch):
        """admin ロールは Webhook 一覧を取得できること"""
        from backend.core import notification_service as ns_module
        import backend.api.routes.notifications as notif_routes

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        response = test_client.get("/api/notifications/webhooks", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "slack_webhooks" in data
        assert "discord_webhooks" in data
        assert "generic_webhooks" in data

    def test_viewer_cannot_list_webhooks(self, test_client, viewer_headers):
        """viewer ロールは Webhook 一覧を取得できないこと (403)"""
        response = test_client.get("/api/notifications/webhooks", headers=viewer_headers)
        assert response.status_code == 403


# ==============================================================================
# POST /api/notifications/webhooks テスト (5件)
# ==============================================================================


class TestAddWebhook:
    """POST /api/notifications/webhooks"""

    def test_add_slack_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """有効な Slack Webhook URL を追加できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {
            "name": "テスト Slack",
            "url": "https://hooks.slack.com/services/T000/B000/xxxx",
            "type": "slack",
            "enabled": True,
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "webhook" in data
        assert data["webhook"]["name"] == "テスト Slack"
        assert "id" in data["webhook"]

    def test_add_discord_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """有効な Discord Webhook URL を追加できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {
            "name": "テスト Discord",
            "url": "https://discord.com/api/webhooks/12345/xxxx",
            "type": "discord",
            "enabled": True,
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_add_generic_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """有効な Generic Webhook URL を追加できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {
            "name": "テスト Generic",
            "url": "https://example.com/webhook",
            "type": "generic",
            "enabled": False,
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_invalid_url_rejected(self, test_client, admin_headers):
        """http/https スキーム以外の URL は拒否されること (422)"""
        payload = {
            "name": "不正 URL",
            "url": "ftp://evil.com/webhook",
            "type": "generic",
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_invalid_type_rejected(self, test_client, admin_headers):
        """不正な Webhook タイプは拒否されること (422)"""
        payload = {
            "name": "不正タイプ",
            "url": "https://example.com/webhook",
            "type": "telegram",
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 422


# ==============================================================================
# DELETE /api/notifications/webhooks/{id} テスト (3件)
# ==============================================================================


class TestDeleteWebhook:
    """DELETE /api/notifications/webhooks/{id}"""

    def test_delete_existing_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """登録済み Webhook を削除できること"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        # まず追加
        add_payload = {
            "name": "削除テスト",
            "url": "https://hooks.slack.com/services/A/B/C",
            "type": "slack",
        }
        add_response = test_client.post("/api/notifications/webhooks", json=add_payload, headers=admin_headers)
        assert add_response.status_code == 200
        webhook_id = add_response.json()["webhook"]["id"]

        # 削除
        del_response = test_client.delete(f"/api/notifications/webhooks/{webhook_id}", headers=admin_headers)
        assert del_response.status_code == 200
        data = del_response.json()
        assert data["status"] == "success"
        assert data["deleted_id"] == webhook_id

    def test_delete_nonexistent_webhook_returns_404(self, test_client, admin_headers, tmp_path, monkeypatch):
        """存在しない Webhook ID は 404 を返すこと"""
        from backend.core import notification_service as ns_module
        import backend.api.routes.notifications as notif_routes

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        response = test_client.delete("/api/notifications/webhooks/nonexistent-id-12345", headers=admin_headers)
        assert response.status_code == 404

    def test_viewer_cannot_delete_webhook(self, test_client, viewer_headers):
        """viewer ロールは Webhook を削除できないこと (403)"""
        response = test_client.delete("/api/notifications/webhooks/some-id", headers=viewer_headers)
        assert response.status_code == 403


# ==============================================================================
# GET /api/notifications/history テスト (3件)
# ==============================================================================


class TestNotificationHistory:
    """GET /api/notifications/history"""

    def test_admin_can_get_history(self, test_client, admin_headers, tmp_path, monkeypatch):
        """admin ロールは通知履歴を取得できること"""
        from backend.core import notification_service as ns_module
        import backend.api.routes.notifications as notif_routes

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        response = test_client.get("/api/notifications/history", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "history" in data
        assert "count" in data
        assert isinstance(data["history"], list)

    def test_viewer_cannot_get_history(self, test_client, viewer_headers):
        """viewer ロールは通知履歴を取得できないこと (403)"""
        response = test_client.get("/api/notifications/history", headers=viewer_headers)
        assert response.status_code == 403

    def test_history_limit_validation(self, test_client, admin_headers):
        """limit パラメータが範囲外 (0) の場合は 422 を返すこと"""
        response = test_client.get("/api/notifications/history?limit=0", headers=admin_headers)
        assert response.status_code == 422


# ==============================================================================
# セキュリティテスト (5件)
# ==============================================================================


class TestNotificationSecurity:
    """入力バリデーション・セキュリティテスト"""

    def test_forbidden_char_semicolon_in_webhook_name(self, test_client, admin_headers):
        """セミコロンを含む Webhook 名は拒否されること (422)"""
        payload = {
            "name": "test; evil",
            "url": "https://hooks.slack.com/services/X/Y/Z",
            "type": "slack",
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_forbidden_char_pipe_in_webhook_name(self, test_client, admin_headers):
        """パイプを含む Webhook 名は拒否されること (422)"""
        payload = {
            "name": "test | evil",
            "url": "https://hooks.slack.com/services/X/Y/Z",
            "type": "slack",
        }
        response = test_client.post("/api/notifications/webhooks", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_forbidden_char_dollar_in_message(self, test_client, admin_headers, tmp_path, monkeypatch):
        """ドル記号を含むメッセージは拒否されること (422)"""
        from backend.core import notification_service as ns_module

        svc = ns_module.NotificationService(
            settings_file=tmp_path / "settings.json",
            history_file=tmp_path / "history.json",
        )
        monkeypatch.setattr(ns_module, "notification_service", svc)
        import backend.api.routes.notifications as notif_routes
        monkeypatch.setattr(notif_routes, "notification_service", svc)

        payload = {"message": "$(rm -rf /)", "severity": "info", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_shell_injection_in_smtp_host_rejected(self, test_client, admin_headers):
        """shell injection を含む smtp_host は拒否されること (422)"""
        payload = {"smtp_host": "smtp.example.com; rm -rf /"}
        response = test_client.put("/api/notifications/settings", json=payload, headers=admin_headers)
        assert response.status_code == 422

    def test_unauthenticated_test_notification_forbidden(self, test_client):
        """認証なしのテスト通知は 403 を返すこと"""
        payload = {"message": "テスト", "severity": "info", "event_type": "alert_triggered"}
        response = test_client.post("/api/notifications/test", json=payload)
        assert response.status_code == 403
