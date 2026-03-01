"""
System Time 管理 API ルーター

システムの時刻・タイムゾーンを参照・変更します。
タイムゾーン変更は承認フロー経由のみ実行可能です。

エンドポイント一覧:
    GET  /api/time/status      - 現在の時刻・タイムゾーン情報（全ロール）
    GET  /api/time/timezones   - 利用可能なタイムゾーン一覧（全ロール）
    POST /api/time/timezone    - タイムゾーン変更（承認フロー、Admin のみ）
"""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapper, SudoWrapperError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/time", tags=["time"])
sudo_wrapper = SudoWrapper()

# ===================================================================
# タイムゾーン名の正規表現パターン（例: Asia/Tokyo, UTC, US/Eastern）
# ===================================================================
_TZ_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9/_+\-]{1,50}$")


# ===================================================================
# リクエストモデル
# ===================================================================


class TimezoneSetRequest(BaseModel):
    """タイムゾーン設定リクエスト"""

    timezone: str = Field(
        ...,
        description="設定するタイムゾーン（例: Asia/Tokyo, UTC）",
        min_length=2,
        max_length=60,
    )
    reason: str = Field(..., description="変更理由（承認リクエスト用）", min_length=1, max_length=500)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_format(cls, v: str) -> str:
        """タイムゾーン名の形式を検証します。"""
        if not _TZ_PATTERN.match(v):
            raise ValueError(
                f"タイムゾーン名の形式が無効です: '{v}' "
                "(英字・数字・スラッシュ・ハイフン・アンダースコアのみ使用可能)"
            )
        if ".." in v:
            raise ValueError("タイムゾーン名にパストラバーサルが含まれています")
        return v


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    summary="システム時刻・タイムゾーン状態取得",
    description=(
        "現在のシステム時刻、タイムゾーン、NTP同期状態を返します。\n"
        "全ロールが参照可能です。"
    ),
)
async def get_time_status(
    current_user: Annotated[TokenData, Depends(require_permission("read:time"))],
) -> dict:
    """システム時刻・タイムゾーン状態を取得します。

    Returns:
        時刻情報（system_time, utc_time, timezone, ntp_synchronized, ntp_service, rtc_time）

    Raises:
        HTTPException 500: 状態取得失敗
    """
    try:
        result = sudo_wrapper.get_time_status()

        audit_log.record(
            operation="time_status_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return result

    except SudoWrapperError as e:
        logger.error("Failed to get time status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="時刻状態の取得に失敗しました",
        ) from e


@router.get(
    "/timezones",
    summary="利用可能なタイムゾーン一覧",
    description=(
        "設定可能なタイムゾーンの一覧を返します。\n"
        "全ロールが参照可能です。"
    ),
)
async def list_timezones(
    current_user: Annotated[TokenData, Depends(require_permission("read:time"))],
) -> dict:
    """利用可能なタイムゾーン一覧を返します。

    Returns:
        タイムゾーン名のリスト

    Raises:
        HTTPException 500: 取得失敗
    """
    try:
        result = sudo_wrapper.get_timezones()

        return result

    except SudoWrapperError as e:
        logger.error("Failed to list timezones: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="タイムゾーン一覧の取得に失敗しました",
        ) from e


@router.get(
    "/ntp-servers",
    summary="NTPサーバー一覧取得",
    description="chrony または ntpd から NTP ソースサーバーの一覧を返します。",
)
async def get_ntp_servers(
    current_user: Annotated[TokenData, Depends(require_permission("read:time"))],
) -> dict:
    """NTPサーバー一覧を返します。

    Returns:
        NTPサーバー出力

    Raises:
        HTTPException 500: 取得失敗
    """
    try:
        result = sudo_wrapper.get_ntp_servers()

        audit_log.record(
            operation="time_ntp_servers_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return result

    except SudoWrapperError as e:
        logger.error("Failed to get NTP servers: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NTPサーバー一覧の取得に失敗しました",
        ) from e


@router.get(
    "/sync-status",
    summary="時刻同期状態詳細取得",
    description="timedatectl show の出力から詳細な時刻同期状態を返します。",
)
async def get_time_sync_status(
    current_user: Annotated[TokenData, Depends(require_permission("read:time"))],
) -> dict:
    """詳細な時刻同期状態を返します。

    Returns:
        時刻同期状態出力

    Raises:
        HTTPException 500: 取得失敗
    """
    try:
        result = sudo_wrapper.get_time_sync_status()

        audit_log.record(
            operation="time_sync_status_view",
            user_id=current_user.user_id,
            target="system",
            status="success",
        )

        return result

    except SudoWrapperError as e:
        logger.error("Failed to get time sync status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="時刻同期状態の取得に失敗しました",
        ) from e


@router.post(
    "/timezone",
    summary="タイムゾーン変更（承認フロー必須・Admin のみ）",
    description=(
        "システムのタイムゾーンを変更します。\n"
        "**重要**: この操作は Admin 権限 + 承認フロー経由でのみ実行可能です。\n"
        "タイムゾーン名は IANA timezone database の形式（例: Asia/Tokyo）を使用してください。"
    ),
    status_code=status.HTTP_200_OK,
)
async def set_timezone(
    request: TimezoneSetRequest,
    current_user: Annotated[TokenData, Depends(require_permission("write:time"))],
) -> dict:
    """タイムゾーンを変更します。

    Args:
        request: タイムゾーン名と変更理由
        current_user: Admin権限が必要

    Returns:
        変更結果（新しいタイムゾーン）

    Raises:
        HTTPException 400: 無効なタイムゾーン名
        HTTPException 403: 権限不足
        HTTPException 500: 変更失敗
    """
    try:
        result = sudo_wrapper.set_timezone(request.timezone)

        audit_log.record(
            operation="time_timezone_set",
            user_id=current_user.user_id,
            target=request.timezone,
            status="success",
        )

        return {
            "message": f"タイムゾーンを '{request.timezone}' に変更しました",
            "timezone": request.timezone,
            "result": result,
        }

    except SudoWrapperError as e:
        logger.error("Failed to set timezone: %s, timezone=%s", e, request.timezone)
        audit_log.record(
            operation="time_timezone_set",
            user_id=current_user.user_id,
            target=request.timezone,
            status="failure",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"タイムゾーン '{request.timezone}' への変更に失敗しました",
        ) from e
