"""
notification_service.py カバレッジ改善テスト

対象: backend/core/notification_service.py (49% -> 90%+)
未カバー箇所を重点的にテスト:
  - get_settings: ファイル存在/不存在/読込エラー/JSONデコードエラー
  - update_settings: 設定マージ+書き込み
  - _load_history / _save_history / _append_history / get_history
  - send_slack: ペイロード構築+_post_json呼び出し
  - send_discord: ペイロード構築+_post_json呼び出し
  - send_generic_webhook: ペイロード転送
  - send_email: SMTP正常系/不完全設定/例外
  - send_notification: 全チャンネル統合送信 + フィルタ分岐
  - _post_json: 成功/エラーレスポンス/タイムアウト/RequestError
"""

import json
import os
import smtplib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.core.notification_service import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_SEVERITY_LEVELS,
    DEFAULT_SETTINGS,
    SEVERITY_COLORS,
    SEVERITY_SLACK_COLORS,
    NotificationService,
)


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture
def svc(tmp_path):
    """テスト用 NotificationService インスタンス"""
    settings_file = tmp_path / "settings.json"
    history_file = tmp_path / "history.json"
    return NotificationService(settings_file=settings_file, history_file=history_file)


@pytest.fixture
def svc_with_settings(tmp_path):
    """設定ファイルありの NotificationService"""
    settings_file = tmp_path / "settings.json"
    history_file = tmp_path / "history.json"
    custom = {**DEFAULT_SETTINGS, "enabled": True, "slack_webhooks": ["https://hooks.slack.com/test"]}
    settings_file.write_text(json.dumps(custom), encoding="utf-8")
    return NotificationService(settings_file=settings_file, history_file=history_file)


# ===================================================================
# get_settings テスト
# ===================================================================

class TestGetSettings:
    """get_settings の全分岐"""

    @pytest.mark.asyncio
    async def test_default_settings_when_no_file(self, tmp_path):
        """設定ファイルなしの場合はデフォルト設定を返す"""
        # 独立したディレクトリで他テストの影響を排除
        isolated = tmp_path / "isolated_default"
        isolated.mkdir()
        svc = NotificationService(
            settings_file=isolated / "settings.json",
            history_file=isolated / "history.json",
        )
        settings = await svc.get_settings()
        assert settings["enabled"] is True
        assert settings["slack_webhooks"] == []
        assert settings["smtp_port"] == 587

    @pytest.mark.asyncio
    async def test_settings_from_file(self, tmp_path):
        """設定ファイルがある場合はマージした結果を返す"""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"enabled": False, "smtp_port": 465}), encoding="utf-8")
        svc = NotificationService(settings_file=settings_file, history_file=tmp_path / "h.json")
        settings = await svc.get_settings()
        assert settings["enabled"] is False
        assert settings["smtp_port"] == 465
        # デフォルトキーも補完される
        assert "slack_webhooks" in settings

    @pytest.mark.asyncio
    async def test_settings_invalid_json(self, tmp_path):
        """JSON デコードエラーの場合はデフォルトを返す"""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("not valid json {{{", encoding="utf-8")
        svc = NotificationService(settings_file=settings_file, history_file=tmp_path / "h.json")
        settings = await svc.get_settings()
        assert settings == {**DEFAULT_SETTINGS}

    @pytest.mark.asyncio
    async def test_settings_os_error(self, tmp_path):
        """OSError の場合はデフォルトを返す"""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{}", encoding="utf-8")
        svc = NotificationService(settings_file=settings_file, history_file=tmp_path / "h.json")
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
                settings = await svc.get_settings()
        assert settings == {**DEFAULT_SETTINGS}


# ===================================================================
# update_settings テスト
# ===================================================================

class TestUpdateSettings:
    """update_settings の分岐"""

    @pytest.mark.asyncio
    async def test_update_merges_with_current(self, tmp_path):
        """既存設定とマージされる"""
        # 独立したディレクトリで他テストの影響を排除
        isolated = tmp_path / "isolated_update"
        isolated.mkdir()
        svc = NotificationService(
            settings_file=isolated / "settings.json",
            history_file=isolated / "history.json",
        )
        result = await svc.update_settings({"enabled": False, "smtp_port": 465})
        assert result["enabled"] is False
        assert result["smtp_port"] == 465
        assert result["slack_webhooks"] == []  # デフォルトから補完

    @pytest.mark.asyncio
    async def test_update_persists_to_file(self, svc):
        """更新がファイルに永続化される"""
        await svc.update_settings({"smtp_host": "mail.example.com"})
        # 再度読み込んで確認
        settings = await svc.get_settings()
        assert settings["smtp_host"] == "mail.example.com"


