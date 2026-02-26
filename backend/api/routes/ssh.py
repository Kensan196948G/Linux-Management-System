"""
SSH サーバー設定 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/ssh/status  - SSHサービスの状態
  GET /api/ssh/config  - sshd_config パース結果 + 危険設定チェック
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

router = APIRouter(prefix="/ssh", tags=["ssh"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class SSHStatusResponse(BaseModel):
    """SSHサービス状態レスポンス"""

    status: str
    service: str = "sshd"
    active_state: str = "unknown"
    enabled_state: str = "unknown"
    pid: str = "0"
    port: str = "22"
    timestamp: str


class SSHWarning(BaseModel):
    """SSH設定警告"""

    key: str
    value: str
    level: str  # CRITICAL / WARNING / LOW
    message: str


class SSHConfigResponse(BaseModel):
    """SSH設定レスポンス"""

    status: str
    config_path: str = "/etc/ssh/sshd_config"
    settings: dict = Field(default_factory=dict)
    warnings: list[Any] = Field(default_factory=list)
    warning_count: int = 0
    critical_count: int = 0
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=SSHStatusResponse,
    summary="SSHサービス状態",
    description="SSHサービスの稼働状態・ポート番号を取得します（読み取り専用）",
)
async def get_ssh_status(
    current_user: TokenData = Depends(require_permission("read:ssh")),
) -> SSHStatusResponse:
    """SSHサービスの状態を取得する"""
    try:
        result = sudo_wrapper.get_ssh_status()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="ssh_status_read",
            user_id=current_user.user_id,
            target="ssh",
            status="success",
            details={},
        )
        return SSHStatusResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("SSH status fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SSH状態取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_ssh_status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/config",
    response_model=SSHConfigResponse,
    summary="SSH設定確認",
    description="sshd_config をパースして設定値と危険設定の警告を返します",
)
async def get_ssh_config(
    current_user: TokenData = Depends(require_permission("read:ssh")),
) -> SSHConfigResponse:
    """sshd_config を読み取り、危険設定を警告する"""
    try:
        result = sudo_wrapper.get_ssh_config()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="ssh_config_read",
            user_id=current_user.user_id,
            target="ssh",
            status="success",
            details={"warning_count": parsed.get("warning_count", 0)},
        )
        return SSHConfigResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("SSH config fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SSH設定取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_ssh_config: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )
