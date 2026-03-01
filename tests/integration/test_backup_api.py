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
