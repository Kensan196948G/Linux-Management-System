"""
Squid Proxy Server 管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/squid/status       - Squid サービス状態
  GET /api/squid/cache        - キャッシュ統計 (squidclient mgr:info)
  GET /api/squid/logs         - アクセスログ (lines=1〜200)
  GET /api/squid/config-check - 設定確認 (squid -k check)

セキュリティ:
  - 全エンドポイントは read:squid 権限を要求
  - allowlist方式（サブコマンドは固定）
  - 全操作を audit_log に記録
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/squid", tags=["squid"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class SquidStatusResponse(BaseModel):
    """Squid サービス状態レスポンス"""

    status: str
    service: Optional[str] = None
    active: Optional[str] = None
    enabled: Optional[str] = None
    version: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class SquidCacheResponse(BaseModel):
    """Squid キャッシュ統計レスポンス"""

    status: str
    cache_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class SquidLogsResponse(BaseModel):
    """Squid ログレスポンス"""

    status: str
    logs_raw: Optional[str] = None
    lines: Optional[int] = None
    message: Optional[str] = None
    timestamp: str


class SquidConfigCheckResponse(BaseModel):
    """Squid 設定構文チェックレスポンス"""

    status: str
    syntax_ok: Optional[bool] = None
    output: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=SquidStatusResponse,
    summary="Squid サービス状態取得",
    description="Squid プロキシサーバーのサービス状態（active/enabled/version）を取得します。",
)
async def get_squid_status(
    current_user: TokenData = Depends(require_permission("read:squid")),
) -> dict:
    """Squid サービス状態を取得する。

    Squid がインストールされていない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_squid_status()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="squid_status",
            target="squid",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Squid status error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Squid status unavailable: {e}",
        )


@router.get(
    "/cache",
    response_model=SquidCacheResponse,
    summary="キャッシュ統計取得",
    description="Squid キャッシュ統計（squidclient mgr:info）を取得します。",
)
async def get_squid_cache(
    current_user: TokenData = Depends(require_permission("read:squid")),
) -> dict:
    """Squid キャッシュ統計を取得する。"""
    try:
        result = sudo_wrapper.get_squid_cache()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="squid_cache",
            target="squid",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Squid cache error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Squid cache unavailable: {e}",
        )


@router.get(
    "/logs",
    response_model=SquidLogsResponse,
    summary="アクセスログ取得",
    description="Squid アクセスログ（/var/log/squid/access.log）を取得します。lines=1〜200。",
)
async def get_squid_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得するログ行数 (1〜200)"),
    current_user: TokenData = Depends(require_permission("read:squid")),
) -> dict:
    """Squid アクセスログを取得する。

    Args:
        lines: 取得するログ行数（1〜200）
    """
    try:
        result = sudo_wrapper.get_squid_logs(lines=lines)
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="squid_logs",
            target="squid",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Squid logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Squid logs unavailable: {e}",
        )


@router.get(
    "/config-check",
    response_model=SquidConfigCheckResponse,
    summary="設定構文チェック",
    description="Squid 設定ファイルの構文チェック（squid -k check）を実行します。",
)
async def get_squid_config_check(
    current_user: TokenData = Depends(require_permission("read:squid")),
) -> dict:
    """Squid 設定ファイルの構文チェックを実行する。

    syntax_ok が True であれば設定に構文エラーなし。
    """
    try:
        result = sudo_wrapper.get_squid_config_check()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="squid_config_check",
            target="squid",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Squid config-check error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Squid config-check unavailable: {e}",
        )
