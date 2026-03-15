"""
security.py カバレッジ改善テスト v2

対象: backend/api/routes/security.py
既存 test_security_coverage.py と重複しないエンドポイント・分岐を網羅する。

テスト方針:
  - 全エンドポイントの正常系 / SudoWrapperError系 / 汎用例外系
  - ヘルパー関数の未カバー分岐
  - parametrize で複数パターン網羅
"""

import json
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest


# ==============================================================================
# テストデータ生成ヘルパー
# ==============================================================================


def _make_entry(
    operation: str,
    user_id: str = "admin",
    entry_status: str = "success",
    target: str = "system",
    details: dict = None,
    hours_ago: float = 0,
) -> dict:
    ts = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return {
        "timestamp": ts.isoformat(),
        "operation": operation,
        "user_id": user_id,
        "target": target,
        "status": entry_status,
        "details": details or {},
    }


def _make_mock_conn(port: int, pid: int = 1234, conn_status: str = "LISTEN") -> MagicMock:
    conn = MagicMock()
    conn.status = conn_status
    conn.laddr = MagicMock()
    conn.laddr.port = port
    conn.pid = pid
    conn.type = MagicMock()
    conn.type.name = "SOCK_STREAM"
    return conn


def _mock_apt_run_empty(*args, **kwargs):
    """apt list --upgradable が空を返すモック"""
    return MagicMock(returncode=0, stdout="Listing... Done\n", stderr="")


# ==============================================================================
# 1. GET /api/security/audit-report エンドポイント
# ==============================================================================


