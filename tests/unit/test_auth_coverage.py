"""
auth.py カバレッジ向上テスト

対象行:
  452  - verify_password() の return 文
  476  - create_access_token() expires_delta なし時のデフォルト有効期限
  512-513 - authenticate_user() disabled ユーザーの早期リターン
  560  - decode_token() payload フィールド欠落時の HTTPException
  600-601 - require_permission() 未定義ロール時のエラーログ + HTTPException
"""
import asyncio

import pytest
from fastapi import HTTPException
from unittest.mock import patch


class TestVerifyPassword:
    """verify_password() / get_password_hash()（line 452）"""

    def test_verify_password_correct(self):
        """正しいパスワードは True を返す"""
        from backend.core.auth import get_password_hash, verify_password

        hashed = get_password_hash("mysecret")
        assert verify_password("mysecret", hashed) is True

    def test_verify_password_wrong(self):
        """誤ったパスワードは False を返す"""
        from backend.core.auth import get_password_hash, verify_password

        hashed = get_password_hash("correct")
        assert verify_password("wrong", hashed) is False


class TestCreateAccessTokenDefaultExpiry:
    """create_access_token() expires_delta なし（line 476）"""

    def test_create_token_without_expires_delta(self):
        """expires_delta 未指定でもトークンが生成される（デフォルト有効期限を使用）"""
        from backend.core.auth import create_access_token

        token = create_access_token(data={"sub": "u1", "username": "user1", "role": "Viewer"})
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # 有効な JWT は 3 パートから成る


class TestAuthenticateUserDisabled:
    """authenticate_user() disabled ユーザー（lines 512-513）"""

    def test_authenticate_disabled_user_returns_none(self):
        """disabled=True のユーザーは None を返す"""
        from backend.core.auth import DEMO_USERS_DEV, User, authenticate_user

        disabled_user = User(
            user_id="disabled_001",
            username="disabled_user",
            email="disabled@example.com",
            role="Viewer",
            hashed_password="$2b$12$fakehash",
            disabled=True,
        )
        with patch.dict(
            DEMO_USERS_DEV,
            {"disabled@example.com": {"user": disabled_user, "plain_password": "testpass"}},
        ):
            result = authenticate_user("disabled@example.com", "testpass")
        assert result is None


class TestDecodeTokenMissingFields:
    """decode_token() payload フィールド欠落（line 560）"""

    def test_decode_token_missing_all_required_fields(self):
        """sub / username / role が欠落したトークンは 401 HTTPException"""
        from backend.core.auth import decode_token
        from backend.core.auth import settings as auth_settings
        from jose import jwt as jose_jwt

        payload = {"email": "test@example.com"}  # sub, username, role がない
        token = jose_jwt.encode(payload, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_decode_token_missing_username(self):
        """username が欠落したトークンは 401 HTTPException"""
        from backend.core.auth import decode_token
        from backend.core.auth import settings as auth_settings
        from jose import jwt as jose_jwt

        payload = {"sub": "user_001", "role": "Viewer"}  # username がない
        token = jose_jwt.encode(payload, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_decode_token_missing_role(self):
        """role が欠落したトークンは 401 HTTPException"""
        from backend.core.auth import decode_token
        from backend.core.auth import settings as auth_settings
        from jose import jwt as jose_jwt

        payload = {"sub": "user_001", "username": "user1"}  # role がない
        token = jose_jwt.encode(payload, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestRequirePermissionInvalidRole:
    """require_permission() 未定義ロール（lines 600-601）"""

    def test_invalid_role_raises_403(self):
        """ROLES に存在しないロールは 403 Forbidden + 'Invalid role' メッセージ"""
        from backend.core.auth import TokenData, require_permission

        check_fn = require_permission("read:system")
        fake_user = TokenData(
            user_id="u1",
            username="testuser",
            role="NonExistentRole",
            email="test@example.com",
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(check_fn(current_user=fake_user))
        assert exc_info.value.status_code == 403
        assert "Invalid role" in exc_info.value.detail
