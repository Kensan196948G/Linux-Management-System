"""
ユーザー・グループ管理 API エンドポイント

CLAUDE.md のセキュリティ原則に従い、allowlist検証 + sudo ラッパー経由で実行
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.constants import ALLOWED_SHELLS, FORBIDDEN_GROUPS, FORBIDDEN_USERNAMES
from ...core.sudo_wrapper import SudoWrapperError
from ...core.validation import (
    ValidationError,
    validate_groupname,
    validate_no_forbidden_chars,
    validate_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# ===================================================================
# リクエスト・レスポンスモデル
# ===================================================================


class UserListResponse(BaseModel):
    """ユーザー一覧レスポンス"""

    status: str
    total_users: int = 0
    returned_users: int = 0
    sort_by: str = ""
    users: list[dict] = []
    timestamp: str = ""


class UserDetailResponse(BaseModel):
    """ユーザー詳細レスポンス"""

    status: str
    user: dict = {}
    timestamp: str = ""


class CreateUserRequest(BaseModel):
    """ユーザー作成リクエスト"""

    username: str = Field(
        ..., min_length=1, max_length=32, pattern=r"^[a-z_][a-z0-9_-]{0,31}$"
    )
    password: str = Field(..., min_length=8, max_length=128)
    shell: str = Field("/bin/bash")
    gecos: str = Field("", max_length=256)
    groups: list[str] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    """パスワード変更リクエスト"""

    password: str = Field(..., min_length=8, max_length=128)


class DeleteUserRequest(BaseModel):
    """ユーザー削除リクエスト（オプションパラメータ）"""

    remove_home: bool = False
    backup_home: bool = False
    force_logout: bool = False


class GroupListResponse(BaseModel):
    """グループ一覧レスポンス"""

    status: str
    total_groups: int = 0
    returned_groups: int = 0
    sort_by: str = ""
    groups: list[dict] = []
    timestamp: str = ""


class CreateGroupRequest(BaseModel):
    """グループ作成リクエスト"""

    name: str = Field(
        ..., min_length=1, max_length=32, pattern=r"^[a-z_][a-z0-9_-]{0,31}$"
    )


class ModifyMembershipRequest(BaseModel):
    """グループメンバーシップ変更リクエスト"""

    action: str = Field(..., pattern=r"^(add|remove)$")
    user: str = Field(
        ..., min_length=1, max_length=32, pattern=r"^[a-z_][a-z0-9_-]{0,31}$"
    )


# ===================================================================
# ユーザー管理エンドポイント
# ===================================================================


@router.get("", response_model=UserListResponse)
async def list_users(
    sort_by: str = Query("username", pattern="^(username|uid|last_login)$"),
    limit: int = Query(100, ge=1, le=500),
    filter_locked: Optional[str] = Query(None, pattern="^(true|false)$"),
    username_filter: Optional[str] = Query(
        None, min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$"
    ),
    current_user: TokenData = Depends(require_permission("read:users")),
):
    """
    ユーザー一覧を取得

    Args:
        sort_by: ソートキー (username/uid/last_login)
        limit: 取得件数 (1-500)
        filter_locked: ロック状態フィルタ (true/false)
        username_filter: ユーザー名フィルタ
        current_user: 現在のユーザー (read:users 権限必須)

    Returns:
        ユーザー一覧
    """
    logger.info(
        f"User list requested: sort={sort_by}, limit={limit}, "
        f"filter_locked={filter_locked}, username_filter={username_filter}, "
        f"by={current_user.username}"
    )

    audit_log.record(
        operation="user_list",
        user_id=current_user.user_id,
        target="system",
        status="attempt",
        details={
            "sort_by": sort_by,
            "limit": limit,
            "filter_locked": filter_locked,
            "username_filter": username_filter,
        },
    )

    try:
        result = sudo_wrapper.list_users(
            sort_by=sort_by,
            limit=limit,
            filter_locked=filter_locked,
            username_filter=username_filter,
        )

        if result.get("status") == "error":
            audit_log.record(
                operation="user_list",
                user_id=current_user.user_id,
                target="system",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "User list denied"),
            )

        audit_log.record(
            operation="user_list",
            user_id=current_user.user_id,
            target="system",
            status="success",
            details={"returned_users": result.get("returned_users", 0)},
        )

        return UserListResponse(**result)

    except SudoWrapperError as e:
        audit_log.record(
            operation="user_list",
            user_id=current_user.user_id,
            target="system",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"User list failed: error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User list retrieval failed: {str(e)}",
        )


@router.get("/list", response_model=UserListResponse)
async def list_users_alias(
    sort_by: str = Query("username", pattern="^(username|uid|last_login)$"),
    limit: int = Query(100, ge=1, le=500),
    filter_locked: Optional[str] = Query(None, pattern="^(true|false)$"),
    username_filter: Optional[str] = Query(
        None, min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$"
    ),
    current_user: TokenData = Depends(require_permission("read:users")),
):
    """
    ユーザー一覧を取得 (/api/users/list エイリアス)

    Args:
        sort_by: ソートキー (username/uid/last_login)
        limit: 取得件数 (1-500)
        filter_locked: ロック状態フィルタ (true/false)
        username_filter: ユーザー名フィルタ
        current_user: 現在のユーザー (read:users 権限必須)

    Returns:
        ユーザー一覧
    """
    return await list_users(
        sort_by=sort_by,
        limit=limit,
        filter_locked=filter_locked,
        username_filter=username_filter,
        current_user=current_user,
    )


@router.get("/groups", response_model=GroupListResponse)
async def list_groups_alias(
    sort_by: str = Query("name", pattern="^(name|gid|member_count)$"),
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(require_permission("read:users")),
):
    """
    グループ一覧を取得 (/api/users/groups エイリアス)

    Args:
        sort_by: ソートキー (name/gid/member_count)
        limit: 取得件数 (1-500)
        current_user: 現在のユーザー (read:users 権限必須)

    Returns:
        グループ一覧
    """
    return await list_groups(
        sort_by=sort_by,
        limit=limit,
        current_user=current_user,
    )


@router.get("/{username}", response_model=UserDetailResponse)
async def get_user_detail(
    username: str,
    current_user: TokenData = Depends(require_permission("read:users")),
):
    """
    ユーザー詳細情報を取得

    Args:
        username: ユーザー名
        current_user: 現在のユーザー (read:users 権限必須)

    Returns:
        ユーザー詳細
    """
    # Python 層でのバリデーション（多層防御）
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid username: {str(e)}",
        )

    logger.info(
        f"User detail requested: username={username}, by={current_user.username}"
    )

    audit_log.record(
        operation="user_detail",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={"username": username},
    )

    try:
        result = sudo_wrapper.get_user_detail(username=username)

        if result.get("status") == "error":
            audit_log.record(
                operation="user_detail",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.get("message", "User not found"),
            )

        audit_log.record(
            operation="user_detail",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={},
        )

        return UserDetailResponse(**result)

    except SudoWrapperError as e:
        audit_log.record(
            operation="user_detail",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"User detail failed: username={username}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User detail retrieval failed: {str(e)}",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    ユーザーを作成

    Args:
        request: ユーザー作成リクエスト
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        作成結果
    """
    # Python 層でのバリデーション（多層防御）
    try:
        validate_username(request.username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid username: {str(e)}",
        )

    # FORBIDDEN_USERNAMES チェック
    if request.username in FORBIDDEN_USERNAMES:
        logger.warning(
            f"Forbidden username creation attempt: {request.username}, "
            f"by={current_user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Username is reserved: {request.username}",
        )

    # シェル allowlist チェック
    if request.shell not in ALLOWED_SHELLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shell not allowed: {request.shell}. Allowed: {', '.join(ALLOWED_SHELLS)}",
        )

    # GECOS フィールドの禁止文字チェック
    if request.gecos:
        try:
            validate_no_forbidden_chars(request.gecos, "gecos")
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid gecos: {str(e)}",
            )

    # グループ名の検証
    for group in request.groups:
        try:
            validate_groupname(group)
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid group name '{group}': {str(e)}",
            )

    logger.info(
        f"User creation requested: username={request.username}, "
        f"shell={request.shell}, by={current_user.username}"
    )

    audit_log.record(
        operation="user_create",
        user_id=current_user.user_id,
        target=request.username,
        status="attempt",
        details={
            "username": request.username,
            "shell": request.shell,
            "groups": request.groups,
        },
    )

    try:
        # パスワードを bcrypt ハッシュに変換
        from ...core.auth import get_password_hash

        password_hash = get_password_hash(request.password)

        result = sudo_wrapper.add_user(  # nosec B604 - 'shell' kwarg sets login shell path, not subprocess invocation
            username=request.username,
            password_hash=password_hash,
            shell=request.shell,
            gecos=request.gecos,
            groups=request.groups if request.groups else None,
        )

        if result.get("status") == "error":
            audit_log.record(
                operation="user_create",
                user_id=current_user.user_id,
                target=request.username,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "User creation denied"),
            )

        audit_log.record(
            operation="user_create",
            user_id=current_user.user_id,
            target=request.username,
            status="success",
            details={"username": request.username},
        )

        logger.info(
            f"User created: username={request.username}, by={current_user.username}"
        )

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="user_create",
            user_id=current_user.user_id,
            target=request.username,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"User creation failed: username={request.username}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User creation failed: {str(e)}",
        )


