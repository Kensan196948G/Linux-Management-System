"""
pytest フィクスチャ定義
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 環境変数を設定
os.environ["ENV"] = "dev"


@pytest.fixture(scope="session")
def test_client():
    """FastAPI テストクライアント"""
    from backend.api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_token(test_client):
    """認証トークンを取得"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """認証ヘッダー"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def admin_token(test_client):
    """Admin ユーザーのトークン"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def viewer_token(test_client):
    """Viewer ユーザーのトークン"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    """Admin ユーザーの認証ヘッダー"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    """Viewer ユーザーの認証ヘッダー"""
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture
def operator_headers(auth_token):
    """Operator ユーザーの認証ヘッダー（auth_token はoperatorユーザー）"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def user1_headers(test_client):
    """テスト用ユーザー1の認証ヘッダー"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "user1@example.com", "password": "user1pass123"},
    )
    if response.status_code == 200:
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    # ユーザーが存在しない場合はoperatorトークンをフォールバック
    response = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def user2_headers(test_client):
    """テスト用ユーザー2の認証ヘッダー"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "user2@example.com", "password": "user2pass123"},
    )
    if response.status_code == 200:
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    # ユーザーが存在しない場合はviewerトークンをフォールバック
    response = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def audit_log():
    """監査ログのモック"""
    from unittest.mock import MagicMock

    mock_log = MagicMock()
    mock_log.records = []

    def record_side_effect(**kwargs):
        mock_log.records.append(kwargs)

    mock_log.record.side_effect = record_side_effect
    return mock_log
