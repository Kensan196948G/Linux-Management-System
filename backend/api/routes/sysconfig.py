"""
システム設定 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/sysconfig/hostname  - ホスト名情報
  GET /api/sysconfig/timezone  - タイムゾーン情報
  GET /api/sysconfig/locale    - ロケール情報
  GET /api/sysconfig/kernel    - カーネル情報
  GET /api/sysconfig/uptime    - システム稼働時間
  GET /api/sysconfig/modules   - カーネルモジュール一覧
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sysconfig", tags=["sysconfig"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class SysconfigHostnameResponse(BaseModel):
    """ホスト名情報レスポンス"""

    status: str
    hostname: str = ""
    fqdn: str = ""
    short: str = ""
    timestamp: str


class SysconfigTimezoneResponse(BaseModel):
    """タイムゾーン情報レスポンス"""

    status: str
    timezone: str = ""
    timezone_file: str = ""
    ntp_enabled: str = ""
    local_rtc: str = ""
    rtc_in_local_tz: str = ""
    timestamp: str


class SysconfigLocaleResponse(BaseModel):
    """ロケール情報レスポンス"""

    status: str
    lang: str = ""
    lc_ctype: str = ""
    lc_messages: str = ""
    charmap: str = ""
    timestamp: str


class SysconfigKernelResponse(BaseModel):
    """カーネル情報レスポンス"""

    status: str
    uname: str = ""
    kernel_name: str = ""
    kernel_release: str = ""
    kernel_version: str = ""
    machine: str = ""
    proc_version: str = ""
    timestamp: str


class SysconfigUptimeResponse(BaseModel):
    """システム稼働時間レスポンス"""

    status: str
    uptime_string: str = ""
    uptime_seconds: str = ""
    load_1min: str = ""
    load_5min: str = ""
    load_15min: str = ""
    timestamp: str


class SysconfigModulesResponse(BaseModel):
    """カーネルモジュール一覧レスポンス"""

    status: str
    modules: Any = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/hostname", response_model=SysconfigHostnameResponse)
async def get_sysconfig_hostname(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigHostnameResponse:
    """
    ホスト名情報を取得

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        ホスト名情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig hostname requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_hostname",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_hostname()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_hostname",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Hostname data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_hostname",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigHostnameResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_hostname",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig hostname failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hostname retrieval failed: {str(e)}",
        )


@router.get("/timezone", response_model=SysconfigTimezoneResponse)
async def get_sysconfig_timezone(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigTimezoneResponse:
    """
    タイムゾーン情報を取得

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        タイムゾーン情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig timezone requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_timezone",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_timezone()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_timezone",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Timezone data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_timezone",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigTimezoneResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_timezone",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig timezone failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Timezone retrieval failed: {str(e)}",
        )


@router.get("/locale", response_model=SysconfigLocaleResponse)
async def get_sysconfig_locale(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigLocaleResponse:
    """
    ロケール情報を取得

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        ロケール情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig locale requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_locale",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_locale()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_locale",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Locale data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_locale",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigLocaleResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_locale",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig locale failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Locale retrieval failed: {str(e)}",
        )


@router.get("/kernel", response_model=SysconfigKernelResponse)
async def get_sysconfig_kernel(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigKernelResponse:
    """
    カーネル情報を取得

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        カーネル情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig kernel requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_kernel",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_kernel()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_kernel",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Kernel data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_kernel",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigKernelResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_kernel",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig kernel failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kernel info retrieval failed: {str(e)}",
        )


@router.get("/uptime", response_model=SysconfigUptimeResponse)
async def get_sysconfig_uptime(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigUptimeResponse:
    """
    システム稼働時間を取得

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        稼働時間情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig uptime requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_uptime",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_uptime()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_uptime",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Uptime data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_uptime",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigUptimeResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_uptime",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig uptime failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uptime retrieval failed: {str(e)}",
        )


@router.get("/modules", response_model=SysconfigModulesResponse)
async def get_sysconfig_modules(
    current_user: TokenData = Depends(require_permission("read:sysconfig")),
) -> SysconfigModulesResponse:
    """
    カーネルモジュール一覧を取得 (lsmod)

    Args:
        current_user: 現在のユーザー (read:sysconfig 権限必須)

    Returns:
        カーネルモジュール一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Sysconfig modules requested by={current_user.username}")

    audit_log.record(
        operation="sysconfig_modules",
        user_id=current_user.user_id,
        target="sysconfig",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_sysconfig_modules()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error":
            audit_log.record(
                operation="sysconfig_modules",
                user_id=current_user.user_id,
                target="sysconfig",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=result.get("message", "Modules data unavailable"),
            )

        audit_log.record(
            operation="sysconfig_modules",
            user_id=current_user.user_id,
            target="sysconfig",
            status="success",
            details={},
        )

        return SysconfigModulesResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="sysconfig_modules",
            user_id=current_user.user_id,
            target="sysconfig",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Sysconfig modules failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modules retrieval failed: {str(e)}",
        )
