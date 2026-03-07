"""
通知管理 API ルーター

Slack / Discord / Generic Webhook / SMTP メール通知の設定・管理・送信を提供する。
シェル起動は絶対禁止。全ユーザー入力は FORBIDDEN_CHARS で検証する。
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from ...core import require_permission
from ...core.audit_log import AuditLog
from ...core.auth import TokenData
from ...core.notification_service import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_SEVERITY_LEVELS,
    notification_service,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

audit_log = AuditLog()

# 入力バリデーション用禁止文字リスト
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

# Webhook 設定ファイルのパス（通知設定に統合して管理）
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


# ==============================================================================
# 入力バリデーション
# ==============================================================================


def validate_text(value: str, field_name: str = "input") -> str:
    """テキスト入力に禁止文字が含まれていないことを確認する

    Args:
        value: 検証する文字列
        field_name: フィールド名（エラーメッセージ用）

    Returns:
        検証済みの文字列

    Raises:
        HTTPException: 禁止文字が含まれている場合
    """
    for char in FORBIDDEN_CHARS:
        if char in value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"禁止文字が含まれています: '{char}' in {field_name}",
            )
    return value


def validate_url(url: str) -> str:
    """URL が http:// または https:// で始まることを確認する

    Args:
        url: 検証する URL

    Returns:
        検証済みの URL

    Raises:
        HTTPException: URL 形式が不正な場合
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL は http:// または https:// で始まる必要があります",
        )
    # URL に禁止文字チェック（スキーム以降の部分のみ）
    for char in [";", "|", "&", "$", "`"]:
        if char in url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"URL に禁止文字が含まれています: '{char}'",
            )
    return url


# ==============================================================================
# Pydantic モデル
# ==============================================================================


