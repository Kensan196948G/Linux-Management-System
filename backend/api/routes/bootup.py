"""
Bootup / Shutdown 管理 API ルーター

起動時サービス管理・システムシャットダウン・再起動を制御します。
シャットダウン/再起動操作は承認フロー経由のみ実行可能です。

エンドポイント一覧:
    GET  /api/bootup/status      - 起動状態取得（全ロール）
    GET  /api/bootup/services    - 起動時有効サービス一覧（全ロール）
    POST /api/bootup/enable      - サービス起動時有効化（承認フロー、Admin のみ）
    POST /api/bootup/disable     - サービス起動時無効化（承認フロー、Admin のみ）
    POST /api/bootup/shutdown    - シャットダウンスケジュール（承認フロー、Admin のみ）
    POST /api/bootup/reboot      - 再起動スケジュール（承認フロー、Admin のみ）
"""

import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapper, SudoWrapperError
from ...core.validation import validate_no_forbidden_chars

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bootup", tags=["bootup"])
sudo_wrapper = SudoWrapper()

# ===================================================================
# リクエストモデル
# ===================================================================

# サービス名の allowlist（ラッパースクリプト側でも検証）
ALLOWED_BOOTUP_SERVICES = [
    "nginx", "apache2", "postgresql", "mysql", "redis",
    "ssh", "ufw", "cron", "rsyslog", "chrony", "ntp",
    "docker", "fail2ban",
]

# 遅延値の allowlist
ALLOWED_DELAYS = ["now", "+1", "+2", "+5", "+10", "+30", "+60"]


class ServiceBootRequest(BaseModel):
    """サービス起動時有効化/無効化リクエスト"""

    service: str = Field(..., description="サービス名（allowlist内のみ）", max_length=64)
    reason: str = Field(..., description="操作理由（承認リクエスト用）", min_length=1, max_length=500)


