"""
FTP Server モジュール - 統合テスト

テストケース数: 20件
- 正常系: status/users/sessions/logs エンドポイント
- unavailable 系: FTP 未インストール環境
- 異常系: 権限不足、未認証
- セキュリティ: SudoWrapperError 処理、logs パラメータバリデーション
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

FTP_STATUS_OK = {
    "status": "success",
    "service": "proftpd",
    "active": "active",
    "enabled": "enabled",
    "version": "ProFTPD 1.3.6 (maint)",
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_STATUS_VSFTPD = {
    "status": "success",
    "service": "vsftpd",
    "active": "active",
    "enabled": "enabled",
    "version": "vsftpd 3.0.5",
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_STATUS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "FTP service not found (proftpd/vsftpd/pure-ftpd)",
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_USERS_OK = {
    "status": "success",
    "users_raw": "root\ndaemon\nbin\nsys\n",
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_USERS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "FTP service not found",
    "users": [],
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_SESSIONS_OK = {
    "status": "success",
    "sessions_raw": "State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port\nESTAB  0       0       192.168.1.1:21    192.168.1.2:54321",
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_SESSIONS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "FTP service not found",
    "sessions": [],
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_LOGS_OK = {
    "status": "success",
    "logs_raw": "Mar 01 00:00:00 host proftpd[1234]: 192.168.1.2 - USER anonymous: Login successful.",
    "lines": 50,
    "timestamp": "2026-03-01T00:00:00Z",
}

FTP_LOGS_UNAVAILABLE = {
    "status": "unavailable",
    "message": "No FTP log entries found",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストケース
# ===================================================================


class TestFtpStatus:
    """TC_FTP_001〜005: FTP status エンドポイントテスト"""

    def test_TC_FTP_001_status_ok(self, test_client, admin_token):
        """TC_FTP_001: proftpd 正常稼働時のステータス取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_status", return_value=FTP_STATUS_OK):
            resp = test_client.get("/api/ftp/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "proftpd"
        assert data["active"] == "active"

    def test_TC_FTP_002_status_vsftpd(self, test_client, admin_token):
        """TC_FTP_002: vsftpd サービス正常稼働時のステータス取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_status", return_value=FTP_STATUS_VSFTPD):
            resp = test_client.get("/api/ftp/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "vsftpd"

    def test_TC_FTP_003_status_unavailable(self, test_client, admin_token):
        """TC_FTP_003: FTP 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_status", return_value=FTP_STATUS_UNAVAILABLE):
            resp = test_client.get("/api/ftp/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_FTP_004_status_unauthorized(self, test_client):
        """TC_FTP_004: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/ftp/status")
        assert resp.status_code in (401, 403)

    def test_TC_FTP_005_status_viewer_allowed(self, test_client, viewer_token):
        """TC_FTP_005: viewer ロールは read:ftp 権限で取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_status", return_value=FTP_STATUS_OK):
            resp = test_client.get("/api/ftp/status", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_FTP_006_status_wrapper_error(self, test_client, admin_token):
        """TC_FTP_006: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_status", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/ftp/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestFtpUsers:
    """TC_FTP_007〜010: FTP users エンドポイントテスト"""

    def test_TC_FTP_007_users_ok(self, test_client, admin_token):
        """TC_FTP_007: FTP ユーザー一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_users", return_value=FTP_USERS_OK):
            resp = test_client.get("/api/ftp/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "users_raw" in data

    def test_TC_FTP_008_users_unavailable(self, test_client, admin_token):
        """TC_FTP_008: FTP 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_users", return_value=FTP_USERS_UNAVAILABLE):
            resp = test_client.get("/api/ftp/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_FTP_009_users_unauthorized(self, test_client):
        """TC_FTP_009: 未認証時の 401/403 返却"""
        resp = test_client.get("/api/ftp/users")
        assert resp.status_code in (401, 403)

    def test_TC_FTP_010_users_wrapper_error(self, test_client, admin_token):
        """TC_FTP_010: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_users", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/ftp/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503


class TestFtpSessions:
    """TC_FTP_011〜013: FTP sessions エンドポイントテスト"""

    def test_TC_FTP_011_sessions_ok(self, test_client, admin_token):
        """TC_FTP_011: アクティブセッション一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_sessions", return_value=FTP_SESSIONS_OK):
            resp = test_client.get("/api/ftp/sessions", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "sessions_raw" in data

    def test_TC_FTP_012_sessions_unavailable(self, test_client, admin_token):
        """TC_FTP_012: FTP 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_sessions", return_value=FTP_SESSIONS_UNAVAILABLE):
            resp = test_client.get("/api/ftp/sessions", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_FTP_013_sessions_viewer_allowed(self, test_client, viewer_token):
        """TC_FTP_013: viewer ロールでもセッション取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_sessions", return_value=FTP_SESSIONS_OK):
            resp = test_client.get("/api/ftp/sessions", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200


class TestFtpLogs:
    """TC_FTP_014〜020: FTP logs エンドポイントテスト"""

    def test_TC_FTP_014_logs_ok(self, test_client, admin_token):
        """TC_FTP_014: FTP ログの正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_OK):
            resp = test_client.get("/api/ftp/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "logs_raw" in data

    def test_TC_FTP_015_logs_with_lines_param(self, test_client, admin_token):
        """TC_FTP_015: lines パラメータ指定でのログ取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_OK) as mock:
            resp = test_client.get("/api/ftp/logs?lines=100", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        mock.assert_called_once_with(lines=100)

    def test_TC_FTP_016_logs_lines_max_boundary(self, test_client, admin_token):
        """TC_FTP_016: lines=200（上限値）は許可される"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_OK):
            resp = test_client.get("/api/ftp/logs?lines=200", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

    def test_TC_FTP_017_logs_lines_over_max(self, test_client, admin_token):
        """TC_FTP_017: lines=201（上限超過）は 422 Unprocessable Entity"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_OK):
            resp = test_client.get("/api/ftp/logs?lines=201", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 422

    def test_TC_FTP_018_logs_lines_zero(self, test_client, admin_token):
        """TC_FTP_018: lines=0（下限未満）は 422 Unprocessable Entity"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_OK):
            resp = test_client.get("/api/ftp/logs?lines=0", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 422

    def test_TC_FTP_019_logs_unavailable(self, test_client, admin_token):
        """TC_FTP_019: FTP 未インストール環境での unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", return_value=FTP_LOGS_UNAVAILABLE):
            resp = test_client.get("/api/ftp/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_FTP_020_logs_wrapper_error(self, test_client, admin_token):
        """TC_FTP_020: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ftp_logs", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/ftp/logs", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503
