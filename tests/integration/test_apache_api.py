"""
Apache Webserver モジュール - 統合テスト

テストケース数: 20件
- 正常系: status/vhosts/modules/config-check エンドポイント
- unavailable 系: Apache 未インストール環境
- 異常系: 権限不足、未認証
- セキュリティ: SudoWrapperError 処理
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

APACHE_STATUS_OK = {
    "status": "success",
    "service": "apache2",
    "active": "active",
    "enabled": "enabled",
    "version": "Apache/2.4.57 (Ubuntu)",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_STATUS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Apache service not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_VHOSTS_OK = {
    "status": "success",
    "vhosts_raw": "VirtualHost configuration:\n*:80 localhost (/etc/apache2/sites-enabled/000-default.conf:1)",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_VHOSTS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "apache2ctl not found",
    "vhosts": [],
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_MODULES_OK = {
    "status": "success",
    "modules_raw": "Loaded Modules:\n core_module (static)\n so_module (static)\n mod_rewrite (shared)",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_MODULES_UNAVAILABLE = {
    "status": "unavailable",
    "message": "apache2ctl not found",
    "modules": [],
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_CONFIG_OK = {
    "status": "success",
    "syntax_ok": True,
    "output": "Syntax OK\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_CONFIG_ERROR = {
    "status": "success",
    "syntax_ok": False,
    "output": "AH00526: Syntax error on line 1 of /etc/apache2/sites-enabled/bad.conf",
    "timestamp": "2026-03-01T00:00:00Z",
}

APACHE_CONFIG_UNAVAILABLE = {
    "status": "unavailable",
    "message": "apache2ctl not found",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストケース
# ===================================================================


class TestApacheStatus:
    """TC_APH_001〜005: Apache status エンドポイントテスト"""

    def test_TC_APH_001_status_ok(self, test_client, admin_token):
        """TC_APH_001: Apache 正常稼働時のステータス取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_status", return_value=APACHE_STATUS_OK):
            resp = test_client.get("/api/apache/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "apache2"
        assert data["active"] == "active"

    def test_TC_APH_002_status_unavailable(self, test_client, admin_token):
        """TC_APH_002: Apache 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_status", return_value=APACHE_STATUS_UNAVAILABLE):
            resp = test_client.get("/api/apache/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_APH_003_status_unauthorized(self, test_client):
        """TC_APH_003: 未認証時の 401 返却"""
        resp = test_client.get("/api/apache/status")
        assert resp.status_code in (401, 403)

    def test_TC_APH_004_status_viewer_allowed(self, test_client, viewer_token):
        """TC_APH_004: viewer ロールは read:servers 権限で取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_status", return_value=APACHE_STATUS_OK):
            resp = test_client.get("/api/apache/status", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_APH_005_status_wrapper_error(self, test_client, admin_token):
        """TC_APH_005: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_status", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/apache/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestApacheVhosts:
    """TC_APH_006〜010: Apache vhosts エンドポイントテスト"""

    def test_TC_APH_006_vhosts_ok(self, test_client, admin_token):
        """TC_APH_006: 仮想ホスト一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_vhosts", return_value=APACHE_VHOSTS_OK):
            resp = test_client.get("/api/apache/vhosts", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "vhosts_raw" in data

    def test_TC_APH_007_vhosts_unavailable(self, test_client, admin_token):
        """TC_APH_007: apache2ctl 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_vhosts", return_value=APACHE_VHOSTS_UNAVAILABLE):
            resp = test_client.get("/api/apache/vhosts", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_APH_008_vhosts_unauthorized(self, test_client):
        """TC_APH_008: 未認証時の 401 返却"""
        resp = test_client.get("/api/apache/vhosts")
        assert resp.status_code in (401, 403)

    def test_TC_APH_009_vhosts_viewer_allowed(self, test_client, viewer_token):
        """TC_APH_009: viewer ロールでも仮想ホスト取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_vhosts", return_value=APACHE_VHOSTS_OK):
            resp = test_client.get("/api/apache/vhosts", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_APH_010_vhosts_wrapper_error(self, test_client, admin_token):
        """TC_APH_010: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_vhosts", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/apache/vhosts", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestApacheModules:
    """TC_APH_011〜015: Apache modules エンドポイントテスト"""

    def test_TC_APH_011_modules_ok(self, test_client, admin_token):
        """TC_APH_011: ロード済みモジュール一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_modules", return_value=APACHE_MODULES_OK):
            resp = test_client.get("/api/apache/modules", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "modules_raw" in data

    def test_TC_APH_012_modules_unavailable(self, test_client, admin_token):
        """TC_APH_012: apache2ctl 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_modules", return_value=APACHE_MODULES_UNAVAILABLE):
            resp = test_client.get("/api/apache/modules", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_APH_013_modules_unauthorized(self, test_client):
        """TC_APH_013: 未認証時の 401 返却"""
        resp = test_client.get("/api/apache/modules")
        assert resp.status_code in (401, 403)

    def test_TC_APH_014_modules_operator_allowed(self, test_client, auth_token):
        """TC_APH_014: operator ロールでもモジュール取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_modules", return_value=APACHE_MODULES_OK):
            resp = test_client.get("/api/apache/modules", headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200

    def test_TC_APH_015_modules_wrapper_error(self, test_client, admin_token):
        """TC_APH_015: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_modules", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/apache/modules", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestApacheConfigCheck:
    """TC_APH_016〜020: Apache config-check エンドポイントテスト"""

    def test_TC_APH_016_config_check_syntax_ok(self, test_client, admin_token):
        """TC_APH_016: 設定ファイル構文 OK の場合 syntax_ok=True"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_config_check", return_value=APACHE_CONFIG_OK):
            resp = test_client.get("/api/apache/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["syntax_ok"] is True

    def test_TC_APH_017_config_check_syntax_error(self, test_client, admin_token):
        """TC_APH_017: 設定ファイルに構文エラーがある場合 syntax_ok=False"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_config_check", return_value=APACHE_CONFIG_ERROR):
            resp = test_client.get("/api/apache/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["syntax_ok"] is False

    def test_TC_APH_018_config_check_unavailable(self, test_client, admin_token):
        """TC_APH_018: apache2ctl 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_config_check", return_value=APACHE_CONFIG_UNAVAILABLE):
            resp = test_client.get("/api/apache/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_APH_019_config_check_unauthorized(self, test_client):
        """TC_APH_019: 未認証時の 401 返却"""
        resp = test_client.get("/api/apache/config-check")
        assert resp.status_code in (401, 403)

    def test_TC_APH_020_config_check_wrapper_error(self, test_client, admin_token):
        """TC_APH_020: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_apache_config_check", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/apache/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503
