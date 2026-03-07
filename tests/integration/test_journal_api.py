"""システムジャーナルAPIの統合テスト"""
import sys

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")

import os
os.environ["ENV"] = "dev"

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


def get_auth_headers():
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    if resp.status_code == 200:
        return {"Authorization": f"Bearer {resp.json().get('access_token', '')}"}
    return {}


def make_mock_result(stdout="log line 1\nlog line 2", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ─── /api/journal/list ───────────────────────────────────────────────────────


@patch("subprocess.run")
def test_journal_list_200(mock_run):
    mock_run.return_value = make_mock_result("2024-01-01T00:00:00+0000 host sshd: line1\n2024-01-01T00:00:01+0000 host sshd: line2")
    headers = get_auth_headers()
    resp = client.get("/api/journal/list", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "count" in data
    assert data["count"] == 2


def test_journal_list_403_no_auth():
    resp = client.get("/api/journal/list")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_journal_list_lines_200(mock_run):
    mock_run.return_value = make_mock_result("line1\nline2\nline3")
    headers = get_auth_headers()
    resp = client.get("/api/journal/list?lines=200", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


def test_journal_list_lines_0_422():
    headers = get_auth_headers()
    resp = client.get("/api/journal/list?lines=0", headers=headers)
    assert resp.status_code == 422


def test_journal_list_lines_9999_422():
    headers = get_auth_headers()
    resp = client.get("/api/journal/list?lines=9999", headers=headers)
    assert resp.status_code == 422


@patch("subprocess.run")
def test_journal_list_503_on_exception(mock_run):
    mock_run.side_effect = Exception("command failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/list", headers=headers)
    assert resp.status_code == 503


# ─── /api/journal/units ──────────────────────────────────────────────────────


@patch("subprocess.run")
def test_journal_units_200(mock_run):
    mock_run.return_value = make_mock_result("nginx.service loaded active running\nsshd.service loaded active running")
    headers = get_auth_headers()
    resp = client.get("/api/journal/units", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "units" in data
    assert data["count"] == 2


def test_journal_units_403_no_auth():
    resp = client.get("/api/journal/units")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_journal_units_503_on_exception(mock_run):
    mock_run.side_effect = Exception("systemctl unavailable")
    headers = get_auth_headers()
    resp = client.get("/api/journal/units", headers=headers)
    assert resp.status_code == 503


# ─── /api/journal/unit-logs/{unit_name} ──────────────────────────────────────


@patch("subprocess.run")
def test_journal_unit_logs_nginx_200(mock_run):
    mock_run.return_value = make_mock_result("2024-01-01T00:00:00+0000 host nginx: started")
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["unit"] == "nginx"
    assert "logs" in data


def test_journal_unit_logs_403_no_auth():
    resp = client.get("/api/journal/unit-logs/nginx")
    assert resp.status_code == 403


def test_journal_unit_logs_evil_cmd_400():
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/evil;cmd", headers=headers)
    assert resp.status_code == 400


def test_journal_unit_logs_invalid_chars_400():
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx%7Crm", headers=headers)
    assert resp.status_code == 400


# ─── /api/journal/boot-logs ──────────────────────────────────────────────────


@patch("subprocess.run")
def test_journal_boot_logs_200(mock_run):
    mock_run.return_value = make_mock_result("boot log line 1\nboot log line 2")
    headers = get_auth_headers()
    resp = client.get("/api/journal/boot-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert data["count"] == 2


def test_journal_boot_logs_403_no_auth():
    resp = client.get("/api/journal/boot-logs")
    assert resp.status_code == 403


# ─── /api/journal/kernel-logs ────────────────────────────────────────────────


@patch("subprocess.run")
def test_journal_kernel_logs_200(mock_run):
    mock_run.return_value = make_mock_result("kernel: usb device added\nkernel: net eth0 up")
    headers = get_auth_headers()
    resp = client.get("/api/journal/kernel-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data


def test_journal_kernel_logs_403_no_auth():
    resp = client.get("/api/journal/kernel-logs")
    assert resp.status_code == 403


# ─── /api/journal/priority-logs ──────────────────────────────────────────────


@patch("subprocess.run")
def test_journal_priority_logs_200(mock_run):
    mock_run.return_value = make_mock_result("err log 1\nerr log 2")
    headers = get_auth_headers()
    resp = client.get("/api/journal/priority-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "priority" in data
    assert "logs" in data


def test_journal_priority_logs_403_no_auth():
    resp = client.get("/api/journal/priority-logs")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_journal_priority_logs_err_200(mock_run):
    mock_run.return_value = make_mock_result("error: something failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/priority-logs?priority=err", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["priority"] == "err"


def test_journal_priority_logs_invalid_400():
    headers = get_auth_headers()
    resp = client.get("/api/journal/priority-logs?priority=invalid", headers=headers)
    assert resp.status_code == 400


# ─── 例外パス カバレッジ ──────────────────────────────────────────────────


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
def test_journal_list_exception_503(mock_method):
    """get_journal_list で Exception → 503 (line 25)"""
    mock_method.side_effect = Exception("journalctl failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/list", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units")
def test_journal_units_exception_503(mock_method):
    """get_journal_units で Exception → 503 (line 40)"""
    mock_method.side_effect = Exception("unit list failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/units", headers=headers)
    assert resp.status_code == 503


def test_journal_unit_logs_invalid_name_400():
    """単位名が不正 → 400 (line 52)"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx;rm", headers=headers)
    assert resp.status_code == 400


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
def test_journal_unit_logs_value_error_400(mock_method):
    """get_journal_unit_logs で ValueError → 400 (lines 57-58)"""
    mock_method.side_effect = ValueError("unknown unit")
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx", headers=headers)
    assert resp.status_code == 400


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
def test_journal_unit_logs_exception_503(mock_method):
    """get_journal_unit_logs で Exception → 503 (lines 59-62)"""
    mock_method.side_effect = Exception("unit logs failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs")
def test_journal_boot_logs_exception_503(mock_method):
    """get_journal_boot_logs で Exception → 503 (lines 74-77)"""
    mock_method.side_effect = Exception("boot logs failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/boot-logs", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs")
def test_journal_kernel_logs_exception_503(mock_method):
    """get_journal_kernel_logs で Exception → 503 (lines 89-92)"""
    mock_method.side_effect = Exception("kernel logs failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/kernel-logs", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
def test_journal_priority_logs_exception_503(mock_method):
    """get_journal_priority_logs で Exception → 503 (lines 108-111)"""
    mock_method.side_effect = Exception("priority logs failed")
    headers = get_auth_headers()
    resp = client.get("/api/journal/priority-logs?priority=err", headers=headers)
    assert resp.status_code == 503


# ===== HTTPException再送出テスト（lines 25, 40, 60, 75, 90, 109）=====
@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_list_reraises_http_exception(mock_method):
    """get_journal_list が HTTPException を投げた場合に再送出する（line 25）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/list", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_units_reraises_http_exception(mock_method):
    """get_journal_units が HTTPException を投げた場合に再送出する（line 40）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/units", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_unit_logs_reraises_http_exception(mock_method):
    """get_journal_unit_logs が HTTPException を投げた場合に再送出する（line 60）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/unit-logs/nginx.service", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_boot_logs_reraises_http_exception(mock_method):
    """get_journal_boot_logs が HTTPException を投げた場合に再送出する（line 75）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/boot-logs", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_kernel_logs_reraises_http_exception(mock_method):
    """get_journal_kernel_logs が HTTPException を投げた場合に再送出する（line 90）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/kernel-logs", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="upstream"))
def test_journal_priority_logs_reraises_http_exception(mock_method):
    """get_journal_priority_logs が HTTPException を投げた場合に再送出する（line 109）"""
    headers = get_auth_headers()
    resp = client.get("/api/journal/priority-logs?priority=err", headers=headers)
    assert resp.status_code == 503


# ─── /api/journal/search (高度フィルタ) ──────────────────────────────────────

class TestJournalSearch:
    """GET /api/journal/search のテスト"""

    @patch("subprocess.run")
    def test_search_basic_200(self, mock_run):
        """基本検索が成功すること"""
        mock_run.return_value = make_mock_result("2026-01-01 00:00:00 nginx: started")
        headers = get_auth_headers()
        resp = client.get("/api/journal/search", headers=headers)
        assert resp.status_code == 200

    @patch("subprocess.run")
    def test_search_with_priority(self, mock_run):
        """優先度フィルタ付き検索"""
        mock_run.return_value = make_mock_result("error line 1")
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?priority=err", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"]["priority"] == "err"

    def test_search_invalid_priority_rejected(self):
        """不正な優先度は400"""
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?priority=invalid_pri", headers=headers)
        assert resp.status_code == 400

    @patch("subprocess.run")
    def test_search_with_unit(self, mock_run):
        """ユニットフィルタ付き検索"""
        mock_run.return_value = make_mock_result("nginx log line")
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?units=nginx.service", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "nginx.service" in data["query"]["units"]

    def test_search_invalid_unit_name_rejected(self):
        """不正なユニット名（特殊文字）は400"""
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?units=nginx;rm+-rf+/", headers=headers)
        assert resp.status_code in (400, 422)

    @patch("subprocess.run")
    def test_search_with_grep(self, mock_run):
        """キーワードフィルタ付き検索"""
        mock_run.return_value = make_mock_result("nginx started")
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?grep=nginx", headers=headers)
        assert resp.status_code == 200

    def test_search_grep_with_shell_chars_rejected(self):
        """grep に危険な文字があれば400"""
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?grep=nginx%7Ccat+/etc/passwd", headers=headers)
        assert resp.status_code in (400, 422)

    def test_search_unauthenticated_rejected(self):
        """未認証は拒否"""
        resp = client.get("/api/journal/search")
        assert resp.status_code in (401, 403)

    def test_search_lines_too_many_rejected(self):
        """lines > 2000 は拒否"""
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?lines=9999", headers=headers)
        assert resp.status_code == 422

    @patch("subprocess.run")
    def test_search_response_structure(self, mock_run):
        """レスポンス構造が正しい"""
        mock_run.return_value = make_mock_result("line1\nline2")
        headers = get_auth_headers()
        resp = client.get("/api/journal/search?lines=10", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "query" in data
        assert "count" in data
        assert "logs" in data
        assert isinstance(data["logs"], list)


class TestJournalStats:
    """GET /api/journal/stats のテスト"""

    @patch("subprocess.run")
    def test_stats_returns_200(self, mock_run):
        """統計取得が成功"""
        mock_run.return_value = make_mock_result("error line 1\nerror line 2")
        headers = get_auth_headers()
        resp = client.get("/api/journal/stats", headers=headers)
        assert resp.status_code == 200

    @patch("subprocess.run")
    def test_stats_response_structure(self, mock_run):
        """レスポンス構造確認"""
        mock_run.return_value = make_mock_result("line")
        headers = get_auth_headers()
        resp = client.get("/api/journal/stats", headers=headers)
        data = resp.json()
        assert "by_priority" in data
        assert "total_errors" in data
        assert "period_hours" in data

    def test_stats_hours_too_large_rejected(self):
        """720時間超は拒否"""
        headers = get_auth_headers()
        resp = client.get("/api/journal/stats?hours=721", headers=headers)
        assert resp.status_code == 422

    def test_stats_unauthenticated_rejected(self):
        """未認証は拒否"""
        resp = client.get("/api/journal/stats")
        assert resp.status_code in (401, 403)

    @patch("subprocess.run")
    def test_stats_default_24h(self, mock_run):
        """デフォルト24時間集計"""
        mock_run.return_value = make_mock_result("")
        headers = get_auth_headers()
        resp = client.get("/api/journal/stats", headers=headers)
        data = resp.json()
        assert data["period_hours"] == 24
