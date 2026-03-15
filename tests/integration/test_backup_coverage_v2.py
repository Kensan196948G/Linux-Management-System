"""バックアップ管理API カバレッジ向上テスト v2

backup.py の全分岐を網羅的にテスト:
- ヘルパー関数 (_load_schedules, _save_schedules, _load_history, _validate_cron, _validate_target)
- 全エンドポイントの正常系/異常系/エッジケース
- 承認フロー経由エンドポイント (restore, run-now)
- toggle_schedule エンドポイント
- Pydantic バリデーション
"""

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─── ヘルパー関数のテスト ──────────────────────────────────────────────────


class TestLoadSchedules:
    """_load_schedules のテスト"""

    def test_file_not_exists_creates_default(self, tmp_path):
        """ファイルが存在しない場合、デフォルトJSONを作成して返す"""
        from backend.api.routes import backup as mod

        orig = mod.SCHEDULES_FILE
        mod.SCHEDULES_FILE = tmp_path / "nonexistent" / "schedules.json"
        try:
            result = mod._load_schedules()
            assert result == {"schedules": []}
            assert mod.SCHEDULES_FILE.exists()
        finally:
            mod.SCHEDULES_FILE = orig

    def test_valid_json_loaded(self, tmp_path):
        """正常なJSONファイルを読み込む"""
        from backend.api.routes import backup as mod

        f = tmp_path / "schedules.json"
        data = {"schedules": [{"id": "abc", "name": "test"}]}
        f.write_text(json.dumps(data), encoding="utf-8")

        orig = mod.SCHEDULES_FILE
        mod.SCHEDULES_FILE = f
        try:
            result = mod._load_schedules()
            assert result == data
        finally:
            mod.SCHEDULES_FILE = orig

    def test_invalid_json_returns_default(self, tmp_path):
        """不正なJSONの場合デフォルトを返す"""
        from backend.api.routes import backup as mod

        f = tmp_path / "schedules.json"
        f.write_text("{invalid json!!", encoding="utf-8")

        orig = mod.SCHEDULES_FILE
        mod.SCHEDULES_FILE = f
        try:
            result = mod._load_schedules()
            assert result == {"schedules": []}
        finally:
            mod.SCHEDULES_FILE = orig


class TestSaveSchedules:
    """_save_schedules のテスト"""

    def test_save_creates_parent_dirs(self, tmp_path):
        """親ディレクトリを自動作成して保存する"""
        from backend.api.routes import backup as mod

        f = tmp_path / "sub" / "dir" / "schedules.json"
        orig = mod.SCHEDULES_FILE
        mod.SCHEDULES_FILE = f
        try:
            data = {"schedules": [{"id": "x"}]}
            mod._save_schedules(data)
            assert f.exists()
            loaded = json.loads(f.read_text(encoding="utf-8"))
            assert loaded == data
        finally:
            mod.SCHEDULES_FILE = orig


class TestLoadHistory:
    """_load_history のテスト"""

    def test_file_not_exists_creates_default(self, tmp_path):
        """ファイルが存在しない場合、デフォルトJSONを作成して返す"""
        from backend.api.routes import backup as mod

        orig = mod.HISTORY_FILE
        mod.HISTORY_FILE = tmp_path / "nonexistent" / "history.json"
        try:
            result = mod._load_history()
            assert result == {"history": []}
            assert mod.HISTORY_FILE.exists()
        finally:
            mod.HISTORY_FILE = orig

    def test_valid_json_loaded(self, tmp_path):
        """正常なJSONファイルを読み込む"""
        from backend.api.routes import backup as mod

        f = tmp_path / "history.json"
        data = {"history": [{"id": "h1", "status": "ok"}]}
        f.write_text(json.dumps(data), encoding="utf-8")

        orig = mod.HISTORY_FILE
        mod.HISTORY_FILE = f
        try:
            result = mod._load_history()
            assert result == data
        finally:
            mod.HISTORY_FILE = orig

    def test_invalid_json_returns_default(self, tmp_path):
        """不正なJSONの場合デフォルトを返す"""
        from backend.api.routes import backup as mod

        f = tmp_path / "history.json"
        f.write_text("not json", encoding="utf-8")

        orig = mod.HISTORY_FILE
        mod.HISTORY_FILE = f
        try:
            result = mod._load_history()
            assert result == {"history": []}
        finally:
            mod.HISTORY_FILE = orig


