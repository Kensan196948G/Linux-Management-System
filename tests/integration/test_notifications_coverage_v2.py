"""
notifications.py カバレッジ改善テスト v2

対象: backend/api/routes/notifications.py (46% -> 85%+)
未カバー箇所を重点的にテスト:
  - validate_text: 全禁止文字の個別テスト
  - validate_url: http/https プレフィックスチェック、URL内禁止文字
  - NotificationSettingsUpdate: field_validator（notification_levels, event_types）
  - WebhookAddRequest: field_validator（type）
  - TestNotificationRequest: field_validator（severity, event_type）
  - update_notification_settings: smtp_host/smtp_user/email_from バリデーション
  - send_test_notification: message 禁止文字チェック
  - add_webhook: name バリデーション + URL バリデーション
  - delete_webhook: 全 webhook_list 走査
  - get_notification_history: limit 範囲チェック
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _monkeypatch_notification_service(monkeypatch, tmp_path):
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


# ===================================================================
# validate_text ヘルパー 全禁止文字テスト
# ===================================================================


class TestValidateText:
    """validate_text の全分岐テスト"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"])
    def test_forbidden_char_raises_422(self, char):
        from backend.api.routes.notifications import validate_text
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_text(f"test{char}value", "test_field")
        assert exc_info.value.status_code == 422
        assert char in exc_info.value.detail

    def test_valid_text_passes(self):
        from backend.api.routes.notifications import validate_text
        result = validate_text("normal text with spaces and-dashes_underscores.dots", "field")
        assert result == "normal text with spaces and-dashes_underscores.dots"

    def test_empty_string_passes(self):
        from backend.api.routes.notifications import validate_text
        result = validate_text("", "field")
        assert result == ""

    def test_unicode_text_passes(self):
        from backend.api.routes.notifications import validate_text
        result = validate_text("テスト通知メッセージ", "message")
        assert result == "テスト通知メッセージ"


# ===================================================================
# validate_url ヘルパーテスト
# ===================================================================


