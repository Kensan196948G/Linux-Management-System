"""
Nginx Webサーバー管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/nginx/status      - Nginx サービス状態
  GET /api/nginx/config      - 設定内容 (nginx -T)
  GET /api/nginx/vhosts      - バーチャルホスト一覧
  GET /api/nginx/connections - 接続状況
  GET /api/nginx/logs        - アクセスログ

セキュリティ:
  - 全エンドポイントは read:nginx 権限を要求
  - allowlist方式（サブコマンドは固定）
  - 全操作を audit_log に記録
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nginx", tags=["nginx"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class NginxStatusResponse(BaseModel):
    """Nginx サービス状態レスポンス"""

    status: str
    service: Optional[str] = None
    active: Optional[str] = None
    enabled: Optional[str] = None
    version: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class NginxConfigResponse(BaseModel):
    """Nginx 設定内容レスポンス"""

    status: str
    config: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class NginxVhostsResponse(BaseModel):
    """Nginx バーチャルホスト一覧レスポンス"""

    status: str
    vhosts: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class NginxConnectionsResponse(BaseModel):
    """Nginx 接続状況レスポンス"""

    status: str
    connections_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class NginxLogsResponse(BaseModel):
    """Nginx アクセスログレスポンス"""

    status: str
    logs: Optional[str] = None
    lines: Optional[int] = None
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=NginxStatusResponse,
    summary="Nginx サービス状態取得",
    description="Nginx のサービス状態（active/enabled/version）を取得します。",
)
async def get_nginx_status(
    current_user: TokenData = Depends(require_permission("read:nginx")),
) -> dict:
    """Nginx サービス状態を取得する。

    Nginx がインストールされていない環境では unavailable を返す。
    """
    logger.info(f"Nginx status requested by={current_user.username}")

    audit_log.record(
        operation="nginx_status",
        user_id=current_user.user_id,
        target="nginx",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_nginx_status()
        data = parse_wrapper_result(result)

        audit_log.record(
            operation="nginx_status",
            user_id=current_user.user_id,
            target="nginx",
            status="success",
            details={},
        )
        return data

    except SudoWrapperError as e:
        audit_log.record(
            operation="nginx_status",
            user_id=current_user.user_id,
            target="nginx",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Nginx status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nginx status unavailable: {e}",
        )


@router.get(
    "/config",
    response_model=NginxConfigResponse,
    summary="Nginx 設定内容取得",
    description="Nginx 設定ダンプ（nginx -T）を取得します。",
)
async def get_nginx_config(
    current_user: TokenData = Depends(require_permission("read:nginx")),
) -> dict:
    """Nginx 設定内容を取得する。"""
    logger.info(f"Nginx config requested by={current_user.username}")

    audit_log.record(
        operation="nginx_config",
        user_id=current_user.user_id,
        target="nginx",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_nginx_config()
        data = parse_wrapper_result(result)

        audit_log.record(
            operation="nginx_config",
            user_id=current_user.user_id,
            target="nginx",
            status="success",
            details={},
        )
        return data

    except SudoWrapperError as e:
        audit_log.record(
            operation="nginx_config",
            user_id=current_user.user_id,
            target="nginx",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Nginx config error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nginx config unavailable: {e}",
        )


@router.get(
    "/vhosts",
    response_model=NginxVhostsResponse,
    summary="バーチャルホスト一覧取得",
    description="Nginx バーチャルホスト一覧（/etc/nginx/sites-enabled/）を取得します。",
)
async def get_nginx_vhosts(
    current_user: TokenData = Depends(require_permission("read:nginx")),
) -> dict:
    """Nginx バーチャルホスト一覧を取得する。"""
    logger.info(f"Nginx vhosts requested by={current_user.username}")

    audit_log.record(
        operation="nginx_vhosts",
        user_id=current_user.user_id,
        target="nginx",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_nginx_vhosts()
        data = parse_wrapper_result(result)

        audit_log.record(
            operation="nginx_vhosts",
            user_id=current_user.user_id,
            target="nginx",
            status="success",
            details={},
        )
        return data

    except SudoWrapperError as e:
        audit_log.record(
            operation="nginx_vhosts",
            user_id=current_user.user_id,
            target="nginx",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Nginx vhosts error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nginx vhosts unavailable: {e}",
        )


@router.get(
    "/connections",
    response_model=NginxConnectionsResponse,
    summary="接続状況取得",
    description="Nginx の接続状況（ss -tnp | grep nginx）を取得します。",
)
async def get_nginx_connections(
    current_user: TokenData = Depends(require_permission("read:nginx")),
) -> dict:
    """Nginx 接続状況を取得する。"""
    logger.info(f"Nginx connections requested by={current_user.username}")

    audit_log.record(
        operation="nginx_connections",
        user_id=current_user.user_id,
        target="nginx",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_nginx_connections()
        data = parse_wrapper_result(result)

        audit_log.record(
            operation="nginx_connections",
            user_id=current_user.user_id,
            target="nginx",
            status="success",
            details={},
        )
        return data

    except SudoWrapperError as e:
        audit_log.record(
            operation="nginx_connections",
            user_id=current_user.user_id,
            target="nginx",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Nginx connections error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nginx connections unavailable: {e}",
        )


@router.get(
    "/logs",
    response_model=NginxLogsResponse,
    summary="アクセスログ取得",
    description="Nginx アクセスログの末尾N行を取得します（最大200行）。",
)
async def get_nginx_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得行数 (1-200)"),
    current_user: TokenData = Depends(require_permission("read:nginx")),
) -> dict:
    """Nginx アクセスログを取得する。

    Args:
        lines: 取得行数 (1-200、デフォルト50)
        current_user: 現在のユーザー (read:nginx 権限必須)
    """
    logger.info(f"Nginx logs requested by={current_user.username} lines={lines}")

    audit_log.record(
        operation="nginx_logs",
        user_id=current_user.user_id,
        target="nginx",
        status="attempt",
        details={"lines": lines},
    )

    try:
        result = sudo_wrapper.get_nginx_logs(lines=lines)
        data = parse_wrapper_result(result)

        if data.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=data.get("message", "Nginx logs unavailable"),
            )

        audit_log.record(
            operation="nginx_logs",
            user_id=current_user.user_id,
            target="nginx",
            status="success",
            details={"lines": lines},
        )
        return data

    except SudoWrapperError as e:
        audit_log.record(
            operation="nginx_logs",
            user_id=current_user.user_id,
            target="nginx",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Nginx logs error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Nginx logs unavailable: {e}",
        )
