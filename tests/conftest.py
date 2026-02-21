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
def approver_token(test_client):
    """Approver ユーザーのトークン"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "approver@example.com", "password": "approver123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def approver_headers(approver_token):
    """Approver ユーザーの認証ヘッダー"""
    return {"Authorization": f"Bearer {approver_token}"}


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


@pytest.fixture
def approval_db_path(tmp_path):
    """テスト用 SQLite データベースパスを生成"""
    return str(tmp_path / "test_approval.db")


@pytest.fixture
def approval_service(approval_db_path):
    """テスト用 ApprovalService（DB初期化済み）"""
    import asyncio
    from backend.core.approval_service import ApprovalService

    service = ApprovalService(db_path=approval_db_path)
    asyncio.get_event_loop().run_until_complete(service.initialize_db())
    return service


@pytest.fixture
def approval_service_with_mock_audit(approval_db_path, audit_log):
    """テスト用 ApprovalService（監査ログモック付き）"""
    import asyncio
    from backend.core.approval_service import ApprovalService

    service = ApprovalService(db_path=approval_db_path)
    service.audit_log = audit_log
    asyncio.get_event_loop().run_until_complete(service.initialize_db())
    return service