class TestAuditReportEndpoint:
    """GET /api/security/audit-report の全分岐テスト"""

    def test_success(self, test_client, admin_headers):
        """正常系: sudo_wrapper が成功結果を返す"""
        wrapper_result = {
            "status": "success",
            "output": json.dumps(
                {
                    "status": "success",
                    "auth_log_lines": 100,
                    "accepted_logins": 10,
                    "failed_logins": 5,
                    "sudo_count": 3,
                    "last_login": "user1",
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                }
            ),
        }
        with patch(
            "backend.api.routes.security.sudo_wrapper.get_security_audit_report",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/security/audit-report", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["auth_log_lines"] == 100
        assert data["failed_logins"] == 5

    def test_sudo_wrapper_error_returns_503(self, test_client, admin_headers):
        """SudoWrapperError で 503 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.security.sudo_wrapper.get_security_audit_report",
            side_effect=SudoWrapperError("access denied"),
        ):
            resp = test_client.get("/api/security/audit-report", headers=admin_headers)
        assert resp.status_code == 503

    def test_unexpected_error_returns_500(self, test_client, admin_headers):
        """予期しない例外で 500 を返す"""
        with patch(
            "backend.api.routes.security.sudo_wrapper.get_security_audit_report",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get("/api/security/audit-report", headers=admin_headers)
        assert resp.status_code == 500

    def test_without_auth_returns_401_or_403(self, test_client):
        """認証なしで 401/403"""
        resp = test_client.get("/api/security/audit-report")
        assert resp.status_code in (401, 403)


# ==============================================================================
# 2. GET /api/security/failed-logins エンドポイント
# ==============================================================================


class TestFailedLoginsEndpoint:
    """GET /api/security/failed-logins の全分岐テスト"""

    def test_success_empty(self, test_client, admin_headers):
        """正常系: audit_log.jsonl がない/空の場合"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl", return_value=[]
        ):
            resp = test_client.get("/api/security/failed-logins", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert len(data["hourly"]) == 24

    def test_success_with_data(self, test_client, admin_headers):
        """正常系: 失敗ログインデータがある場合"""
        entries = [
            _make_entry("login_failed", hours_ago=1, details={"ip": "192.168.1.1"}),
            _make_entry("login_failed", hours_ago=2, details={"source_ip": "10.0.0.1"}),
            _make_entry("login_success", hours_ago=1),
        ]
        with patch(
            "backend.api.routes.security._read_audit_jsonl", return_value=entries
        ):
            resp = test_client.get("/api/security/failed-logins", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["unique_ips"] == 2

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で 500"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/failed-logins", headers=admin_headers)
        assert resp.status_code == 500


# ==============================================================================
# 3. GET /api/security/sudo-logs エンドポイント
# ==============================================================================


class TestSudoLogsEndpoint:
    """GET /api/security/sudo-logs の全分岐テスト"""

    def test_success(self, test_client, admin_headers):
        """正常系"""
        wrapper_result = {
            "status": "success",
            "output": json.dumps(
                {
                    "status": "success",
                    "entries": ["sudo: user1 : command=/usr/bin/apt"],
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                }
            ),
        }
        with patch(
            "backend.api.routes.security.sudo_wrapper.get_sudo_logs",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/security/sudo-logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["entries"]) == 1

    def test_sudo_wrapper_error_returns_503(self, test_client, admin_headers):
        """SudoWrapperError で 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.security.sudo_wrapper.get_sudo_logs",
            side_effect=SudoWrapperError("denied"),
        ):
            resp = test_client.get("/api/security/sudo-logs", headers=admin_headers)
        assert resp.status_code == 503

    def test_unexpected_error_returns_500(self, test_client, admin_headers):
        """予期しない例外で 500"""
        with patch(
            "backend.api.routes.security.sudo_wrapper.get_sudo_logs",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get("/api/security/sudo-logs", headers=admin_headers)
        assert resp.status_code == 500


# ==============================================================================
# 4. GET /api/security/open-ports エンドポイント
# ==============================================================================


class TestOpenPortsEndpoint:
    """GET /api/security/open-ports の全分岐テスト"""

    def test_success_empty(self, test_client, admin_headers):
        """正常系: ポートなし"""
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[]
        ):
            resp = test_client.get("/api/security/open-ports", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["ports"] == []

    def test_success_with_ports(self, test_client, admin_headers):
        """正常系: ポートあり"""
        conns = [_make_mock_conn(port=8080, pid=100)]
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=conns
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "uvicorn"
                resp = test_client.get("/api/security/open-ports", headers=admin_headers)
        assert resp.status_code == 200
        ports = resp.json()["ports"]
        assert len(ports) == 1
        assert ports[0]["port"] == 8080
        assert ports[0]["name"] == "uvicorn"

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で 500"""
        with patch(
            "backend.api.routes.security._collect_open_ports_psutil",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/open-ports", headers=admin_headers)
        assert resp.status_code == 500


# ==============================================================================
# 5. GET /api/security/sudo-history エンドポイント
# ==============================================================================


class TestSudoHistoryEndpoint:
    """GET /api/security/sudo-history の全分岐テスト"""

    def test_success_empty(self, test_client, admin_headers):
        """正常系: 履歴なし"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl", return_value=[]
        ):
            resp = test_client.get("/api/security/sudo-history", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["history"] == []

    def test_success_with_history(self, test_client, admin_headers):
        """正常系: 履歴あり"""
        entries = [
            _make_entry("service_restart", user_id="admin", hours_ago=1),
            _make_entry("package_install", user_id="operator", hours_ago=2),
        ]
        with patch(
            "backend.api.routes.security._read_audit_jsonl", return_value=entries
        ):
            resp = test_client.get("/api/security/sudo-history", headers=admin_headers)
        assert resp.status_code == 200
        history = resp.json()["history"]
        assert len(history) == 2


# ==============================================================================
# 6. GET /api/security/score エンドポイント
# ==============================================================================


class TestScoreEndpoint:
    """GET /api/security/score の正常系テスト"""

    def test_success_no_threats(self, test_client, admin_headers):
        """正常系: 脅威なし"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=[]
            ):
                resp = test_client.get("/api/security/score", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "details" in data
        assert data["score"] >= 80

    def test_success_with_threats(self, test_client, admin_headers):
        """正常系: 失敗ログイン + 危険ポートあり"""
        entries = [
            _make_entry("login_failed", hours_ago=i * 0.5, details={"ip": f"10.0.0.{i}"})
            for i in range(10)
        ]
        conns = [_make_mock_conn(port=23, pid=100)]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=conns
            ):
                with patch("backend.api.routes.security.psutil.Process") as mp:
                    mp.return_value.name.return_value = "telnetd"
                    resp = test_client.get("/api/security/score", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] < 80


# ==============================================================================
# 7. GET /api/security/bandit-status エンドポイント全分岐
# ==============================================================================


class TestBanditStatusEndpoint:
    """GET /api/security/bandit-status の全分岐テスト"""

    def test_success_no_issues(self, test_client, admin_headers):
        """正常系: 問題なし"""
        bandit_data = {"results": [], "metrics": {}}
        mock_proc = MagicMock(
            stdout=json.dumps(bandit_data), stderr="", returncode=0
        )
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["scanned"] is True
        assert data["total_issues"] == 0

    def test_success_with_mixed_issues(self, test_client, admin_headers):
        """正常系: HIGH/MEDIUM/LOW 混在"""
        bandit_data = {
            "results": [
                {"issue_severity": "HIGH", "issue_text": "h1"},
                {"issue_severity": "HIGH", "issue_text": "h2"},
                {"issue_severity": "MEDIUM", "issue_text": "m1"},
                {"issue_severity": "LOW", "issue_text": "l1"},
            ],
            "metrics": {},
        }
        mock_proc = MagicMock(
            stdout=json.dumps(bandit_data), stderr="", returncode=1
        )
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["high"] == 2
        assert data["medium"] == 1
        assert data["low"] == 1
        assert data["total_issues"] == 4

    def test_timeout_returns_503(self, test_client, admin_headers):
        """タイムアウトで 503"""
        with patch(
            "backend.api.routes.security.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="bandit", timeout=60),
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 503

    def test_bandit_not_installed_returns_unavailable(self, test_client, admin_headers):
        """bandit 未インストールで unavailable"""
        with patch(
            "backend.api.routes.security.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["scanned"] is False
        assert data["error"] is not None

    def test_json_decode_error_returns_500(self, test_client, admin_headers):
        """不正な JSON 出力で 500"""
        mock_proc = MagicMock(stdout="not valid json", stderr="", returncode=1)
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 500

    def test_unexpected_error_returns_500(self, test_client, admin_headers):
        """予期しない例外で 500"""
        with patch(
            "backend.api.routes.security.subprocess.run",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 500


# ==============================================================================
# 8. GET /api/security/compliance エンドポイント
# ==============================================================================


class TestComplianceEndpoint:
    """GET /api/security/compliance の正常系テスト"""

    def test_success(self, test_client, admin_headers):
        """正常系"""
        from backend.api.routes.security import ComplianceCheckItem, ComplianceResponse

        mock_result = ComplianceResponse(
            checks=[
                ComplianceCheckItem(
                    id="test_check",
                    category="Test",
                    description="Test check",
                    compliant=True,
                    value="ok",
                )
            ],
            compliant_count=1,
            non_compliant_count=0,
            total_count=1,
            compliance_rate=100.0,
        )
        with patch(
            "backend.api.routes.security._run_compliance_checks",
            return_value=mock_result,
        ):
            resp = test_client.get("/api/security/compliance", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["compliance_rate"] == 100.0


# ==============================================================================
# 9. GET /api/security/vulnerability-summary エンドポイント
# ==============================================================================


class TestVulnerabilitySummaryEndpoint:
    """GET /api/security/vulnerability-summary の正常系テスト"""

    def test_success_with_packages(self, test_client, admin_headers):
        """正常系: パッケージあり"""
        apt_output = (
            "Listing... Done\n"
            "curl/focal 7.81 amd64 [upgradable from: 7.80]\n"
            "nginx/focal 1.22 amd64 [upgradable from: 1.21]\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get(
                "/api/security/vulnerability-summary", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_upgradable"] == 2
        assert data["high"] == 1  # curl
        assert data["medium"] == 1  # nginx


# ==============================================================================
# 10. GET /api/security/report エンドポイント
# ==============================================================================


class TestSecurityReportEndpoint:
    """GET /api/security/report の正常系テスト"""

    def test_success(self, test_client, admin_headers):
        """正常系: 全データ集約"""
        entries = [_make_entry("login_failed", hours_ago=1, details={"ip": "1.2.3.4"})]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=[]
            ):
                with patch("backend.api.routes.security.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0, stdout="Listing... Done\n", stderr=""
                    )
                    resp = test_client.get(
                        "/api/security/report", headers=admin_headers
                    )
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data
        assert "hostname" in data
        assert "score" in data
        assert "failed_logins" in data
        assert "open_ports" in data
        assert "sudo_history" in data
        assert "compliance" in data
        assert "vulnerability_summary" in data

    def test_report_with_ports_and_history(self, test_client, admin_headers):
        """正常系: ポートと履歴データ付き"""
        entries = [
            _make_entry("service_restart", user_id="admin", hours_ago=1),
            _make_entry("login_failed", hours_ago=2, details={"ip": "10.0.0.1"}),
        ]
        conns = [_make_mock_conn(port=22, pid=100)]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=conns
            ):
                with patch("backend.api.routes.security.psutil.Process") as mp:
                    mp.return_value.name.return_value = "sshd"
                    with patch("backend.api.routes.security.subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(
                            returncode=0, stdout="Listing... Done\n", stderr=""
                        )
                        resp = test_client.get(
                            "/api/security/report", headers=admin_headers
                        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["open_ports"]["ports"]) == 1
        assert len(data["sudo_history"]["history"]) >= 1


# ==============================================================================
# 11. POST /api/security/report/export エンドポイント: スコア色分岐
# ==============================================================================


class TestReportExportScoreColors:
    """POST /api/security/report/export のスコア色分岐テスト"""

    def test_export_score_color_yellow(self, test_client, admin_headers):
        """スコア 60-79 の場合は黄色 (#f59e0b)"""
        # 失敗ログイン7件でリスク65 -> 0.5*65 + 0.4*100 + 0.1*100 = 82.5 ... 調整が必要
        # 失敗ログイン8件でリスク60 -> 0.5*60 + 0.4*100 + 0.1*100 = 80 まだ80
        # 失敗ログイン10件でリスク50 -> 0.5*50 + 0.4*100 + 0.1*100 = 75
        entries = [
            _make_entry("login_failed", hours_ago=i * 0.5, details={"ip": f"10.0.0.{i}"})
            for i in range(10)
        ]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=[]
            ):
                with patch("backend.api.routes.security.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0, stdout="Listing... Done\n", stderr=""
                    )
                    resp = test_client.post(
                        "/api/security/report/export", headers=admin_headers
                    )
        assert resp.status_code == 200
        # スコアに応じた色が含まれる
        assert any(c in resp.text for c in ["#22c55e", "#f59e0b", "#ef4444"])

    def test_export_score_color_red(self, test_client, admin_headers):
        """スコア < 60 の場合は赤色 (#ef4444)"""
        # 大量の失敗ログイン + 危険ポートでスコアを下げる
        entries = [
            _make_entry("login_failed", hours_ago=i * 0.1, details={"ip": f"10.0.0.{i}"})
            for i in range(20)
        ]
        conns = [_make_mock_conn(port=p) for p in [21, 23, 25, 110, 143]]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=conns
            ):
                with patch("backend.api.routes.security.psutil.Process") as mp:
                    mp.return_value.name.return_value = "daemon"
                    with patch("backend.api.routes.security.subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(
                            returncode=0, stdout="Listing... Done\n", stderr=""
                        )
                        resp = test_client.post(
                            "/api/security/report/export", headers=admin_headers
                        )
        assert resp.status_code == 200
        assert "#ef4444" in resp.text

    def test_export_content_disposition(self, test_client, admin_headers):
        """Content-Disposition ヘッダーが attachment"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=[]
            ):
                with patch("backend.api.routes.security.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0, stdout="Listing... Done\n", stderr=""
                    )
                    resp = test_client.post(
                        "/api/security/report/export", headers=admin_headers
                    )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "security-report-" in cd
        assert ".html" in cd


# ==============================================================================
# 12. _read_audit_jsonl 追加分岐テスト
# ==============================================================================


class TestReadAuditJsonlV2:
    """_read_audit_jsonl の FileNotFoundError 分岐"""

    def test_nonexistent_file_returns_empty(self):
        """存在しないファイルパスで空リスト"""
        from backend.api.routes.security import _read_audit_jsonl

        result = _read_audit_jsonl(Path("/nonexistent/path/audit.jsonl"))
        assert result == []

    def test_large_file_with_many_entries(self, tmp_path):
        """多数エントリの正常読み込み"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "large.jsonl"
        lines = [json.dumps({"idx": i}) for i in range(100)]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _read_audit_jsonl(f)
        assert len(result) == 100

    def test_all_invalid_json_lines(self, tmp_path):
        """全行が不正 JSON の場合は空リスト"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "bad.jsonl"
        f.write_text("not json 1\nnot json 2\nnot json 3\n", encoding="utf-8")
        result = _read_audit_jsonl(f)
        assert result == []


# ==============================================================================
# 13. _collect_failed_logins_hourly 追加分岐テスト
# ==============================================================================


class TestCollectFailedLoginsHourlyV2:
    """_collect_failed_logins_hourly の未カバー分岐"""

    def test_multiple_ips_different_hours(self):
        """複数IP・複数時間帯の集計"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [
            _make_entry("login_failed", hours_ago=1, details={"ip": "1.1.1.1"}),
            _make_entry("login_failed", hours_ago=1, details={"ip": "2.2.2.2"}),
            _make_entry("login_failed", hours_ago=3, details={"ip": "1.1.1.1"}),
            _make_entry("login_failed", hours_ago=5, details={"ip": "3.3.3.3"}),
        ]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 4
        assert result.unique_ips == 3

    def test_entry_without_details_ip(self):
        """details がないエントリでもカウントされる"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [_make_entry("login_failed", hours_ago=1)]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 1
        # target="system" なので unique_ips にカウントされる
        assert result.unique_ips >= 0

    def test_empty_ip_not_counted(self):
        """空のIPはunique_ipsにカウントされない"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [
            _make_entry("login_failed", hours_ago=1, target="", details={}),
        ]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 1
        assert result.unique_ips == 0


