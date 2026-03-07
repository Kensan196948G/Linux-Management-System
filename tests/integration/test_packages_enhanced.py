"""
パッケージ管理強化 - 統合テスト (test_packages_enhanced.py)

テスト対象エンドポイント:
  GET  /api/packages/upgradable       - アップグレード可能パッケージ一覧（構造化）
  GET  /api/packages/show/{name}      - パッケージ詳細情報
  POST /api/packages/install          - パッケージインストール承認リクエスト
  POST /api/packages/remove           - パッケージ削除承認リクエスト

テスト件数: 25件
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# フィクスチャ
# ============================================================================


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient"""
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="module")
def init_db(tmp_path_factory):
    """モジュール単位でテスト用 DB を初期化する"""
    from backend.api.routes import packages as pkg_module

    tmp_db = str(tmp_path_factory.mktemp("pkg_db") / "test_pkg.db")
    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_db) as conn:
        conn.executescript(schema_sql)
    pkg_module._approval_service.db_path = tmp_db
    return tmp_db


@pytest.fixture(autouse=True)
def cleanup_db(init_db):
    """各テスト前に承認テーブルをクリア"""
    with sqlite3.connect(init_db) as conn:
        conn.execute("DELETE FROM approval_history")
        conn.execute("DELETE FROM approval_requests")
        conn.commit()
    yield


@pytest.fixture
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def approver_headers(client):
    resp = client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(client):
    resp = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


SAMPLE_UPDATES = {
    "status": "success",
    "updates": [
        {
            "name": "openssl",
            "repository": "focal-security",
            "new_version": "1.1.1f-1ubuntu2.22",
            "arch": "amd64",
            "current_version": "1.1.1f-1ubuntu2.21",
        },
        {
            "name": "nginx",
            "repository": "focal-updates",
            "new_version": "1.18.0-4",
            "arch": "amd64",
            "current_version": "1.18.0-3",
        },
    ],
    "count": 2,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_UPDATES_EMPTY = {
    "status": "success",
    "updates": [],
    "count": 0,
    "timestamp": "2026-01-01T00:00:00Z",
}


# ============================================================================
# GET /api/packages/upgradable
# ============================================================================


class TestUpgradablePackages:
    """アップグレード可能パッケージ一覧テスト"""

    def test_upgradable_success(self, client, admin_headers):
        """正常系: アップグレード可能パッケージ一覧を取得できる"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {"output": '{"status":"success","updates":[{"name":"openssl","repository":"focal-security","new_version":"1.1.1f-2","arch":"amd64","current_version":"1.1.1f-1"}],"count":1,"timestamp":"2026-01-01T00:00:00Z"}'}
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "packages" in data
        assert "total" in data
        assert "security_count" in data

    def test_upgradable_response_structure(self, client, admin_headers):
        """レスポンス構造: packages/total/security_count を含む"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {"output": '{"status":"success","updates":[],"count":0,"timestamp":"2026-01-01T00:00:00Z"}'}
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["packages"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["security_count"], int)

    def test_upgradable_security_flag_set(self, client, admin_headers):
        """セキュリティアップデート: is_security=True が設定される"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {
                "output": '{"status":"success","updates":[{"name":"openssl","repository":"focal-security","new_version":"1.1.2","arch":"amd64","current_version":"1.1.1"}],"count":1,"timestamp":"2026-01-01T00:00:00Z"}'
            }
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["security_count"] >= 1
        security_pkgs = [p for p in data["packages"] if p["is_security"]]
        assert len(security_pkgs) >= 1

    def test_upgradable_non_security_flag_unset(self, client, admin_headers):
        """非セキュリティパッケージ: is_security=False"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {
                "output": '{"status":"success","updates":[{"name":"curl","repository":"focal-updates","new_version":"7.81","arch":"amd64","current_version":"7.80"}],"count":1,"timestamp":"2026-01-01T00:00:00Z"}'
            }
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        non_sec = [p for p in data["packages"] if not p["is_security"]]
        assert len(non_sec) >= 1

    def test_upgradable_empty_list(self, client, admin_headers):
        """空リスト: アップグレード可能パッケージがない場合"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {
                "output": '{"status":"success","updates":[],"count":0,"timestamp":"2026-01-01T00:00:00Z"}'
            }
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["security_count"] == 0

    def test_upgradable_unauthenticated(self, client):
        """未認証: 401/403"""
        resp = client.get("/api/packages/upgradable")
        assert resp.status_code in (401, 403)

    def test_upgradable_viewer_can_read(self, client, viewer_headers):
        """閲覧者: read:packages 権限で取得可能"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {
                "output": '{"status":"success","updates":[],"count":0,"timestamp":"2026-01-01T00:00:00Z"}'
            }
            resp = client.get("/api/packages/upgradable", headers=viewer_headers)
        assert resp.status_code == 200


# ============================================================================
# GET /api/packages/show/{package_name}
# ============================================================================


