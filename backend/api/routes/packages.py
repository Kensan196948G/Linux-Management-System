"""
パッケージ管理 API エンドポイント

提供エンドポイント:
  GET  /api/packages/installed        - インストール済みパッケージ一覧
  GET  /api/packages/updates          - 更新可能なパッケージ一覧
  GET  /api/packages/security         - セキュリティ更新一覧
  GET  /api/packages/upgrade/dryrun   - アップグレードのドライラン
  POST /api/packages/upgrade          - 特定パッケージのアップグレードリクエスト
  POST /api/packages/upgrade-all      - 全パッケージのアップグレードリクエスト
  GET  /api/packages/upgradeable      - アップグレード可能パッケージ一覧 (v0.23)
  GET  /api/packages/search           - パッケージ検索 (v0.23)
  GET  /api/packages/info/{pkg}       - パッケージ詳細情報 (v0.23)
  GET  /api/packages/security-updates - セキュリティアップデート一覧 (v0.23)
"""

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/packages", tags=["packages"])

# パッケージ名の許可パターン（dpkg 準拠）
_PKG_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9+._-]{0,127}$")


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


class UpgradeDryrunResponse(BaseModel):
    """アップグレードドライランレスポンス"""

    status: str
    packages: list[Any] = Field(default_factory=list)
    count: int = 0
    message: Optional[str] = None
    timestamp: str


class UpgradePackageRequest(BaseModel):
    """特定パッケージアップグレードリクエスト"""

    package_name: str = Field(..., description="アップグレード対象パッケージ名")

    @field_validator("package_name")
    @classmethod
    def validate_package_name(cls, v: str) -> str:
        """パッケージ名のバリデーション"""
        if not _PKG_NAME_PATTERN.match(v):
            raise ValueError(f"Invalid package name: {v}")
        return v


class UpgradeResponse(BaseModel):
    """アップグレード実行レスポンス"""

    status: str
    message: str
    timestamp: str = ""


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


@router.get(
    "/upgrade/dryrun",
    response_model=UpgradeDryrunResponse,
    summary="アップグレードのドライラン",
    description="実際にはインストールせず、アップグレード対象パッケージを確認します",
)
async def get_upgrade_dryrun(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> UpgradeDryrunResponse:
    """アップグレードのドライランを実行する（読み取り専用）"""
    try:
        result = sudo_wrapper.get_packages_upgrade_dryrun()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="packages_upgrade_dryrun",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": parsed.get("count", 0)},
        )
        return UpgradeDryrunResponse(
            status=parsed.get("status", "success"),
            packages=parsed.get("packages", []),
            count=parsed.get("count", 0),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except SudoWrapperError as e:
        logger.error("Upgrade dryrun error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ドライランエラー: {e}",
        )


@router.post(
    "/upgrade",
    response_model=UpgradeResponse,
    summary="特定パッケージのアップグレード",
    description="特定パッケージをアップグレードします（Admin/Approver のみ）",
)
async def upgrade_package(
    request: UpgradePackageRequest,
    current_user: TokenData = Depends(require_permission("write:packages")),
) -> UpgradeResponse:
    """特定パッケージをアップグレードする"""
    try:
        result = sudo_wrapper.upgrade_package(request.package_name)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="package_upgrade",
            user_id=current_user.user_id,
            target=request.package_name,
            status="success",
        )
        return UpgradeResponse(
            status=parsed.get("status", "success"),
            message=parsed.get("message", f"Package {request.package_name} upgraded"),
            timestamp=parsed.get("timestamp", ""),
        )
    except SudoWrapperError as e:
        logger.error("Package upgrade error: %s", e)
        audit_log.record(
            operation="package_upgrade",
            user_id=current_user.user_id,
            target=request.package_name,
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"パッケージアップグレードエラー: {e}",
        )


@router.post(
    "/upgrade-all",
    response_model=UpgradeResponse,
    summary="全パッケージのアップグレード",
    description="更新可能な全パッケージをアップグレードします（Admin のみ）",
)
async def upgrade_all_packages(
    current_user: TokenData = Depends(require_permission("execute:upgrade_all")),
) -> UpgradeResponse:
    """全パッケージをアップグレードする"""
    try:
        result = sudo_wrapper.upgrade_all_packages()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="packages_upgrade_all",
            user_id=current_user.user_id,
            target="all_packages",
            status="success",
        )
        return UpgradeResponse(
            status=parsed.get("status", "success"),
            message=parsed.get("message", "All packages upgraded"),
            timestamp=parsed.get("timestamp", ""),
        )
    except SudoWrapperError as e:
        logger.error("Upgrade all packages error: %s", e)
        audit_log.record(
            operation="packages_upgrade_all",
            user_id=current_user.user_id,
            target="all_packages",
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"全パッケージアップグレードエラー: {e}",
        )


# ===================================================================
# v0.23 UI強化エンドポイント
# ===================================================================

_FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]


@router.get(
    "/upgradeable",
    summary="アップグレード可能なパッケージ一覧 (v0.23)",
    description="apt list --upgradeable で取得した生テキスト行を返します",
)
async def get_upgradeable_packages(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> dict:
    """アップグレード可能なパッケージ一覧を取得する"""
    try:
        result = sudo_wrapper.get_packages_upgradeable()
        lines = [line for line in result["stdout"].splitlines() if line and not line.startswith("Listing")]
        from datetime import datetime, timezone
        audit_log.record(
            operation="packages_upgradeable_read",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": len(lines)},
        )
        return {"packages": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error("get_upgradeable_packages error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/search",
    summary="パッケージ検索 (v0.23)",
    description="apt-cache search でパッケージを検索します",
)
async def search_packages_endpoint(
    q: str = Query(..., min_length=1, max_length=100),
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> dict:
    """パッケージを検索する"""
    for char in _FORBIDDEN_CHARS:
        if char in q:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Forbidden character in query: {char}")
    try:
        result = sudo_wrapper.search_packages(q)
        lines = [line for line in result["stdout"].splitlines() if line]
        audit_log.record(
            operation="packages_search",
            user_id=current_user.user_id,
            target=q,
            status="success",
            details={"count": len(lines)},
        )
        return {"query": q, "results": lines, "count": len(lines)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("search_packages error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/info/{package_name}",
    summary="パッケージ詳細情報 (v0.23)",
    description="apt-cache show でパッケージ詳細を取得します",
)
async def get_package_info_endpoint(
    package_name: str,
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> dict:
    """パッケージ詳細情報を取得する"""
    forbidden = _FORBIDDEN_CHARS + [" "]
    for char in forbidden:
        if char in package_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid package name")
    try:
        result = sudo_wrapper.get_package_info(package_name)
        if result["returncode"] != 0:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Package lookup failed")
        audit_log.record(
            operation="packages_info_read",
            user_id=current_user.user_id,
            target=package_name,
            status="success",
        )
        return {"package": package_name, "info": result["stdout"]}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("get_package_info error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get(
    "/security-updates",
    summary="セキュリティアップデート一覧 (v0.23)",
    description="apt list --upgradeable からセキュリティ更新のみを返します",
)
async def get_security_updates_v2(
    current_user: TokenData = Depends(require_permission("read:packages")),
) -> dict:
    """セキュリティアップデート一覧を取得する"""
    try:
        result = sudo_wrapper.get_packages_security_updates()
        lines = [line for line in result["stdout"].splitlines() if line]
        from datetime import datetime, timezone
        audit_log.record(
            operation="packages_security_updates_read",
            user_id=current_user.user_id,
            target="packages",
            status="success",
            details={"count": len(lines)},
        )
        return {"updates": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error("get_security_updates_v2 error: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
