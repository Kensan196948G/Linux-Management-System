"""
ディスククォータ管理 API エンドポイント

提供エンドポイント:
  GET  /api/quotas/status           - ディスククォータ全体状態
  GET  /api/quotas/users            - 全ユーザークォータ一覧
  GET  /api/quotas/user/{username}  - 特定ユーザーのクォータ情報
  GET  /api/quotas/group/{groupname}- 特定グループのクォータ情報
  GET  /api/quotas/report           - クォータレポート
  POST /api/quotas/set              - クォータ設定（承認フロー経由）
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

router = APIRouter(prefix="/quotas", tags=["quotas"])

# 許可するユーザー名/グループ名パターン
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
# 許可するファイルシステムパターン
_FS_PATTERN = re.compile(r"^(/[a-zA-Z0-9/_.-]*|/dev/[a-zA-Z0-9/_.-]+|UUID=[a-zA-Z0-9-]+)$")


def _validate_name(name: str, label: str) -> str:
    """ユーザー名/グループ名のバリデーション"""
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {label}: {name}",
        )
    return name


def _validate_filesystem(filesystem: str) -> str:
    """ファイルシステムパスのバリデーション"""
    if filesystem and not _FS_PATTERN.match(filesystem):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid filesystem: {filesystem}",
        )
    return filesystem


# ===================================================================
# レスポンスモデル
# ===================================================================


class QuotaStatusResponse(BaseModel):
    """クォータ状態レスポンス"""

    status: str
    data: Any = None
    message: Optional[str] = None
    timestamp: str = ""


class QuotaUserInfo(BaseModel):
    """ユーザークォータ情報"""

    username: str
    filesystem: str = ""
    used_kb: int = 0
    soft_limit_kb: int = 0
    hard_limit_kb: int = 0
    grace_period: str = ""
    inodes_used: int = 0
    inode_soft: int = 0
    inode_hard: int = 0


class QuotaSetRequest(BaseModel):
    """クォータ設定リクエスト"""

    type: str = Field(..., description="'user' または 'group'")
    name: str = Field(..., description="ユーザー名またはグループ名")
    filesystem: str = Field(..., description="対象ファイルシステム")
    soft_kb: int = Field(..., ge=0, description="ソフトリミット（KB）")
    hard_kb: int = Field(..., ge=0, description="ハードリミット（KB）")
    isoft: int = Field(0, ge=0, description="inode ソフトリミット")
    ihard: int = Field(0, ge=0, description="inode ハードリミット")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """タイプのバリデーション"""
        if v not in ("user", "group"):
            raise ValueError("type must be 'user' or 'group'")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """名前のバリデーション"""
        if not _NAME_PATTERN.match(v):
            raise ValueError(f"Invalid name: {v}")
        return v

    @field_validator("filesystem")
    @classmethod
    def validate_filesystem(cls, v: str) -> str:
        """ファイルシステムのバリデーション"""
        if not _FS_PATTERN.match(v):
            raise ValueError(f"Invalid filesystem: {v}")
        return v

    @field_validator("hard_kb")
    @classmethod
    def validate_hard_kb(cls, v: int, info: Any) -> int:
        """ハードリミットはソフトリミット以上であること"""
        if "soft_kb" in (info.data or {}) and v > 0 and v < info.data["soft_kb"]:
            raise ValueError("hard_kb must be >= soft_kb")
        return v


class QuotaSetResponse(BaseModel):
    """クォータ設定レスポンス"""

    status: str
    message: str
    type: str
    name: str
    filesystem: str
    soft_kb: int
    hard_kb: int


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/status",
    response_model=QuotaStatusResponse,
    summary="ディスククォータ状態",
    description="システム全体のディスククォータ状態を取得します",
)
async def get_quota_status(
    filesystem: Optional[str] = Query(None, description="対象ファイルシステム"),
    current_user: TokenData = Depends(require_permission("read:quotas")),
) -> QuotaStatusResponse:
    """ディスククォータの全体状態を取得する"""
    fs = _validate_filesystem(filesystem or "")
    try:
        result = sudo_wrapper.get_quota_status(fs)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_status_read",
            user_id=current_user.user_id,
            target=fs or "all",
            status="success",
        )
        return QuotaStatusResponse(status=parsed.get("status", "success"), data=parsed, timestamp=parsed.get("timestamp", ""))
    except SudoWrapperError as e:
        logger.error("Quota status error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"クォータ状態取得エラー: {e}",
        )


@router.get(
    "/users",
    response_model=QuotaStatusResponse,
    summary="全ユーザークォータ一覧",
    description="全ユーザーのディスククォータ使用状況一覧を取得します",
)
async def get_all_user_quotas(
    filesystem: Optional[str] = Query(None, description="対象ファイルシステム"),
    current_user: TokenData = Depends(require_permission("read:quotas")),
) -> QuotaStatusResponse:
    """全ユーザーのクォータ一覧を取得する"""
    fs = _validate_filesystem(filesystem or "")
    try:
        result = sudo_wrapper.get_all_user_quotas(fs)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_users_read",
            user_id=current_user.user_id,
            target=fs or "all",
            status="success",
        )
        return QuotaStatusResponse(status=parsed.get("status", "success"), data=parsed, timestamp=parsed.get("timestamp", ""))
    except SudoWrapperError as e:
        logger.error("Quota users list error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ユーザークォータ一覧取得エラー: {e}",
        )


@router.get(
    "/user/{username}",
    response_model=QuotaStatusResponse,
    summary="ユーザークォータ情報",
    description="特定ユーザーのディスククォータ情報を取得します",
)
async def get_user_quota(
    username: str,
    current_user: TokenData = Depends(require_permission("read:quotas")),
) -> QuotaStatusResponse:
    """特定ユーザーのクォータ情報を取得する"""
    _validate_name(username, "username")
    try:
        result = sudo_wrapper.get_user_quota(username)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_user_read",
            user_id=current_user.user_id,
            target=username,
            status="success",
        )
        return QuotaStatusResponse(status=parsed.get("status", "success"), data=parsed, timestamp=parsed.get("timestamp", ""))
    except SudoWrapperError as e:
        logger.error("User quota fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ユーザークォータ取得エラー: {e}",
        )


@router.get(
    "/group/{groupname}",
    response_model=QuotaStatusResponse,
    summary="グループクォータ情報",
    description="特定グループのディスククォータ情報を取得します",
)
async def get_group_quota(
    groupname: str,
    current_user: TokenData = Depends(require_permission("read:quotas")),
) -> QuotaStatusResponse:
    """特定グループのクォータ情報を取得する"""
    _validate_name(groupname, "groupname")
    try:
        result = sudo_wrapper.get_group_quota(groupname)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_group_read",
            user_id=current_user.user_id,
            target=groupname,
            status="success",
        )
        return QuotaStatusResponse(status=parsed.get("status", "success"), data=parsed, timestamp=parsed.get("timestamp", ""))
    except SudoWrapperError as e:
        logger.error("Group quota fetch error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"グループクォータ取得エラー: {e}",
        )


@router.get(
    "/report",
    response_model=QuotaStatusResponse,
    summary="クォータレポート",
    description="ディスククォータの詳細レポートを取得します",
)
async def get_quota_report(
    filesystem: Optional[str] = Query(None, description="対象ファイルシステム"),
    current_user: TokenData = Depends(require_permission("read:quotas")),
) -> QuotaStatusResponse:
    """クォータレポートを取得する"""
    fs = _validate_filesystem(filesystem or "")
    try:
        result = sudo_wrapper.get_quota_report(fs)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_report_read",
            user_id=current_user.user_id,
            target=fs or "all",
            status="success",
        )
        return QuotaStatusResponse(status=parsed.get("status", "success"), data=parsed, timestamp=parsed.get("timestamp", ""))
    except SudoWrapperError as e:
        logger.error("Quota report error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"クォータレポート取得エラー: {e}",
        )


@router.post(
    "/set",
    response_model=QuotaSetResponse,
    summary="クォータ設定",
    description="ユーザーまたはグループのディスククォータを設定します（Admin/Approver のみ）",
)
async def set_quota(
    request: QuotaSetRequest,
    current_user: TokenData = Depends(require_permission("write:quotas")),
) -> QuotaSetResponse:
    """ディスククォータを設定する"""
    try:
        if request.type == "user":
            result = sudo_wrapper.set_user_quota(
                request.name,
                request.filesystem,
                request.soft_kb,
                request.hard_kb,
                request.isoft,
                request.ihard,
            )
        else:
            result = sudo_wrapper.set_group_quota(
                request.name,
                request.filesystem,
                request.soft_kb,
                request.hard_kb,
                request.isoft,
                request.ihard,
            )
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="quota_set",
            user_id=current_user.user_id,
            target=f"{request.type}:{request.name}",
            status="success",
            details={
                "filesystem": request.filesystem,
                "soft_kb": request.soft_kb,
                "hard_kb": request.hard_kb,
            },
        )
        return QuotaSetResponse(
            status=parsed.get("status", "success"),
            message=parsed.get("message", f"Quota set for {request.type} {request.name}"),
            type=request.type,
            name=request.name,
            filesystem=request.filesystem,
            soft_kb=request.soft_kb,
            hard_kb=request.hard_kb,
        )
    except SudoWrapperError as e:
        logger.error("Quota set error: %s", e)
        audit_log.record(
            operation="quota_set",
            user_id=current_user.user_id,
            target=f"{request.type}:{request.name}",
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"クォータ設定エラー: {e}",
        )