# ===================================================================
# 履歴管理テスト
# ===================================================================

class TestHistoryManagement:
    """_load_history / _save_history / _append_history / get_history"""

    def test_load_history_no_file(self, svc):
        """履歴ファイルなしの場合は空リスト"""
        result = svc._load_history()
        assert result == []

    def test_load_history_with_data(self, svc):
        """履歴ファイルがある場合はリストを返す"""
        entries = [{"event": "test1"}, {"event": "test2"}]
        svc._history_file.write_text(json.dumps(entries), encoding="utf-8")
        result = svc._load_history()
        assert len(result) == 2

    def test_load_history_invalid_json(self, svc):
        """JSON デコードエラーの場合は空リスト"""
        svc._history_file.write_text("invalid json", encoding="utf-8")
        result = svc._load_history()
        assert result == []

    def test_load_history_os_error(self, svc):
        """OSError の場合は空リスト"""
        svc._history_file.write_text("[]", encoding="utf-8")
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", side_effect=OSError("denied")):
                result = svc._load_history()
        assert result == []

    def test_save_history_truncates_to_200(self, svc):
        """最大 200 件に切り詰められる"""
        entries = [{"event": f"entry_{i}"} for i in range(250)]
        svc._save_history(entries)
        loaded = json.loads(svc._history_file.read_text(encoding="utf-8"))
        assert len(loaded) == 200
        # 最新 200 件が保持される
        assert loaded[0]["event"] == "entry_50"
        assert loaded[-1]["event"] == "entry_249"

    def test_append_history(self, svc):
        """エントリが追加される"""
        svc._append_history({"event": "first"})
        svc._append_history({"event": "second"})
        history = svc._load_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_history_returns_reversed(self, svc):
        """get_history は新しい順で返す"""
        svc._append_history({"event": "old"})
        svc._append_history({"event": "new"})
        history = await svc.get_history(limit=10)
        assert history[0]["event"] == "new"
        assert history[1]["event"] == "old"

    @pytest.mark.asyncio
    async def test_get_history_respects_limit(self, svc):
        """get_history は limit を超えない"""
        for i in range(10):
            svc._append_history({"event": f"e_{i}"})
        history = await svc.get_history(limit=3)
        assert len(history) == 3


# ===================================================================
# send_slack テスト
# ===================================================================

class TestSendSlack:
    """send_slack の全分岐"""

    @pytest.mark.asyncio
    async def test_send_slack_success(self, svc):
        """正常送信"""
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 200, "error": None}
            result = await svc.send_slack("https://hooks.slack.com/test", "Test message", "info")
        assert result["success"] is True
        call_args = mock_post.call_args
        payload = call_args[0][1]
        assert ":information_source:" in payload["text"]
        assert payload["attachments"][0]["color"] == "#2196F3"

    @pytest.mark.asyncio
    async def test_send_slack_warning_severity(self, svc):
        """warning 重大度"""
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 200, "error": None}
            await svc.send_slack("https://hooks.slack.com/test", "Warning", "warning")
        payload = mock_post.call_args[0][1]
        assert ":warning:" in payload["text"]
        assert payload["attachments"][0]["color"] == "#FF9800"

    @pytest.mark.asyncio
    async def test_send_slack_critical_severity(self, svc):
        """critical 重大度"""
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 200, "error": None}
            await svc.send_slack("https://hooks.slack.com/test", "Critical", "critical")
        payload = mock_post.call_args[0][1]
        assert ":red_circle:" in payload["text"]
        assert payload["attachments"][0]["color"] == "#F44336"

    @pytest.mark.asyncio
    async def test_send_slack_unknown_severity(self, svc):
        """未知の重大度はデフォルト値"""
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 200, "error": None}
            await svc.send_slack("https://hooks.slack.com/test", "Unknown", "debug")
        payload = mock_post.call_args[0][1]
        assert ":bell:" in payload["text"]


# ===================================================================
# send_discord テスト
# ===================================================================

