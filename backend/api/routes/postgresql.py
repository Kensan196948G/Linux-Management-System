"""
PostgreSQL 管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/postgresql/status    - PostgreSQL サービス状態・バージョン
  GET /api/postgresql/databases - データベース一覧（pg_database）
  GET /api/postgresql/users     - ロール/ユーザー一覧（pg_roles）
  GET /api/postgresql/activity  - 現在の接続・クエリ（pg_stat_activity）
  GET /api/postgresql/config    - 設定パラメータ（pg_settings 主要項目）
  GET /api/postgresql/logs      - PostgreSQL ログ（lines=1〜200）

セキュリティ:
  - 全エンドポイントは read:postgresql 権限を要求
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

router = APIRouter(prefix="/postgresql", tags=["postgresql"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class PostgreSQLStatusResponse(BaseModel):
    """PostgreSQL サービス状態レスポンス"""

    status: str
    service: Optional[str] = None
    active: Optional[str] = None
    enabled: Optional[str] = None
    version: Optional[str] = None
    ready: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class PostgreSQLDatabasesResponse(BaseModel):
    """PostgreSQL データベース一覧レスポンス"""

    status: str
    databases_raw: Optional[str] = None
    databases: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class PostgreSQLUsersResponse(BaseModel):
    """PostgreSQL ユーザー/ロール一覧レスポンス"""

    status: str
    users_raw: Optional[str] = None
    users: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class PostgreSQLActivityResponse(BaseModel):
    """PostgreSQL 接続・クエリ状況レスポンス"""

    status: str
    activity_raw: Optional[str] = None
    connection_count: Optional[int] = None
    message: Optional[str] = None
    timestamp: str


class PostgreSQLConfigResponse(BaseModel):
    """PostgreSQL 設定パラメータレスポンス"""

    status: str
    config_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class PostgreSQLLogsResponse(BaseModel):
    """PostgreSQL ログレスポンス"""

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
    response_model=PostgreSQLStatusResponse,
    summary="PostgreSQL サービス状態取得",
    description="PostgreSQL のサービス状態（active/enabled/version/ready）を取得します。",
)
async def get_postgresql_status(
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL サービス状態を取得する。

    PostgreSQL がインストールされていない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_postgresql_status()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_status",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL status error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL status unavailable: {e}",
        )


@router.get(
    "/databases",
    response_model=PostgreSQLDatabasesResponse,
    summary="データベース一覧取得",
    description="PostgreSQL データベース一覧（pg_database）を取得します。",
)
async def get_postgresql_databases(
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL データベース一覧を取得する。"""
    try:
        result = sudo_wrapper.get_postgresql_databases()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_databases",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL databases error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL databases unavailable: {e}",
        )


@router.get(
    "/users",
    response_model=PostgreSQLUsersResponse,
    summary="ユーザー/ロール一覧取得",
    description="PostgreSQL ロール/ユーザー一覧（pg_roles）を取得します。",
)
async def get_postgresql_users(
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL ユーザー/ロール一覧を取得する。"""
    try:
        result = sudo_wrapper.get_postgresql_users()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_users",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL users error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL users unavailable: {e}",
        )


@router.get(
    "/activity",
    response_model=PostgreSQLActivityResponse,
    summary="接続・クエリ状況取得",
    description="PostgreSQL の現在の接続・クエリ状況（pg_stat_activity）を取得します。",
)
async def get_postgresql_activity(
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL 接続・クエリ状況を取得する。"""
    try:
        result = sudo_wrapper.get_postgresql_activity()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_activity",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL activity error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL activity unavailable: {e}",
        )


@router.get(
    "/config",
    response_model=PostgreSQLConfigResponse,
    summary="設定パラメータ取得",
    description="PostgreSQL の主要設定パラメータ（pg_settings）を取得します。",
)
async def get_postgresql_config(
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL 設定パラメータを取得する。"""
    try:
        result = sudo_wrapper.get_postgresql_config()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_config",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL config error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL config unavailable: {e}",
        )


@router.get(
    "/logs",
    response_model=PostgreSQLLogsResponse,
    summary="ログ取得",
    description="PostgreSQL ログを取得します（lines: 1〜200行、デフォルト50行）。",
)
async def get_postgresql_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得するログ行数（1〜200）"),
    current_user: TokenData = Depends(require_permission("read:postgresql")),
) -> dict:
    """PostgreSQL ログを取得する。

    lines パラメータで取得行数を指定（1〜200行）。
    """
    try:
        result = sudo_wrapper.get_postgresql_logs(lines=lines)
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="postgresql_logs",
            target="postgresql",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("PostgreSQL logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PostgreSQL logs unavailable: {e}",
        )
