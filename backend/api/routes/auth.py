"""
認証 API エンドポイント
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from ...core import get_current_user, settings
from ...core.audit_log import audit_log
from ...core.auth import TokenData, authenticate_user, create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ===================================================================
# リクエスト・レスポンスモデル
# ===================================================================


class LoginRequest(BaseModel):
    """ログインリクエスト"""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """ログインレスポンス"""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str


class UserInfoResponse(BaseModel):
    """ユーザー情報レスポンス"""

    user_id: str
    username: str
    email: str
    role: str
    permissions: list[str]


# ===================================================================
# エンドポイント
# ===================================================================


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    ログイン

    Args:
        request: ログインリクエスト

    Returns:
        JWT アクセストークン

    Raises:
        HTTPException: 認証失敗時
    """
    logger.info(f"Login attempt: {request.email}")

    # 認証
    user = authenticate_user(request.email, request.password)

    if not user:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="login",
            user_id=request.email,
            target="system",
            status="failure",
            details={"reason": "invalid_credentials"},
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # JWT トークン生成
    access_token_expires = timedelta(minutes=settings.jwt_expiration_minutes)
    access_token = create_access_token(
        data={"sub": user.user_id, "username": user.username, "role": user.role, "email": user.email},
        expires_delta=access_token_expires,
    )

    # 監査ログ記録（成功）
    audit_log.record(
        operation="login",
        user_id=user.user_id,
        target="system",
        status="success",
        details={"role": user.role},
    )

    logger.info(f"Login successful: {user.username} ({user.role})")

    return LoginResponse(
        access_token=access_token,
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """
    現在のユーザー情報を取得

    Args:
        current_user: 現在のユーザー（JWT から取得）

    Returns:
        ユーザー情報
    """
    from ...core.auth import ROLES

    user_role = ROLES.get(current_user.role)

    return UserInfoResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email if current_user.email else f"{current_user.username}@example.com",
        role=current_user.role,
        permissions=user_role.permissions if user_role else [],
    )


@router.post("/logout")
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    ログアウト

    Note: JWT はステートレスなため、クライアント側でトークンを削除する
    """
    # 監査ログ記録
    audit_log.record(
        operation="logout",
        user_id=current_user.user_id,
        target="system",
        status="success",
    )

    logger.info(f"Logout: {current_user.username}")

    return {"status": "success", "message": "Logged out successfully"}