class TestSendDiscord:
    """send_discord の全分岐"""

    @pytest.mark.asyncio
    async def test_send_discord_info(self, svc):
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 204, "error": None}
            result = await svc.send_discord("https://discord.com/api/webhooks/test", "Info", "info")
        assert result["success"] is True
        payload = mock_post.call_args[0][1]
        assert payload["embeds"][0]["color"] == 0x2196F3

    @pytest.mark.asyncio
    async def test_send_discord_warning(self, svc):
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 204, "error": None}
            await svc.send_discord("https://discord.com/api/webhooks/test", "Warn", "warning")
        payload = mock_post.call_args[0][1]
        assert payload["embeds"][0]["color"] == 0xFF9800

    @pytest.mark.asyncio
    async def test_send_discord_critical(self, svc):
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 204, "error": None}
            await svc.send_discord("https://discord.com/api/webhooks/test", "Crit", "critical")
        payload = mock_post.call_args[0][1]
        assert payload["embeds"][0]["color"] == 0xF44336

    @pytest.mark.asyncio
    async def test_send_discord_unknown_severity(self, svc):
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 204, "error": None}
            await svc.send_discord("https://discord.com/api/webhooks/test", "Unknown", "debug")
        payload = mock_post.call_args[0][1]
        # デフォルト色
        assert payload["embeds"][0]["color"] == 0x2196F3


# ===================================================================
# send_generic_webhook テスト
# ===================================================================

class TestSendGenericWebhook:
    """send_generic_webhook"""

    @pytest.mark.asyncio
    async def test_send_generic_webhook(self, svc):
        with patch.object(svc, "_post_json", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True, "status_code": 200, "error": None}
            result = await svc.send_generic_webhook("https://example.com/hook", {"key": "value"})
        assert result["success"] is True
        mock_post.assert_called_once_with("https://example.com/hook", {"key": "value"})


# ===================================================================
# send_email テスト
# ===================================================================

class TestSendEmail:
    """send_email の全分岐"""

    @pytest.mark.asyncio
    async def test_email_incomplete_settings_no_host(self, svc):
        """smtp_host が空の場合"""
        result = await svc.send_email(
            {"smtp_host": "", "email_to": ["test@example.com"]},
            "Test", "info"
        )
        assert result["success"] is False
        assert "SMTP設定が不完全" in result["error"]

    @pytest.mark.asyncio
    async def test_email_incomplete_settings_no_recipients(self, svc):
        """email_to が空の場合"""
        result = await svc.send_email(
            {"smtp_host": "mail.example.com", "email_to": []},
            "Test", "info"
        )
        assert result["success"] is False
        assert "SMTP設定が不完全" in result["error"]

    @pytest.mark.asyncio
    async def test_email_success_with_auth(self, svc):
        """SMTP 認証あり正常送信"""
        settings = {
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password_env": "TEST_SMTP_PASS",
            "email_from": "sender@example.com",
            "email_to": ["recipient@example.com"],
        }
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        with patch.dict(os.environ, {"TEST_SMTP_PASS": "secret123"}):
            with patch("backend.core.notification_service.smtplib.SMTP", return_value=mock_server):
                with patch("backend.core.notification_service.ssl.create_default_context"):
                    result = await svc.send_email(settings, "Test email body", "warning")
        assert result["success"] is True
        assert result["error"] is None
        mock_server.ehlo.assert_called_once()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret123")
        mock_server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_email_success_without_auth(self, svc):
        """SMTP 認証なし（smtp_user 空）の場合 login をスキップ"""
        settings = {
            "smtp_host": "mail.example.com",
            "smtp_port": 25,
            "smtp_user": "",
            "smtp_password_env": "TEST_SMTP_PASS",
            "email_from": "",
            "email_to": ["recipient@example.com"],
        }
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        with patch.dict(os.environ, {"TEST_SMTP_PASS": ""}):
            with patch("backend.core.notification_service.smtplib.SMTP", return_value=mock_server):
                with patch("backend.core.notification_service.ssl.create_default_context"):
                    result = await svc.send_email(settings, "No auth email", "info")
        assert result["success"] is True
        mock_server.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_smtp_exception(self, svc):
        """SMTP 例外時のエラーハンドリング"""
        settings = {
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password_env": "SMTP_PASSWORD",
            "email_from": "sender@example.com",
            "email_to": ["recipient@example.com"],
        }
        with patch("backend.core.notification_service.smtplib.SMTP", side_effect=smtplib.SMTPException("Connection refused")):
            with patch("backend.core.notification_service.ssl.create_default_context"):
                result = await svc.send_email(settings, "Test", "critical")
        assert result["success"] is False
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_email_default_from_uses_smtp_user(self, svc):
        """email_from が空の場合は smtp_user をフォールバック"""
        settings = {
            "smtp_host": "mail.example.com",
            "smtp_port": 587,
            "smtp_user": "fallback@example.com",
            "smtp_password_env": "TEST_SMTP_PASS",
            "email_to": ["recipient@example.com"],
            # email_from を省略
        }
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        with patch.dict(os.environ, {"TEST_SMTP_PASS": "pass"}):
            with patch("backend.core.notification_service.smtplib.SMTP", return_value=mock_server):
                with patch("backend.core.notification_service.ssl.create_default_context"):
                    result = await svc.send_email(settings, "Test", "info")
        assert result["success"] is True