class TestShowPackage:
    """パッケージ詳細情報取得テスト"""

    def test_show_success(self, client, admin_headers):
        """正常系: パッケージ詳細を取得できる"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.show_package.return_value = {
                "returncode": 0,
                "output": "Package: openssl\nVersion: 1.1.1f\nDescription: SSL toolkit\n",
            }
            resp = client.get("/api/packages/show/openssl", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["package"] == "openssl"
        assert "info" in data

    def test_show_invalid_name_special_chars(self, client, admin_headers):
        """不正パッケージ名: セミコロンを含む → 422"""
        resp = client.get("/api/packages/show/openssl;ls", headers=admin_headers)
        assert resp.status_code == 422

    def test_show_invalid_name_pipe(self, client, admin_headers):
        """不正パッケージ名: パイプを含む → 422"""
        resp = client.get("/api/packages/show/openssl|cat", headers=admin_headers)
        assert resp.status_code == 422

    def test_show_invalid_name_dollar(self, client, admin_headers):
        """不正パッケージ名: ドル記号を含む → 422"""
        resp = client.get("/api/packages/show/open$ssl", headers=admin_headers)
        assert resp.status_code == 422

    def test_show_invalid_name_space(self, client, admin_headers):
        """不正パッケージ名: スペースを含む → 422"""
        resp = client.get("/api/packages/show/open ssl", headers=admin_headers)
        assert resp.status_code in (404, 422)

    def test_show_unauthenticated(self, client):
        """未認証: 401/403"""
        resp = client.get("/api/packages/show/openssl")
        assert resp.status_code in (401, 403)

    def test_show_viewer_can_read(self, client, viewer_headers):
        """閲覧者: read:packages 権限で取得可能"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.show_package.return_value = {
                "returncode": 0,
                "output": "Package: bash\nVersion: 5.1\n",
            }
            resp = client.get("/api/packages/show/bash", headers=viewer_headers)
        assert resp.status_code == 200


# ============================================================================
# POST /api/packages/install
# ============================================================================


class TestPackageInstall:
    """パッケージインストール承認リクエストテスト"""

    def test_install_success(self, client, approver_headers):
        """正常系: 承認リクエストが作成される"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop", "reason": "モニタリング用ツールとして必要"},
            headers=approver_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "request_id" in data
        assert data["status"] == "pending"
        assert data["operation"] == "install"
        assert data["package_name"] == "htop"

    def test_install_creates_approval_request(self, client, admin_headers, init_db):
        """承認リクエスト作成: DBに記録される"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "curl", "reason": "HTTP テスト用"},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        request_id = resp.json()["request_id"]
        with sqlite3.connect(init_db) as conn:
            row = conn.execute(
                "SELECT request_type, status FROM approval_requests WHERE id = ?", (request_id,)
            ).fetchone()
        assert row is not None
        assert row[0] == "package_install"
        assert row[1] == "pending"

    def test_install_invalid_package_name_semicolon(self, client, approver_headers):
        """不正パッケージ名: セミコロン → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop;rm -rf /", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_invalid_package_name_pipe(self, client, approver_headers):
        """不正パッケージ名: パイプ → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop|ls", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_invalid_package_name_dollar(self, client, approver_headers):
        """不正パッケージ名: ドル記号 → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "ht$op", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_invalid_package_name_space(self, client, approver_headers):
        """不正パッケージ名: スペース → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop tool", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_empty_package_name(self, client, approver_headers):
        """空のパッケージ名 → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_empty_reason(self, client, approver_headers):
        """空の理由 → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop", "reason": ""},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_unauthenticated(self, client):
        """未認証 → 401/403"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop", "reason": "テスト"},
        )
        assert resp.status_code in (401, 403)

    def test_install_viewer_forbidden(self, client, viewer_headers):
        """閲覧者: write:packages 権限なし → 403"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop", "reason": "テスト"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_install_shell_injection_backtick(self, client, approver_headers):
        """インジェクション拒否: バッククォート → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "`id`", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_install_shell_injection_ampersand(self, client, approver_headers):
        """インジェクション拒否: アンパサンド → 422"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "htop&&ls", "reason": "テスト"},
            headers=approver_headers,
        )
        assert resp.status_code == 422


# ============================================================================
# POST /api/packages/remove
# ============================================================================


class TestPackageRemove:
    """パッケージ削除承認リクエストテスト"""

    def test_remove_success(self, client, admin_headers):
        """正常系: 削除承認リクエストが作成される"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "htop", "reason": "不要なツールを削除"},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "request_id" in data
        assert data["status"] == "pending"
        assert data["operation"] == "remove"
        assert data["package_name"] == "htop"

    def test_remove_creates_approval_request(self, client, admin_headers, init_db):
        """承認リクエスト作成: DBに package_remove タイプで記録される"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "vim", "reason": "不要"},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        request_id = resp.json()["request_id"]
        with sqlite3.connect(init_db) as conn:
            row = conn.execute(
                "SELECT request_type, status FROM approval_requests WHERE id = ?", (request_id,)
            ).fetchone()
        assert row is not None
        assert row[0] == "package_remove"
        assert row[1] == "pending"

    def test_remove_invalid_package_name_semicolon(self, client, admin_headers):
        """不正パッケージ名: セミコロン → 422"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "vim;cat /etc/passwd", "reason": "テスト"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_remove_unauthenticated(self, client):
        """未認証 → 401/403"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "vim", "reason": "テスト"},
        )
        assert resp.status_code in (401, 403)

    def test_remove_viewer_forbidden(self, client, viewer_headers):
        """閲覧者: write:packages 権限なし → 403"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "vim", "reason": "テスト"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_remove_shell_injection_parentheses(self, client, admin_headers):
        """インジェクション拒否: 括弧 → 422"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": "vim$(id)", "reason": "テスト"},
            headers=admin_headers,
        )
        assert resp.status_code == 422