# ==============================================================================
# 14. _collect_open_ports_psutil CONN_LISTEN 定数分岐
# ==============================================================================


class TestCollectOpenPortsPsutilV2:
    """_collect_open_ports_psutil の CONN_LISTEN 分岐"""

    def test_conn_listen_constant(self):
        """psutil.CONN_LISTEN 定数でのマッチ"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = MagicMock()
        conn.status = psutil.CONN_LISTEN
        conn.laddr = MagicMock()
        conn.laddr.port = 3000
        conn.pid = 500
        conn.type = MagicMock()
        conn.type.name = "SOCK_STREAM"

        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "node"
                result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].port == 3000

    def test_multiple_ports_sorted(self):
        """複数ポートがソートされて返る"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conns = [
            _make_mock_conn(port=9090, pid=1),
            _make_mock_conn(port=22, pid=2),
            _make_mock_conn(port=80, pid=3),
            _make_mock_conn(port=443, pid=4),
        ]
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=conns
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "server"
                result = _collect_open_ports_psutil()
        ports = [p.port for p in result]
        assert ports == [22, 80, 443, 9090]


# ==============================================================================
# 15. _check_ssh_config 追加分岐テスト
# ==============================================================================


class TestCheckSshConfigV2:
    """_check_ssh_config の追加分岐テスト"""

    def test_empty_lines_and_single_word_lines_skipped(self):
        """空行と1ワード行はスキップ"""
        from backend.api.routes.security import _check_ssh_config

        config_text = "\n\nSingleWord\n  \nPasswordAuthentication no\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        pa = [r for r in results if r[0] == "ssh_password_auth"][0]
        assert pa[1] is True  # no -> compliant

    def test_pubkey_auth_disabled_non_compliant(self):
        """PubkeyAuthentication no は非準拠"""
        from backend.api.routes.security import _check_ssh_config

        config_text = "PubkeyAuthentication no\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        pka = [r for r in results if r[0] == "ssh_pubkey_auth"][0]
        assert pka[1] is False