# ===================================================================
# _post_json テスト
# ===================================================================

class TestPostJson:
    """_post_json の全分岐"""

    @pytest.mark.asyncio
    async def test_post_json_success_200(self, svc):
        """200 OK"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.core.notification_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._post_json("https://example.com", {"key": "val"})
        assert result["success"] is True
        assert result["status_code"] == 200
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_post_json_success_204(self, svc):
        """204 No Content (Discord)"""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.core.notification_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._post_json("https://example.com", {})
        assert result["success"] is True
        assert result["status_code"] == 204

    @pytest.mark.asyncio
    async def test_post_json_error_response(self, svc):
        """非 200/204 レスポンス"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.core.notification_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._post_json("https://example.com", {})
        assert result["success"] is False
        assert result["status_code"] == 400
        assert result["error"] == "Bad Request"

    @pytest.mark.asyncio
    async def test_post_json_timeout(self, svc):
        """タイムアウト"""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.core.notification_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._post_json("https://example.com", {})
        assert result["success"] is False
        assert result["status_code"] == 0
        assert "タイムアウト" in result["error"]

    @pytest.mark.asyncio
    async def test_post_json_request_error(self, svc):
        """RequestError"""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("connection failed")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("backend.core.notification_service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._post_json("https://example.com", {})
        assert result["success"] is False
        assert result["status_code"] == 0
        assert "connection failed" in result["error"]


# ===================================================================
# send_notification 統合テスト
# ===================================================================

class TestSendNotification:
    """send_notification の全分岐"""

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, svc):
        """enabled=False の場合は空リスト"""
        await svc.update_settings({"enabled": False})
        results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert results == []

    @pytest.mark.asyncio
    async def test_severity_filter(self, svc):
        """notification_levels に含まれない重大度はスキップ"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["critical"],
            "event_types": ["alert_triggered"],
        })
        results = await svc.send_notification("alert_triggered", "Test", "info", {})
        assert results == []

    @pytest.mark.asyncio
    async def test_event_type_filter(self, svc):
        """event_types に含まれないイベントはスキップ"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning", "critical"],
            "event_types": ["service_down"],
        })
        results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert results == []

    @pytest.mark.asyncio
    async def test_slack_webhook_string(self, svc):
        """Slack webhook が文字列の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": ["https://hooks.slack.com/services/xxx"],
            "discord_webhooks": [],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        with patch.object(svc, "send_slack", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = {"success": True, "status_code": 200, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1
        assert results[0]["channel"] == "slack"

    @pytest.mark.asyncio
    async def test_slack_webhook_dict(self, svc):
        """Slack webhook が dict の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [{"url": "https://hooks.slack.com/services/xxx"}],
            "discord_webhooks": [],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        with patch.object(svc, "send_slack", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = {"success": True, "status_code": 200, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_slack_webhook_dict_empty_url_skipped(self, svc):
        """Slack webhook dict の url が空の場合はスキップ"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [{"url": ""}],
            "discord_webhooks": [],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_discord_webhook_string(self, svc):
        """Discord webhook が文字列の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": ["https://discord.com/api/webhooks/xxx"],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        with patch.object(svc, "send_discord", new_callable=AsyncMock) as mock_discord:
            mock_discord.return_value = {"success": True, "status_code": 204, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1
        assert results[0]["channel"] == "discord"

    @pytest.mark.asyncio
    async def test_discord_webhook_dict(self, svc):
        """Discord webhook が dict の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": [{"url": "https://discord.com/api/webhooks/xxx"}],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        with patch.object(svc, "send_discord", new_callable=AsyncMock) as mock_discord:
            mock_discord.return_value = {"success": True, "status_code": 204, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_generic_webhook_dict_with_payload(self, svc):
        """Generic webhook が dict + extra payload の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": [],
            "generic_webhooks": [{"url": "https://example.com/hook", "payload": {"extra": "data"}}],
            "email_enabled": False,
        })
        with patch.object(svc, "send_generic_webhook", new_callable=AsyncMock) as mock_generic:
            mock_generic.return_value = {"success": True, "status_code": 200, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {"detail": "x"})
        assert len(results) == 1
        assert results[0]["channel"] == "generic"
        # payload に extra と detail が含まれていること
        call_payload = mock_generic.call_args[0][1]
        assert call_payload["extra"] == "data"
        assert call_payload["detail"] == "x"

    @pytest.mark.asyncio
    async def test_generic_webhook_string(self, svc):
        """Generic webhook が文字列の場合"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": [],
            "generic_webhooks": ["https://example.com/hook"],
            "email_enabled": False,
        })
        with patch.object(svc, "send_generic_webhook", new_callable=AsyncMock) as mock_generic:
            mock_generic.return_value = {"success": True, "status_code": 200, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_email_channel_enabled(self, svc):
        """email_enabled=True の場合にメール送信される"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": [],
            "generic_webhooks": [],
            "email_enabled": True,
            "smtp_host": "mail.example.com",
            "email_to": ["admin@example.com"],
        })
        with patch.object(svc, "send_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = {"success": True, "error": None}
            results = await svc.send_notification("alert_triggered", "Test", "warning", {})
        assert len(results) == 1
        assert results[0]["channel"] == "email"

    @pytest.mark.asyncio
    async def test_notification_records_history(self, svc):
        """通知送信後に履歴が記録される"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["warning"],
            "event_types": ["alert_triggered"],
            "slack_webhooks": [],
            "discord_webhooks": [],
            "generic_webhooks": [],
            "email_enabled": False,
        })
        await svc.send_notification("alert_triggered", "Test history", "warning", {"key": "val"})
        history = await svc.get_history(limit=1)
        assert len(history) == 1
        assert history[0]["event_type"] == "alert_triggered"
        assert history[0]["message"] == "Test history"

    @pytest.mark.asyncio
    async def test_all_channels_combined(self, svc):
        """全チャンネル同時送信"""
        await svc.update_settings({
            "enabled": True,
            "notification_levels": ["critical"],
            "event_types": ["system_critical"],
            "slack_webhooks": ["https://hooks.slack.com/xxx"],
            "discord_webhooks": ["https://discord.com/api/webhooks/xxx"],
            "generic_webhooks": ["https://example.com/hook"],
            "email_enabled": True,
            "smtp_host": "mail.example.com",
            "email_to": ["admin@example.com"],
        })
        with patch.object(svc, "send_slack", new_callable=AsyncMock) as mock_s, \
             patch.object(svc, "send_discord", new_callable=AsyncMock) as mock_d, \
             patch.object(svc, "send_generic_webhook", new_callable=AsyncMock) as mock_g, \
             patch.object(svc, "send_email", new_callable=AsyncMock) as mock_e:
            mock_s.return_value = {"success": True, "status_code": 200, "error": None}
            mock_d.return_value = {"success": True, "status_code": 204, "error": None}
            mock_g.return_value = {"success": True, "status_code": 200, "error": None}
            mock_e.return_value = {"success": True, "error": None}
            results = await svc.send_notification("system_critical", "All channels", "critical", {})
        assert len(results) == 4
        channels = [r["channel"] for r in results]
        assert "slack" in channels
        assert "discord" in channels
        assert "generic" in channels
        assert "email" in channels


# ===================================================================
# 定数テスト
# ===================================================================

class TestConstants:
    """モジュールレベル定数の検証"""

    def test_severity_colors(self):
        assert SEVERITY_COLORS["info"] == 0x2196F3
        assert SEVERITY_COLORS["warning"] == 0xFF9800
        assert SEVERITY_COLORS["critical"] == 0xF44336

    def test_severity_slack_colors(self):
        assert SEVERITY_SLACK_COLORS["info"] == "#2196F3"
        assert SEVERITY_SLACK_COLORS["critical"] == "#F44336"

    def test_allowed_severity_levels(self):
        assert ALLOWED_SEVERITY_LEVELS == {"info", "warning", "critical"}

    def test_allowed_event_types(self):
        assert "alert_triggered" in ALLOWED_EVENT_TYPES
        assert "service_down" in ALLOWED_EVENT_TYPES

    def test_default_settings_structure(self):
        assert DEFAULT_SETTINGS["enabled"] is True
        assert DEFAULT_SETTINGS["smtp_port"] == 587
        assert isinstance(DEFAULT_SETTINGS["slack_webhooks"], list)
