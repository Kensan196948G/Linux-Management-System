"""
Security テスト用フィクスチャ

セッションスコープのトークンが他テストにより revoke される問題を回避するため、
セキュリティテスト用に module スコープで新規トークンを取得する。
"""

import pytest


@pytest.fixture(scope="module")
def auth_headers(test_client):
    """セキュリティテスト用の認証ヘッダー（module スコープ）"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_headers(test_client):
    """セキュリティテスト用の Admin 認証ヘッダー（module スコープ）"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    """セキュリティテスト用の Viewer 認証ヘッダー（module スコープ）"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert response.status_code == 200, f"Viewer login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    """セキュリティテスト用の Operator 認証ヘッダー（module スコープ）"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert response.status_code == 200, f"Operator login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
