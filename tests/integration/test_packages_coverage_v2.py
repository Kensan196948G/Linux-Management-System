"""
packages.py カバレッジ改善テスト v2

既存テストでカバー済みの分岐を避け、未カバー行を重点的にテスト:
- get_installed_packages: 一般 Exception パス (lines 165-170)
- get_package_updates: 一般 Exception パス (lines 200-205)
- get_security_updates: 一般 Exception パス (lines 235-240)
- get_upgrade_dryrun: parse_wrapper_result の詳細フィールド展開 (lines 263-269)
- upgrade_package: SudoWrapperError の audit_log 記録パス (lines 303-315)
- upgrade_all_packages: SudoWrapperError の audit_log 記録パス (lines 343-354)
- get_upgradeable_packages: stdout の Listing 行フィルタリング (line 375)
- search_packages_endpoint: 全禁止文字チェック (lines 401-403)
- get_package_info_endpoint: forbidden 配列（スペース含む） (lines 432-435)
- get_package_info_endpoint: returncode != 0 パス (line 438-439)
- get_security_updates_v2: 空 stdout パス (line 467)
- show_package: 正常系、not found パス (lines 603-605)、regex バリデーション失敗 (line 600-601)
- show_package: ValueError パス (line 615-616)、一般 Exception パス (lines 618-619)
- request_package_install: LookupError / ValueError / Exception パス (lines 655-661)
- request_package_remove: LookupError / ValueError / Exception パス (lines 697-703)
- get_upgradable_packages: セキュリティフラグ判定ロジック (lines 554)
- get_upgradable_packages: 一般 Exception パス (lines 581-583)
- UpgradePackageRequest: package_name バリデーション (lines 120-122)
- PackageActionRequest: package_name バリデーション (lines 517-523)
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(scope="module")
def _admin_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def _approver_token(client):
    resp = client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(_admin_token):
    return {"Authorization": f"Bearer {_admin_token}"}


@pytest.fixture
def approver_headers(_approver_token):
    return {"Authorization": f"Bearer {_approver_token}"}


@pytest.fixture(scope="module")
def init_db(tmp_path_factory):
    """承認DB初期化"""
    from backend.api.routes import packages as pkg_module
    tmp_db = str(tmp_path_factory.mktemp("pkg_cov") / "test.db")
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


# ===================================================================
# get_installed_packages: 一般 Exception パス
# ===================================================================


class TestInstalledPackagesException:
    """get_installed_packages の Exception パス"""

    def test_installed_generic_exception_returns_500(self, client, admin_headers):
        """一般 Exception で 500 (lines 165-170)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_list",
            side_effect=Exception("unexpected error"),
        ):
            resp = client.get("/api/packages/installed", headers=admin_headers)
        assert resp.status_code == 500
        body = resp.json()
        assert "unexpected error" in body.get("detail", body.get("message", ""))


# ===================================================================
# get_package_updates: 一般 Exception パス
# ===================================================================


class TestPackageUpdatesException:
    """get_package_updates の Exception パス"""

    def test_updates_generic_exception_returns_500(self, client, admin_headers):
        """一般 Exception で 500 (lines 200-205)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            side_effect=Exception("db error"),
        ):
            resp = client.get("/api/packages/updates", headers=admin_headers)
        assert resp.status_code == 500
        body = resp.json()
        assert "db error" in body.get("detail", body.get("message", ""))


# ===================================================================
# get_security_updates: 一般 Exception パス
# ===================================================================


class TestSecurityUpdatesException:
    """get_security_updates の Exception パス"""

    def test_security_generic_exception_returns_500(self, client, admin_headers):
        """一般 Exception で 500 (lines 235-240)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_security",
            side_effect=Exception("network error"),
        ):
            resp = client.get("/api/packages/security", headers=admin_headers)
        assert resp.status_code == 500


# ===================================================================
# get_upgrade_dryrun: parse_wrapper_result フィールド展開
# ===================================================================


