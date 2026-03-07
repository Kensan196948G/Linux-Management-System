"""バックアップ管理APIの統合テスト"""
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


def make_mock_result(stdout="output line", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ─── /api/backup/list ────────────────────────────────────────────────────────

@patch("subprocess.run")
def test_backup_list_200(mock_run):
    mock_run.return_value = make_mock_result(
        "total 8\n-rw-r--r-- 1 root root 1234 Jan 01 00:00 backup.tar.gz"
    )
    headers = get_auth_headers()
    resp = client.get("/api/backup/list", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "backups" in data
    assert "count" in data
    assert "timestamp" in data
    assert data["count"] == 2


def test_backup_list_403_no_auth():
    resp = client.get("/api/backup/list")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_backup_list_empty(mock_run):
    mock_run.return_value = make_mock_result("No backups found")
    headers = get_auth_headers()
    resp = client.get("/api/backup/list", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "backups" in data
    assert data["count"] == 1


# ─── /api/backup/status ──────────────────────────────────────────────────────

@patch("subprocess.run")
def test_backup_status_200(mock_run):
    mock_run.return_value = make_mock_result(
        "NEXT                        LEFT       LAST                        PASSED       UNIT                         ACTIVATES\n"
        "Mon 2024-01-01 03:00:00 UTC 2h 30min  Sun 2023-12-31 03:00:00 UTC 21h 30min   backup.timer                 backup.service\n"
    )
    headers = get_auth_headers()
    resp = client.get("/api/backup/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "returncode" in data
    assert data["returncode"] == 0


def test_backup_status_403_no_auth():
    resp = client.get("/api/backup/status")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_backup_status_no_timers(mock_run):
    mock_run.return_value = make_mock_result("No backup timers found")
    headers = get_auth_headers()
    resp = client.get("/api/backup/status", headers=headers)
    assert resp.status_code == 200
    assert "No backup timers found" in resp.json()["status"]


# ─── /api/backup/disk-usage ──────────────────────────────────────────────────

@patch("subprocess.run")
def test_backup_disk_usage_200(mock_run):
    mock_run.return_value = make_mock_result("512M\t/var/backups")
    headers = get_auth_headers()
    resp = client.get("/api/backup/disk-usage", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "usage" in data
    assert "timestamp" in data
    assert data["usage"] == "512M\t/var/backups"


def test_backup_disk_usage_403_no_auth():
    resp = client.get("/api/backup/disk-usage")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_backup_disk_usage_not_found(mock_run):
    mock_run.return_value = make_mock_result("0\t/var/backups (not found)")
    headers = get_auth_headers()
    resp = client.get("/api/backup/disk-usage", headers=headers)
    assert resp.status_code == 200
    assert "/var/backups" in resp.json()["usage"]


# ─── /api/backup/recent-logs ─────────────────────────────────────────────────

@patch("subprocess.run")
def test_backup_recent_logs_200(mock_run):
    mock_run.return_value = make_mock_result(
        "Jan 01 00:00:01 host rsync[1234]: log line 1\n"
        "Jan 01 00:00:02 host rsync[1234]: log line 2\n"
    )
    headers = get_auth_headers()
    resp = client.get("/api/backup/recent-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "count" in data
    assert data["count"] == 2


def test_backup_recent_logs_403_no_auth():
    resp = client.get("/api/backup/recent-logs")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_backup_recent_logs_empty(mock_run):
    mock_run.return_value = make_mock_result("No backup logs found")
    headers = get_auth_headers()
    resp = client.get("/api/backup/recent-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data


# ─── 503 レスポンス（コマンド失敗） ─────────────────────────────────────────

@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_list")
def test_backup_list_503(mock_method):
    mock_method.side_effect = Exception("Command failed")
    headers = get_auth_headers()
    resp = client.get("/api/backup/list", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_status")
def test_backup_status_503(mock_method):
    mock_method.side_effect = Exception("Command failed")
    headers = get_auth_headers()
    resp = client.get("/api/backup/status", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_disk_usage")
def test_backup_disk_usage_503(mock_method):
    mock_method.side_effect = Exception("Command failed")
    headers = get_auth_headers()
    resp = client.get("/api/backup/disk-usage", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_recent_logs")
def test_backup_recent_logs_503(mock_method):
    mock_method.side_effect = Exception("Command failed")
    headers = get_auth_headers()
    resp = client.get("/api/backup/recent-logs", headers=headers)
    assert resp.status_code == 503


# ─── レスポンス構造確認 ──────────────────────────────────────────────────────

@patch("subprocess.run")
def test_backup_list_response_structure(mock_run):
    mock_run.return_value = make_mock_result("file1.tar.gz\nfile2.tar.gz\nfile3.tar.gz")
    headers = get_auth_headers()
    resp = client.get("/api/backup/list", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["backups"], list)
    assert isinstance(data["count"], int)
    assert isinstance(data["timestamp"], str)
    assert data["count"] == len(data["backups"])


@patch("subprocess.run")
def test_backup_recent_logs_response_structure(mock_run):
    mock_run.return_value = make_mock_result("log1\nlog2")
    headers = get_auth_headers()
    resp = client.get("/api/backup/recent-logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["logs"], list)
    assert isinstance(data["count"], int)
    assert data["count"] == len(data["logs"])


# ===== HTTPException再送出テスト（lines 23, 37, 51, 66）=====
@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_list",
       side_effect=__import__("fastapi").HTTPException(status_code=404, detail="not found"))
def test_list_reraises_http_exception(mock_method):
    """get_backup_list が HTTPException を投げた場合に再送出する（line 23）"""
    headers = get_auth_headers()
    resp = client.get("/api/backup/list", headers=headers)
    assert resp.status_code == 404


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_status",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="service unavailable"))
def test_status_reraises_http_exception(mock_method):
    """get_backup_status が HTTPException を投げた場合に再送出する（line 37）"""
    headers = get_auth_headers()
    resp = client.get("/api/backup/status", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_disk_usage",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="disk error"))
def test_disk_usage_reraises_http_exception(mock_method):
    """get_backup_disk_usage が HTTPException を投げた場合に再送出する（line 51）"""
    headers = get_auth_headers()
    resp = client.get("/api/backup/disk-usage", headers=headers)
    assert resp.status_code == 503


@patch("backend.core.sudo_wrapper.sudo_wrapper.get_backup_recent_logs",
       side_effect=__import__("fastapi").HTTPException(status_code=503, detail="logs error"))
def test_recent_logs_reraises_http_exception(mock_method):
    """get_backup_recent_logs が HTTPException を投げた場合に再送出する（line 66）"""
    headers = get_auth_headers()
    resp = client.get("/api/backup/recent-logs", headers=headers)
    assert resp.status_code == 503


# ─── スケジュール toggle / run-now テスト ─────────────────────────────────────

class TestScheduleToggle:
    """PATCH /api/backup/schedules/{id}/toggle のテスト"""

    def test_toggle_not_found(self):
        """存在しないスケジュールは404"""
        headers = get_auth_headers()
        resp = client.patch("/api/backup/schedules/nonexistent-id/toggle", headers=headers)
        assert resp.status_code == 404

    def test_toggle_unauthenticated_rejected(self):
        """未認証は拒否"""
        resp = client.patch("/api/backup/schedules/test-id/toggle")
        assert resp.status_code in (401, 403)

    def test_toggle_create_and_toggle(self, tmp_path, monkeypatch):
        """スケジュール作成後にトグル可能"""
        import backend.api.routes.backup as backup_mod
        schedule_file = tmp_path / "schedules.json"
        monkeypatch.setattr(backup_mod, "SCHEDULES_FILE", schedule_file)

        headers = get_auth_headers()

        # スケジュール作成
        create_resp = client.post(
            "/api/backup/schedules",
            json={"name": "test-sched", "cron": "0 2 * * *", "target": "/home", "enabled": True},
            headers=headers,
        )
        assert create_resp.status_code == 201
        sched_id = create_resp.json()["schedule"]["id"]

        # トグル (有効→無効)
        toggle_resp = client.patch(f"/api/backup/schedules/{sched_id}/toggle", headers=headers)
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["enabled"] is False

        # 再度トグル (無効→有効)
        toggle_resp2 = client.patch(f"/api/backup/schedules/{sched_id}/toggle", headers=headers)
        assert toggle_resp2.status_code == 200
        assert toggle_resp2.json()["enabled"] is True


class TestScheduleRunNow:
    """POST /api/backup/schedules/{id}/run-now のテスト"""

    def test_run_now_not_found(self):
        """存在しないスケジュールは404"""
        headers = get_auth_headers()
        resp = client.post("/api/backup/schedules/nonexistent-id/run-now", headers=headers)
        assert resp.status_code == 404

    def test_run_now_unauthenticated_rejected(self):
        """未認証は拒否"""
        resp = client.post("/api/backup/schedules/test-id/run-now")
        assert resp.status_code in (401, 403)

    def test_run_now_creates_approval(self, tmp_path, monkeypatch):
        """run-now は承認フロー経由で202を返す"""
        from unittest.mock import AsyncMock
        import backend.api.routes.backup as backup_mod
        schedule_file = tmp_path / "schedules2.json"
        monkeypatch.setattr(backup_mod, "SCHEDULES_FILE", schedule_file)

        headers = get_auth_headers()

        # スケジュール作成
        create_resp = client.post(
            "/api/backup/schedules",
            json={"name": "run-test", "cron": "0 3 * * *", "target": "/home", "enabled": True},
            headers=headers,
        )
        assert create_resp.status_code == 201
        sched_id = create_resp.json()["schedule"]["id"]

        # 承認フローをモック
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(return_value={"request_id": "test-req-001", "status": "pending"}),
        ):
            resp = client.post(f"/api/backup/schedules/{sched_id}/run-now", headers=headers)

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "request_id" in data