class TestValidateUrl:
    """validate_url の全分岐テスト"""

    def test_valid_https_url(self):
        from backend.api.routes.notifications import validate_url
        result = validate_url("https://hooks.slack.com/services/T/B/X")
        assert result == "https://hooks.slack.com/services/T/B/X"

    def test_valid_http_url(self):
        from backend.api.routes.notifications import validate_url
        result = validate_url("http://localhost:8080/webhook")
        assert result == "http://localhost:8080/webhook"

    def test_ftp_url_rejected(self):
        from backend.api.routes.notifications import validate_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_url("ftp://evil.com/webhook")
        assert exc_info.value.status_code == 422

    def test_file_url_rejected(self):
        from backend.api.routes.notifications import validate_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_url("file:///etc/passwd")
        assert exc_info.value.status_code == 422

    def test_no_scheme_rejected(self):
        from backend.api.routes.notifications import validate_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_url("example.com/webhook")
        assert exc_info.value.status_code == 422

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`"])
    def test_url_with_forbidden_chars_rejected(self, char):
        from backend.api.routes.notifications import validate_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_url(f"https://example.com/webhook{char}evil")
        assert exc_info.value.status_code == 422


# ===================================================================
# NotificationSettingsUpdate バリデーションテスト
# ===================================================================


class TestNotificationSettingsUpdateValidation:
    """NotificationSettingsUpdate の field_validator テスト"""

    def test_valid_notification_levels(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        update = NotificationSettingsUpdate(notification_levels=["info", "warning", "critical"])
        assert update.notification_levels == ["info", "warning", "critical"]

    def test_invalid_notification_level_rejected(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        with pytest.raises(Exception):
            NotificationSettingsUpdate(notification_levels=["invalid_level"])

    def test_valid_event_types(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        from backend.core.notification_service import ALLOWED_EVENT_TYPES
        # 有効なイベントタイプを1つ取得
        valid_event = list(ALLOWED_EVENT_TYPES)[0]
        update = NotificationSettingsUpdate(event_types=[valid_event])
        assert update.event_types == [valid_event]

    def test_invalid_event_type_rejected(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        with pytest.raises(Exception):
            NotificationSettingsUpdate(event_types=["nonexistent_event_type_xyz"])

    def test_none_levels_accepted(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        update = NotificationSettingsUpdate(notification_levels=None)
        assert update.notification_levels is None

    def test_all_none_fields(self):
        from backend.api.routes.notifications import NotificationSettingsUpdate
        update = NotificationSettingsUpdate()
        assert update.enabled is None
        assert update.smtp_host is None


# ===================================================================
# WebhookAddRequest バリデーションテスト
# ===================================================================


class TestWebhookAddRequestValidation:
    """WebhookAddRequest の field_validator テスト"""

    @pytest.mark.parametrize("wh_type", ["slack", "discord", "generic"])
    def test_valid_types(self, wh_type):
        from backend.api.routes.notifications import WebhookAddRequest
        req = WebhookAddRequest(name="test", url="https://example.com", type=wh_type)
        assert req.type == wh_type

    def test_invalid_type_rejected(self):
        from backend.api.routes.notifications import WebhookAddRequest
        with pytest.raises(Exception):
            WebhookAddRequest(name="test", url="https://example.com", type="telegram")

    def test_enabled_defaults_true(self):
        from backend.api.routes.notifications import WebhookAddRequest
        req = WebhookAddRequest(name="test", url="https://example.com", type="slack")
        assert req.enabled is True


# ===================================================================
# TestNotificationRequest バリデーションテスト
# ===================================================================


class TestNotificationRequestValidation:
    """TestNotificationRequest の field_validator テスト"""

    def test_valid_request(self):
        from backend.api.routes.notifications import TestNotificationRequest
        req = TestNotificationRequest(message="test", severity="info", event_type="alert_triggered")
        assert req.severity == "info"

    def test_invalid_severity_rejected(self):
        from backend.api.routes.notifications import TestNotificationRequest
        with pytest.raises(Exception):
            TestNotificationRequest(message="test", severity="fatal", event_type="alert_triggered")

    def test_invalid_event_type_rejected(self):
        from backend.api.routes.notifications import TestNotificationRequest
        with pytest.raises(Exception):
            TestNotificationRequest(message="test", severity="info", event_type="nonexistent")


# ===================================================================
# update_notification_settings エンドポイントテスト
# ===================================================================


class TestUpdateSettingsV2:
    """PUT /api/notifications/settings の追加カバレッジ"""

    def test_update_smtp_host_with_forbidden_char(self, test_client, admin_headers):
        """smtp_host に禁止文字を含む場合は 422"""
        resp = test_client.put(
            "/api/notifications/settings",
            json={"smtp_host": "smtp.example.com|evil"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_smtp_user_with_forbidden_char(self, test_client, admin_headers):
        """smtp_user に禁止文字を含む場合は 422"""
        resp = test_client.put(
            "/api/notifications/settings",
            json={"smtp_user": "user$(cmd)"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_email_from_with_forbidden_char(self, test_client, admin_headers):
        """email_from に禁止文字を含む場合は 422"""
        resp = test_client.put(
            "/api/notifications/settings",
            json={"email_from": "admin@example.com;evil"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_update_smtp_port(self, test_client, admin_headers, tmp_path, monkeypatch):
        """smtp_port の更新が成功する"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.put(
            "/api/notifications/settings",
            json={"smtp_port": 587},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["settings"]["smtp_port"] == 587

    def test_update_email_enabled(self, test_client, admin_headers, tmp_path, monkeypatch):
        """email_enabled の更新が成功する"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.put(
            "/api/notifications/settings",
            json={"email_enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    def test_update_empty_body_succeeds(self, test_client, admin_headers, tmp_path, monkeypatch):
        """空ボディでの更新も成功する（変更なし）"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.put(
            "/api/notifications/settings",
            json={},
            headers=admin_headers,
        )
        assert resp.status_code == 200


# ===================================================================
# send_test_notification エンドポイントテスト
# ===================================================================


class TestSendTestV2:
    """POST /api/notifications/test の追加カバレッジ"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`"])
    def test_message_with_forbidden_char(self, test_client, admin_headers, char, tmp_path, monkeypatch):
        """メッセージ内の禁止文字が拒否される"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.post(
            "/api/notifications/test",
            json={"message": f"test{char}evil", "severity": "info", "event_type": "alert_triggered"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_valid_message_succeeds(self, test_client, admin_headers, tmp_path, monkeypatch):
        """正常なメッセージは成功する"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.post(
            "/api/notifications/test",
            json={"message": "テスト通知メッセージ", "severity": "warning", "event_type": "alert_triggered"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "channels_notified" in data
        assert "results" in data


# ===================================================================
# add_webhook エンドポイントテスト
# ===================================================================


class TestAddWebhookV2:
    """POST /api/notifications/webhooks の追加カバレッジ"""

    def test_add_webhook_name_with_backtick(self, test_client, admin_headers):
        """名前にバックティック含むと 422"""
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "test`evil", "url": "https://example.com/hook", "type": "generic"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_add_webhook_url_with_semicolon(self, test_client, admin_headers):
        """URL にセミコロン含むと 422"""
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "test", "url": "https://example.com/hook;evil", "type": "generic"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_add_webhook_creates_entry_with_id(self, test_client, admin_headers, tmp_path, monkeypatch):
        """追加した Webhook に id と created_at が含まれる"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "test hook", "url": "https://hooks.slack.com/test", "type": "slack", "enabled": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        webhook = resp.json()["webhook"]
        assert "id" in webhook
        assert "created_at" in webhook
        assert webhook["enabled"] is False
        assert webhook["name"] == "test hook"

    def test_add_webhook_disabled(self, test_client, admin_headers, tmp_path, monkeypatch):
        """enabled=False で追加"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "disabled hook", "url": "https://example.com/hook", "type": "discord", "enabled": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["webhook"]["enabled"] is False


# ===================================================================
# delete_webhook エンドポイントテスト
# ===================================================================


class TestDeleteWebhookV2:
    """DELETE /api/notifications/webhooks/{id} の追加カバレッジ"""

    def test_delete_discord_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """Discord webhook の追加→削除"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        # 追加
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "del discord", "url": "https://discord.com/api/webhooks/123/abc", "type": "discord"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        wh_id = resp.json()["webhook"]["id"]
        # 削除
        resp = test_client.delete(f"/api/notifications/webhooks/{wh_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == wh_id

    def test_delete_generic_webhook(self, test_client, admin_headers, tmp_path, monkeypatch):
        """Generic webhook の追加→削除"""
        _monkeypatch_notification_service(monkeypatch, tmp_path)
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "del generic", "url": "https://example.com/hook", "type": "generic"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        wh_id = resp.json()["webhook"]["id"]
        resp = test_client.delete(f"/api/notifications/webhooks/{wh_id}", headers=admin_headers)
        assert resp.status_code == 200

    def test_delete_webhook_id_with_forbidden_char(self, test_client, admin_headers):
        """webhook_id に禁止文字含むと 422"""
        resp = test_client.delete("/api/notifications/webhooks/id;evil", headers=admin_headers)
        assert resp.status_code == 422


# ===================================================================
# get_notification_history エンドポイントテスト
# ===================================================================


class TestHistoryV2:
    """GET /api/notifications/history の追加カバレッジ"""

    def test_history_limit_too_large(self, test_client, admin_headers):
        """limit=201 は 422"""
        resp = test_client.get("/api/notifications/history?limit=201", headers=admin_headers)
        assert resp.status_code == 422

    def test_history_limit_negative(self, test_client, admin_headers):
        """limit=-1 は 422"""
        resp = test_client.get("/api/notifications/history?limit=-1", headers=admin_headers)
        assert resp.status_code == 422

    def test_history_limit_1(self, test_client, admin_headers):
        """limit=1 は成功"""
        resp = test_client.get("/api/notifications/history?limit=1", headers=admin_headers)
        assert resp.status_code == 200

    def test_history_limit_200(self, test_client, admin_headers):
        """limit=200 は成功"""
        resp = test_client.get("/api/notifications/history?limit=200", headers=admin_headers)
        assert resp.status_code == 200

    def test_history_default_limit(self, test_client, admin_headers):
        """デフォルト limit=50 で成功"""
        resp = test_client.get("/api/notifications/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["history"], list)


# ===================================================================
# セキュリティ追加テスト
# ===================================================================


class TestNotificationSecurityV2:
    """追加セキュリティテスト"""

    @pytest.mark.parametrize("field,value", [
        ("smtp_host", "host(cmd)"),
        ("smtp_host", "host>file"),
        ("smtp_host", "host<input"),
        ("smtp_user", "user{evil}"),
        ("smtp_user", "user[index]"),
        ("email_from", "from?query"),
        ("email_from", "from*glob"),
    ])
    def test_settings_forbidden_chars_rejected(self, test_client, admin_headers, field, value):
        """設定更新で各フィールドの禁止文字が拒否される"""
        resp = test_client.put(
            "/api/notifications/settings",
            json={field: value},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_unauthenticated_update_rejected(self, test_client):
        """未認証の設定更新は 403"""
        resp = test_client.put(
            "/api/notifications/settings",
            json={"enabled": False},
        )
        assert resp.status_code == 403

    def test_unauthenticated_webhook_add_rejected(self, test_client):
        """未認証の Webhook 追加は 403"""
        resp = test_client.post(
            "/api/notifications/webhooks",
            json={"name": "test", "url": "https://example.com", "type": "slack"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_webhook_delete_rejected(self, test_client):
        """未認証の Webhook 削除は 403"""
        resp = test_client.delete("/api/notifications/webhooks/some-id")
        assert resp.status_code == 403
