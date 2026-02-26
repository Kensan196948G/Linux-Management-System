"""
パッケージ管理モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import MagicMock, patch

import pytest


SAMPLE_INSTALLED = {
    "status": "success",
    "packages": [
        {"name": "bash", "version": "5.1.16-1ubuntu7.3", "status": "install ok installed", "arch": "amd64"},
        {"name": "nginx", "version": "1.18.0-0ubuntu1.4", "status": "install ok installed", "arch": "amd64"},
        {"name": "python3", "version": "3.10.6-1~22.04", "status": "install ok installed", "arch": "amd64"},
    ],
    "count": 3,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_UPDATES = {
    "status": "success",
    "updates": [
        {
            "name": "nginx",
            "repository": "focal-updates",
            "new_version": "1.18.0-0ubuntu1.4",
            "arch": "amd64",
            "current_version": "1.18.0-0ubuntu1.3",
        }
    ],
    "count": 1,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SECURITY = {
    "status": "success",
    "security_updates": [
        {
            "name": "openssl",
            "repository": "focal-security",
            "new_version": "1.1.1f-1ubuntu2.22",
            "arch": "amd64",
            "current_version": "1.1.1f-1ubuntu2.21",
            "is_security": True,
        }
    ],
    "count": 1,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_NO_UPDATES = {
    "status": "success",
    "updates": [],
    "count": 0,
    "message": "No updates available",
    "timestamp": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def viewer_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


class TestInstalledPackages:
    """インストール済みパッケージ取得テスト"""

    def test_installed_success(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            return_value=SAMPLE_INSTALLED,
        ):
            resp = client.get("/api/packages/installed", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["packages"], list)

    def test_installed_count(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            return_value=SAMPLE_INSTALLED,
        ):
            resp = client.get("/api/packages/installed", headers=auth_headers)
        assert resp.json()["count"] == 3

    def test_installed_no_auth(self, client):
        resp = client.get("/api/packages/installed")
        assert resp.status_code == 403

    def test_installed_viewer_allowed(self, client, viewer_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            return_value=SAMPLE_INSTALLED,
        ):
            resp = client.get("/api/packages/installed", headers=viewer_headers)
        assert resp.status_code == 200

    def test_installed_package_fields(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            return_value=SAMPLE_INSTALLED,
        ):
            resp = client.get("/api/packages/installed", headers=auth_headers)
        pkg = resp.json()["packages"][0]
        assert "name" in pkg
        assert "version" in pkg

    def test_installed_wrapper_error_503(self, client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            side_effect=SudoWrapperError("error"),
        ):
            resp = client.get("/api/packages/installed", headers=auth_headers)
        assert resp.status_code == 503

    def test_installed_timestamp_present(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            return_value=SAMPLE_INSTALLED,
        ):
            resp = client.get("/api/packages/installed", headers=auth_headers)
        assert "timestamp" in resp.json()


class TestPackageUpdates:
    """更新可能パッケージ取得テスト"""

    def test_updates_success(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=SAMPLE_UPDATES,
        ):
            resp = client.get("/api/packages/updates", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["updates"], list)

    def test_updates_no_auth(self, client):
        resp = client.get("/api/packages/updates")
        assert resp.status_code == 403

    def test_updates_viewer_allowed(self, client, viewer_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=SAMPLE_UPDATES,
        ):
            resp = client.get("/api/packages/updates", headers=viewer_headers)
        assert resp.status_code == 200

    def test_updates_empty_list(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=SAMPLE_NO_UPDATES,
        ):
            resp = client.get("/api/packages/updates", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_updates_count_field(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=SAMPLE_UPDATES,
        ):
            resp = client.get("/api/packages/updates", headers=auth_headers)
        assert resp.json()["count"] == 1

    def test_updates_package_has_versions(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=SAMPLE_UPDATES,
        ):
            resp = client.get("/api/packages/updates", headers=auth_headers)
        upd = resp.json()["updates"][0]
        assert "new_version" in upd
        assert "current_version" in upd

    def test_updates_wrapper_error_503(self, client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            side_effect=SudoWrapperError("error"),
        ):
            resp = client.get("/api/packages/updates", headers=auth_headers)
        assert resp.status_code == 503


class TestSecurityUpdates:
    """セキュリティ更新取得テスト"""

    def test_security_success(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            return_value=SAMPLE_SECURITY,
        ):
            resp = client.get("/api/packages/security", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["security_updates"], list)

    def test_security_no_auth(self, client):
        resp = client.get("/api/packages/security")
        assert resp.status_code == 403

    def test_security_viewer_allowed(self, client, viewer_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            return_value=SAMPLE_SECURITY,
        ):
            resp = client.get("/api/packages/security", headers=viewer_headers)
        assert resp.status_code == 200

    def test_security_is_security_flag(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            return_value=SAMPLE_SECURITY,
        ):
            resp = client.get("/api/packages/security", headers=auth_headers)
        upd = resp.json()["security_updates"][0]
        assert upd.get("is_security") is True

    def test_security_wrapper_error_503(self, client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            side_effect=SudoWrapperError("error"),
        ):
            resp = client.get("/api/packages/security", headers=auth_headers)
        assert resp.status_code == 503

    def test_security_timestamp_present(self, client, auth_headers):
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            return_value=SAMPLE_SECURITY,
        ):
            resp = client.get("/api/packages/security", headers=auth_headers)
        assert "timestamp" in resp.json()
