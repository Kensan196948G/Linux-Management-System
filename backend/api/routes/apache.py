"""
Apache Webserver 管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/apache/status       - Apache サービス状態
  GET /api/apache/vhosts       - 仮想ホスト一覧
  GET /api/apache/modules      - ロード済みモジュール一覧
  GET /api/apache/config-check - 設定ファイル構文チェック

セキュリティ:
  - 全エンドポイントは read:servers 権限を要求
  - allowlist方式（サブコマンドは固定）
  - 全操作を audit_log に記録
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apache", tags=["apache"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class ApacheStatusResponse(BaseModel):
    """Apache サービス状態レスポンス"""

    status: str
    service: Optional[str] = None
    active: Optional[str] = None
    enabled: Optional[str] = None
    version: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class ApacheVhostsResponse(BaseModel):
    """Apache 仮想ホスト一覧レスポンス"""

    status: str
    vhosts_raw: Optional[str] = None
    vhosts: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class ApacheModulesResponse(BaseModel):
    """Apache モジュール一覧レスポンス"""

    status: str
    modules_raw: Optional[str] = None
    modules: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


class ApacheConfigCheckResponse(BaseModel):
    """Apache 設定構文チェックレスポンス"""

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
    response_model=ApacheStatusResponse,
    summary="Apache サービス状態取得",
    description="Apache HTTP Server のサービス状態（active/enabled/version）を取得します。",
)
async def get_apache_status(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> dict:
    """Apache サービス状態を取得する。

    Apache がインストールされていない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_apache_status()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="apache_status",
            target="apache",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Apache status error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Apache status unavailable: {e}",
        )


@router.get(
    "/vhosts",
    response_model=ApacheVhostsResponse,
    summary="仮想ホスト一覧取得",
    description="Apache 仮想ホスト一覧（apache2ctl -S）を取得します。",
)
async def get_apache_vhosts(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> dict:
    """Apache 仮想ホスト一覧を取得する。"""
    try:
        result = sudo_wrapper.get_apache_vhosts()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="apache_vhosts",
            target="apache",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Apache vhosts error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Apache vhosts unavailable: {e}",
        )


@router.get(
    "/modules",
    response_model=ApacheModulesResponse,
    summary="ロード済みモジュール一覧取得",
    description="Apache のロード済みモジュール一覧（apache2ctl -M）を取得します。",
)
async def get_apache_modules(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> dict:
    """Apache ロード済みモジュール一覧を取得する。"""
    try:
        result = sudo_wrapper.get_apache_modules()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="apache_modules",
            target="apache",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Apache modules error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Apache modules unavailable: {e}",
        )


@router.get(
    "/config-check",
    response_model=ApacheConfigCheckResponse,
    summary="設定ファイル構文チェック",
    description="Apache 設定ファイルの構文チェック（apache2ctl -t）を実行します。",
)
async def get_apache_config_check(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> dict:
    """Apache 設定ファイルの構文チェックを実行する。

    syntax_ok が True であれば設定に構文エラーなし。
    """
    try:
        result = sudo_wrapper.get_apache_config_check()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="apache_config_check",
            target="apache",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Apache config-check error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Apache config-check unavailable: {e}",
        )
