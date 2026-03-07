"""
通知サービスモジュール

Slack / Discord / Generic Webhook / SMTP メール通知を提供するコアサービス。
シェル起動は絶対禁止。全 HTTP 呼び出しは httpx.AsyncClient を使用。
"""

import json
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# 通知設定ファイルのパス
_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "notification_settings.json"

# 通知履歴ファイルのパス
_HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "notification_history.json"

# 重大度ごとの色マッピング
SEVERITY_COLORS = {
    "info": 0x2196F3,  # 青
    "warning": 0xFF9800,  # オレンジ
    "critical": 0xF44336,  # 赤
}

SEVERITY_SLACK_COLORS = {
    "info": "#2196F3",
    "warning": "#FF9800",
    "critical": "#F44336",
}

# デフォルト設定
DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "slack_webhooks": [],
    "discord_webhooks": [],
    "generic_webhooks": [],
    "email_enabled": False,
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password_env": "SMTP_PASSWORD",
    "email_from": "",
    "email_to": [],
    "notification_levels": ["warning", "critical"],
    "event_types": ["alert_triggered", "approval_requested", "service_down"],
}

ALLOWED_SEVERITY_LEVELS = {"info", "warning", "critical"}
ALLOWED_EVENT_TYPES = {
    "alert_triggered",
    "approval_requested",
    "approval_executed",
    "service_down",
    "system_critical",
}


