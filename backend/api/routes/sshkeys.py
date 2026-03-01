"""
SSH Keys 管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/ssh/keys              - SSH公開鍵一覧と鍵タイプ情報
  GET /api/ssh/sshd-config       - sshd_config の重要設定表示
  GET /api/ssh/host-keys         - ホスト鍵フィンガープリント
  GET /api/ssh/known-hosts-count - /etc/ssh/ssh_known_hosts の行数のみ（内容非表示）
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ssh", tags=["ssh-keys"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class SSHPublicKey(BaseModel):
    """SSH公開鍵エントリ"""

    filename: str
    key_type: str
    comment: str
    size_bytes: int


class SSHKeysResponse(BaseModel):
    """SSH公開鍵一覧レスポンス"""

    status: str
    keys: List[Any] = Field(default_factory=list)
    count: int = 0
    ssh_dir: str = "/etc/ssh"
    timestamp: str


class SSHdConfigResponse(BaseModel):
    """sshd_config 設定レスポンス"""

    status: str
    config_path: str = "/etc/ssh/sshd_config"
    settings: dict = Field(default_factory=dict)
    timestamp: str


class SSHHostKey(BaseModel):
    """ホスト鍵フィンガープリント"""

    key_type: str
    bits: int
    fingerprint: str
    algorithm: str
    file: str


class SSHHostKeysResponse(BaseModel):
    """ホスト鍵フィンガープリントレスポンス"""

    status: str
    host_keys: List[Any] = Field(default_factory=list)
    count: int = 0
    timestamp: str


class SSHKnownHostsCountResponse(BaseModel):
    """known_hosts 行数レスポンス"""

    status: str
    count: int = 0
    path: str = "/etc/ssh/ssh_known_hosts"
    note: str = "内容は非表示（セキュリティポリシー）"
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/keys",
    response_model=SSHKeysResponse,
    summary="SSH公開鍵一覧",
    description="/etc/ssh/ 内の公開鍵（*.pub）の一覧を取得します（鍵の内容は非表示）",
)
async def get_ssh_keys(
    current_user: TokenData = Depends(require_permission("read:sshkeys")),
) -> SSHKeysResponse:
    """SSH公開鍵一覧を取得する"""
    try:
        result = sudo_wrapper.get_ssh_keys()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="ssh_keys_read",
            user_id=current_user.user_id,
            target="ssh_keys",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return SSHKeysResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("SSH keys fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SSH鍵一覧取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_ssh_keys: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sshd-config",
    response_model=SSHdConfigResponse,
    summary="sshd_config 設定表示",
    description="sshd_config の安全なパラメータのみを返します（秘密情報は含みません）",
)
async def get_sshd_config(
    current_user: TokenData = Depends(require_permission("read:sshkeys")),
) -> SSHdConfigResponse:
    """sshd_config の重要設定を取得する"""
    try:
        result = sudo_wrapper.get_sshd_config()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="sshd_config_read",
            user_id=current_user.user_id,
            target="sshd_config",
            status="success",
            details={},
        )
        return SSHdConfigResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("sshd_config fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sshd_config取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_sshd_config: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/host-keys",
    response_model=SSHHostKeysResponse,
    summary="ホスト鍵フィンガープリント",
    description="SSHホスト鍵のフィンガープリントを返します（秘密鍵の内容は非表示）",
)
async def get_ssh_host_keys(
    current_user: TokenData = Depends(require_permission("read:sshkeys")),
) -> SSHHostKeysResponse:
    """SSHホスト鍵フィンガープリントを取得する"""
    try:
        result = sudo_wrapper.get_ssh_host_keys()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="ssh_host_keys_read",
            user_id=current_user.user_id,
            target="ssh_host_keys",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return SSHHostKeysResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("SSH host keys fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ホスト鍵取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_ssh_host_keys: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/known-hosts-count",
    response_model=SSHKnownHostsCountResponse,
    summary="known_hosts エントリ数",
    description="/etc/ssh/ssh_known_hosts のエントリ数のみを返します（内容は非表示）",
)
async def get_known_hosts_count(
    current_user: TokenData = Depends(require_permission("read:sshkeys")),
) -> SSHKnownHostsCountResponse:
    """known_hosts のエントリ数を取得する"""
    try:
        result = sudo_wrapper.get_known_hosts_count()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="ssh_known_hosts_count_read",
            user_id=current_user.user_id,
            target="ssh_known_hosts",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return SSHKnownHostsCountResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("known_hosts count fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"known_hostsカウント取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_known_hosts_count: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )
