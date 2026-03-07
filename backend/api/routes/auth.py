"""
認証 API エンドポイント
"""

import base64
import hashlib
import io
import json
import logging
import re
from datetime import timedelta
from pathlib import Path

import pyotp
import qrcode
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from ...core import get_current_user, settings
from ...core.audit_log import audit_log
from ...core.auth import TokenData, authenticate_user, create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# 2FAシークレット保存パス
_2FA_SECRETS_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "2fa_secrets.json"

# Base32文字セット（RFC 4648）
_BASE32_PATTERN = re.compile(r"^[A-Z2-7]+=*$")


# ===================================================================
# Fernet暗号化ユーティリティ
# ===================================================================


def _get_fernet() -> Fernet:
    """アプリのJWTシークレットキーからFernetキーを導出する。"""
    key_bytes = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def _load_2fa_secrets() -> dict:
    """2FAシークレットをファイルから読み込む。"""
    if not _2FA_SECRETS_PATH.exists():
        return {}
    try:
        raw = _2FA_SECRETS_PATH.read_bytes()
        fernet = _get_fernet()
        decrypted = fernet.decrypt(raw)
        return json.loads(decrypted)
    except Exception:
        return {}


def _save_2fa_secrets(data: dict) -> None:
    """2FAシークレットをファイルに保存する（Fernet暗号化）。"""
    _2FA_SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fernet = _get_fernet()
    encrypted = fernet.encrypt(json.dumps(data).encode())
    _2FA_SECRETS_PATH.write_bytes(encrypted)


def _validate_totp_secret(secret: str) -> bool:
    """TOTPシークレットがBase32文字のみ含むか検証する。"""
    return bool(_BASE32_PATTERN.match(secret)) and len(secret) >= 16


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


class TotpVerifyRequest(BaseModel):
    """TOTPコード検証リクエスト"""

    code: str


class TotpDisableRequest(BaseModel):
    """2FA無効化リクエスト（TOTPコード確認必須）"""

    code: str


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


# ===================================================================
# 2FA（二要素認証）エンドポイント
# ===================================================================


@router.get("/2fa/status")
async def get_2fa_status(current_user: TokenData = Depends(get_current_user)) -> dict:
    """現在のユーザーの2FA設定状態を返す。

    Args:
        current_user: 現在のユーザー

    Returns:
        2FA有効/無効状態と確認済みフラグ
    """
    secrets = _load_2fa_secrets()
    entry = secrets.get(current_user.user_id, {})
    return {
        "enabled": entry.get("enabled", False),
        "verified": entry.get("verified", False),
    }


@router.post("/2fa/setup")
async def setup_2fa(current_user: TokenData = Depends(get_current_user)) -> dict:
    """2FA設定を開始する。シークレットとQRコードを返す。

    既存のシークレットが検証済みの場合はリセットせず再利用する。
    未検証のセットアップ中は新しいシークレットを生成する。

    Args:
        current_user: 現在のユーザー

    Returns:
        Base32シークレット、OTPAuth URI、QRコード（Base64 PNG）
    """
    secrets = _load_2fa_secrets()
    entry = secrets.get(current_user.user_id, {})

    # 検証済みで有効な場合は再セットアップを禁止
    if entry.get("enabled") and entry.get("verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled and verified. Disable it first.",
        )

    # 新しいBase32シークレットを生成
    secret = pyotp.random_base32()

    # ユーザーIDをOTPAuth URI用アカウント名として使用
    account_name = current_user.email if current_user.email else current_user.user_id
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=account_name, issuer_name="LinuxMgmt")

    # QRコードをBase64 PNG形式で生成
    img = qrcode.make(qr_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    # 未検証状態で保存
    secrets[current_user.user_id] = {"secret": secret, "enabled": False, "verified": False}
    _save_2fa_secrets(secrets)

    audit_log.record(
        operation="2fa_setup",
        user_id=current_user.user_id,
        target="2fa",
        status="success",
    )

    return {
        "secret": secret,
        "qr_code_url": qr_uri,
        "qr_code_base64": qr_base64,
    }


@router.post("/2fa/verify")
async def verify_2fa(
    request: TotpVerifyRequest,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """TOTPコードを検証して2FAを有効化する。

    Args:
        request: 検証するTOTPコード（6桁数字）
        current_user: 現在のユーザー

    Returns:
        検証結果

    Raises:
        HTTPException: 2FA未セットアップ、または無効なコード
    """
    secrets = _load_2fa_secrets()
    entry = secrets.get(current_user.user_id)

    if not entry or not entry.get("secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not set up. Call /2fa/setup first.",
        )

    secret = entry["secret"]

    # Base32文字のみ許可（セキュリティバリデーション）
    if not _validate_totp_secret(secret):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid 2FA secret stored.",
        )

    totp = pyotp.TOTP(secret)
    # ±1ウィンドウ（30秒の許容）
    if not totp.verify(request.code, valid_window=1):
        audit_log.record(
            operation="2fa_verify",
            user_id=current_user.user_id,
            target="2fa",
            status="failure",
            details={"reason": "invalid_code"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code.",
        )

    # 検証成功: 有効化
    secrets[current_user.user_id]["enabled"] = True
    secrets[current_user.user_id]["verified"] = True
    _save_2fa_secrets(secrets)

    audit_log.record(
        operation="2fa_verify",
        user_id=current_user.user_id,
        target="2fa",
        status="success",
    )

    return {"status": "success", "message": "2FA enabled successfully."}


@router.post("/2fa/disable")
async def disable_2fa(
    request: TotpDisableRequest,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """TOTPコードを確認して2FAを無効化する。

    Args:
        request: 確認用TOTPコード
        current_user: 現在のユーザー

    Returns:
        無効化結果

    Raises:
        HTTPException: 2FA未有効化、または無効なコード
    """
    secrets = _load_2fa_secrets()
    entry = secrets.get(current_user.user_id)

    if not entry or not entry.get("enabled") or not entry.get("verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled.",
        )

    secret = entry["secret"]
    totp = pyotp.TOTP(secret)

    if not totp.verify(request.code, valid_window=1):
        audit_log.record(
            operation="2fa_disable",
            user_id=current_user.user_id,
            target="2fa",
            status="failure",
            details={"reason": "invalid_code"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code.",
        )

    # 2FA無効化
    secrets[current_user.user_id] = {"secret": "", "enabled": False, "verified": False}
    _save_2fa_secrets(secrets)

    audit_log.record(
        operation="2fa_disable",
        user_id=current_user.user_id,
        target="2fa",
        status="success",
    )

    return {"status": "success", "message": "2FA disabled successfully."}