@router.delete("/{username}")
async def delete_user(
    username: str,
    remove_home: bool = Query(False),
    backup_home: bool = Query(False),
    force_logout: bool = Query(False),
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    ユーザーを削除

    Args:
        username: 削除対象ユーザー名
        remove_home: ホームディレクトリを削除するか
        backup_home: ホームディレクトリをバックアップするか
        force_logout: アクティブセッションを強制ログアウトするか
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        削除結果
    """
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid username: {str(e)}",
        )

    logger.info(
        f"User deletion requested: username={username}, "
        f"remove_home={remove_home}, backup_home={backup_home}, "
        f"force_logout={force_logout}, by={current_user.username}"
    )

    audit_log.record(
        operation="user_delete",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={
            "username": username,
            "remove_home": remove_home,
            "backup_home": backup_home,
            "force_logout": force_logout,
        },
    )

    try:
        result = sudo_wrapper.delete_user(
            username=username,
            remove_home=remove_home,
            backup_home=backup_home,
            force_logout=force_logout,
        )

        if result.get("status") == "error":
            audit_log.record(
                operation="user_delete",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "User deletion denied"),
            )

        audit_log.record(
            operation="user_delete",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={"username": username},
        )

        logger.info(f"User deleted: username={username}, by={current_user.username}")

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="user_delete",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"User deletion failed: username={username}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User deletion failed: {str(e)}",
        )


@router.put("/{username}/password")
async def change_password(
    username: str,
    request: ChangePasswordRequest,
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    ユーザーパスワードを変更

    Args:
        username: 対象ユーザー名
        request: パスワード変更リクエスト
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        変更結果
    """
    try:
        validate_username(username)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid username: {str(e)}",
        )

    logger.info(
        f"Password change requested: username={username}, by={current_user.username}"
    )

    audit_log.record(
        operation="user_change_password",
        user_id=current_user.user_id,
        target=username,
        status="attempt",
        details={"username": username},
    )

    try:
        from ...core.auth import get_password_hash

        password_hash = get_password_hash(request.password)

        result = sudo_wrapper.change_user_password(
            username=username,
            password_hash=password_hash,
        )

        if result.get("status") == "error":
            audit_log.record(
                operation="user_change_password",
                user_id=current_user.user_id,
                target=username,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Password change denied"),
            )

        audit_log.record(
            operation="user_change_password",
            user_id=current_user.user_id,
            target=username,
            status="success",
            details={"username": username},
        )

        logger.info(
            f"Password changed: username={username}, by={current_user.username}"
        )

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="user_change_password",
            user_id=current_user.user_id,
            target=username,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Password change failed: username={username}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password change failed: {str(e)}",
        )


