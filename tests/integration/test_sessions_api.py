"""Integration tests for /api/sessions endpoints"""
import sys
sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def get_auth_headers():
    resp = client.post("/api/auth/token", json={"username": "admin", "password": "admin123"})
    if resp.status_code == 200:
        return {"Authorization": f"Bearer {resp.json().get('access_token', '')}"}
    return {}


def make_mock(stdout="user pts/0 2026-03-01 10:00", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ------------------------------------------------------------------ active
class TestActiveSessions:
    def test_active_200(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("user pts/0 2026-03-01")):
            resp = client.get("/api/sessions/active", headers=headers)
        assert resp.status_code == 200

    def test_active_403_no_auth(self):
        resp = client.get("/api/sessions/active")
        assert resp.status_code == 403

    def test_active_response_keys(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("user pts/0")):
            resp = client.get("/api/sessions/active", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert "count" in data
        assert "timestamp" in data

    def test_active_count_matches(self):
        headers = get_auth_headers()
        stdout = "user1 pts/0 2026-03-01\nuser2 pts/1 2026-03-01"
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock(stdout)):
            resp = client.get("/api/sessions/active", headers=headers)
        data = resp.json()
        assert data["count"] == len(data["sessions"])

    def test_active_empty_stdout(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("")):
            resp = client.get("/api/sessions/active", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_active_503_on_exception(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", side_effect=Exception("command failed")):
            resp = client.get("/api/sessions/active", headers=headers)
        assert resp.status_code == 503


# ------------------------------------------------------------------ history
class TestSessionHistory:
    def test_history_200(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("admin pts/0 host 2026-03-01T10:00 still logged in")):
            resp = client.get("/api/sessions/history", headers=headers)
        assert resp.status_code == 200

    def test_history_403_no_auth(self):
        resp = client.get("/api/sessions/history")
        assert resp.status_code == 403

    def test_history_response_keys(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("admin pts/0")):
            resp = client.get("/api/sessions/history", headers=headers)
        data = resp.json()
        assert "history" in data
        assert "count" in data
        assert "timestamp" in data

    def test_history_count_matches(self):
        headers = get_auth_headers()
        stdout = "admin pts/0 host\nroot pts/1 host"
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock(stdout)):
            resp = client.get("/api/sessions/history", headers=headers)
        data = resp.json()
        assert data["count"] == len(data["history"])

    def test_history_503_on_exception(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", side_effect=Exception("command failed")):
            resp = client.get("/api/sessions/history", headers=headers)
        assert resp.status_code == 503


# ------------------------------------------------------------------ failed
class TestFailedSessions:
    def test_failed_200(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("Login failure from 192.168.1.1")):
            resp = client.get("/api/sessions/failed", headers=headers)
        assert resp.status_code == 200

    def test_failed_403_no_auth(self):
        resp = client.get("/api/sessions/failed")
        assert resp.status_code == 403

    def test_failed_response_keys(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("Failed login")):
            resp = client.get("/api/sessions/failed", headers=headers)
        data = resp.json()
        assert "failed_logins" in data
        assert "count" in data

    def test_failed_count_matches(self):
        headers = get_auth_headers()
        stdout = "Failed from 1.1.1.1\nFailed from 2.2.2.2"
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock(stdout)):
            resp = client.get("/api/sessions/failed", headers=headers)
        data = resp.json()
        assert data["count"] == len(data["failed_logins"])

    def test_failed_503_on_exception(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", side_effect=Exception("command failed")):
            resp = client.get("/api/sessions/failed", headers=headers)
        assert resp.status_code == 503


# ------------------------------------------------------------------ wtmp-summary
class TestWtmpSummary:
    def test_wtmp_200(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("admin pts/0 2026-03-01T10:00")):
            resp = client.get("/api/sessions/wtmp-summary", headers=headers)
        assert resp.status_code == 200

    def test_wtmp_403_no_auth(self):
        resp = client.get("/api/sessions/wtmp-summary")
        assert resp.status_code == 403

    def test_wtmp_response_keys(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock("admin pts/0")):
            resp = client.get("/api/sessions/wtmp-summary", headers=headers)
        data = resp.json()
        assert "summary" in data
        assert "count" in data

    def test_wtmp_count_matches(self):
        headers = get_auth_headers()
        stdout = "line1\nline2\nline3"
        with patch("backend.core.sudo_wrapper.subprocess.run", return_value=make_mock(stdout)):
            resp = client.get("/api/sessions/wtmp-summary", headers=headers)
        data = resp.json()
        assert data["count"] == len(data["summary"])

    def test_wtmp_503_on_exception(self):
        headers = get_auth_headers()
        with patch("backend.core.sudo_wrapper.subprocess.run", side_effect=Exception("command failed")):
            resp = client.get("/api/sessions/wtmp-summary", headers=headers)
        assert resp.status_code == 503
