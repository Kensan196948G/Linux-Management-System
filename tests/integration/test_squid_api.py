"""
Squid Proxy Server モジュール - 統合テスト

テストケース数: 20件
- 正常系: status/cache/logs/config-check エンドポイント
- unavailable 系: Squid 未インストール環境
- 異常系: 権限不足、未認証
- セキュリティ: SudoWrapperError 処理、logs パラメータバリデーション
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SQUID_STATUS_OK = {
    "status": "success",
    "service": "squid",
    "active": "active",
    "enabled": "enabled",
    "version": "Squid Cache: Version 5.7",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_STATUS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "Squid service not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_CACHE_OK = {
    "status": "success",
    "cache_raw": "Squid Object Cache: Version 5.7\nStart Time: Thu, 01 Mar 2026 00:00:00 GMT\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_CACHE_UNAVAILABLE = {
    "status": "unavailable",
    "message": "squid not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_LOGS_OK = {
    "status": "success",
    "logs_raw": "1709251200.000   1234 192.168.1.2 TCP_MISS/200 1234 GET http://example.com/ - DIRECT/93.184.216.34 text/html",
    "lines": 50,
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_LOGS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "squid not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_CONFIG_OK = {
    "status": "success",
    "syntax_ok": True,
    "output": "",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_CONFIG_ERROR = {
    "status": "success",
    "syntax_ok": False,
    "output": "FATAL: Bungled squid.conf line 1: invalid directive",
    "timestamp": "2026-03-01T00:00:00Z",
}

SQUID_CONFIG_UNAVAILABLE = {
    "status": "unavailable",
    "message": "squid not found",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストケース
# ===================================================================


class TestSquidStatus:
    """TC_SQD_001〜005: Squid status エンドポイントテスト"""

    def test_TC_SQD_001_status_ok(self, test_client, admin_token):
        """TC_SQD_001: Squid 正常稼働時のステータス取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_status", return_value=SQUID_STATUS_OK):
            resp = test_client.get("/api/squid/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "squid"
        assert data["active"] == "active"

    def test_TC_SQD_002_status_unavailable(self, test_client, admin_token):
        """TC_SQD_002: Squid 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_status", return_value=SQUID_STATUS_UNAVAILABLE):
            resp = test_client.get("/api/squid/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SQD_003_status_unauthorized(self, test_client):
        """TC_SQD_003: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/squid/status")
        assert resp.status_code in (401, 403)

    def test_TC_SQD_004_status_viewer_allowed(self, test_client, viewer_token):
        """TC_SQD_004: viewer ロールは read:squid 権限で取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_status", return_value=SQUID_STATUS_OK):
            resp = test_client.get("/api/squid/status", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_SQD_005_status_wrapper_error(self, test_client, admin_token):
        """TC_SQD_005: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_status", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/squid/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestSquidCache:
    """TC_SQD_006〜009: Squid cache エンドポイントテスト"""

    def test_TC_SQD_006_cache_ok(self, test_client, admin_token):
        """TC_SQD_006: Squid キャッシュ統計の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_cache", return_value=SQUID_CACHE_OK):
            resp = test_client.get("/api/squid/cache", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "cache_raw" in data

    def test_TC_SQD_007_cache_unavailable(self, test_client, admin_token):
        """TC_SQD_007: Squid 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_cache", return_value=SQUID_CACHE_UNAVAILABLE):
            resp = test_client.get("/api/squid/cache", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SQD_008_cache_unauthorized(self, test_client):
        """TC_SQD_008: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/squid/cache")
        assert resp.status_code in (401, 403)

    def test_TC_SQD_009_cache_wrapper_error(self, test_client, admin_token):
        """TC_SQD_009: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_cache", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/squid/cache", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestSquidLogs:
    """TC_SQD_010〜015: Squid logs エンドポイントテスト"""

    def test_TC_SQD_010_logs_ok(self, test_client, admin_token):
        """TC_SQD_010: Squid アクセスログの正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_OK):
            resp = test_client.get("/api/squid/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "logs_raw" in data

    def test_TC_SQD_011_logs_with_lines_param(self, test_client, admin_token):
        """TC_SQD_011: lines パラメータ指定でのログ取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_OK) as mock:
            resp = test_client.get("/api/squid/logs?lines=100", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        mock.assert_called_once_with(lines=100)

    def test_TC_SQD_012_logs_lines_max_boundary(self, test_client, admin_token):
        """TC_SQD_012: lines=200（上限値）は許可される"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_OK):
            resp = test_client.get("/api/squid/logs?lines=200", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_TC_SQD_013_logs_lines_over_max(self, test_client, admin_token):
        """TC_SQD_013: lines=201（上限超過）は 422 Unprocessable Entity"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_OK):
            resp = test_client.get("/api/squid/logs?lines=201", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 422

    def test_TC_SQD_014_logs_lines_zero(self, test_client, admin_token):
        """TC_SQD_014: lines=0（下限未満）は 422 Unprocessable Entity"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_OK):
            resp = test_client.get("/api/squid/logs?lines=0", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 422

    def test_TC_SQD_015_logs_unavailable(self, test_client, admin_token):
        """TC_SQD_015: Squid 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_logs", return_value=SQUID_LOGS_UNAVAILABLE):
            resp = test_client.get("/api/squid/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"


class TestSquidConfigCheck:
    """TC_SQD_016〜020: Squid config-check エンドポイントテスト"""

    def test_TC_SQD_016_config_check_syntax_ok(self, test_client, admin_token):
        """TC_SQD_016: 設定ファイル構文 OK の場合 syntax_ok=True"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_config_check", return_value=SQUID_CONFIG_OK):
            resp = test_client.get("/api/squid/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["syntax_ok"] is True

    def test_TC_SQD_017_config_check_syntax_error(self, test_client, admin_token):
        """TC_SQD_017: 設定ファイルに構文エラーがある場合 syntax_ok=False"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_config_check", return_value=SQUID_CONFIG_ERROR):
            resp = test_client.get("/api/squid/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["syntax_ok"] is False

    def test_TC_SQD_018_config_check_unavailable(self, test_client, admin_token):
        """TC_SQD_018: Squid 未インストール時の unavailable"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_config_check", return_value=SQUID_CONFIG_UNAVAILABLE):
            resp = test_client.get("/api/squid/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_SQD_019_config_check_unauthorized(self, test_client):
        """TC_SQD_019: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/squid/config-check")
        assert resp.status_code in (401, 403)

    def test_TC_SQD_020_config_check_wrapper_error(self, test_client, admin_token):
        """TC_SQD_020: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_squid_config_check", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/squid/config-check", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503
