"""
FTP Server (ProFTPD/vsftpd) 管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/ftp/status   - FTP サービス状態・バージョン
  GET /api/ftp/users    - FTP 許可ユーザー一覧
  GET /api/ftp/sessions - アクティブセッション
  GET /api/ftp/logs     - FTP ログ (lines=1〜200)

セキュリティ:
  - 全エンドポイントは read:ftp 権限を要求
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

router = APIRouter(prefix="/ftp", tags=["ftp"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class FtpStatusResponse(BaseModel):
    """FTP サービス状態レスポンス"""

    status: str
    service: Optional[str] = None
    active: Optional[str] = None
    enabled: Optional[str] = None
    version: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class FtpUsersResponse(BaseModel):
    """FTP ユーザー一覧レスポンス"""

    status: str
    users_raw: Optional[str] = None
    users: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class FtpSessionsResponse(BaseModel):
    """FTP アクティブセッションレスポンス"""

    status: str
    sessions_raw: Optional[str] = None
    sessions: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class FtpLogsResponse(BaseModel):
    """FTP ログレスポンス"""

    status: str
    logs_raw: Optional[str] = None
    lines: Optional[int] = None
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=FtpStatusResponse,
    summary="FTP サービス状態取得",
    description="ProFTPD / vsftpd サービスの状態（active/enabled/version）を取得します。",
)
async def get_ftp_status(
    current_user: TokenData = Depends(require_permission("read:ftp")),
) -> dict:
    """FTP サービス状態を取得する。

    FTP サーバーがインストールされていない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_ftp_status()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="ftp_status",
            target="ftp",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("FTP status error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"FTP status unavailable: {e}",
        )


@router.get(
    "/users",
    response_model=FtpUsersResponse,
    summary="FTP ユーザー一覧取得",
    description="FTP 許可ユーザー一覧（/etc/ftpusers 等）を取得します。",
)
async def get_ftp_users(
    current_user: TokenData = Depends(require_permission("read:ftp")),
) -> dict:
    """FTP 許可ユーザー一覧を取得する。"""
    try:
        result = sudo_wrapper.get_ftp_users()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="ftp_users",
            target="ftp",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("FTP users error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"FTP users unavailable: {e}",
        )


@router.get(
    "/sessions",
    response_model=FtpSessionsResponse,
    summary="アクティブセッション取得",
    description="現在のアクティブな FTP セッション（ポート21接続）を取得します。",
)
async def get_ftp_sessions(
    current_user: TokenData = Depends(require_permission("read:ftp")),
) -> dict:
    """FTP アクティブセッションを取得する。"""
    try:
        result = sudo_wrapper.get_ftp_sessions()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="ftp_sessions",
            target="ftp",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("FTP sessions error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"FTP sessions unavailable: {e}",
        )


@router.get(
    "/logs",
    response_model=FtpLogsResponse,
    summary="FTP ログ取得",
    description="FTP サーバーのログ（journalctl / /var/log/proftpd/）を取得します。lines=1〜200。",
)
async def get_ftp_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得するログ行数 (1〜200)"),
    current_user: TokenData = Depends(require_permission("read:ftp")),
) -> dict:
    """FTP ログを取得する。

    Args:
        lines: 取得するログ行数（1〜200）
    """
    try:
        result = sudo_wrapper.get_ftp_logs(lines=lines)
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="ftp_logs",
            target="ftp",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("FTP logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"FTP logs unavailable: {e}",
        )
