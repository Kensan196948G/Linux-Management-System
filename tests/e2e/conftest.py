"""
E2E テスト設定・フィクスチャ

Linux Management System の E2E テスト（Playwright）

テスト構成:
  - FastAPI テストサーバーをバックグラウンドで起動
  - Playwright ブラウザで実際のUIを操作
  - テスト後にサーバーを停止

使用方法:
  pytest tests/e2e/ --headed  # ブラウザを表示
  pytest tests/e2e/ --browser chromium  # Chromium で実行
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 環境変数
os.environ["ENV"] = "dev"

# テストサーバー設定
E2E_HOST = "127.0.0.1"
E2E_PORT = 18765  # 通常の開発サーバーと衝突しない特殊ポート
E2E_BASE_URL = f"http://{E2E_HOST}:{E2E_PORT}"

# テストユーザー認証情報
ADMIN_USER = {"email": "admin@example.com", "password": "admin123"}
OPERATOR_USER = {"email": "operator@example.com", "password": "operator123"}
VIEWER_USER = {"email": "viewer@example.com", "password": "viewer123"}


# ==============================================================================
# テストサーバー起動（セッションスコープ）
# ==============================================================================


class UvicornTestServer(uvicorn.Server):
    """テスト用 Uvicorn サーバー（スレッドで起動）"""

    def install_signal_handlers(self):
        pass


@pytest.fixture(scope="session")
def live_server():
    """
    E2E テスト用の実際の HTTP サーバーを起動する

    Returns:
        ベース URL（例: http://127.0.0.1:18765）
    """
    from backend.api.main import app

    config = uvicorn.Config(
        app=app,
        host=E2E_HOST,
        port=E2E_PORT,
        log_level="warning",  # E2E テスト中はログを抑制
    )
    server = UvicornTestServer(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # サーバーが起動するまで待機
    import socket

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            with socket.create_connection((E2E_HOST, E2E_PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"E2E サーバーが起動しませんでした: {E2E_BASE_URL}")

    yield E2E_BASE_URL

    # クリーンアップ
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def base_url(live_server):
    """ベース URL"""
    return live_server


# ==============================================================================
# 認証ヘルパー
# ==============================================================================


@pytest.fixture(scope="session")
def api_client(live_server):
    """httpx クライアント（ライブサーバーに接続）"""
    import httpx

    with httpx.Client(base_url=live_server, timeout=10.0) as client:
        yield client


def _get_token_direct(base_url: str, email: str, password: str) -> str:
    """httpx 経由でトークンを取得する"""
    import httpx

    response = httpx.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, f"Login failed: {response.status_code}"
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def auth_token(live_server):
    """Operator ユーザーのアクセストークン"""
    return _get_token_direct(live_server, "operator@example.com", "operator123")


@pytest.fixture(scope="session")
def admin_token(live_server):
    """Admin ユーザーのアクセストークン"""
    return _get_token_direct(live_server, "admin@example.com", "admin123")


@pytest.fixture(scope="session")
def viewer_token(live_server):
    """Viewer ユーザーのアクセストークン"""
    return _get_token_direct(live_server, "viewer@example.com", "viewer123")


def get_api_token(page, base_url: str, email: str, password: str) -> str:
    """
    API 経由でトークンを取得する（ページオブジェクトを通じて）

    Args:
        page: Playwright ページオブジェクト
        base_url: ベース URL
        email: ユーザーメール
        password: パスワード

    Returns:
        アクセストークン
    """
    response = page.request.post(
        f"{base_url}/api/auth/login",
        data={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    assert response.ok, f"Login failed: {response.status}"
    return response.json()["access_token"]