class NotificationService:
    """通知サービスクラス

    Slack / Discord / Generic Webhook / SMTP を経由した通知送信を管理する。
    全 HTTP 呼び出しは httpx.AsyncClient を使用。シェル起動禁止。
    """

    def __init__(self, settings_file: Optional[Path] = None, history_file: Optional[Path] = None) -> None:
        """初期化

        Args:
            settings_file: 通知設定 JSON ファイルのパス（None の場合はデフォルト）
            history_file: 通知履歴 JSON ファイルのパス（None の場合はデフォルト）
        """
        self._settings_file = settings_file or _SETTINGS_FILE
        self._history_file = history_file or _HISTORY_FILE
        # data ディレクトリの確保
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._history_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 設定管理
    # ------------------------------------------------------------------

    async def get_settings(self) -> dict[str, Any]:
        """通知設定を取得する

        Returns:
            通知設定の辞書。ファイルが存在しない場合はデフォルト設定を返す。
        """
        try:
            if self._settings_file.exists():
                raw = self._settings_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                # デフォルト値で不足キーを補完
                merged = {**DEFAULT_SETTINGS, **data}
                return merged
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("通知設定ファイルの読み込みに失敗しました: %s", exc)
        return {**DEFAULT_SETTINGS}

    async def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """通知設定を更新する

        Args:
            settings: 更新する設定の辞書

        Returns:
            更新後の通知設定の辞書
        """
        current = await self.get_settings()
        merged = {**current, **settings}
        self._settings_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged

    # ------------------------------------------------------------------
    # 履歴管理
    # ------------------------------------------------------------------

    def _load_history(self) -> list[dict[str, Any]]:
        """通知履歴をファイルから読み込む

        Returns:
            通知履歴のリスト
        """
        try:
            if self._history_file.exists():
                raw = self._history_file.read_text(encoding="utf-8")
                return json.loads(raw)
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_history(self, history: list[dict[str, Any]]) -> None:
        """通知履歴をファイルに保存する（最大 200 件保持）

        Args:
            history: 保存する通知履歴のリスト
        """
        # 最新 200 件のみ保持
        history = history[-200:]
        self._history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_history(self, entry: dict[str, Any]) -> None:
        """通知履歴にエントリを追加する

        Args:
            entry: 追加する履歴エントリ
        """
        history = self._load_history()
        history.append(entry)
        self._save_history(history)

    async def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """通知履歴を取得する

        Args:
            limit: 取得件数の上限（デフォルト 50）

        Returns:
            通知履歴のリスト（新しい順）
        """
        history = self._load_history()
        # 新しい順で返す
        return list(reversed(history))[:limit]

    # ------------------------------------------------------------------
    # Slack 通知
    # ------------------------------------------------------------------

    async def send_slack(self, webhook_url: str, message: str, severity: str) -> dict[str, Any]:
        """Slack Webhook に通知を送信する

        Args:
            webhook_url: Slack Incoming Webhook URL
            message: 送信するメッセージ本文
            severity: 重大度 ("info" / "warning" / "critical")

        Returns:
            送信結果の辞書 {"success": bool, "status_code": int, "error": str|None}
        """
        color = SEVERITY_SLACK_COLORS.get(severity, "#2196F3")
        emoji = {"info": ":information_source:", "warning": ":warning:", "critical": ":red_circle:"}.get(severity, ":bell:")
        payload = {
            "text": f"{emoji} *Linux Management System* 通知",
            "attachments": [
                {
                    "color": color,
                    "text": message,
                    "footer": f"重大度: {severity.upper()}",
                    "ts": int(datetime.now(timezone.utc).timestamp()),
                }
            ],
        }
        return await self._post_json(webhook_url, payload)

    # ------------------------------------------------------------------
    # Discord 通知
    # ------------------------------------------------------------------

    async def send_discord(self, webhook_url: str, message: str, severity: str) -> dict[str, Any]:
        """Discord Webhook に通知を送信する

        Args:
            webhook_url: Discord Webhook URL
            message: 送信するメッセージ本文
            severity: 重大度 ("info" / "warning" / "critical")

        Returns:
            送信結果の辞書 {"success": bool, "status_code": int, "error": str|None}
        """
        color = SEVERITY_COLORS.get(severity, 0x2196F3)
        title = {"info": "ℹ️ 情報", "warning": "⚠️ 警告", "critical": "🔴 緊急"}.get(severity, "🔔 通知")
        payload = {
            "embeds": [
                {
                    "title": f"{title} - Linux Management System",
                    "description": message,
                    "color": color,
                    "footer": {"text": f"重大度: {severity.upper()}"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
        return await self._post_json(webhook_url, payload)

    # ------------------------------------------------------------------
    # Generic Webhook
    # ------------------------------------------------------------------

    async def send_generic_webhook(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """汎用 Webhook に JSON ペイロードを送信する

        Args:
            url: 送信先 URL
            payload: 送信する JSON ペイロード

        Returns:
            送信結果の辞書 {"success": bool, "status_code": int, "error": str|None}
        """
        return await self._post_json(url, payload)

    # ------------------------------------------------------------------
    # SMTP メール通知
    # ------------------------------------------------------------------

    async def send_email(self, settings: dict[str, Any], message: str, severity: str) -> dict[str, Any]:
        """SMTP でメール通知を送信する

        smtplib を直接呼び出す（シェル起動禁止）。

        Args:
            settings: 通知設定の辞書（smtp_host, smtp_port, smtp_user, etc.）
            message: 送信するメッセージ本文
            severity: 重大度 ("info" / "warning" / "critical")

        Returns:
            送信結果の辞書 {"success": bool, "error": str|None}
        """
        try:
            smtp_host = settings.get("smtp_host", "")
            smtp_port = int(settings.get("smtp_port", 587))
            smtp_user = settings.get("smtp_user", "")
            password_env = settings.get("smtp_password_env", "SMTP_PASSWORD")
            smtp_password = os.environ.get(password_env, "")
            email_from = settings.get("email_from", smtp_user)
            email_to: list[str] = settings.get("email_to", [])

            if not smtp_host or not email_to:
                return {"success": False, "error": "SMTP設定が不完全です"}

            subject = f"[Linux Management] {severity.upper()} 通知"

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = email_from
            msg["To"] = ", ".join(email_to)
            msg.set_content(message)

            context = ssl.create_default_context()
            # シェル起動禁止 - smtplib を直接呼び出す
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)

            return {"success": True, "error": None}
        except Exception as exc:
            logger.error("メール送信エラー: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # 統合通知送信
    # ------------------------------------------------------------------

    async def send_notification(
        self,
        event_type: str,
        message: str,
        severity: str,
        details: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """設定されたすべてのチャンネルに通知を送信する

        Args:
            event_type: イベント種別（例: "alert_triggered", "service_down"）
            message: 通知メッセージ本文
            severity: 重大度 ("info" / "warning" / "critical")
            details: 追加詳細情報

        Returns:
            各チャンネルの送信結果リスト
        """
        cfg = await self.get_settings()
        results: list[dict[str, Any]] = []

        if not cfg.get("enabled", True):
            return results

        # 重大度フィルタ
        notification_levels: list[str] = cfg.get("notification_levels", ["warning", "critical"])
        if severity not in notification_levels:
            return results

        # イベント種別フィルタ
        allowed_events: list[str] = cfg.get("event_types", list(ALLOWED_EVENT_TYPES))
        if event_type not in allowed_events:
            return results

        full_message = f"[{event_type}] {message}"

        # Slack
        for webhook_url in cfg.get("slack_webhooks", []):
            if isinstance(webhook_url, dict):
                url = webhook_url.get("url", "")
            else:
                url = str(webhook_url)
            if url:
                result = await self.send_slack(url, full_message, severity)
                results.append({"channel": "slack", "url": url[:30] + "...", **result})

        # Discord
        for webhook_url in cfg.get("discord_webhooks", []):
            if isinstance(webhook_url, dict):
                url = webhook_url.get("url", "")
            else:
                url = str(webhook_url)
            if url:
                result = await self.send_discord(url, full_message, severity)
                results.append({"channel": "discord", "url": url[:30] + "...", **result})

        # Generic Webhooks
        for wh in cfg.get("generic_webhooks", []):
            if isinstance(wh, dict):
                url = wh.get("url", "")
                extra_payload = wh.get("payload", {})
            else:
                url = str(wh)
                extra_payload = {}
            if url:
                payload = {
                    "event_type": event_type,
                    "message": message,
                    "severity": severity,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **extra_payload,
                    **details,
                }
                result = await self.send_generic_webhook(url, payload)
                results.append({"channel": "generic", "url": url[:30] + "...", **result})

        # SMTP メール
        if cfg.get("email_enabled", False):
            result = await self.send_email(cfg, full_message, severity)
            results.append({"channel": "email", **result})

        # 履歴に記録
        history_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "message": message,
            "severity": severity,
            "results": results,
            "channels_notified": len(results),
        }
        self._append_history(history_entry)

        return results

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """JSON ペイロードを指定 URL に POST する

        httpx.AsyncClient を使用。シェル起動禁止。

        Args:
            url: 送信先 URL
            payload: 送信する JSON ペイロード

        Returns:
            {"success": bool, "status_code": int, "error": str|None}
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                success = response.status_code in (200, 204)
                return {
                    "success": success,
                    "status_code": response.status_code,
                    "error": None if success else response.text[:200],
                }
        except httpx.TimeoutException:
            return {"success": False, "status_code": 0, "error": "リクエストタイムアウト"}
        except httpx.RequestError as exc:
            return {"success": False, "status_code": 0, "error": str(exc)}


# シングルトンインスタンス
notification_service = NotificationService()