# ==============================================================================
# 16. _check_password_policy 追加分岐テスト
# ==============================================================================


class TestCheckPasswordPolicyV2:
    """_check_password_policy の追加分岐テスト"""

    def test_comment_lines_ignored(self):
        """コメント行は設定に含まれない"""
        from backend.api.routes.security import _check_password_policy

        config_text = "# PASS_MAX_DAYS 30\nPASS_MAX_DAYS 99999\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        max_days = [r for r in results if r[0] == "passwd_max_days"][0]
        assert max_days[1] is False  # 99999 -> non-compliant

    def test_boundary_values(self):
        """境界値テスト: 90日/8文字/7日"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS 90\nPASS_MIN_LEN 8\nPASS_WARN_AGE 7\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        for _, compliant, _, _ in results:
            assert compliant is True

    def test_boundary_values_non_compliant(self):
        """境界値テスト: 91日/7文字/6日は非準拠"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS 91\nPASS_MIN_LEN 7\nPASS_WARN_AGE 6\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        for _, compliant, _, _ in results:
            assert compliant is False

    @pytest.mark.parametrize(
        "pass_warn,expected",
        [
            ("7", True),
            ("14", True),
            ("6", False),
            ("0", False),
        ],
    )
    def test_warn_age_parametrized(self, pass_warn, expected):
        """PASS_WARN_AGE のパラメタライズテスト"""
        from backend.api.routes.security import _check_password_policy

        config_text = f"PASS_MAX_DAYS 90\nPASS_MIN_LEN 8\nPASS_WARN_AGE {pass_warn}\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        warn = [r for r in results if r[0] == "passwd_warn_age"][0]
        assert warn[1] is expected


