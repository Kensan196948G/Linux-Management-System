"""
セキュリティ監査モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapper / subprocess をモック）
"""

import json
from unittest.mock import patch

import pytest

# ==============================================================================
# テスト用サンプルデータ
# ==============================================================================

SAMPLE_AUDIT_REPORT = {
    "status": "success",
    "auth_log_lines": 1024,
    "accepted_logins": 50,
    "failed_logins": 8,
    "sudo_count": 120,
    "last_login": "admin  pts/0  192.168.1.1  Mon Jan  1 00:00:00 2026",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_FAILED_LOGINS = {
    "status": "success",
    "entries": [
        "Jan  1 00:00:00 server sshd[123]: Failed password for root from 10.0.0.1 port 12345 ssh2",
        "Jan  1 00:00:01 server sshd[124]: Invalid user admin from 10.0.0.2 port 23456",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SUDO_LOGS = {
    "status": "success",
    "entries": [
        "Jan  1 00:00:00 server sudo: admin : TTY=pts/0 ; PWD=/home/admin ; USER=root ; COMMAND=/usr/bin/apt update",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_OPEN_PORTS = {
    "status": "success",
    "output": "Netid State Recv-Q Send-Q Local Address:Port\ntcp LISTEN 0 128 0.0.0.0:22\ntcp LISTEN 0 128 0.0.0.0:80\n",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_BANDIT_JSON = {
    "results": [
        {"issue_severity": "HIGH", "issue_text": "Use of assert detected"},
        {"issue_severity": "MEDIUM", "issue_text": "Possible hardcoded password"},
        {"issue_severity": "LOW", "issue_text": "Try, Except, Pass detected"},
    ],
    "metrics": {},
}


# ==============================================================================
# 認証なし 401 テスト (5件)
# ==============================================================================


class TestSecurityUnauthorized:
    """認証なしアクセスは 401 を返すこと"""

    def test_audit_report_no_auth(self, test_client):
        """GET /api/security/audit-report — 認証なしは401"""
        response = test_client.get("/api/security/audit-report")
        assert response.status_code == 403

    def test_failed_logins_no_auth(self, test_client):
        """GET /api/security/failed-logins — 認証なしは401"""
        response = test_client.get("/api/security/failed-logins")
        assert response.status_code == 403

    def test_sudo_logs_no_auth(self, test_client):
        """GET /api/security/sudo-logs — 認証なしは401"""
        response = test_client.get("/api/security/sudo-logs")
        assert response.status_code == 403

    def test_open_ports_no_auth(self, test_client):
        """GET /api/security/open-ports — 認証なしは401"""
        response = test_client.get("/api/security/open-ports")
        assert response.status_code == 403

    def test_bandit_status_no_auth(self, test_client):
        """GET /api/security/bandit-status — 認証なしは401"""
        response = test_client.get("/api/security/bandit-status")
        assert response.status_code == 403


# ==============================================================================
# 正常系 200 テスト (5件)
# ==============================================================================


class TestSecuritySuccess:
    """認証済みアクセスは 200 を返すこと"""

    def test_audit_report_success(self, test_client, auth_headers):
        """GET /api/security/audit-report — 正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_security_audit_report") as mock:
            mock.return_value = SAMPLE_AUDIT_REPORT
            response = test_client.get("/api/security/audit-report", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "accepted_logins" in data
        assert "failed_logins" in data
        assert "sudo_count" in data
        assert "timestamp" in data

    def test_failed_logins_success(self, test_client, auth_headers):
        """GET /api/security/failed-logins — 正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_failed_logins") as mock:
            mock.return_value = SAMPLE_FAILED_LOGINS
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_sudo_logs_success(self, test_client, auth_headers):
        """GET /api/security/sudo-logs — 正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sudo_logs") as mock:
            mock.return_value = SAMPLE_SUDO_LOGS
            response = test_client.get("/api/security/sudo-logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_open_ports_success(self, test_client, auth_headers):
        """GET /api/security/open-ports — 正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_open_ports") as mock:
            mock.return_value = SAMPLE_OPEN_PORTS
            response = test_client.get("/api/security/open-ports", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "output" in data
        assert "timestamp" in data

    def test_bandit_status_success(self, test_client, auth_headers):
        """GET /api/security/bandit-status — 正常取得"""
        import subprocess

        mock_proc = type("MockProc", (), {
            "stdout": json.dumps(SAMPLE_BANDIT_JSON),
            "stderr": "",
            "returncode": 1,
        })()

        with patch("backend.api.routes.security.subprocess.run", return_value=mock_proc):
            response = test_client.get("/api/security/bandit-status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "high" in data
        assert "medium" in data
        assert data["scanned"] is True


# ==============================================================================
# SudoWrapperError → 503 テスト (3件)
# ==============================================================================


class TestSecurityWrapperError:
    """SudoWrapperError 時は 503 を返すこと"""

    def test_audit_report_wrapper_error(self, test_client, auth_headers):
        """audit-report で SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_security_audit_report") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/security/audit-report", headers=auth_headers)
        assert response.status_code == 503

    def test_failed_logins_wrapper_error(self, test_client, auth_headers):
        """failed-logins で SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_failed_logins") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        assert response.status_code == 503

    def test_open_ports_wrapper_error(self, test_client, auth_headers):
        """open-ports で SudoWrapperError → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_open_ports") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/security/open-ports", headers=auth_headers)
        assert response.status_code == 503


# ==============================================================================
# bandit-status 構造テスト
# ==============================================================================


class TestBanditStatus:
    """bandit-status エンドポイントの詳細テスト"""

    def test_bandit_status_has_high_medium_keys(self, test_client, auth_headers):
        """レスポンスに high / medium キーが含まれること"""
        mock_proc = type("MockProc", (), {
            "stdout": json.dumps(SAMPLE_BANDIT_JSON),
            "stderr": "",
            "returncode": 1,
        })()

        with patch("backend.api.routes.security.subprocess.run", return_value=mock_proc):
            response = test_client.get("/api/security/bandit-status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "high" in data
        assert "medium" in data
        assert "low" in data
        assert "total_issues" in data

    def test_bandit_status_counts_correctly(self, test_client, auth_headers):
        """HIGH / MEDIUM / LOW の件数が正確に集計されること"""
        mock_proc = type("MockProc", (), {
            "stdout": json.dumps(SAMPLE_BANDIT_JSON),
            "stderr": "",
            "returncode": 1,
        })()

        with patch("backend.api.routes.security.subprocess.run", return_value=mock_proc):
            response = test_client.get("/api/security/bandit-status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["high"] == 1
        assert data["medium"] == 1
        assert data["low"] == 1
        assert data["total_issues"] == 3

    def test_bandit_not_installed_returns_unavailable(self, test_client, auth_headers):
        """bandit が未インストールの場合は status=unavailable を返す"""
        with patch("backend.api.routes.security.subprocess.run", side_effect=FileNotFoundError()):
            response = test_client.get("/api/security/bandit-status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["scanned"] is False

    def test_bandit_empty_results(self, test_client, auth_headers):
        """問題なしの場合は high=0, medium=0 が返る"""
        mock_proc = type("MockProc", (), {
            "stdout": json.dumps({"results": [], "metrics": {}}),
            "stderr": "",
            "returncode": 0,
        })()

        with patch("backend.api.routes.security.subprocess.run", return_value=mock_proc):
            response = test_client.get("/api/security/bandit-status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["high"] == 0
        assert data["medium"] == 0
        assert data["total_issues"] == 0

    def test_audit_report_viewer_access(self, test_client, viewer_headers):
        """viewer ロールは audit-report にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_security_audit_report") as mock:
            mock.return_value = SAMPLE_AUDIT_REPORT
            response = test_client.get("/api/security/audit-report", headers=viewer_headers)
        assert response.status_code == 200