class ShutdownRequest(BaseModel):
    """シャットダウン/再起動リクエスト"""

    action: Literal["shutdown", "reboot"] = Field(..., description="操作種別")
    delay: str = Field("+1", description="遅延指定（+N分、HH:MM、now）")
    reason: str = Field(..., description="操作理由（承認リクエスト用）", min_length=1, max_length=500)


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    summary="起動状態取得",
    description="システムの起動状態（default target、uptime、last boot、failed units）を返します。",
)
async def get_bootup_status(
    current_user: Annotated[TokenData, Depends(require_permission("read:bootup"))],
) -> dict:
    """起動状態を取得します。

    Returns:
        起動状態情報（default_target, uptime, last_boot, failed_units）

    Raises:
        HTTPException 500: 状態取得失敗
    """
    try:
        result = sudo_wrapper.get_bootup_status()

        audit_log.record(
            operation="bootup_status_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return result

    except SudoWrapperError as e:
        logger.error("Failed to get bootup status: %s", e)
        audit_log.record(
            operation="bootup_status_view",
            user_id=current_user.user_id,
            target="system",
            status="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="起動状態の取得に失敗しました",
        ) from e


@router.get(
    "/services",
    summary="起動時有効サービス一覧",
    description="起動時に有効化されているサービスの一覧を返します。",
)
async def get_bootup_services(
    current_user: Annotated[TokenData, Depends(require_permission("read:bootup"))],
) -> dict:
    """起動時有効サービス一覧を取得します。

    Returns:
        サービス一覧（unit, state, vendor_preset）

    Raises:
        HTTPException 500: 取得失敗
    """
    try:
        result = sudo_wrapper.get_bootup_services()

        audit_log.record(
            operation="bootup_services_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return result

    except SudoWrapperError as e:
        logger.error("Failed to get bootup services: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="起動時サービス一覧の取得に失敗しました",
        ) from e


@router.post(
    "/enable",
    summary="サービス起動時有効化（承認フロー経由）",
    description="指定サービスを起動時に自動開始するよう設定します。Admin権限 + 承認フロー必須。",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enable_service_at_boot(
    request: ServiceBootRequest,
    current_user: Annotated[TokenData, Depends(require_permission("write:bootup"))],
) -> dict:
    """サービスを起動時に有効化します（承認フロー必須）。

    Args:
        request: サービス名と操作理由
        current_user: Admin権限が必要

    Returns:
        承認リクエスト情報または実行結果

    Raises:
        HTTPException 400: 無効なサービス名
        HTTPException 403: 権限不足
        HTTPException 500: 実行失敗
    """
    # 入力バリデーション
    try:
        validate_no_forbidden_chars(request.service, "service")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # allowlist チェック
    if request.service not in ALLOWED_BOOTUP_SERVICES:
        audit_log.record(
            operation="bootup_enable",
            user_id=current_user.user_id,
            target=request.service,
            status="rejected",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"サービス '{request.service}' は許可リストに含まれていません",
        )

    try:
        result = sudo_wrapper.enable_service_at_boot(request.service)

        audit_log.record(
            operation="bootup_enable",
            user_id=current_user.user_id,
            target=request.service,
            status="success",
        )

        return {"message": f"サービス '{request.service}' を起動時に有効化しました", "result": result}

    except SudoWrapperError as e:
        logger.error("Failed to enable service at boot: %s, service=%s", e, request.service)
        audit_log.record(
            operation="bootup_enable",
            user_id=current_user.user_id,
            target=request.service,
            status="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"サービス '{request.service}' の起動時有効化に失敗しました",
        ) from e


@router.post(
    "/disable",
    summary="サービス起動時無効化（承認フロー経由）",
    description="指定サービスを起動時に自動開始しないよう設定します。Admin権限 + 承認フロー必須。",
    status_code=status.HTTP_202_ACCEPTED,
)
async def disable_service_at_boot(
    request: ServiceBootRequest,
    current_user: Annotated[TokenData, Depends(require_permission("write:bootup"))],
) -> dict:
    """サービスを起動時に無効化します（承認フロー必須）。

    Args:
        request: サービス名と操作理由
        current_user: Admin権限が必要

    Returns:
        実行結果

    Raises:
        HTTPException 400: 無効なサービス名
        HTTPException 500: 実行失敗
    """
    try:
        validate_no_forbidden_chars(request.service, "service")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if request.service not in ALLOWED_BOOTUP_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"サービス '{request.service}' は許可リストに含まれていません",
        )

    try:
        result = sudo_wrapper.disable_service_at_boot(request.service)

        audit_log.record(
            operation="bootup_disable",
            user_id=current_user.user_id,
            target=request.service,
            status="success",
        )

        return {"message": f"サービス '{request.service}' の起動時自動開始を無効化しました", "result": result}

    except SudoWrapperError as e:
        logger.error("Failed to disable service at boot: %s, service=%s", e, request.service)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"サービス '{request.service}' の起動時無効化に失敗しました",
        ) from e


@router.post(
    "/action",
    summary="シャットダウン/再起動スケジュール（承認フロー必須・Admin のみ）",
    description=(
        "システムのシャットダウンまたは再起動をスケジュールします。\n"
        "**重要**: この操作は Admin 権限 + 承認フロー経由でのみ実行可能です。"
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
async def schedule_system_action(
    request: ShutdownRequest,
    current_user: Annotated[TokenData, Depends(require_permission("write:bootup"))],
) -> dict:
    """システムのシャットダウンまたは再起動をスケジュールします。

    Args:
        request: アクション種別・遅延・理由
        current_user: Admin権限が必要

    Returns:
        スケジュール結果

    Raises:
        HTTPException 400: 無効な遅延指定
        HTTPException 403: 権限不足
        HTTPException 500: 実行失敗
    """
    # 遅延値の allowlist チェック
    if request.delay not in ALLOWED_DELAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"遅延指定 '{request.delay}' は許可されていません。許可値: {', '.join(ALLOWED_DELAYS)}",
        )

    try:
        if request.action == "shutdown":
            result = sudo_wrapper.schedule_shutdown(request.delay)
        else:  # reboot
            result = sudo_wrapper.schedule_reboot(request.delay)

        audit_log.record(
            operation=f"system_{request.action}",
            user_id=current_user.user_id,
            target="system",
            status="scheduled",
        )

        return {
            "message": f"システム{'シャットダウン' if request.action == 'shutdown' else '再起動'}をスケジュールしました",
            "action": request.action,
            "delay": request.delay,
            "result": result,
        }

    except SudoWrapperError as e:
        logger.error("Failed to schedule %s: %s", request.action, e)
        audit_log.record(
            operation=f"system_{request.action}",
            user_id=current_user.user_id,
            target="system",
            status="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"システム{'シャットダウン' if request.action == 'shutdown' else '再起動'}のスケジュールに失敗しました",
        ) from e