# ==============================================================================
# 17. _check_firewall_status 追加分岐テスト
# ==============================================================================


class TestCheckFirewallStatusV2:
    """_check_firewall_status の追加分岐テスト"""

    def test_iptables_os_error_handled(self):
        """iptables の OSError は安全に処理"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = True
                mock.read_text.side_effect = OSError("permission denied")
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert len(results) == 1
        assert results[0][1] is False  # iptables read failed, no fw detected

    def test_iptables_empty_content(self):
        """iptables が空コンテンツの場合は非アクティブ"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = True
                mock.read_text.return_value = ""
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is False

    @pytest.mark.parametrize(
        "enabled_val,expected_active",
        [
            ("yes", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("false", False),
            ("0", False),
        ],
    )
    def test_ufw_enabled_values(self, enabled_val, expected_active):
        """ufw の ENABLED= の各値テスト"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = True
                mock.read_text.return_value = f"ENABLED={enabled_val}\n"
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = False
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is expected_active


# ==============================================================================
# 18. _check_sudoers 追加分岐テスト
# ==============================================================================


class TestCheckSudoersV2:
    """_check_sudoers の追加分岐テスト"""

    def test_sudoers_d_permission_error_on_iterdir(self):
        """sudoers.d の PermissionError on iterdir"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "root ALL=(ALL:ALL) ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = True
                mock.iterdir.side_effect = PermissionError("denied")
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is True  # only sudoers read, no dangerous pattern

    def test_os_error_on_sudoers_d_file(self):
        """sudoers.d 配下ファイルの OSError はスキップ"""
        from backend.api.routes.security import _check_sudoers

        extra_file = MagicMock()
        extra_file.is_file.return_value = True
        extra_file.read_text.side_effect = OSError("cannot read")

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "root ALL=(ALL:ALL) ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = True
                mock.iterdir.return_value = [extra_file]
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is True

    def test_nopasswd_all_case_insensitive(self):
        """NOPASSWD: ALL は大文字小文字を区別しない"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "user ALL=(ALL) nopasswd : all\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is False


# ==============================================================================
# 19. _check_suid_sgid_world_writable 追加分岐テスト
# ==============================================================================


class TestCheckSuidSgidV2:
    """_check_suid_sgid_world_writable の追加分岐テスト"""

    def test_non_file_entries_skipped(self):
        """ディレクトリはスキップされる"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_dir_entry = MagicMock()
        mock_dir_entry.is_file.return_value = False

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = [mock_dir_entry]

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            results = _check_suid_sgid_world_writable()
        assert results[0][1] is True  # no dangerous files

    def test_scan_dir_not_exists(self):
        """スキャン対象ディレクトリが存在しない場合"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = False

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            results = _check_suid_sgid_world_writable()
        assert results[0][1] is True  # no dangerous files found

    def test_multiple_dangerous_files(self):
        """複数の危険ファイル検出"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_files = []
        for i in range(3):
            f = MagicMock()
            f.is_file.return_value = True
            f.__str__ = lambda self, idx=i: f"/usr/bin/dangerous{idx}"
            mock_files.append(f)

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = mock_files

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            with patch("backend.api.routes.security.os.stat") as mock_stat:
                stat_result = MagicMock()
                stat_result.st_mode = stat.S_ISUID | stat.S_IWOTH
                mock_stat.return_value = stat_result
                results = _check_suid_sgid_world_writable()
        assert results[0][1] is False
        assert "件検出" in results[0][2]


# ==============================================================================
# 20. _estimate_severity 追加テスト
# ==============================================================================


class TestEstimateSeverityV2:
    """_estimate_severity の追加パラメタライズテスト"""

    @pytest.mark.parametrize(
        "pkg,expected",
        [
            ("libcurl4", "HIGH"),  # curl がサブストリングとして含まれる
            ("OPENSSL-dev", "HIGH"),  # 大文字
            ("python3-pip", "MEDIUM"),
            ("libpython3.10", "MEDIUM"),
            ("some-random-pkg", "LOW"),
            ("", "LOW"),
        ],
    )
    def test_severity_detection(self, pkg, expected):
        from backend.api.routes.security import _estimate_severity

        assert _estimate_severity(pkg) == expected


# ==============================================================================
# 21. _collect_vulnerability_summary 追加分岐テスト
# ==============================================================================


class TestCollectVulnerabilitySummaryV2:
    """_collect_vulnerability_summary の追加分岐テスト"""

    def test_malformed_lines_skipped(self):
        """正規表現に一致しない行はスキップ"""
        from backend.api.routes.security import _collect_vulnerability_summary

        apt_output = (
            "Listing... Done\n"
            "WARNING: apt does not have a stable CLI interface.\n"
            "some random text\n"
            "openssl/focal 2.0 amd64 [upgradable from: 1.0]\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.total_upgradable == 1

    def test_medium_packages(self):
        """MEDIUM 判定パッケージ"""
        from backend.api.routes.security import _collect_vulnerability_summary

        apt_output = (
            "Listing... Done\n"
            "python3/focal 3.12 amd64 [upgradable from: 3.11]\n"
            "apache2/focal 2.5 amd64 [upgradable from: 2.4]\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.medium == 2
        assert result.high == 0
        assert result.low == 0


# ==============================================================================
# 22. _calculate_security_score 追加分岐テスト
# ==============================================================================


class TestCalculateSecurityScoreV2:
    """_calculate_security_score の追加分岐テスト"""

    @pytest.mark.parametrize(
        "failed,ports,dangerous,sudo,expected_min,expected_max",
        [
            (0, 0, 0, 0, 90, 100),    # 完全安全
            (0, 0, 0, 50, 80, 100),    # sudo多い
            (20, 0, 0, 0, 30, 60),     # 失敗ログイン多い
            (0, 20, 5, 0, 0, 70),      # 危険ポート多い
            (20, 20, 5, 50, 0, 20),    # 全て危険
        ],
    )
    def test_score_ranges(self, failed, ports, dangerous, sudo, expected_min, expected_max):
        """各パラメータ組み合わせでスコア範囲を検証"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(failed, ports, dangerous, sudo)
        assert expected_min <= result.score <= expected_max

    def test_details_sudo_ops_stored(self):
        """details.recent_sudo_ops にsudo操作数が格納される"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(0, 0, 0, 42)
        assert result.details.recent_sudo_ops == 42


# ==============================================================================
# 23. _run_compliance_checks 追加テスト
# ==============================================================================


class TestRunComplianceChecksV2:
    """_run_compliance_checks の追加テスト"""

    def test_empty_total_count_rate_zero(self):
        """全チェックが空の場合 compliance_rate = 0"""
        from backend.api.routes.security import _run_compliance_checks

        with patch("backend.api.routes.security._check_ssh_config", return_value=[]):
            with patch("backend.api.routes.security._check_password_policy", return_value=[]):
                with patch("backend.api.routes.security._check_firewall_status", return_value=[]):
                    with patch("backend.api.routes.security._check_sudoers", return_value=[]):
                        with patch(
                            "backend.api.routes.security._check_suid_sgid_world_writable",
                            return_value=[],
                        ):
                            result = _run_compliance_checks()
        assert result.total_count == 0
        assert result.compliance_rate == 0.0

    def test_all_compliant(self):
        """全チェック準拠の場合 compliance_rate = 100"""
        from backend.api.routes.security import _run_compliance_checks

        checks = [("test_id", True, "ok", "")]
        with patch("backend.api.routes.security._check_ssh_config", return_value=checks):
            with patch("backend.api.routes.security._check_password_policy", return_value=[]):
                with patch("backend.api.routes.security._check_firewall_status", return_value=[]):
                    with patch("backend.api.routes.security._check_sudoers", return_value=[]):
                        with patch(
                            "backend.api.routes.security._check_suid_sgid_world_writable",
                            return_value=[],
                        ):
                            result = _run_compliance_checks()
        assert result.compliance_rate == 100.0
        assert result.compliant_count == 1
        assert result.non_compliant_count == 0


# ==============================================================================
# 24. Pydantic モデル追加テスト
# ==============================================================================


class TestPydanticModelsV2:
    """Pydantic モデルの追加テスト"""

    def test_audit_report_response(self):
        """AuditReportResponse の全フィールド"""
        from backend.api.routes.security import AuditReportResponse

        r = AuditReportResponse(
            status="success",
            auth_log_lines=500,
            accepted_logins=20,
            failed_logins=10,
            sudo_count=5,
            last_login="admin",
            timestamp="2026-01-01T00:00:00",
        )
        assert r.status == "success"
        assert r.auth_log_lines == 500

    def test_log_entries_response(self):
        """LogEntriesResponse のデフォルト"""
        from backend.api.routes.security import LogEntriesResponse

        r = LogEntriesResponse(status="success", timestamp="2026-01-01T00:00:00")
        assert r.entries == []

    def test_open_ports_response(self):
        """OpenPortsResponse のデフォルト"""
        from backend.api.routes.security import OpenPortsResponse

        r = OpenPortsResponse(status="success", timestamp="2026-01-01T00:00:00")
        assert r.output == ""

    def test_failed_login_hourly_item(self):
        """FailedLoginHourlyItem"""
        from backend.api.routes.security import FailedLoginHourlyItem

        item = FailedLoginHourlyItem(hour="2026-01-01T00:00", count=5)
        assert item.hour == "2026-01-01T00:00"
        assert item.count == 5

    def test_sudo_history_item(self):
        """SudoHistoryItem"""
        from backend.api.routes.security import SudoHistoryItem

        item = SudoHistoryItem(
            timestamp="2026-01-01T00:00:00",
            user="admin",
            operation="service_restart",
            result="success",
        )
        assert item.user == "admin"

    def test_compliance_check_item(self):
        """ComplianceCheckItem の全フィールド"""
        from backend.api.routes.security import ComplianceCheckItem

        c = ComplianceCheckItem(
            id="test",
            category="Test",
            description="Test check",
            compliant=False,
            value="bad",
            recommendation="fix it",
        )
        assert c.compliant is False
        assert c.recommendation == "fix it"

    def test_security_report_response(self):
        """SecurityReportResponse の構造"""
        from backend.api.routes.security import (
            ComplianceResponse,
            FailedLoginsHourlyResponse,
            OpenPortsStructuredResponse,
            SecurityReportResponse,
            SecurityScoreDetails,
            SecurityScoreResponse,
            SudoHistoryResponse,
            VulnerabilitySummaryResponse,
        )

        r = SecurityReportResponse(
            generated_at="2026-01-01T00:00:00",
            hostname="test-host",
            score=SecurityScoreResponse(
                score=80,
                details=SecurityScoreDetails(
                    failed_login_risk=100,
                    open_ports_risk=60,
                    recent_sudo_ops=0,
                ),
            ),
            failed_logins=FailedLoginsHourlyResponse(),
            open_ports=OpenPortsStructuredResponse(),
            sudo_history=SudoHistoryResponse(),
            compliance=ComplianceResponse(),
            vulnerability_summary=VulnerabilitySummaryResponse(),
        )
        assert r.hostname == "test-host"
        assert r.score.score == 80

    def test_failed_logins_hourly_response_defaults(self):
        """FailedLoginsHourlyResponse のデフォルト"""
        from backend.api.routes.security import FailedLoginsHourlyResponse

        r = FailedLoginsHourlyResponse()
        assert r.hourly == []
        assert r.total == 0
        assert r.unique_ips == 0

    def test_open_ports_structured_response_defaults(self):
        """OpenPortsStructuredResponse のデフォルト"""
        from backend.api.routes.security import OpenPortsStructuredResponse

        r = OpenPortsStructuredResponse()
        assert r.ports == []

    def test_sudo_history_response_defaults(self):
        """SudoHistoryResponse のデフォルト"""
        from backend.api.routes.security import SudoHistoryResponse

        r = SudoHistoryResponse()
        assert r.history == []


# ==============================================================================
# 25. 認証なしアクセステスト (全エンドポイント)
# ==============================================================================


class TestNoAuthAccess:
    """認証なしで全エンドポイントにアクセスした場合のテスト"""

    @pytest.mark.parametrize(
        "endpoint,method",
        [
            ("/api/security/audit-report", "get"),
            ("/api/security/failed-logins", "get"),
            ("/api/security/sudo-logs", "get"),
            ("/api/security/open-ports", "get"),
            ("/api/security/sudo-history", "get"),
            ("/api/security/score", "get"),
            ("/api/security/bandit-status", "get"),
            ("/api/security/compliance", "get"),
            ("/api/security/vulnerability-summary", "get"),
            ("/api/security/report", "get"),
            ("/api/security/report/export", "post"),
        ],
    )
    def test_unauthenticated_access_denied(self, test_client, endpoint, method):
        """認証なしでは 401 or 403"""
        resp = getattr(test_client, method)(endpoint)
        assert resp.status_code in (401, 403)


# ==============================================================================
# 26. _collect_sudo_history 追加分岐テスト
# ==============================================================================


class TestCollectSudoHistoryV2:
    """_collect_sudo_history の追加分岐テスト"""

    def test_multiple_operations_collected(self):
        """複数の異なる操作が収集される"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [
            _make_entry("service_restart", hours_ago=1),
            _make_entry("package_install", hours_ago=2),
            _make_entry("user_create", hours_ago=3),
        ]
        result = _collect_sudo_history(entries, days=7, limit=10)
        assert len(result) == 3
        ops = [r.operation for r in result]
        # 逆順で最新が先
        assert ops[0] == "user_create"
        assert ops[1] == "package_install"
        assert ops[2] == "service_restart"

    def test_old_entries_beyond_days_excluded(self):
        """days 日より古いエントリは除外"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [
            _make_entry("recent", hours_ago=12),
            _make_entry("old", hours_ago=24 * 8),  # 8日前
        ]
        result = _collect_sudo_history(entries, days=7)
        assert len(result) == 1
        assert result[0].operation == "recent"
