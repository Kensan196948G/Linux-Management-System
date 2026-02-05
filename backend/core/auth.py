"""
認証・認可モジュール

JWT ベースの認証と、ユーザーロールベースの認可を実装
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

# パスワードハッシュ化
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Bearer トークン
security = HTTPBearer()


# ===================================================================
# データモデル
# ===================================================================


class UserRole(BaseModel):
    """ユーザーロール"""

    name: str
    permissions: list[str]


class User(BaseModel):
    """ユーザー"""

    user_id: str
    username: str
    email: str
    role: str
    hashed_password: str
    disabled: bool = False


class TokenData(BaseModel):
    """JWT トークンデータ"""

    user_id: str
    username: str
    role: str


# ===================================================================
# ユーザーロール定義
# ===================================================================

ROLES = {
    "Viewer": UserRole(
        name="Viewer",
        permissions=["read:status", "read:logs"],
    ),
    "Operator": UserRole(
        name="Operator",
        permissions=["read:status", "read:logs", "execute:service_restart"],
    ),
    "Approver": UserRole(
        name="Approver",
        permissions=[
            "read:status",
            "read:logs",
            "execute:service_restart",
            "approve:dangerous_operation",
        ],
    ),
    "Admin": UserRole(
        name="Admin",
        permissions=[
            "read:status",
            "read:logs",
            "execute:service_restart",
            "approve:dangerous_operation",
            "manage:users",
            "manage:settings",
        ],
    ),
}

# ===================================================================
# デモユーザー（開発環境のみ）
# ===================================================================

# 遅延初期化（モジュールロード時のハッシュ化を避ける）
_DEMO_USERS_CACHE = None


def get_demo_users():
    """デモユーザーを取得（遅延初期化）"""
    global _DEMO_USERS_CACHE

    if _DEMO_USERS_CACHE is None:
        _DEMO_USERS_CACHE = {
            "viewer@example.com": User(
                user_id="user_001",
                username="viewer",
                email="viewer@example.com",
                role="Viewer",
                hashed_password=pwd_context.hash("viewer123"),
            ),
            "operator@example.com": User(
                user_id="user_002",
                username="operator",
                email="operator@example.com",
                role="Operator",
                hashed_password=pwd_context.hash("operator123"),
            ),
            "admin@example.com": User(
                user_id="user_003",
                username="admin",
                email="admin@example.com",
                role="Admin",
                hashed_password=pwd_context.hash("admin123"),
            ),
        }

    return _DEMO_USERS_CACHE


# ===================================================================
# 認証関数
# ===================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """パスワード検証"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """パスワードハッシュ化"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    JWT アクセストークンを生成

    Args:
        data: トークンに含めるデータ
        expires_delta: 有効期限

    Returns:
        JWT トークン文字列
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def authenticate_user(email: str, password: str) -> Optional[User]:
    """
    ユーザー認証

    Args:
        email: メールアドレス
        password: パスワード

    Returns:
        認証成功時は User オブジェクト、失敗時は None
    """
    # デモユーザーから検索（本番環境ではデータベースから取得）
    demo_users = get_demo_users()
    user = demo_users.get(email)

    if not user:
        logger.warning(f"Authentication failed: user not found - {email}")
        return None

    if user.disabled:
        logger.warning(f"Authentication failed: user disabled - {email}")
        return None

    if not verify_password(password, user.hashed_password):
        logger.warning(f"Authentication failed: invalid password - {email}")
        return None

    logger.info(f"Authentication successful: {email}")
    return user


# ===================================================================
# 認可関数
# ===================================================================


def decode_token(token: str) -> TokenData:
    """
    JWT トークンをデコード

    Args:
        token: JWT トークン文字列

    Returns:
        TokenData オブジェクト

    Raises:
        HTTPException: トークンが無効な場合
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )

        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")

        if user_id is None or username is None or role is None:
            raise credentials_exception

        return TokenData(user_id=user_id, username=username, role=role)

    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenData:
    """
    現在のユーザーを取得（依存性注入用）

    Args:
        credentials: HTTP Bearer トークン

    Returns:
        TokenData オブジェクト
    """
    token = credentials.credentials
    return decode_token(token)


def require_permission(permission: str):
    """
    権限チェックのデコレータファクトリ

    Args:
        permission: 必要な権限（例: "execute:service_restart"）

    Returns:
        依存性注入関数
    """

    async def check_permission(current_user: TokenData = Depends(get_current_user)):
        user_role = ROLES.get(current_user.role)

        if not user_role:
            logger.error(f"Invalid role: {current_user.role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid role: {current_user.role}",
            )

        if permission not in user_role.permissions:
            logger.warning(
                f"Permission denied: user={current_user.username}, "
                f"role={current_user.role}, required={permission}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required",
            )

        return current_user

    return check_permission
