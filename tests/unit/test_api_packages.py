"""
Packages API エンドポイントのユニットテスト

backend/api/routes/packages.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetInstalledPackages:
    """GET /api/packages/installed テスト"""

    def test_installed_success(self, test_client, auth_headers):
        """正常系: インストール済みパッケージ取得"""
        mock_output = json.dumps({
            "status": "success",
            "packages": [{"name": "vim", "version": "8.2", "status": "ii", "arch": "amd64"}],
            "count": 1,
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_list.return_value = {"status": "success", "output": mock_output}
            response = test_client.get("/api/packages/installed", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_installed_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_list.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/packages/installed", headers=auth_headers)
        assert response.status_code == 503

    def test_installed_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_list.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/packages/installed", headers=auth_headers)
        assert response.status_code == 500

    def test_installed_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/packages/installed")
        assert response.status_code == 403


class TestGetPackageUpdates:
    """GET /api/packages/updates テスト"""

    def test_updates_success(self, test_client, auth_headers):
        """正常系: 更新可能パッケージ取得"""
        mock_output = json.dumps({
            "status": "success",
            "updates": [{"name": "vim", "new_version": "9.0"}],
            "count": 1,
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.return_value = {"status": "success", "output": mock_output}
            response = test_client.get("/api/packages/updates", headers=auth_headers)
        assert response.status_code == 200

    def test_updates_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/packages/updates", headers=auth_headers)
        assert response.status_code == 503

    def test_updates_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_updates.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/packages/updates", headers=auth_headers)
        assert response.status_code == 500


class TestGetSecurityUpdates:
    """GET /api/packages/security テスト"""

    def test_security_success(self, test_client, auth_headers):
        """正常系: セキュリティ更新取得"""
        mock_output = json.dumps({
            "status": "success",
            "security_updates": [],
            "count": 0,
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_security.return_value = {"status": "success", "output": mock_output}
            response = test_client.get("/api/packages/security", headers=auth_headers)
        assert response.status_code == 200

    def test_security_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_security.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/packages/security", headers=auth_headers)
        assert response.status_code == 503

    def test_security_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_security.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/packages/security", headers=auth_headers)
        assert response.status_code == 500


class TestGetUpgradeDryrun:
    """GET /api/packages/upgrade/dryrun テスト"""

    def test_dryrun_success(self, test_client, auth_headers):
        """正常系: ドライラン実行"""
        mock_output = json.dumps({
            "status": "success",
            "packages": [{"name": "vim", "new_version": "9.0"}],
            "count": 1,
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_upgrade_dryrun.return_value = {"status": "success", "output": mock_output}
            response = test_client.get("/api/packages/upgrade/dryrun", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_dryrun_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.get_packages_upgrade_dryrun.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/packages/upgrade/dryrun", headers=auth_headers)
        assert response.status_code == 503


class TestUpgradePackage:
    """POST /api/packages/upgrade テスト"""

    def test_upgrade_success(self, test_client, admin_headers):
        """正常系: パッケージアップグレード（Admin）"""
        mock_output = json.dumps({
            "status": "success",
            "message": "Package vim upgraded",
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.upgrade_package.return_value = {"status": "success", "output": mock_output}
            response = test_client.post(
                "/api/packages/upgrade",
                json={"package_name": "vim"},
                headers=admin_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_upgrade_approver(self, test_client, approver_headers):
        """正常系: パッケージアップグレード（Approver）"""
        mock_output = json.dumps({
            "status": "success",
            "message": "Package nginx upgraded",
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.upgrade_package.return_value = {"status": "success", "output": mock_output}
            response = test_client.post(
                "/api/packages/upgrade",
                json={"package_name": "nginx"},
                headers=approver_headers,
            )
        assert response.status_code == 200

    def test_upgrade_invalid_package_name(self, test_client, admin_headers):
        """不正なパッケージ名"""
        response = test_client.post(
            "/api/packages/upgrade",
            json={"package_name": ";;rm -rf /"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_upgrade_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.upgrade_package.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/packages/upgrade",
                json={"package_name": "vim"},
                headers=admin_headers,
            )
        assert response.status_code == 503

    def test_upgrade_operator_forbidden(self, test_client, auth_headers):
        """Operator権限不足"""
        response = test_client.post(
            "/api/packages/upgrade",
            json={"package_name": "vim"},
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestUpgradeAllPackages:
    """POST /api/packages/upgrade-all テスト"""

    def test_upgrade_all_success(self, test_client, admin_headers):
        """正常系: 全パッケージアップグレード（Admin）"""
        mock_output = json.dumps({
            "status": "success",
            "message": "All packages upgraded",
            "timestamp": "2026-03-01T00:00:00Z",
        })
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.upgrade_all_packages.return_value = {"status": "success", "output": mock_output}
            response = test_client.post("/api/packages/upgrade-all", headers=admin_headers)
        assert response.status_code == 200

    def test_upgrade_all_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.packages.sudo_wrapper") as mock_sw:
            mock_sw.upgrade_all_packages.side_effect = SudoWrapperError("Failed")
            response = test_client.post("/api/packages/upgrade-all", headers=admin_headers)
        assert response.status_code == 503

    def test_upgrade_all_approver_forbidden(self, test_client, approver_headers):
        """Approver権限不足（execute:upgrade_all はAdminのみ）"""
        response = test_client.post("/api/packages/upgrade-all", headers=approver_headers)
        assert response.status_code == 403

    def test_upgrade_all_operator_forbidden(self, test_client, auth_headers):
        """Operator権限不足"""
        response = test_client.post("/api/packages/upgrade-all", headers=auth_headers)
        assert response.status_code == 403
