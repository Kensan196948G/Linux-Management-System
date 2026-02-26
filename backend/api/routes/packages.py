"""
パッケージ管理 API エンドポイント（読み取り専用）

提供エンドポイント:
  GET /api/packages/installed  - インストール済みパッケージ一覧
  GET /api/packages/updates    - 更新可能なパッケージ一覧
  GET /api/packages/security   - セキュリティ更新一覧
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

router = APIRouter(prefix="/packages", tags=["packages"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class PackageInfo(BaseModel):
    """パッケージ情報"""

    name: str
    version: str = ""
    status: str = ""
    arch: str = ""


class PackageUpdateInfo(BaseModel):
    """更新可能パッケージ情報"""

    name: str
    repository: str = ""
    new_version: str = ""
    arch: str = ""
    current_version: str = ""
    is_security: bool = False


class InstalledPackagesResponse(BaseModel):
    """インストール済みパッケージ一覧レスポンス"""

    status: str
    packages: list[Any] = Field(default_factory=list)
    count: int = 0
    timestamp: str


class PackageUpdatesResponse(BaseModel):
    """更新可能パッケージ一覧レスポンス"""

    status: str
    updates: list[Any] = Field(default_factory=list)
    count: int = 0
    message: Optional[str] = None
    timestamp: str


class SecurityUpdatesResponse(BaseModel):
    """セキュリティ更新一覧レスポンス"""

    status: str
    security_updates: list[Any] = Field(default_factory=list)
    count: int = 0
    message: Optional[str] = None
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/installed",
    response_model=InstalledPackagesResponse,
    summary="インストール済みパッケージ一覧",
    description="dpkg-query でインストール済みパッケージを取得します（読み取り専用）",
)
async def get_installed_packages(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> InstalledPackagesResponse:
    """インストール済みパッケージ一覧を取得する"""
    try:
        result = sudo_wrapper.get_packages_list()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="packages_list_read",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return InstalledPackagesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Packages list fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"パッケージ一覧取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_installed_packages: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/updates",
    response_model=PackageUpdatesResponse,
    summary="更新可能なパッケージ一覧",
    description="apt list --upgradable で更新可能なパッケージを取得します",
)
async def get_package_updates(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> PackageUpdatesResponse:
    """更新可能なパッケージ一覧を取得する"""
    try:
        result = sudo_wrapper.get_packages_updates()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="packages_updates_read",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return PackageUpdatesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Package updates fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"更新パッケージ取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_package_updates: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/security",
    response_model=SecurityUpdatesResponse,
    summary="セキュリティ更新一覧",
    description="セキュリティ系リポジトリからの更新パッケージを取得します",
)
async def get_security_updates(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> SecurityUpdatesResponse:
    """セキュリティ更新一覧を取得する"""
    try:
        result = sudo_wrapper.get_packages_security()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="packages_security_read",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return SecurityUpdatesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security updates fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"セキュリティ更新取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_security_updates: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )
