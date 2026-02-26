"""
サーバー管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/servers/status              - 全許可サーバーの状態一覧
  GET /api/servers/{server}/status     - 特定サーバーの状態
  GET /api/servers/{server}/version    - バージョン情報
  GET /api/servers/{server}/config     - 設定ファイル情報
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/servers", tags=["servers"])

# 許可サーバー名（APIレベルのバリデーション用）
ALLOWED_SERVERS = ("nginx", "apache2", "mysql", "postgresql", "redis")


# ===================================================================
# レスポンスモデル
# ===================================================================


class ServerStatusItem(BaseModel):
    """単一サーバーの状態"""

    service: str
    active_state: str = "unknown"
    sub_state: str = "unknown"
    load_state: str = "unknown"
    main_pid: int = 0
    enabled: str = "unknown"


class AllServerStatusResponse(BaseModel):
    """全サーバー状態一覧レスポンス"""

    status: str
    servers: list[Any] = Field(default_factory=list)
    timestamp: str


class ServerStatusResponse(BaseModel):
    """単一サーバー状態レスポンス"""

    status: str
    server: Any
    timestamp: str


class ServerVersionResponse(BaseModel):
    """サーバーバージョンレスポンス"""

    status: str
    server: str
    version: str
    timestamp: str


class ServerConfigInfoResponse(BaseModel):
    """サーバー設定ファイル情報レスポンス"""

    status: str
    server: str
    config_path: str
    exists: bool
    type: str = ""
    timestamp: str


# ===================================================================
# ヘルパー
# ===================================================================




def _validate_server_name(server: str) -> None:
    """サーバー名のallowlistチェック"""
    if server not in ALLOWED_SERVERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Server not allowed: {server}. Allowed: {', '.join(ALLOWED_SERVERS)}",
        )


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/status", response_model=AllServerStatusResponse)
async def get_all_server_status(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> AllServerStatusResponse:
    """
    全許可サーバー (nginx/apache2/mysql/postgresql/redis) の状態を一括取得

    Args:
        current_user: 現在のユーザー (read:servers 権限必須)

    Returns:
        全サーバーの状態一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"All server status requested by={current_user.username}")

    audit_log.record(
        operation="server_status_all",
        user_id=current_user.user_id,
        target="servers",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_all_server_status()
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="server_status_all",
                user_id=current_user.user_id,
                target="servers",
                status="denied",
                details={"reason": parsed.get("message", result.get("message", "unknown"))},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=parsed.get("message", result.get("message", "Server status unavailable")),
            )

        audit_log.record(
            operation="server_status_all",
            user_id=current_user.user_id,
            target="servers",
            status="success",
            details={"count": len(parsed.get("servers", []))},
        )

        return AllServerStatusResponse(**parsed)

    except SudoWrapperError as e:
        audit_log.record(
            operation="server_status_all",
            user_id=current_user.user_id,
            target="servers",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Server status failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server status retrieval failed: {str(e)}",
        )


@router.get("/{server}/status", response_model=ServerStatusResponse)
async def get_server_status(
    server: str = Path(
        ..., pattern="^(nginx|apache2|mysql|postgresql|redis)$"
    ),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> ServerStatusResponse:
    """
    特定サーバーの状態を取得

    Args:
        server: サーバー名（nginx/apache2/mysql/postgresql/redis）
        current_user: 現在のユーザー (read:servers 権限必須)

    Returns:
        サーバー状態

    Raises:
        HTTPException: 取得失敗時 / 不正なサーバー名
    """
    logger.info(f"Server status requested: server={server}, by={current_user.username}")

    audit_log.record(
        operation="server_status",
        user_id=current_user.user_id,
        target=server,
        status="attempt",
        details={"server": server},
    )

    try:
        result = sudo_wrapper.get_server_status(server)
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="server_status",
                user_id=current_user.user_id,
                target=server,
                status="denied",
                details={"reason": parsed.get("message", result.get("message", "unknown"))},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=parsed.get("message", result.get("message", "Server status unavailable")),
            )

        audit_log.record(
            operation="server_status",
            user_id=current_user.user_id,
            target=server,
            status="success",
            details={"server": server},
        )

        return ServerStatusResponse(**parsed)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="server_status",
            user_id=current_user.user_id,
            target=server,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Server status failed: server={server}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server status retrieval failed: {str(e)}",
        )


@router.get("/{server}/version", response_model=ServerVersionResponse)
async def get_server_version(
    server: str = Path(
        ..., pattern="^(nginx|apache2|mysql|postgresql|redis)$"
    ),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> ServerVersionResponse:
    """
    特定サーバーのバージョン情報を取得

    Args:
        server: サーバー名
        current_user: 現在のユーザー (read:servers 権限必須)

    Returns:
        バージョン情報

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Server version requested: server={server}, by={current_user.username}")

    audit_log.record(
        operation="server_version",
        user_id=current_user.user_id,
        target=server,
        status="attempt",
        details={"server": server},
    )

    try:
        result = sudo_wrapper.get_server_version(server)
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="server_version",
                user_id=current_user.user_id,
                target=server,
                status="denied",
                details={"reason": parsed.get("message", result.get("message", "unknown"))},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=parsed.get("message", result.get("message", "Server version unavailable")),
            )

        audit_log.record(
            operation="server_version",
            user_id=current_user.user_id,
            target=server,
            status="success",
            details={"server": server, "version": parsed.get("version", "unknown")},
        )

        return ServerVersionResponse(**parsed)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="server_version",
            user_id=current_user.user_id,
            target=server,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Server version failed: server={server}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server version retrieval failed: {str(e)}",
        )


@router.get("/{server}/config", response_model=ServerConfigInfoResponse)
async def get_server_config_info(
    server: str = Path(
        ..., pattern="^(nginx|apache2|mysql|postgresql|redis)$"
    ),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> ServerConfigInfoResponse:
    """
    特定サーバーの設定ファイルパスと存在確認（内容は返さない）

    Args:
        server: サーバー名
        current_user: 現在のユーザー (read:servers 権限必須)

    Returns:
        設定ファイル情報（パス・存在有無・種別）

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Server config info requested: server={server}, by={current_user.username}")

    audit_log.record(
        operation="server_config_info",
        user_id=current_user.user_id,
        target=server,
        status="attempt",
        details={"server": server},
    )

    try:
        result = sudo_wrapper.get_server_config_info(server)
        parsed = parse_wrapper_result(result)

        if parsed.get("status") == "error" or result.get("status") == "error":
            audit_log.record(
                operation="server_config_info",
                user_id=current_user.user_id,
                target=server,
                status="denied",
                details={"reason": parsed.get("message", result.get("message", "unknown"))},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=parsed.get("message", result.get("message", "Server config info unavailable")),
            )

        audit_log.record(
            operation="server_config_info",
            user_id=current_user.user_id,
            target=server,
            status="success",
            details={"server": server},
        )

        return ServerConfigInfoResponse(**parsed)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except SudoWrapperError as e:
        audit_log.record(
            operation="server_config_info",
            user_id=current_user.user_id,
            target=server,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Server config info failed: server={server}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server config info retrieval failed: {str(e)}",
        )
