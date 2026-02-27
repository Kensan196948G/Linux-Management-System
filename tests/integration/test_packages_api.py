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
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture
def approver_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "approver@example.com", "password": "approver123"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def approver_headers(approver_token):
    return {"Authorization": f"Bearer {approver_token}"}

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


# ===================================================================
# Package Updates 強化テスト (TC_PKG_021 - TC_PKG_035)
# ===================================================================

SAMPLE_DRYRUN = {
    "status": "success",
    "packages": [
        {"name": "nginx", "current_version": "1.18.0-0ubuntu1", "new_version": "1.18.0-0ubuntu2"},
        {"name": "curl", "current_version": "7.68.0-1ubuntu2.20", "new_version": "7.68.0-1ubuntu2.21"},
    ],
    "count": 2,
    "timestamp": "2026-02-27T10:00:00Z",
}

SAMPLE_UPGRADE_OK = {
    "status": "success",
    "message": "Package 'nginx' upgraded successfully",
    "timestamp": "2026-02-27T10:00:01Z",
}

SAMPLE_UPGRADE_ALL_OK = {
    "status": "success",
    "message": "All packages upgraded successfully",
    "timestamp": "2026-02-27T10:00:10Z",
}


class TestPackageUpgradeDryrun:
    """GET /api/packages/upgrade/dryrun のテスト"""

    def test_dryrun_viewer_success(self, client, viewer_headers):
        """TC_PKG_021: Viewer でドライラン成功"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgrade_dryrun",
            return_value=SAMPLE_DRYRUN,
        ):
            resp = client.get("/api/packages/upgrade/dryrun", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["packages"]) == 2

    def test_dryrun_unauthorized(self, client):
        """TC_PKG_022: 未認証でドライラン拒否"""
        resp = client.get("/api/packages/upgrade/dryrun")
        assert resp.status_code in (401, 403)

    def test_dryrun_wrapper_error_503(self, client, auth_headers):
        """TC_PKG_023: SudoWrapperError で503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgrade_dryrun",
            side_effect=SudoWrapperError("apt failed"),
        ):
            resp = client.get("/api/packages/upgrade/dryrun", headers=auth_headers)
        assert resp.status_code == 503

    def test_dryrun_empty_result(self, client, auth_headers):
        """TC_PKG_024: アップグレードなしの場合は空リスト"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgrade_dryrun",
            return_value={"status": "success", "packages": [], "count": 0, "timestamp": "2026-02-27T10:00:00Z"},
        ):
            resp = client.get("/api/packages/upgrade/dryrun", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestPackageUpgrade:
    """POST /api/packages/upgrade のテスト"""

    def test_upgrade_admin_success(self, client, admin_headers):
        """TC_PKG_025: Admin でパッケージアップグレード成功"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_package",
            return_value=SAMPLE_UPGRADE_OK,
        ):
            resp = client.post(
                "/api/packages/upgrade",
                json={"package_name": "nginx"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_upgrade_viewer_forbidden(self, client, viewer_headers):
        """TC_PKG_026: Viewer でアップグレードは403"""
        resp = client.post(
            "/api/packages/upgrade",
            json={"package_name": "nginx"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_upgrade_unauthorized(self, client):
        """TC_PKG_027: 未認証でアップグレード拒否"""
        resp = client.post("/api/packages/upgrade", json={"package_name": "nginx"})
        assert resp.status_code in (401, 403)

    def test_upgrade_invalid_package_name_injection(self, client, admin_headers):
        """TC_PKG_028: シェルインジェクション攻撃を含むパッケージ名を拒否"""
        resp = client.post(
            "/api/packages/upgrade",
            json={"package_name": "nginx; rm -rf /"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upgrade_invalid_package_name_special_chars(self, client, admin_headers):
        """TC_PKG_029: 特殊文字を含むパッケージ名を拒否"""
        resp = client.post(
            "/api/packages/upgrade",
            json={"package_name": "$(whoami)"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upgrade_empty_package_name(self, client, admin_headers):
        """TC_PKG_030: 空のパッケージ名を拒否"""
        resp = client.post(
            "/api/packages/upgrade",
            json={"package_name": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upgrade_wrapper_error_503(self, client, admin_headers):
        """TC_PKG_031: SudoWrapperError で503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_package",
            side_effect=SudoWrapperError("package not found"),
        ):
            resp = client.post(
                "/api/packages/upgrade",
                json={"package_name": "nginx"},
                headers=admin_headers,
            )
        assert resp.status_code == 503

    def test_upgrade_valid_package_names(self, client, admin_headers):
        """TC_PKG_032: 有効なパッケージ名パターン（ハイフン・ドット・プラス）"""
        valid_names = ["lib32-gcc-s1", "python3.11", "g++", "pkg-config"]
        for name in valid_names:
            with patch(
                "backend.api.routes.packages.sudo_wrapper.upgrade_package",
                return_value=SAMPLE_UPGRADE_OK,
            ):
                resp = client.post(
                    "/api/packages/upgrade",
                    json={"package_name": name},
                    headers=admin_headers,
                )
            assert resp.status_code == 200, f"Failed for package name: {name}"


class TestPackageUpgradeAll:
    """POST /api/packages/upgrade-all のテスト"""

    def test_upgrade_all_admin_success(self, client, admin_headers):
        """TC_PKG_033: Admin で全パッケージアップグレード成功"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_all_packages",
            return_value=SAMPLE_UPGRADE_ALL_OK,
        ):
            resp = client.post("/api/packages/upgrade-all", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_upgrade_all_approver_forbidden(self, client, approver_headers):
        """TC_PKG_034: Approver で全アップグレードは403"""
        resp = client.post("/api/packages/upgrade-all", headers=approver_headers)
        assert resp.status_code == 403

    def test_upgrade_all_wrapper_error_503(self, client, admin_headers):
        """TC_PKG_035: SudoWrapperError で503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_all_packages",
            side_effect=SudoWrapperError("apt-get failed"),
        ):
            resp = client.post("/api/packages/upgrade-all", headers=admin_headers)
        assert resp.status_code == 503