class TestValidateCronV2:
    """_validate_cron の追加テスト"""

    @pytest.mark.parametrize("preset,expected", [
        ("daily", "0 2 * * *"),
        ("weekly", "0 2 * * 0"),
        ("monthly", "0 2 1 * *"),
    ])
    def test_all_presets(self, preset, expected):
        from backend.api.routes.backup import _validate_cron
        assert _validate_cron(preset) == expected

    def test_valid_custom_cron(self):
        from backend.api.routes.backup import _validate_cron
        assert _validate_cron("15 4 * * 3") == "15 4 * * 3"

    @pytest.mark.parametrize("bad", [
        "0 2 * *",       # 4 fields
        "0 2 * * * *",   # 6 fields
        "invalid",       # single word not a preset
        "",              # empty
    ])
    def test_invalid_cron_raises(self, bad):
        from backend.api.routes.backup import _validate_cron
        with pytest.raises(HTTPException) as exc_info:
            _validate_cron(bad)
        assert exc_info.value.status_code == 400


class TestValidateTargetV2:
    """_validate_target のテスト"""

    @pytest.mark.parametrize("target", ["/home", "/etc", "/var/www", "/opt", "/var/backups"])
    def test_allowed_targets(self, target):
        from backend.api.routes.backup import _validate_target
        assert _validate_target(target) == target

    @pytest.mark.parametrize("target", ["/tmp", "/root", "/usr", "/", "/var/log"])
    def test_disallowed_targets_raise(self, target):
        from backend.api.routes.backup import _validate_target
        with pytest.raises(HTTPException) as exc_info:
            _validate_target(target)
        assert exc_info.value.status_code == 400


# ─── エンドポイントテスト ──────────────────────────────────────────────────


