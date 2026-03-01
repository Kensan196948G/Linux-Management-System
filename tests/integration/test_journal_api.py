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
