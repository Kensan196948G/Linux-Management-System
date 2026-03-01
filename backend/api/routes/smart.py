"""
SMART Drive Status API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/smart/disks          - SMART 対応ディスク一覧 (lsblk 経由)
  GET /api/smart/info/{disk}    - ディスク詳細情報 (smartctl -i)
  GET /api/smart/health/{disk}  - ディスク健全性 (smartctl -H)
  GET /api/smart/tests          - テスト結果一覧 (smartctl -l selftest)

セキュリティ:
  - 全エンドポイントは read:smart 権限を要求
  - allowlist 方式（ディスク名は /dev/sd[a-z], /dev/nvme[0-9]n[0-9] のみ許可）
  - 全操作を audit_log に記録
"""

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart", tags=["smart"])

# ディスク名 allowlist パターン: /dev/sd[a-z] または /dev/nvme[0-9]n[0-9]
_DISK_PATTERN = re.compile(r"^/dev/(sd[a-z]|nvme[0-9]n[0-9])$")


def _validate_disk_name(disk: str) -> str:
    """ディスク名を allowlist で検証する。

    URL パスから取得したディスク名は先頭の `/` が除去されているため、
    `/dev/` プレフィックスが省略されている場合は補完する。

    Args:
        disk: 検証対象のディスク名 (例: "dev/sda" または "/dev/sda")

    Returns:
        検証済みディスク名（先頭 `/` 付き）

    Raises:
        HTTPException: 不正なディスク名の場合
    """
    # URL パスから得た "dev/sda" を "/dev/sda" に正規化
    if not disk.startswith("/"):
        disk = "/" + disk
    if not _DISK_PATTERN.match(disk):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid disk name: {disk}. Allowed: /dev/sd[a-z], /dev/nvme[0-9]n[0-9]",
        )
    return disk


# ===================================================================
# レスポンスモデル
# ===================================================================


class SmartDisksResponse(BaseModel):
    """SMART 対応ディスク一覧レスポンス"""

    status: str
    smartctl_available: Optional[bool] = None
    lsblk: Optional[Any] = None
    message: Optional[str] = None
    timestamp: str


class SmartInfoResponse(BaseModel):
    """ディスク詳細情報レスポンス"""

    status: str
    disk: Optional[str] = None
    info_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class SmartHealthResponse(BaseModel):
    """ディスク健全性レスポンス"""

    status: str
    disk: Optional[str] = None
    health: Optional[str] = None
    output_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class SmartTestsResponse(BaseModel):
    """SMART テスト結果一覧レスポンス"""

    status: str
    tests: Optional[list[Any]] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/disks",
    response_model=SmartDisksResponse,
    summary="SMART 対応ディスク一覧取得",
    description="lsblk を使用してシステム上のブロックデバイス一覧を取得します。smartctl の有無も確認します。",
)
async def get_smart_disks(
    current_user: TokenData = Depends(require_permission("read:smart")),
) -> dict:
    """SMART 対応ディスク一覧を取得する。

    smartctl が未インストールの環境では smartctl_available=false を返す。
    """
    try:
        result = sudo_wrapper.get_smart_disks()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="smart_disks",
            target="smart",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("SMART disks error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SMART disks unavailable: {e}",
        )


@router.get(
    "/info/{disk:path}",
    response_model=SmartInfoResponse,
    summary="ディスク詳細情報取得",
    description="smartctl -i を使用して指定ディスクの詳細情報を取得します。",
)
async def get_smart_info(
    disk: str = Path(..., description="ディスクデバイスパス (例: /dev/sda)"),
    current_user: TokenData = Depends(require_permission("read:smart")),
) -> dict:
    """指定ディスクの SMART 詳細情報を取得する。

    ディスク名は allowlist で検証済み。
    """
    _validate_disk_name(disk)

    try:
        result = sudo_wrapper.get_smart_info(disk)
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="smart_info",
            target=disk,
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("SMART info error for %s: %s", disk, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SMART info unavailable: {e}",
        )


@router.get(
    "/health/{disk:path}",
    response_model=SmartHealthResponse,
    summary="ディスク健全性チェック",
    description="smartctl -H を使用して指定ディスクの健全性（PASSED/FAILED）を確認します。",
)
async def get_smart_health(
    disk: str = Path(..., description="ディスクデバイスパス (例: /dev/sda)"),
    current_user: TokenData = Depends(require_permission("read:smart")),
) -> dict:
    """指定ディスクの SMART 健全性を取得する。

    health フィールドに PASSED / FAILED / unknown が返る。
    """
    _validate_disk_name(disk)

    try:
        result = sudo_wrapper.get_smart_health(disk)
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="smart_health",
            target=disk,
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("SMART health error for %s: %s", disk, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SMART health unavailable: {e}",
        )


@router.get(
    "/tests",
    response_model=SmartTestsResponse,
    summary="SMART テスト結果一覧取得",
    description="smartctl -l selftest を使用して全ディスクの selftest ログを取得します。",
)
async def get_smart_tests(
    current_user: TokenData = Depends(require_permission("read:smart")),
) -> dict:
    """全ディスクの SMART selftest ログを取得する。

    smartctl が未インストールの環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_smart_tests()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="smart_tests",
            target="smart",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("SMART tests error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SMART tests unavailable: {e}",
        )