class TestGetBackupList:
    """GET /api/backup/list エンドポイント"""

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/backup/list")
        assert resp.status_code == 403

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_success_with_lines(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_list.return_value = {
            "stdout": "backup1.tar.gz\nbackup2.tar.gz\n",
            "returncode": 0,
        }
        resp = test_client.get("/api/backup/list", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["backups"]) == 2
        assert "timestamp" in data

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_success_empty(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_list.return_value = {"stdout": "", "returncode": 0}
        resp = test_client.get("/api/backup/list", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_exception_returns_503(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_list.side_effect = RuntimeError("disk error")
        resp = test_client.get("/api/backup/list", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_http_exception_reraised(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_list.side_effect = HTTPException(status_code=403, detail="forbidden")
        resp = test_client.get("/api/backup/list", headers=admin_headers)
        assert resp.status_code == 403


class TestGetBackupDiskUsage:
    """GET /api/backup/disk-usage エンドポイント"""

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_success(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_disk_usage.return_value = {"stdout": "1.5G\t/var/backups\n", "returncode": 0}
        resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" in data
        assert "timestamp" in data

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_exception_returns_503(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_disk_usage.side_effect = RuntimeError("fail")
        resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_http_exception_reraised(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_disk_usage.side_effect = HTTPException(status_code=500, detail="internal")
        resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
        assert resp.status_code == 500


class TestGetBackupRecentLogs:
    """GET /api/backup/recent-logs エンドポイント"""

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_success(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_recent_logs.return_value = {
            "stdout": "2026-03-01 backup started\n2026-03-01 backup completed\n",
            "returncode": 0,
        }
        resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_empty_logs(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_recent_logs.return_value = {"stdout": "", "returncode": 0}
        resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_exception_returns_503(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_recent_logs.side_effect = OSError("log read fail")
        resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_http_exception_reraised(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_recent_logs.side_effect = HTTPException(status_code=401, detail="unauth")
        resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
        assert resp.status_code == 401


class TestGetBackupStatus:
    """GET /api/backup/status エンドポイント"""

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_running_status(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_status.return_value = {
            "stdout": "backup.service - Running backup\nActive: active (running)\n",
            "returncode": 0,
        }
        resp = test_client.get("/api/backup/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert "status_lines" in data
        assert "timestamp" in data

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_not_running_status(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_status.return_value = {
            "stdout": "backup.service - Stopped\nStatus: dead\n",
            "returncode": 0,
        }
        resp = test_client.get("/api/backup/status", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["running"] is False

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_exception_returns_503(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_status.side_effect = RuntimeError("check fail")
        resp = test_client.get("/api/backup/status", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_http_exception_reraised(self, mock_sw, test_client, admin_headers):
        mock_sw.get_backup_status.side_effect = HTTPException(status_code=403, detail="nope")
        resp = test_client.get("/api/backup/status", headers=admin_headers)
        assert resp.status_code == 403


class TestGetBackupStorage:
    """GET /api/backup/storage エンドポイント"""

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_success_with_json_lines(self, mock_sw, test_client, admin_headers):
        json_line = json.dumps({"name": "backup1.tar.gz", "path": "/var/backups/backup1.tar.gz", "size": 1024, "mtime": "2026-03-01"})
        mock_sw.list_backup_files.return_value = {"stdout": json_line + "\n", "returncode": 0}
        mock_sw.get_backup_disk_usage.return_value = {"stdout": "2.0G", "returncode": 0}
        resp = test_client.get("/api/backup/storage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["files"][0]["name"] == "backup1.tar.gz"
        assert data["total_usage"] == "2.0G"

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_non_json_lines_fallback(self, mock_sw, test_client, admin_headers):
        """JSON解析できない行はフォールバック形式で返す"""
        mock_sw.list_backup_files.return_value = {"stdout": "some-plain-text\n", "returncode": 0}
        mock_sw.get_backup_disk_usage.return_value = {"stdout": "500M", "returncode": 0}
        resp = test_client.get("/api/backup/storage", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["files"][0]["name"] == "some-plain-text"
        assert data["files"][0]["size"] is None

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_skip_header_lines(self, mock_sw, test_client, admin_headers):
        """'Backup' や 'No backup' で始まる行はスキップ"""
        mock_sw.list_backup_files.return_value = {"stdout": "Backup files:\nNo backup found\n", "returncode": 0}
        mock_sw.get_backup_disk_usage.return_value = {"stdout": "0", "returncode": 0}
        resp = test_client.get("/api/backup/storage", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_exception_returns_503(self, mock_sw, test_client, admin_headers):
        mock_sw.list_backup_files.side_effect = RuntimeError("fail")
        resp = test_client.get("/api/backup/storage", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.api.routes.backup.sudo_wrapper")
    def test_http_exception_reraised(self, mock_sw, test_client, admin_headers):
        mock_sw.list_backup_files.side_effect = HTTPException(status_code=403, detail="no")
        resp = test_client.get("/api/backup/storage", headers=admin_headers)
        assert resp.status_code == 403


class TestGetBackupHistory:
    """GET /api/backup/history エンドポイント"""

    def test_success_with_history(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.HISTORY_FILE
        f = tmp_path / "history.json"
        entries = [{"id": f"h{i}", "status": "ok"} for i in range(60)]
        f.write_text(json.dumps({"history": entries}), encoding="utf-8")
        mod.HISTORY_FILE = f
        try:
            resp = test_client.get("/api/backup/history", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 50  # max 50
            assert data["total"] == 60
        finally:
            mod.HISTORY_FILE = orig

    def test_empty_history(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.HISTORY_FILE
        f = tmp_path / "history.json"
        f.write_text(json.dumps({"history": []}), encoding="utf-8")
        mod.HISTORY_FILE = f
        try:
            resp = test_client.get("/api/backup/history", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
        finally:
            mod.HISTORY_FILE = orig

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup._load_history", side_effect=RuntimeError("fail")):
            resp = test_client.get("/api/backup/history", headers=admin_headers)
            assert resp.status_code == 503


# ─── スケジュール管理テスト ────────────────────────────────────────────────


class TestListSchedules:
    """GET /api/backup/schedules エンドポイント"""

    def test_success(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": [{"id": "s1", "name": "daily"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.get("/api/backup/schedules", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1
            assert "presets" in data
        finally:
            mod.SCHEDULES_FILE = orig

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup._load_schedules", side_effect=RuntimeError("err")):
            resp = test_client.get("/api/backup/schedules", headers=admin_headers)
            assert resp.status_code == 503

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/backup/schedules")
        assert resp.status_code == 403


class TestCreateSchedule:
    """POST /api/backup/schedules エンドポイント"""

    def test_success_with_preset(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "nightly", "cron": "daily", "target": "/home", "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "created"
            assert data["schedule"]["cron"] == "0 2 * * *"
        finally:
            mod.SCHEDULES_FILE = orig

    def test_success_with_custom_cron(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "custom", "cron": "30 3 * * 5", "target": "/etc", "enabled": False},
                headers=admin_headers,
            )
            assert resp.status_code == 201
            assert resp.json()["schedule"]["enabled"] is False
        finally:
            mod.SCHEDULES_FILE = orig

    def test_invalid_target_returns_400(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "bad", "cron": "daily", "target": "/tmp"},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            mod.SCHEDULES_FILE = orig

    def test_invalid_cron_returns_400(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "bad", "cron": "not-valid", "target": "/home"},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            mod.SCHEDULES_FILE = orig

    def test_forbidden_chars_in_name_returns_400(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "bad;rm -rf /", "cron": "daily", "target": "/home"},
                headers=admin_headers,
            )
            assert resp.status_code == 400
        finally:
            mod.SCHEDULES_FILE = orig

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup._load_schedules", side_effect=RuntimeError("db fail")):
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "test", "cron": "daily", "target": "/home"},
                headers=admin_headers,
            )
            assert resp.status_code == 503

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.post(
            "/api/backup/schedules",
            json={"name": "test", "cron": "daily", "target": "/home"},
        )
        assert resp.status_code == 403


class TestDeleteSchedule:
    """DELETE /api/backup/schedules/{id} エンドポイント"""

    def test_success(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "todel", "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.delete(f"/api/backup/schedules/{sid}", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "deleted"
        finally:
            mod.SCHEDULES_FILE = orig

    def test_not_found_returns_404(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.delete(f"/api/backup/schedules/{uuid.uuid4()}", headers=admin_headers)
            assert resp.status_code == 404
        finally:
            mod.SCHEDULES_FILE = orig

    def test_forbidden_chars_returns_400(self, test_client, admin_headers):
        resp = test_client.delete("/api/backup/schedules/bad;cmd", headers=admin_headers)
        assert resp.status_code == 400

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup._load_schedules", side_effect=RuntimeError("fail")):
            resp = test_client.delete(f"/api/backup/schedules/{uuid.uuid4()}", headers=admin_headers)
            assert resp.status_code == 503


class TestToggleSchedule:
    """PATCH /api/backup/schedules/{id}/toggle エンドポイント"""

    def test_toggle_enabled_to_disabled(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "t", "enabled": True, "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.patch(f"/api/backup/schedules/{sid}/toggle", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
            assert data["status"] == "updated"
        finally:
            mod.SCHEDULES_FILE = orig

    def test_toggle_disabled_to_enabled(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "t", "enabled": False, "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.patch(f"/api/backup/schedules/{sid}/toggle", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["enabled"] is True
        finally:
            mod.SCHEDULES_FILE = orig

    def test_toggle_default_enabled(self, test_client, admin_headers, tmp_path):
        """enabled キーが存在しない場合、デフォルトTrue -> Falseにトグル"""
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "no-key", "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.patch(f"/api/backup/schedules/{sid}/toggle", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["enabled"] is False
        finally:
            mod.SCHEDULES_FILE = orig

    def test_toggle_not_found_returns_404(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.patch(f"/api/backup/schedules/{uuid.uuid4()}/toggle", headers=admin_headers)
            assert resp.status_code == 404
        finally:
            mod.SCHEDULES_FILE = orig

    def test_toggle_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup._load_schedules", side_effect=RuntimeError("fail")):
            resp = test_client.patch(f"/api/backup/schedules/{uuid.uuid4()}/toggle", headers=admin_headers)
            assert resp.status_code == 503


class TestRunScheduleNow:
    """POST /api/backup/schedules/{id}/run-now エンドポイント"""

    def test_success(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "run-test", "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = {"request_id": "req-123"}
                resp = test_client.post(f"/api/backup/schedules/{sid}/run-now", headers=admin_headers)
            assert resp.status_code == 202
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["request_id"] == "req-123"
        finally:
            mod.SCHEDULES_FILE = orig

    def test_not_found_returns_404(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            resp = test_client.post(f"/api/backup/schedules/{uuid.uuid4()}/run-now", headers=admin_headers)
            assert resp.status_code == 404
        finally:
            mod.SCHEDULES_FILE = orig

    def test_approval_lookup_error_returns_400(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "run-test", "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
                mock_create.side_effect = LookupError("no policy")
                resp = test_client.post(f"/api/backup/schedules/{sid}/run-now", headers=admin_headers)
            assert resp.status_code == 400
        finally:
            mod.SCHEDULES_FILE = orig

    def test_exception_returns_503(self, test_client, admin_headers, tmp_path):
        from backend.api.routes import backup as mod
        orig = mod.SCHEDULES_FILE
        f = tmp_path / "schedules.json"
        sid = str(uuid.uuid4())
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "r", "target": "/home"}]}), encoding="utf-8")
        mod.SCHEDULES_FILE = f
        try:
            with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
                mock_create.side_effect = RuntimeError("internal fail")
                resp = test_client.post(f"/api/backup/schedules/{sid}/run-now", headers=admin_headers)
            assert resp.status_code == 503
        finally:
            mod.SCHEDULES_FILE = orig


class TestRequestRestore:
    """POST /api/backup/restore エンドポイント"""

    def test_success(self, test_client, admin_headers):
        from backend.api.routes import backup as mod
        with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"request_id": "restore-123"}
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "backup_2026.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "Restore for disaster recovery testing",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["approval_required"] is True
        assert data["request_id"] == "restore-123"

    def test_forbidden_chars_in_backup_file(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "file;rm -rf /",
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "Test restore reason for validation",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_chars_in_restore_target(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "backup.tar.gz",
                "restore_target": "/var/tmp;bad",
                "reason": "Test restore reason for validation",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_reason_too_short_returns_422(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "backup.tar.gz",
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "ab",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_lookup_error_returns_400(self, test_client, admin_headers):
        from backend.api.routes import backup as mod
        with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = LookupError("no policy")
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "backup.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "Testing restore with LookupError",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_value_error_returns_400(self, test_client, admin_headers):
        from backend.api.routes import backup as mod
        with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = ValueError("bad value")
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "backup.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "Testing restore with ValueError",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_exception_returns_503(self, test_client, admin_headers):
        from backend.api.routes import backup as mod
        with patch.object(mod.approval_service, "create_request", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("internal")
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "backup.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "Testing restore with exception",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 503

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "backup.tar.gz",
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "Test without auth",
            },
        )
        assert resp.status_code == 403
