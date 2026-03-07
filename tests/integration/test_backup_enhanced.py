"""バックアップ管理API拡張の統合テスト (20件以上)"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")
import os
os.environ["ENV"] = "dev"

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture(scope="module")
def test_client():
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def temp_schedules_file(tmp_path, monkeypatch):
    """テスト用スケジュールファイルを一時ディレクトリに作成"""
    schedules_file = tmp_path / "backup_schedules.json"
    schedules_file.write_text(json.dumps({"schedules": []}))
    monkeypatch.setattr(
        "backend.api.routes.backup.SCHEDULES_FILE",
        schedules_file,
    )
    return schedules_file


@pytest.fixture
def temp_history_file(tmp_path, monkeypatch):
    """テスト用履歴ファイルを一時ディレクトリに作成"""
    history_file = tmp_path / "backup_history.json"
    sample_history = {
        "history": [
            {"timestamp": "2025-01-01T02:00:00Z", "target": "/home", "size": "1.2G", "status": "success"},
            {"timestamp": "2025-01-02T02:00:00Z", "target": "/etc", "size": "50M", "status": "failed"},
        ]
    }
    history_file.write_text(json.dumps(sample_history))
    monkeypatch.setattr(
        "backend.api.routes.backup.HISTORY_FILE",
        history_file,
    )
    return history_file


def make_mock_result(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ───────────────────────────────────────────────────────────────────
# 1) GET /api/backup/schedules - 一覧取得
# ───────────────────────────────────────────────────────────────────

def test_get_schedules_200(test_client, admin_headers, temp_schedules_file):
    """スケジュール一覧が200で返る"""
    resp = test_client.get("/api/backup/schedules", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "schedules" in data
    assert "count" in data
    assert "presets" in data
    assert isinstance(data["schedules"], list)


def test_get_schedules_403_no_auth(test_client):
    """認証なしは403"""
    resp = test_client.get("/api/backup/schedules")
    assert resp.status_code == 403


# ───────────────────────────────────────────────────────────────────
# 2) POST /api/backup/schedules - スケジュール追加
# ───────────────────────────────────────────────────────────────────

def test_create_schedule_201(test_client, admin_headers, temp_schedules_file):
    """スケジュール追加が201で返る"""
    payload = {"name": "テストスケジュール", "cron": "0 2 * * *", "target": "/home", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert "schedule" in data
    assert data["schedule"]["name"] == "テストスケジュール"
    assert data["schedule"]["cron"] == "0 2 * * *"
    assert "id" in data["schedule"]


def test_create_schedule_preset(test_client, admin_headers, temp_schedules_file):
    """プリセット名(daily)でスケジュール追加できる"""
    payload = {"name": "毎日バックアップ", "cron": "daily", "target": "/etc", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["schedule"]["cron"] == "0 2 * * *"


def test_create_schedule_weekly_preset(test_client, admin_headers, temp_schedules_file):
    """weekly プリセットが正しいcron式になる"""
    payload = {"name": "週次バックアップ", "cron": "weekly", "target": "/var/www", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["schedule"]["cron"] == "0 2 * * 0"


def test_create_schedule_invalid_target(test_client, admin_headers, temp_schedules_file):
    """allowlist外のtargetは400エラー"""
    payload = {"name": "不正スケジュール", "cron": "0 2 * * *", "target": "/root", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code in (400, 503)


def test_create_schedule_invalid_cron(test_client, admin_headers, temp_schedules_file):
    """不正なcron式は400エラー"""
    payload = {"name": "不正cron", "cron": "invalid-cron", "target": "/home", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code in (400, 503)


def test_create_schedule_403_no_auth(test_client):
    """認証なしは403"""
    payload = {"name": "Test", "cron": "0 2 * * *", "target": "/home", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload)
    assert resp.status_code == 403


def test_create_schedule_forbidden_char(test_client, admin_headers, temp_schedules_file):
    """禁止文字を含む名前は400または503"""
    payload = {"name": "test;rm -rf /", "cron": "0 2 * * *", "target": "/home", "enabled": True}
    resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert resp.status_code in (400, 503)


# ───────────────────────────────────────────────────────────────────
# 3) DELETE /api/backup/schedules/{id} - スケジュール削除
# ───────────────────────────────────────────────────────────────────

def test_delete_schedule_200(test_client, admin_headers, temp_schedules_file):
    """スケジュールを追加して削除できる"""
    # 追加
    payload = {"name": "削除テスト", "cron": "0 3 * * *", "target": "/opt", "enabled": True}
    create_resp = test_client.post("/api/backup/schedules", json=payload, headers=admin_headers)
    assert create_resp.status_code == 201
    sid = create_resp.json()["schedule"]["id"]

    # 削除
    del_resp = test_client.delete(f"/api/backup/schedules/{sid}", headers=admin_headers)
    assert del_resp.status_code == 200
    data = del_resp.json()
    assert data["status"] == "deleted"
    assert data["schedule_id"] == sid


def test_delete_schedule_404(test_client, admin_headers, temp_schedules_file):
    """存在しないIDは404"""
    resp = test_client.delete("/api/backup/schedules/nonexistent-id-12345", headers=admin_headers)
    assert resp.status_code == 404


def test_delete_schedule_403_no_auth(test_client):
    """認証なしは403"""
    resp = test_client.delete("/api/backup/schedules/some-id")
    assert resp.status_code == 403


# ───────────────────────────────────────────────────────────────────
# 4) GET /api/backup/history - 履歴取得
# ───────────────────────────────────────────────────────────────────

def test_get_history_200(test_client, admin_headers, temp_history_file):
    """履歴一覧が200で返る"""
    resp = test_client.get("/api/backup/history", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "history" in data
    assert "count" in data
    assert "total" in data
    assert isinstance(data["history"], list)
    assert data["count"] == 2


def test_get_history_403_no_auth(test_client):
    """認証なしは403"""
    resp = test_client.get("/api/backup/history")
    assert resp.status_code == 403


def test_get_history_structure(test_client, admin_headers, temp_history_file):
    """履歴の各エントリにstatus/target/timestampがある"""
    resp = test_client.get("/api/backup/history", headers=admin_headers)
    assert resp.status_code == 200
    history = resp.json()["history"]
    if history:
        h = history[0]
        assert "timestamp" in h
        assert "target" in h
        assert "status" in h


# ───────────────────────────────────────────────────────────────────
# 5) GET /api/backup/storage - ストレージ一覧
# ───────────────────────────────────────────────────────────────────

@patch("subprocess.run")
def test_get_storage_200(mock_run, test_client, admin_headers):
    """ストレージ一覧が200で返る"""
    mock_run.return_value = make_mock_result(
        '{"name":"backup.tar.gz","path":"/var/backups/backup.tar.gz","size":1024,"mtime":"2025-01-01T00:00:00"}\n'
    )
    resp = test_client.get("/api/backup/storage", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert "count" in data
    assert "total_usage" in data


def test_get_storage_403_no_auth(test_client):
    """認証なしは403"""
    resp = test_client.get("/api/backup/storage")
    assert resp.status_code == 403


@patch("subprocess.run")
def test_get_storage_empty(mock_run, test_client, admin_headers):
    """バックアップなし時は空リスト"""
    mock_run.return_value = make_mock_result("No backup files found")
    resp = test_client.get("/api/backup/storage", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["files"] == []


# ───────────────────────────────────────────────────────────────────
# 6) GET /api/backup/status - 現在のバックアップ状態
# ───────────────────────────────────────────────────────────────────

@patch("subprocess.run")
def test_get_status_200(mock_run, test_client, admin_headers):
    """バックアップステータスが200で返る"""
    mock_run.return_value = make_mock_result("No backup timers found")
    resp = test_client.get("/api/backup/status", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "status_lines" in data
    assert "timestamp" in data


def test_get_status_403_no_auth(test_client):
    """認証なしは403"""
    resp = test_client.get("/api/backup/status")
    assert resp.status_code == 403


# ───────────────────────────────────────────────────────────────────
# 7) POST /api/backup/restore - リストア申請（承認フロー・202）
# ───────────────────────────────────────────────────────────────────

def test_restore_request_202(test_client, admin_headers):
    """リストア申請が202で返り、approval_requiredがTrue"""
    payload = {
        "backup_file": "/var/backups/test.tar.gz",
        "restore_target": "/var/tmp/adminui-restore",
        "reason": "障害復旧のためリストアが必要です",
    }
    resp = test_client.post("/api/backup/restore", json=payload, headers=admin_headers)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["approval_required"] is True
    assert "request_id" in data


def test_restore_request_403_no_auth(test_client):
    """認証なしは403"""
    payload = {
        "backup_file": "/var/backups/test.tar.gz",
        "restore_target": "/var/tmp/adminui-restore",
        "reason": "テスト理由",
    }
    resp = test_client.post("/api/backup/restore", json=payload)
    assert resp.status_code == 403


def test_restore_request_short_reason(test_client, admin_headers):
    """理由が短すぎる場合はバリデーションエラー"""
    payload = {
        "backup_file": "/var/backups/test.tar.gz",
        "restore_target": "/var/tmp/adminui-restore",
        "reason": "ok",
    }
    resp = test_client.post("/api/backup/restore", json=payload, headers=admin_headers)
    # Pydantic validation → 422
    assert resp.status_code == 422


def test_restore_request_forbidden_char_in_file(test_client, admin_headers):
    """バックアップファイルパスに禁止文字があれば400または503"""
    payload = {
        "backup_file": "/var/backups/test;rm.tar.gz",
        "restore_target": "/var/tmp/adminui-restore",
        "reason": "テスト目的のリストア申請です",
    }
    resp = test_client.post("/api/backup/restore", json=payload, headers=admin_headers)
    assert resp.status_code in (400, 503)