# ===================================================================
# グループ管理エンドポイント
# ===================================================================


@router.get("/groups/list", response_model=GroupListResponse)
async def list_groups(
    sort_by: str = Query("name", pattern="^(name|gid|member_count)$"),
    limit: int = Query(100, ge=1, le=500),
    current_user: TokenData = Depends(require_permission("read:users")),
):
    """
    グループ一覧を取得

    Args:
        sort_by: ソートキー (name/gid/member_count)
        limit: 取得件数 (1-500)
        current_user: 現在のユーザー (read:users 権限必須)

    Returns:
        グループ一覧
    """
    logger.info(
        f"Group list requested: sort={sort_by}, limit={limit}, "
        f"by={current_user.username}"
    )

    audit_log.record(
        operation="group_list",
        user_id=current_user.user_id,
        target="system",
        status="attempt",
        details={"sort_by": sort_by, "limit": limit},
    )

    try:
        result = sudo_wrapper.list_groups(sort_by=sort_by, limit=limit)

        if result.get("status") == "error":
            audit_log.record(
                operation="group_list",
                user_id=current_user.user_id,
                target="system",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "Group list denied"),
            )

        audit_log.record(
            operation="group_list",
            user_id=current_user.user_id,
            target="system",
            status="success",
            details={"returned_groups": result.get("returned_groups", 0)},
        )

        return GroupListResponse(**result)

    except SudoWrapperError as e:
        audit_log.record(
            operation="group_list",
            user_id=current_user.user_id,
            target="system",
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Group list failed: error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group list retrieval failed: {str(e)}",
        )


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    request: CreateGroupRequest,
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    グループを作成

    Args:
        request: グループ作成リクエスト
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        作成結果
    """
    try:
        validate_groupname(request.name)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group name: {str(e)}",
        )

    # FORBIDDEN_GROUPS チェック
    if request.name in FORBIDDEN_GROUPS:
        logger.warning(
            f"Forbidden group creation attempt: {request.name}, "
            f"by={current_user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group name is reserved: {request.name}",
        )

    # FORBIDDEN_USERNAMES との衝突チェック
    if request.name in FORBIDDEN_USERNAMES:
        logger.warning(
            f"Group/username collision attempt: {request.name}, "
            f"by={current_user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group name collides with reserved username: {request.name}",
        )

    logger.info(
        f"Group creation requested: name={request.name}, by={current_user.username}"
    )

    audit_log.record(
        operation="group_create",
        user_id=current_user.user_id,
        target=request.name,
        status="attempt",
        details={"name": request.name},
    )

    try:
        result = sudo_wrapper.add_group(name=request.name)

        if result.get("status") == "error":
            audit_log.record(
                operation="group_create",
                user_id=current_user.user_id,
                target=request.name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Group creation denied"),
            )

        audit_log.record(
            operation="group_create",
            user_id=current_user.user_id,
            target=request.name,
            status="success",
            details={"name": request.name},
        )

        logger.info(f"Group created: name={request.name}, by={current_user.username}")

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="group_create",
            user_id=current_user.user_id,
            target=request.name,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Group creation failed: name={request.name}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group creation failed: {str(e)}",
        )


@router.delete("/groups/{name}")
async def delete_group(
    name: str,
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    グループを削除

    Args:
        name: 削除対象グループ名
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        削除結果
    """
    try:
        validate_groupname(name)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group name: {str(e)}",
        )

    logger.info(f"Group deletion requested: name={name}, by={current_user.username}")

    audit_log.record(
        operation="group_delete",
        user_id=current_user.user_id,
        target=name,
        status="attempt",
        details={"name": name},
    )

    try:
        result = sudo_wrapper.delete_group(name=name)

        if result.get("status") == "error":
            audit_log.record(
                operation="group_delete",
                user_id=current_user.user_id,
                target=name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Group deletion denied"),
            )

        audit_log.record(
            operation="group_delete",
            user_id=current_user.user_id,
            target=name,
            status="success",
            details={"name": name},
        )

        logger.info(f"Group deleted: name={name}, by={current_user.username}")

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="group_delete",
            user_id=current_user.user_id,
            target=name,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Group deletion failed: name={name}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group deletion failed: {str(e)}",
        )