class NotificationSettingsUpdate(BaseModel):
    """通知設定更新リクエストモデル"""

    enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password_env: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[list[str]] = None
    notification_levels: Optional[list[str]] = None
    event_types: Optional[list[str]] = None

    @field_validator("notification_levels")
    @classmethod
    def validate_levels(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """通知レベルの値を検証する"""
        if v is not None:
            for level in v:
                if level not in ALLOWED_SEVERITY_LEVELS:
                    raise ValueError(f"不正な通知レベル: {level}")
        return v

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """イベント種別の値を検証する"""
        if v is not None:
            for evt in v:
                if evt not in ALLOWED_EVENT_TYPES:
                    raise ValueError(f"不正なイベント種別: {evt}")
        return v


class WebhookAddRequest(BaseModel):
    """Webhook 追加リクエストモデル"""

    name: str
    url: str
    type: str  # "slack" / "discord" / "generic"
    enabled: bool = True

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Webhook タイプを検証する"""
        if v not in ("slack", "discord", "generic"):
            raise ValueError("type は slack / discord / generic のいずれかである必要があります")
        return v


class TestNotificationRequest(BaseModel):
    """テスト通知送信リクエストモデル"""

    message: str
    severity: str = "info"
    event_type: str = "alert_triggered"

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """重大度を検証する"""
        if v not in ALLOWED_SEVERITY_LEVELS:
            raise ValueError(f"不正な重大度: {v}")
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """イベント種別を検証する"""
        if v not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"不正なイベント種別: {v}")
        return v


# ==============================================================================
# 通知設定エンドポイント
# ==============================================================================


@router.get("/settings")
async def get_notification_settings(
    current_user: TokenData = Depends(require_permission("read:notifications")),
) -> dict[str, Any]:
    """通知設定を取得する

    Returns:
        通知設定の辞書

    Permissions:
        read:notifications (viewer+)
    """
    settings = await notification_service.get_settings()
    # パスワード関連の機密情報はマスク
    safe_settings = {k: v for k, v in settings.items() if k != "smtp_password"}
    return {"status": "success", "settings": safe_settings}


@router.put("/settings")
async def update_notification_settings(
    body: NotificationSettingsUpdate,
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """通知設定を更新する

    Args:
        body: 更新する設定の内容

    Returns:
        更新後の通知設定の辞書

    Permissions:
        write:notifications (admin only)
    """
    # 入力バリデーション
    if body.smtp_host is not None:
        validate_text(body.smtp_host, "smtp_host")
    if body.smtp_user is not None:
        validate_text(body.smtp_user, "smtp_user")
    if body.email_from is not None:
        validate_text(body.email_from, "email_from")

    updates: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await notification_service.update_settings(updates)

    audit_log.record(
        operation="notification_settings_update",
        user_id=current_user.user_id,
        target="notification_settings",
        status="success",
        details={"updated_keys": list(updates.keys())},
    )

    safe = {k: v for k, v in updated.items() if k != "smtp_password"}
    return {"status": "success", "settings": safe}


# ==============================================================================
# テスト通知エンドポイント
# ==============================================================================


@router.post("/test")
async def send_test_notification(
    body: TestNotificationRequest,
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """テスト通知を送信する

    Args:
        body: テスト通知の内容（メッセージ・重大度・イベント種別）

    Returns:
        送信結果のリスト

    Permissions:
        write:notifications (admin only)
    """
    validate_text(body.message, "message")

    results = await notification_service.send_notification(
        event_type=body.event_type,
        message=f"[テスト] {body.message}",
        severity=body.severity,
        details={"test": True, "sent_by": current_user.user_id},
    )

    audit_log.record(
        operation="notification_test",
        user_id=current_user.user_id,
        target="notification",
        status="success",
        details={"severity": body.severity, "event_type": body.event_type, "results_count": len(results)},
    )

    return {
        "status": "success",
        "message": "テスト通知を送信しました",
        "results": results,
        "channels_notified": len(results),
    }


# ==============================================================================
# Webhook 管理エンドポイント
# ==============================================================================


@router.get("/webhooks")
async def list_webhooks(
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """登録済み Webhook 一覧を取得する

    Returns:
        Slack / Discord / Generic Webhook の一覧

    Permissions:
        write:notifications (admin only)
    """
    cfg = await notification_service.get_settings()
    return {
        "status": "success",
        "slack_webhooks": cfg.get("slack_webhooks", []),
        "discord_webhooks": cfg.get("discord_webhooks", []),
        "generic_webhooks": cfg.get("generic_webhooks", []),
    }


@router.post("/webhooks")
async def add_webhook(
    body: WebhookAddRequest,
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """Webhook を追加する

    Args:
        body: Webhook の名前・URL・タイプ・有効フラグ

    Returns:
        追加した Webhook エントリ

    Permissions:
        write:notifications (admin only)
    """
    validate_text(body.name, "name")
    validate_url(body.url)

    cfg = await notification_service.get_settings()
    webhook_entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "url": body.url,
        "enabled": body.enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    list_key = f"{body.type}_webhooks"
    webhooks: list[dict[str, Any]] = cfg.get(list_key, [])
    webhooks.append(webhook_entry)

    await notification_service.update_settings({list_key: webhooks})

    audit_log.record(
        operation="webhook_add",
        user_id=current_user.user_id,
        target=f"{body.type}_webhook",
        status="success",
        details={"name": body.name, "type": body.type},
    )

    return {"status": "success", "webhook": webhook_entry}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """指定 ID の Webhook を削除する

    Args:
        webhook_id: 削除する Webhook の UUID

    Returns:
        削除結果

    Permissions:
        write:notifications (admin only)
    """
    validate_text(webhook_id, "webhook_id")

    cfg = await notification_service.get_settings()
    deleted = False

    for list_key in ("slack_webhooks", "discord_webhooks", "generic_webhooks"):
        webhooks: list[dict[str, Any]] = cfg.get(list_key, [])
        new_list = [w for w in webhooks if w.get("id") != webhook_id]
        if len(new_list) != len(webhooks):
            await notification_service.update_settings({list_key: new_list})
            deleted = True
            break

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook ID '{webhook_id}' が見つかりません",
        )

    audit_log.record(
        operation="webhook_delete",
        user_id=current_user.user_id,
        target="webhook",
        status="success",
        details={"webhook_id": webhook_id},
    )

    return {"status": "success", "deleted_id": webhook_id}


# ==============================================================================
# 通知履歴エンドポイント
# ==============================================================================


@router.get("/history")
async def get_notification_history(
    limit: int = 50,
    current_user: TokenData = Depends(require_permission("write:notifications")),
) -> dict[str, Any]:
    """通知履歴を取得する

    Args:
        limit: 取得件数の上限（デフォルト 50、最大 200）

    Returns:
        通知履歴のリスト（新しい順）

    Permissions:
        write:notifications (admin only)
    """
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit は 1〜200 の範囲で指定してください",
        )

    history = await notification_service.get_history(limit=limit)

    return {
        "status": "success",
        "history": history,
        "count": len(history),
    }
