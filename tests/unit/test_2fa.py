"""
二要素認証（2FA/TOTP）ユニットテスト
"""

import sys
import os

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")
os.environ["ENV"] = "dev"

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pyotp
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture(scope="module")
def client(test_client):
    """FastAPI テストクライアント（module-scoped conftest の test_client を再利用）"""
    return test_client


def _get_token(client: TestClient, email: str, password: str) -> str:
    """指定ユーザーのJWTトークンを取得する。"""
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _clean_2fa(client: TestClient, token: str, secret: str) -> None:
    """テスト後クリーンアップ: 2FAを無効化（有効な場合）。"""
    try:
        totp_code = pyotp.TOTP(secret).now()
        client.post(
            "/api/auth/2fa/disable",
            json={"code": totp_code},
            headers=_auth_headers(token),
        )
    except Exception:
        pass


# ===================================================================
# 2FAステータステスト
# ===================================================================


class TestTwoFAStatus:
    """2FA状態確認エンドポイントテスト"""

    def test_status_requires_auth(self, client):
        """認証なしで 401/403 を返す"""
        resp = client.get("/api/auth/2fa/status")
        assert resp.status_code in (401, 403)

    def test_status_returns_200_with_auth(self, client):
        """認証ありで 200 を返す"""
        token = _get_token(client, "viewer@example.com", "viewer123")
        resp = client.get("/api/auth/2fa/status", headers=_auth_headers(token))
        assert resp.status_code == 200

    def test_status_has_enabled_field(self, client):
        """enabled フィールドが存在する"""
        token = _get_token(client, "operator@example.com", "operator123")
        resp = client.get("/api/auth/2fa/status", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert "enabled" in resp.json()

    def test_status_has_verified_field(self, client):
        """verified フィールドが存在する"""
        token = _get_token(client, "operator@example.com", "operator123")
        resp = client.get("/api/auth/2fa/status", headers=_auth_headers(token))
        assert resp.status_code == 200
        assert "verified" in resp.json()

    def test_status_disabled_by_default(self, client):
        """新規ユーザーは 2FA が無効"""
        token = _get_token(client, "viewer@example.com", "viewer123")
        # user_001 のエントリが存在しないストレージをモック
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            resp = client.get("/api/auth/2fa/status", headers=_auth_headers(token))
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
            assert data["verified"] is False


# ===================================================================
# 2FAセットアップテスト
# ===================================================================


class TestTwoFASetup:
    """2FA設定開始エンドポイントテスト"""

    def test_setup_requires_auth(self, client):
        """認証なしで 401/403 を返す"""
        resp = client.post("/api/auth/2fa/setup")
        assert resp.status_code in (401, 403)

    def test_setup_returns_200(self, client):
        """認証ありで 200 を返す"""
        token = _get_token(client, "operator@example.com", "operator123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
                assert resp.status_code == 200

    def test_setup_returns_secret(self, client):
        """secret フィールドが返される"""
        token = _get_token(client, "operator@example.com", "operator123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
                assert resp.status_code == 200
                assert "secret" in resp.json()

    def test_setup_secret_is_base32(self, client):
        """secret は Base32 文字のみ含む"""
        import re
        token = _get_token(client, "operator@example.com", "operator123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
                assert resp.status_code == 200
                secret = resp.json()["secret"]
                assert re.match(r"^[A-Z2-7]+=*$", secret), f"不正な文字が含まれています: {secret}"

    def test_setup_returns_qr_code_url(self, client):
        """qr_code_url フィールドが返される"""
        token = _get_token(client, "operator@example.com", "operator123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
                assert resp.status_code == 200
                qr_url = resp.json().get("qr_code_url", "")
                assert qr_url.startswith("otpauth://totp/")

    def test_setup_returns_qr_base64(self, client):
        """qr_code_base64 フィールドが返される（data:image/png;base64,... 形式）"""
        token = _get_token(client, "operator@example.com", "operator123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
                assert resp.status_code == 200
                qr_b64 = resp.json().get("qr_code_base64", "")
                assert qr_b64.startswith("data:image/png;base64,")

    def test_setup_blocked_if_already_verified(self, client):
        """すでに有効化・検証済みの場合は 400 を返す"""
        token = _get_token(client, "operator@example.com", "operator123")
        # user_002 (operator) が検証済みのエントリをモック
        existing = {"enabled": True, "verified": True, "secret": pyotp.random_base32()}
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={"user_002": existing}):
            resp = client.post("/api/auth/2fa/setup", headers=_auth_headers(token))
            assert resp.status_code == 400


# ===================================================================
# 2FA検証テスト
# ===================================================================


class TestTwoFAVerify:
    """2FA TOTPコード検証エンドポイントテスト"""

    def test_verify_requires_auth(self, client):
        """認証なしで 401/403 を返す"""
        resp = client.post("/api/auth/2fa/verify", json={"code": "123456"})
        assert resp.status_code in (401, 403)

    def test_verify_valid_code_returns_200(self, client):
        """有効な TOTP コードで 200 を返す"""
        import time

        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        # 固定タイムステップでコードを生成（CI タイミング問題回避）
        fixed_time = int(time.time()) // 30 * 30  # 30秒境界に揃える
        valid_code = pyotp.TOTP(secret).at(fixed_time)
        # user_002 (operator) のエントリをモック
        stored = {"user_002": {"secret": secret, "enabled": False, "verified": False}}

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                with patch("time.time", return_value=float(fixed_time)):
                    resp = client.post(
                        "/api/auth/2fa/verify",
                        json={"code": valid_code},
                        headers=_auth_headers(token),
                    )
                    assert resp.status_code == 200

    def test_verify_invalid_code_returns_400(self, client):
        """無効な TOTP コードで 400 を返す"""
        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        stored = {"user_002": {"secret": secret, "enabled": False, "verified": False}}

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            resp = client.post(
                "/api/auth/2fa/verify",
                json={"code": "000000"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400

    def test_verify_without_setup_returns_400(self, client):
        """セットアップなしで検証しようとすると 400 を返す"""
        token = _get_token(client, "viewer@example.com", "viewer123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            resp = client.post(
                "/api/auth/2fa/verify",
                json={"code": "123456"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400

    def test_verify_saves_enabled_true(self, client):
        """検証成功後、ストレージに enabled=True/verified=True が保存される"""
        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        valid_code = pyotp.TOTP(secret).now()
        stored = {"user_002": {"secret": secret, "enabled": False, "verified": False}}
        saved_data = {}

        def fake_save(data):
            saved_data.update(data)

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            with patch("backend.api.routes.auth._save_2fa_secrets", side_effect=fake_save):
                resp = client.post(
                    "/api/auth/2fa/verify",
                    json={"code": valid_code},
                    headers=_auth_headers(token),
                )
                assert resp.status_code == 200
                # 保存されたデータを確認
                assert saved_data.get("user_002", {}).get("enabled") is True
                assert saved_data.get("user_002", {}).get("verified") is True


# ===================================================================
# 2FA無効化テスト
# ===================================================================


class TestTwoFADisable:
    """2FA無効化エンドポイントテスト"""

    def test_disable_requires_auth(self, client):
        """認証なしで 401/403 を返す"""
        resp = client.post("/api/auth/2fa/disable", json={"code": "123456"})
        assert resp.status_code in (401, 403)

    def test_disable_not_enabled_returns_400(self, client):
        """2FA が有効でない場合 400 を返す"""
        token = _get_token(client, "viewer@example.com", "viewer123")
        with patch("backend.api.routes.auth._load_2fa_secrets", return_value={}):
            resp = client.post(
                "/api/auth/2fa/disable",
                json={"code": "123456"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400

    def test_disable_invalid_code_returns_400(self, client):
        """無効な TOTP コードで無効化しようとすると 400 を返す"""
        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        stored = {"user_002": {"secret": secret, "enabled": True, "verified": True}}

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            resp = client.post(
                "/api/auth/2fa/disable",
                json={"code": "000000"},
                headers=_auth_headers(token),
            )
            assert resp.status_code == 400

    def test_disable_valid_code_returns_200(self, client):
        """有効な TOTP コードで正常に無効化できる"""
        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        valid_code = pyotp.TOTP(secret).now()
        stored = {"user_002": {"secret": secret, "enabled": True, "verified": True}}

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            with patch("backend.api.routes.auth._save_2fa_secrets"):
                resp = client.post(
                    "/api/auth/2fa/disable",
                    json={"code": valid_code},
                    headers=_auth_headers(token),
                )
                assert resp.status_code == 200

    def test_disable_saves_enabled_false(self, client):
        """無効化成功後、ストレージに enabled=False が保存される"""
        token = _get_token(client, "operator@example.com", "operator123")
        secret = pyotp.random_base32()
        valid_code = pyotp.TOTP(secret).now()
        stored = {"user_002": {"secret": secret, "enabled": True, "verified": True}}
        saved_data = {}

        def fake_save(data):
            saved_data.update(data)

        with patch("backend.api.routes.auth._load_2fa_secrets", return_value=stored):
            with patch("backend.api.routes.auth._save_2fa_secrets", side_effect=fake_save):
                resp = client.post(
                    "/api/auth/2fa/disable",
                    json={"code": valid_code},
                    headers=_auth_headers(token),
                )
                assert resp.status_code == 200
                assert saved_data.get("user_002", {}).get("enabled") is False