@router.put("/groups/{name}/members")
async def modify_group_membership(
    name: str,
    request: ModifyMembershipRequest,
    current_user: TokenData = Depends(require_permission("write:users")),
):
    """
    グループメンバーシップを変更

    Args:
        name: グループ名
        request: メンバーシップ変更リクエスト (action: add/remove, user: username)
        current_user: 現在のユーザー (write:users 権限必須)

    Returns:
        変更結果
    """
    try:
        validate_groupname(name)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid group name: {str(e)}",
        )

    try:
        validate_username(request.user)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid username: {str(e)}",
        )

    # FORBIDDEN_GROUPS チェック
    if name in FORBIDDEN_GROUPS:
        logger.warning(
            f"Forbidden group membership modification attempt: group={name}, "
            f"by={current_user.username}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Group is forbidden: {name}",
        )

    logger.info(
        f"Group membership modification requested: group={name}, "
        f"action={request.action}, user={request.user}, by={current_user.username}"
    )

    audit_log.record(
        operation="group_modify_membership",
        user_id=current_user.user_id,
        target=name,
        status="attempt",
        details={
            "group": name,
            "action": request.action,
            "target_user": request.user,
        },
    )

    try:
        result = sudo_wrapper.modify_group_membership(
            group=name,
            action=request.action,
            user=request.user,
        )

        if result.get("status") == "error":
            audit_log.record(
                operation="group_modify_membership",
                user_id=current_user.user_id,
                target=name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Group membership modification denied"),
            )

        audit_log.record(
            operation="group_modify_membership",
            user_id=current_user.user_id,
            target=name,
            status="success",
            details={
                "group": name,
                "action": request.action,
                "target_user": request.user,
            },
        )

        logger.info(
            f"Group membership modified: group={name}, action={request.action}, "
            f"user={request.user}, by={current_user.username}"
        )

        return result

    except SudoWrapperError as e:
        audit_log.record(
            operation="group_modify_membership",
            user_id=current_user.user_id,
            target=name,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Group membership modification failed: group={name}, error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Group membership modification failed: {str(e)}",
        )
