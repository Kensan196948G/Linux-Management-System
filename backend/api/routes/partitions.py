"""
Disk Partitions API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/partitions/list    - パーティション一覧 (lsblk -J)
  GET /api/partitions/usage   - ディスク使用量 (df -h)
  GET /api/partitions/detail  - ブロックデバイス詳細 (blkid)

セキュリティ:
  - 全エンドポイントは read:partitions 権限を要求
  - allowlist 方式（サブコマンドは固定）
  - 全操作を audit_log に記録
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/partitions", tags=["partitions"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class PartitionsListResponse(BaseModel):
    """パーティション一覧レスポンス"""

    status: str
    partitions: Optional[Any] = None
    message: Optional[str] = None
    timestamp: str


class PartitionsUsageResponse(BaseModel):
    """ディスク使用量レスポンス"""

    status: str
    usage_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


class PartitionsDetailResponse(BaseModel):
    """ブロックデバイス詳細レスポンス"""

    status: str
    blkid_raw: Optional[str] = None
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/list",
    response_model=PartitionsListResponse,
    summary="パーティション一覧取得",
    description="lsblk -J を使用してパーティション一覧を JSON 形式で取得します。",
)
async def get_partitions_list(
    current_user: TokenData = Depends(require_permission("read:partitions")),
) -> dict:
    """パーティション一覧を取得する。

    lsblk が利用できない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_partitions_list()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="partitions_list",
            target="partitions",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Partitions list error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Partitions list unavailable: {e}",
        )


@router.get(
    "/usage",
    response_model=PartitionsUsageResponse,
    summary="ディスク使用量取得",
    description="df -h を使用して各パーティションのディスク使用量を取得します。",
)
async def get_partitions_usage(
    current_user: TokenData = Depends(require_permission("read:partitions")),
) -> dict:
    """各パーティションのディスク使用量を取得する。"""
    try:
        result = sudo_wrapper.get_partitions_usage()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="partitions_usage",
            target="partitions",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Partitions usage error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Partitions usage unavailable: {e}",
        )


@router.get(
    "/detail",
    response_model=PartitionsDetailResponse,
    summary="ブロックデバイス詳細取得",
    description="blkid を使用してブロックデバイスの UUID・ファイルシステムタイプ等の詳細を取得します。",
)
async def get_partitions_detail(
    current_user: TokenData = Depends(require_permission("read:partitions")),
) -> dict:
    """ブロックデバイスの詳細情報を取得する。

    blkid が利用できない環境では unavailable を返す。
    """
    try:
        result = sudo_wrapper.get_partitions_detail()
        data = parse_wrapper_result(result)

        audit_log.record(
            user_id=current_user.user_id,
            operation="partitions_detail",
            target="partitions",
            status="success",
        )
        return data

    except SudoWrapperError as e:
        logger.error("Partitions detail error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Partitions detail unavailable: {e}",
        )