class TestUpgradeDryrunFields:
    """get_upgrade_dryrun の詳細フィールド展開パス"""

    def test_dryrun_with_message_field(self, client, admin_headers):
        """message フィールドが含まれる場合 (line 267)"""
        mock_result = {
            "status": "success",
            "packages": [{"name": "curl", "current_version": "7.80", "new_version": "7.81"}],
            "count": 1,
            "message": "Dry run completed",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgrade_dryrun",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgrade/dryrun", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Dry run completed"

    def test_dryrun_missing_optional_fields(self, client, admin_headers):
        """オプションフィールドが欠けている場合デフォルト値使用 (lines 264-268)"""
        mock_result = {
            "output": '{"status": "ok"}'
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgrade_dryrun",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgrade/dryrun", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["packages"] == []
        assert data["count"] == 0


# ===================================================================
# upgrade_package: audit_log 詳細パス
# ===================================================================


class TestUpgradePackageAuditLog:
    """upgrade_package の SudoWrapperError 時 audit_log パス"""

    def test_upgrade_wrapper_error_records_audit(self, client, admin_headers):
        """SudoWrapperError 時に audit_log.record が呼ばれること (lines 305-311)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_package",
            side_effect=SudoWrapperError("apt-get failed"),
        ):
            with patch("backend.api.routes.packages.audit_log.record") as mock_audit:
                resp = client.post(
                    "/api/packages/upgrade",
                    json={"package_name": "nginx"},
                    headers=admin_headers,
                )
        assert resp.status_code == 503
        # audit_log.record が error ステータスで呼ばれたことを確認
        error_calls = [c for c in mock_audit.call_args_list if c.kwargs.get("status") == "error"]
        assert len(error_calls) >= 1


# ===================================================================
# upgrade_all_packages: audit_log 詳細パス
# ===================================================================


class TestUpgradeAllAuditLog:
    """upgrade_all_packages の SudoWrapperError 時 audit_log パス"""

    def test_upgrade_all_wrapper_error_records_audit(self, client, admin_headers):
        """SudoWrapperError 時に audit_log.record が呼ばれること (lines 344-350)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.upgrade_all_packages",
            side_effect=SudoWrapperError("apt-get upgrade failed"),
        ):
            with patch("backend.api.routes.packages.audit_log.record") as mock_audit:
                resp = client.post("/api/packages/upgrade-all", headers=admin_headers)
        assert resp.status_code == 503
        error_calls = [c for c in mock_audit.call_args_list if c.kwargs.get("status") == "error"]
        assert len(error_calls) >= 1


# ===================================================================
# get_upgradeable_packages: Listing 行フィルタリング
# ===================================================================


class TestUpgradeableListingFilter:
    """get_upgradeable_packages の Listing 行フィルタリング"""

    def test_listing_line_filtered_out(self, client, admin_headers):
        """'Listing...' 行がフィルタリングされること (line 375)"""
        mock_result = {
            "stdout": "Listing... Done\nnginx/focal-updates 1.18.0 amd64\n",
            "stderr": "",
            "returncode": 0,
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgradeable",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradeable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "Listing" not in data["packages"][0]

    def test_empty_lines_filtered_out(self, client, admin_headers):
        """空行がフィルタリングされること"""
        mock_result = {
            "stdout": "\n\nnginx/focal-updates 1.18.0 amd64\n\n",
            "stderr": "",
            "returncode": 0,
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_upgradeable",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradeable", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ===================================================================
# search_packages_endpoint: 全禁止文字テスト
# ===================================================================


class TestSearchPackagesForbiddenChars:
    """search_packages_endpoint の全禁止文字チェック"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"])
    def test_forbidden_char_returns_400(self, client, admin_headers, char):
        """禁止文字 '{char}' で 400 (lines 401-403)"""
        import urllib.parse
        encoded_q = urllib.parse.quote(f"test{char}inject", safe="")
        resp = client.get(f"/api/packages/search?q={encoded_q}", headers=admin_headers)
        assert resp.status_code == 400


# ===================================================================
# get_package_info_endpoint: スペースを含むパッケージ名
# ===================================================================


class TestPackageInfoForbiddenNames:
    """get_package_info_endpoint のバリデーション"""

    def test_info_space_in_name_rejected(self, client, admin_headers):
        """スペースを含むパッケージ名で 400 (line 432-435)"""
        resp = client.get("/api/packages/info/bad name", headers=admin_headers)
        assert resp.status_code == 400

    @pytest.mark.parametrize("char", ["{", "}", "[", "]"])
    def test_info_additional_forbidden_chars(self, client, admin_headers, char):
        """追加禁止文字で 400"""
        resp = client.get(f"/api/packages/info/pkg{char}bad", headers=admin_headers)
        assert resp.status_code == 400


# ===================================================================
# show_package: 詳細分岐テスト
# ===================================================================


class TestShowPackageDetailed:
    """GET /api/packages/show/{name} の詳細分岐"""

    def test_show_not_found_returns_404(self, client, admin_headers):
        """returncode!=0 or empty output で 404 (lines 603-605)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.show_package",
            return_value={"returncode": 1, "output": ""},
        ):
            resp = client.get("/api/packages/show/nonexistent-pkg", headers=admin_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body.get("detail", body.get("message", ""))

    def test_show_empty_output_returns_404(self, client, admin_headers):
        """returncode=0 but empty output で 404"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.show_package",
            return_value={"returncode": 0, "output": "   "},
        ):
            resp = client.get("/api/packages/show/empty-pkg", headers=admin_headers)
        assert resp.status_code == 404

    def test_show_regex_validation_failure(self, client, admin_headers):
        """正規表現バリデーション失敗で 422 (lines 600-601)"""
        # 数字で始まらないパッケージ名（先頭が特殊）
        resp = client.get("/api/packages/show/.invalid-start", headers=admin_headers)
        assert resp.status_code == 422

    def test_show_value_error_returns_422(self, client, admin_headers):
        """ValueError で 422 (lines 615-616)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.show_package",
            side_effect=ValueError("bad package format"),
        ):
            resp = client.get("/api/packages/show/validpkg", headers=admin_headers)
        assert resp.status_code == 422

    def test_show_generic_exception_returns_503(self, client, admin_headers):
        """一般 Exception で 503 (lines 618-619)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.show_package",
            side_effect=Exception("apt-cache crashed"),
        ):
            resp = client.get("/api/packages/show/validpkg", headers=admin_headers)
        assert resp.status_code == 503

    def test_show_success_with_output(self, client, admin_headers):
        """正常系: output 付きレスポンス"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.show_package",
            return_value={"returncode": 0, "output": "Package: curl\nVersion: 7.81\n"},
        ):
            resp = client.get("/api/packages/show/curl", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["package"] == "curl"
        assert "curl" in data["info"].lower()

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]", " "])
    def test_show_forbidden_chars(self, client, admin_headers, char):
        """全禁止文字で 422 (lines 596-599)"""
        resp = client.get(f"/api/packages/show/pkg{char}bad", headers=admin_headers)
        assert resp.status_code in (404, 422)


# ===================================================================
# request_package_install: エラーパス
# ===================================================================


class TestInstallErrorPaths:
    """POST /api/packages/install のエラーパス"""

    def test_install_lookup_error_returns_400(self, client, approver_headers):
        """LookupError で 400 (line 655-656)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=LookupError("request type not found"),
        ):
            resp = client.post(
                "/api/packages/install",
                json={"package_name": "htop", "reason": "testing"},
                headers=approver_headers,
            )
        assert resp.status_code == 400

    def test_install_value_error_returns_422(self, client, approver_headers):
        """ValueError で 422 (line 657-658)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=ValueError("invalid payload"),
        ):
            resp = client.post(
                "/api/packages/install",
                json={"package_name": "htop", "reason": "testing"},
                headers=approver_headers,
            )
        assert resp.status_code == 422

    def test_install_generic_exception_returns_503(self, client, approver_headers):
        """一般 Exception で 503 (lines 659-661)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=Exception("db connection lost"),
        ):
            resp = client.post(
                "/api/packages/install",
                json={"package_name": "htop", "reason": "testing"},
                headers=approver_headers,
            )
        assert resp.status_code == 503


# ===================================================================
# request_package_remove: エラーパス
# ===================================================================


class TestRemoveErrorPaths:
    """POST /api/packages/remove のエラーパス"""

    def test_remove_lookup_error_returns_400(self, client, admin_headers):
        """LookupError で 400 (line 697-698)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=LookupError("not found"),
        ):
            resp = client.post(
                "/api/packages/remove",
                json={"package_name": "vim", "reason": "cleanup"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_remove_value_error_returns_422(self, client, admin_headers):
        """ValueError で 422 (line 699-700)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=ValueError("bad format"),
        ):
            resp = client.post(
                "/api/packages/remove",
                json={"package_name": "vim", "reason": "cleanup"},
                headers=admin_headers,
            )
        assert resp.status_code == 422

    def test_remove_generic_exception_returns_503(self, client, admin_headers):
        """一般 Exception で 503 (lines 701-703)"""
        with patch(
            "backend.api.routes.packages._approval_service.create_request",
            side_effect=Exception("timeout"),
        ):
            resp = client.post(
                "/api/packages/remove",
                json={"package_name": "vim", "reason": "cleanup"},
                headers=admin_headers,
            )
        assert resp.status_code == 503


# ===================================================================
# get_upgradable_packages: セキュリティフラグ・Exception パス
# ===================================================================


class TestUpgradablePackagesDetailed:
    """GET /api/packages/upgradable の詳細分岐"""

    def test_upgradable_security_in_name_sets_flag(self, client, admin_headers):
        """パッケージ名に 'security' を含む場合 is_security=True (line 554)"""
        mock_result = {
            "status": "success",
            "updates": [
                {
                    "name": "linux-security-tools",
                    "repository": "focal-updates",
                    "new_version": "2.0",
                    "arch": "amd64",
                    "current_version": "1.0",
                },
            ],
            "count": 1,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["packages"][0]["is_security"] is True

    def test_upgradable_security_in_repo_sets_flag(self, client, admin_headers):
        """リポジトリに 'security' を含む場合 is_security=True (line 554)"""
        mock_result = {
            "status": "success",
            "updates": [
                {
                    "name": "openssl",
                    "repository": "focal-security",
                    "new_version": "1.1.2",
                    "arch": "amd64",
                    "current_version": "1.1.1",
                },
            ],
            "count": 1,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["security_count"] == 1

    def test_upgradable_non_security_unset(self, client, admin_headers):
        """セキュリティ無関係パッケージは is_security=False"""
        mock_result = {
            "status": "success",
            "updates": [
                {
                    "name": "curl",
                    "repository": "focal-updates",
                    "new_version": "7.81",
                    "arch": "amd64",
                    "current_version": "7.80",
                },
            ],
            "count": 1,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["packages"][0]["is_security"] is False
        assert resp.json()["security_count"] == 0

    def test_upgradable_generic_exception_returns_503(self, client, admin_headers):
        """一般 Exception で 503 (lines 581-583)"""
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            side_effect=RuntimeError("parse error"),
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 503

    def test_upgradable_empty_updates_list(self, client, admin_headers):
        """空の更新リストの場合"""
        mock_result = {
            "status": "success",
            "updates": [],
            "count": 0,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["security_count"] == 0
        assert data["packages"] == []

    def test_upgradable_package_fields_populated(self, client, admin_headers):
        """UpgradablePackageInfo の全フィールドが正しく設定されること"""
        mock_result = {
            "status": "success",
            "updates": [
                {
                    "name": "nginx",
                    "repository": "focal-updates",
                    "new_version": "1.18.0-4",
                    "arch": "amd64",
                    "current_version": "1.18.0-3",
                },
            ],
            "count": 1,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.api.routes.packages.sudo_wrapper.get_packages_updates",
            return_value=mock_result,
        ):
            resp = client.get("/api/packages/upgradable", headers=admin_headers)
        assert resp.status_code == 200
        pkg = resp.json()["packages"][0]
        assert pkg["name"] == "nginx"
        assert pkg["current_version"] == "1.18.0-3"
        assert pkg["available_version"] == "1.18.0-4"
        assert pkg["repository"] == "focal-updates"
        assert pkg["arch"] == "amd64"


# ===================================================================
# PackageActionRequest バリデーション
# ===================================================================


class TestPackageActionRequestValidation:
    """PackageActionRequest の package_name バリデーション"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]", " "])
    def test_install_forbidden_chars_rejected(self, client, approver_headers, char):
        """install: 禁止文字 '{char}' で 422 (lines 517-520)"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": f"pkg{char}bad", "reason": "test"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]", " "])
    def test_remove_forbidden_chars_rejected(self, client, admin_headers, char):
        """remove: 禁止文字 '{char}' で 422 (lines 517-520)"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": f"pkg{char}bad", "reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_install_invalid_format_rejected(self, client, approver_headers):
        """install: 正規表現パターン不一致で 422 (line 521-522)"""
        resp = client.post(
            "/api/packages/install",
            json={"package_name": "-invalid-start", "reason": "test"},
            headers=approver_headers,
        )
        assert resp.status_code == 422

    def test_remove_invalid_format_rejected(self, client, admin_headers):
        """remove: 正規表現パターン不一致で 422"""
        resp = client.post(
            "/api/packages/remove",
            json={"package_name": ".dotstart", "reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ===================================================================
# UpgradePackageRequest バリデーション
# ===================================================================


class TestUpgradePackageRequestValidation:
    """UpgradePackageRequest の package_name バリデーション"""

    def test_upgrade_long_package_name_rejected(self, client, admin_headers):
        """128文字超のパッケージ名で 422 (line 120-121)"""
        long_name = "a" * 129
        resp = client.post(
            "/api/packages/upgrade",
            json={"package_name": long_name},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upgrade_valid_complex_names(self, client, admin_headers):
        """有効な複雑パッケージ名が通過"""
        mock_result = {
            "status": "success",
            "message": "Upgraded",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        valid_names = ["lib32-gcc-s1", "python3.11", "pkg-config", "libssl1.1"]
        for name in valid_names:
            with patch(
                "backend.api.routes.packages.sudo_wrapper.upgrade_package",
                return_value=mock_result,
            ):
                resp = client.post(
                    "/api/packages/upgrade",
                    json={"package_name": name},
                    headers=admin_headers,
                )
            assert resp.status_code == 200, f"Failed for: {name}"
