"""
認証・認可モジュール

JWT ベースの認証と、ユーザーロールベースの認可を実装
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
    email: str = ""


# ===================================================================
# ユーザーロール定義
# ===================================================================

ROLES = {
    "Viewer": UserRole(
        name="Viewer",
        permissions=[
            "read:status",
            "read:logs",
            "read:processes",
            "read:network",
            "read:servers",
            "read:hardware",
            "read:firewall",
            "read:packages",
            "read:ssh",
            "read:cron",
            "read:users",
            "read:bootup",
            "read:time",
            # クォータ管理
            "read:quotas",
            # DB監視（read:servers 再利用）
            # PostgreSQL 管理
            "read:postgresql",
            # MySQL/MariaDB
            "read:mysql",
        ],
    ),
    "Operator": UserRole(
        name="Operator",
        permissions=[
            "read:status",
            "read:logs",
            "read:processes",
            "read:network",
            "read:servers",
            "read:hardware",
            "read:firewall",
            "read:packages",
            "read:ssh",
            "execute:service_restart",
            # Cron ジョブ管理
            "read:cron",
            "write:cron",
            # ユーザー・グループ管理
            "read:users",
            # 承認関連
            "request:approval",
            "view:approval_policies",
            # 監査ログ（自分のログのみ）
            "read:audit",
            "read:bootup",
            "read:time",
            # クォータ管理
            "read:quotas",
            # PostgreSQL 管理
            "read:postgresql",
            # MySQL/MariaDB
            "read:mysql",
        ],
    ),
    "Approver": UserRole(
        name="Approver",
        permissions=[
            "read:status",
            "read:logs",
            "read:processes",
            "read:network",
            "read:servers",
            "read:hardware",
            "read:firewall",
            "read:packages",
            "read:ssh",
            "execute:service_restart",
            "approve:dangerous_operation",
            # Cron ジョブ管理
            "read:cron",
            "write:cron",
            # ユーザー・グループ管理
            "read:users",
            "write:users",
            # 承認関連
            "request:approval",
            "view:approval_pending",
            "execute:approval",
            "view:approval_policies",
            # 監査ログ（自分のログのみ）
            "read:audit",
            "read:bootup",
            "read:time",
            # クォータ管理
            "read:quotas",
            "write:quotas",
            # パッケージ管理（個別アップグレード）
            "write:packages",
            # PostgreSQL 管理
            "read:postgresql",
            # MySQL/MariaDB
            "read:mysql",
        ],
    ),
    "Admin": UserRole(
        name="Admin",
        permissions=[
            "read:status",
            "read:logs",
            "read:processes",
            "read:network",
            "read:servers",
            "read:hardware",
            "read:firewall",
            "write:firewall",
            "read:packages",
            "read:ssh",
            "execute:service_restart",
            "approve:dangerous_operation",
            "manage:users",
            "manage:settings",
            # Cron ジョブ管理
            "read:cron",
            "write:cron",
            # ユーザー・グループ管理
            "read:users",
            "write:users",
            # 承認関連
            "request:approval",
            "view:approval_pending",
            "execute:approval",
            "execute:approved_action",
            "view:approval_history",
            "export:approval_history",
            "view:approval_policies",
            "view:approval_stats",
            # 監査ログ（全ユーザーのログ閲覧・エクスポート）
            "read:audit",
            "export:audit",
            # 起動・シャットダウン管理
            "read:bootup",
            "write:bootup",
            # システム時刻管理
            "read:time",
            "write:time",
            # クォータ管理
            "read:quotas",
            "write:quotas",
            # パッケージ管理（個別/全体アップグレード）
            "write:packages",
            "execute:upgrade_all",
            # PostgreSQL 管理
            "read:postgresql",
            # MySQL/MariaDB
            "read:mysql",
        ],
    ),
}

# ===================================================================
# デモユーザー（開発環境のみ）
# ===================================================================

# デモユーザー（開発環境専用）
# 注意: 本番環境では使用しない
# 開発環境では簡易認証（plain text 比較）を使用
DEMO_USERS_DEV = {
    "viewer@example.com": {
        "user": User(
            user_id="user_001",
            username="viewer",
            email="viewer@example.com",
            role="Viewer",
            hashed_password="",  # 開発環境では未使用
        ),
        "plain_password": "viewer123",
    },
    "operator@example.com": {
        "user": User(
            user_id="user_002",
            username="operator",
            email="operator@example.com",
            role="Operator",
            hashed_password="",
        ),
        "plain_password": "operator123",
    },
    "approver@example.com": {
        "user": User(
            user_id="user_004",
            username="approver",
            email="approver@example.com",
            role="Approver",
            hashed_password="",
        ),
        "plain_password": "approver123",
    },
    "admin@example.com": {
        "user": User(
            user_id="user_003",
            username="admin",
            email="admin@example.com",
            role="Admin",
            hashed_password="",
        ),
        "plain_password": "admin123",
    },
}


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
    from .config import settings

    # デモユーザーから取得（開発・本番共通）
    # NOTE: 本番DBが実装されるまでの暫定措置
    user_data = DEMO_USERS_DEV.get(email)

    if not user_data:
        logger.warning(f"Authentication failed: user not found - {email}")
        return None

    user = user_data["user"]
    plain_password = user_data["plain_password"]

    if user.disabled:
        logger.warning(f"Authentication failed: user disabled - {email}")
        return None

    # 開発環境: plain text 比較
    if password != plain_password:
        logger.warning(f"Authentication failed: invalid password - {email}")
        return None

    env_label = "DEV" if settings.environment == "development" else "PROD"
    logger.info(f"Authentication successful ({env_label} mode): {email}")
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
        email: str = payload.get("email", "")

        if user_id is None or username is None or role is None:
            raise credentials_exception

        return TokenData(user_id=user_id, username=username, role=role, email=email)

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
