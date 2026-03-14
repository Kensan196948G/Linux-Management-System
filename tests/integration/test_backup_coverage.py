"""バックアップ管理API カバレッジ向上テスト

backup.py の未カバー行を重点的にテスト:
- ヘルパー関数 (_load_schedules, _save_schedules, _load_history, _validate_cron, _validate_target)
- 全エンドポイントの正常系/異常系/エッジケース
- 承認フロー経由エンドポイント (restore, run-now)
- Pydantic バリデーション
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


# ─── ヘルパー関数の単体テスト ─────────────────────────────────────────────────


class TestValidateCron:
    """_validate_cron のテスト"""

    def test_preset_daily(self):
        from backend.api.routes.backup import _validate_cron

        assert _validate_cron("daily") == "0 2 * * *"

    def test_preset_weekly(self):
        from backend.api.routes.backup import _validate_cron

        assert _validate_cron("weekly") == "0 2 * * 0"

    def test_preset_monthly(self):
        from backend.api.routes.backup import _validate_cron

        assert _validate_cron("monthly") == "0 2 1 * *"

    def test_valid_5_field_cron(self):
        from backend.api.routes.backup import _validate_cron

        assert _validate_cron("30 3 * * 1") == "30 3 * * 1"

    def test_valid_every_minute(self):
        from backend.api.routes.backup import _validate_cron

        assert _validate_cron("* * * * *") == "* * * * *"

    @pytest.mark.parametrize(
        "bad_cron",
        [
            "invalid",
            "0 2 * *",  # 4 fields
            "0 2 * * * *",  # 6 fields
            "",  # empty
            "not-a-preset",
            "hourly",  # not in presets
            "0 2 *",  # 3 fields
        ],
    )
    def test_invalid_cron_raises_400(self, bad_cron):
        from backend.api.routes.backup import _validate_cron

        with pytest.raises(HTTPException) as exc_info:
            _validate_cron(bad_cron)
        assert exc_info.value.status_code == 400
        assert "5フィールド" in exc_info.value.detail


class TestValidateTarget:
    """_validate_target のテスト"""

    @pytest.mark.parametrize(
        "target",
        ["/home", "/etc", "/var/www", "/opt", "/var/backups"],
    )
    def test_allowed_targets(self, target):
        from backend.api.routes.backup import _validate_target

        assert _validate_target(target) == target

    @pytest.mark.parametrize(
        "target",
        [
            "/root",
            "/tmp",
            "/usr",
            "/var",
            "/home/user",  # subdirectory not in allowlist
            "/etc/passwd",  # file, not directory
            "",
            "/",
        ],
    )
    def test_denied_targets_raise_400(self, target):
        from backend.api.routes.backup import _validate_target

        with pytest.raises(HTTPException) as exc_info:
            _validate_target(target)
        assert exc_info.value.status_code == 400
        assert "許可リスト外" in exc_info.value.detail


class TestLoadSchedules:
    """_load_schedules のテスト"""

    def test_creates_file_if_missing(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "sub" / "schedules.json"
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)
        result = mod._load_schedules()
        assert result == {"schedules": []}
        assert f.exists()

    def test_reads_existing_file(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        data = {"schedules": [{"id": "abc", "name": "test"}]}
        f.write_text(json.dumps(data))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)
        result = mod._load_schedules()
        assert result == data

    def test_returns_empty_on_invalid_json(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text("{invalid json!!")
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)
        result = mod._load_schedules()
        assert result == {"schedules": []}


class TestSaveSchedules:
    """_save_schedules のテスト"""

    def test_saves_to_file(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)
        data = {"schedules": [{"id": "x", "name": "y"}]}
        mod._save_schedules(data)
        assert json.loads(f.read_text()) == data

    def test_creates_parent_dirs(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "deep" / "nested" / "schedules.json"
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)
        mod._save_schedules({"schedules": []})
        assert f.exists()


class TestLoadHistory:
    """_load_history のテスト"""

    def test_creates_file_if_missing(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        monkeypatch.setattr(mod, "HISTORY_FILE", f)
        result = mod._load_history()
        assert result == {"history": []}
        assert f.exists()

    def test_reads_existing_file(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        data = {"history": [{"ts": "2025-01-01", "status": "ok"}]}
        f.write_text(json.dumps(data))
        monkeypatch.setattr(mod, "HISTORY_FILE", f)
        result = mod._load_history()
        assert result == data

    def test_returns_empty_on_invalid_json(self, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        f.write_text("NOT JSON {{")
        monkeypatch.setattr(mod, "HISTORY_FILE", f)
        result = mod._load_history()
        assert result == {"history": []}


# ─── エンドポイント統合テスト ─────────────────────────────────────────────────


class TestGetBackupList:
    """GET /api/backup/list"""

    def test_success_multiple_lines(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_list.return_value = {
                "stdout": "backup1.tar.gz\nbackup2.tar.gz\nbackup3.tar.gz",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/list", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 3
            assert len(data["backups"]) == 3
            assert "timestamp" in data

    def test_empty_stdout(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_list.return_value = {"stdout": "", "returncode": 0}
            resp = test_client.get("/api/backup/list", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_list.side_effect = RuntimeError("disk error")
            resp = test_client.get("/api/backup/list", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_list.side_effect = HTTPException(
                status_code=502, detail="bad gw"
            )
            resp = test_client.get("/api/backup/list", headers=admin_headers)
            assert resp.status_code == 502


class TestGetDiskUsage:
    """GET /api/backup/disk-usage"""

    def test_success(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_disk_usage.return_value = {
                "stdout": "  1.5G\t/var/backups  \n",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["usage"] == "1.5G\t/var/backups"

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_disk_usage.side_effect = RuntimeError("fail")
            resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_disk_usage.side_effect = HTTPException(
                status_code=500, detail="err"
            )
            resp = test_client.get("/api/backup/disk-usage", headers=admin_headers)
            assert resp.status_code == 500


class TestGetRecentLogs:
    """GET /api/backup/recent-logs"""

    def test_success(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_recent_logs.return_value = {
                "stdout": "line1\nline2\n\nline3",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 3  # empty lines excluded
            assert len(data["logs"]) == 3

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_recent_logs.side_effect = RuntimeError("fail")
            resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_recent_logs.side_effect = HTTPException(
                status_code=401, detail="unauth"
            )
            resp = test_client.get("/api/backup/recent-logs", headers=admin_headers)
            assert resp.status_code == 401


class TestGetBackupStatus:
    """GET /api/backup/status"""

    def test_running_detected(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_status.return_value = {
                "stdout": "backup.service - Running backup\nActive: active (running)",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/status", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["running"] is True

    def test_not_running(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_status.return_value = {
                "stdout": "No backup timers found",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/status", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["running"] is False

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_status.side_effect = RuntimeError("fail")
            resp = test_client.get("/api/backup/status", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_status.side_effect = HTTPException(
                status_code=429, detail="rate limited"
            )
            resp = test_client.get("/api/backup/status", headers=admin_headers)
            assert resp.status_code == 429

    def test_response_structure(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.get_backup_status.return_value = {"stdout": "idle", "returncode": 0}
            resp = test_client.get("/api/backup/status", headers=admin_headers)
            data = resp.json()
            assert "running" in data
            assert "status" in data
            assert "status_lines" in data
            assert "returncode" in data
            assert "timestamp" in data


class TestGetBackupStorage:
    """GET /api/backup/storage"""

    def test_json_lines_parsed(self, test_client, admin_headers):
        json_line = json.dumps(
            {
                "name": "b.tar.gz",
                "path": "/var/backups/b.tar.gz",
                "size": 1024,
                "mtime": "2025-01-01",
            }
        )
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.return_value = {
                "stdout": json_line + "\n",
                "returncode": 0,
            }
            mock_sw.get_backup_disk_usage.return_value = {
                "stdout": "2G\t/var/backups",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1
            assert data["files"][0]["name"] == "b.tar.gz"
            assert data["total_usage"] == "2G\t/var/backups"

    def test_non_json_line_as_fallback(self, test_client, admin_headers):
        """non-JSON line is stored as plain entry"""
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.return_value = {
                "stdout": "some-plain-text-line\n",
                "returncode": 0,
            }
            mock_sw.get_backup_disk_usage.return_value = {
                "stdout": "0\t/var/backups",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 200
            files = resp.json()["files"]
            assert len(files) == 1
            assert files[0]["name"] == "some-plain-text-line"
            assert files[0]["size"] is None

    def test_skip_header_lines(self, test_client, admin_headers):
        """Lines starting with 'Backup' or 'No backup' are skipped"""
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.return_value = {
                "stdout": "Backup directory listing:\nNo backup files\n",
                "returncode": 0,
            }
            mock_sw.get_backup_disk_usage.return_value = {
                "stdout": "0",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0

    def test_empty_lines_skipped(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.return_value = {
                "stdout": "\n\n  \n",
                "returncode": 0,
            }
            mock_sw.get_backup_disk_usage.return_value = {
                "stdout": "0",
                "returncode": 0,
            }
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.side_effect = RuntimeError("fail")
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch("backend.api.routes.backup.sudo_wrapper") as mock_sw:
            mock_sw.list_backup_files.side_effect = HTTPException(
                status_code=403, detail="forbidden"
            )
            resp = test_client.get("/api/backup/storage", headers=admin_headers)
            assert resp.status_code == 403


class TestGetBackupHistory:
    """GET /api/backup/history"""

    def test_success_with_data(self, test_client, admin_headers, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        entries = [{"ts": f"2025-01-{i:02d}", "status": "ok"} for i in range(1, 4)]
        f.write_text(json.dumps({"history": entries}))
        monkeypatch.setattr(mod, "HISTORY_FILE", f)

        resp = test_client.get("/api/backup/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert data["total"] == 3

    def test_max_50_entries(self, test_client, admin_headers, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        entries = [{"ts": f"item-{i}", "status": "ok"} for i in range(80)]
        f.write_text(json.dumps({"history": entries}))
        monkeypatch.setattr(mod, "HISTORY_FILE", f)

        resp = test_client.get("/api/backup/history", headers=admin_headers)
        data = resp.json()
        assert data["count"] == 50
        assert data["total"] == 80

    def test_empty_history(self, test_client, admin_headers, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "history.json"
        f.write_text(json.dumps({"history": []}))
        monkeypatch.setattr(mod, "HISTORY_FILE", f)

        resp = test_client.get("/api/backup/history", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_history",
            side_effect=RuntimeError("io error"),
        ):
            resp = test_client.get("/api/backup/history", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_history",
            side_effect=HTTPException(status_code=500, detail="err"),
        ):
            resp = test_client.get("/api/backup/history", headers=admin_headers)
            assert resp.status_code == 500


class TestListSchedules:
    """GET /api/backup/schedules"""

    def test_success(self, test_client, admin_headers, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": [{"id": "s1", "name": "test"}]}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.get("/api/backup/schedules", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "presets" in data
        assert data["presets"]["daily"] == "0 2 * * *"

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules", side_effect=RuntimeError("err")
        ):
            resp = test_client.get("/api/backup/schedules", headers=admin_headers)
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules",
            side_effect=HTTPException(status_code=404, detail="nf"),
        ):
            resp = test_client.get("/api/backup/schedules", headers=admin_headers)
            assert resp.status_code == 404


class TestCreateSchedule:
    """POST /api/backup/schedules"""

    def test_create_with_cron_expr(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules",
            json={
                "name": "nightly",
                "cron": "0 3 * * *",
                "target": "/home",
                "enabled": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        assert data["schedule"]["cron"] == "0 3 * * *"
        assert data["schedule"]["target"] == "/home"
        assert "id" in data["schedule"]

    def test_create_with_preset_monthly(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules",
            json={
                "name": "monthly-bak",
                "cron": "monthly",
                "target": "/etc",
                "enabled": False,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["schedule"]["cron"] == "0 2 1 * *"
        assert resp.json()["schedule"]["enabled"] is False

    def test_invalid_target_returns_400(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules",
            json={"name": "bad", "cron": "daily", "target": "/root", "enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_invalid_cron_returns_400(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules",
            json={
                "name": "bad-cron",
                "cron": "every hour",
                "target": "/home",
                "enabled": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_chars_in_name_returns_400(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules",
            json={
                "name": "test;rm -rf /",
                "cron": "daily",
                "target": "/home",
                "enabled": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_empty_name_returns_422(self, test_client, admin_headers):
        """Pydantic min_length=1 violation"""
        resp = test_client.post(
            "/api/backup/schedules",
            json={"name": "", "cron": "daily", "target": "/home"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_missing_name_returns_422(self, test_client, admin_headers):
        """Required field missing"""
        resp = test_client.post(
            "/api/backup/schedules",
            json={"cron": "daily", "target": "/home"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules", side_effect=RuntimeError("io")
        ):
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "x", "cron": "daily", "target": "/home"},
                headers=admin_headers,
            )
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.validate_no_forbidden_chars",
            side_effect=HTTPException(status_code=400, detail="forbidden char"),
        ):
            resp = test_client.post(
                "/api/backup/schedules",
                json={"name": "x", "cron": "daily", "target": "/home"},
                headers=admin_headers,
            )
            assert resp.status_code == 400


class TestDeleteSchedule:
    """DELETE /api/backup/schedules/{id}"""

    def test_delete_existing(self, test_client, admin_headers, tmp_path, monkeypatch):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "to-delete"}]}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.delete(f"/api/backup/schedules/{sid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        # Verify file updated
        remaining = json.loads(f.read_text())["schedules"]
        assert len(remaining) == 0

    def test_delete_nonexistent_returns_404(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.delete(
            "/api/backup/schedules/no-such-id", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_forbidden_chars_in_id_returns_400(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.delete(
            "/api/backup/schedules/id%3Brm%20-rf", headers=admin_headers
        )
        assert resp.status_code in (400, 404)

    def test_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules", side_effect=RuntimeError("err")
        ):
            resp = test_client.delete(
                "/api/backup/schedules/some-id", headers=admin_headers
            )
            assert resp.status_code == 503

    def test_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.validate_no_forbidden_chars",
            side_effect=HTTPException(status_code=400, detail="bad"),
        ):
            resp = test_client.delete(
                "/api/backup/schedules/some-id", headers=admin_headers
            )
            assert resp.status_code == 400


class TestToggleSchedule:
    """PATCH /api/backup/schedules/{id}/toggle"""

    def test_toggle_enabled_to_disabled(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps(
                {
                    "schedules": [
                        {"id": sid, "name": "t", "enabled": True, "target": "/home"}
                    ]
                }
            )
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.patch(
            f"/api/backup/schedules/{sid}/toggle", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        assert resp.json()["schedule_id"] == sid

    def test_toggle_disabled_to_enabled(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps(
                {
                    "schedules": [
                        {"id": sid, "name": "t", "enabled": False, "target": "/etc"}
                    ]
                }
            )
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.patch(
            f"/api/backup/schedules/{sid}/toggle", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_toggle_without_enabled_field_defaults(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        """Schedule without 'enabled' key defaults to True, toggle makes it False"""
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps({"schedules": [{"id": sid, "name": "t", "target": "/opt"}]})
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.patch(
            f"/api/backup/schedules/{sid}/toggle", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_toggle_nonexistent_returns_404(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.patch(
            "/api/backup/schedules/nonexistent/toggle", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_toggle_updates_timestamp(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps(
                {
                    "schedules": [
                        {"id": sid, "name": "t", "enabled": True, "target": "/home"}
                    ]
                }
            )
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        test_client.patch(f"/api/backup/schedules/{sid}/toggle", headers=admin_headers)
        saved = json.loads(f.read_text())
        assert "updated_at" in saved["schedules"][0]

    def test_toggle_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules", side_effect=RuntimeError("err")
        ):
            resp = test_client.patch(
                "/api/backup/schedules/some-id/toggle", headers=admin_headers
            )
            assert resp.status_code == 503

    def test_toggle_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup._load_schedules",
            side_effect=HTTPException(status_code=418, detail="teapot"),
        ):
            resp = test_client.patch(
                "/api/backup/schedules/some-id/toggle", headers=admin_headers
            )
            assert resp.status_code == 418


class TestRestoreRequest:
    """POST /api/backup/restore"""

    def test_restore_success_202(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(return_value={"request_id": "req-001", "status": "pending"}),
        ):
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "/var/backups/backup.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "Disaster recovery needed",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 202
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["approval_required"] is True
            assert data["request_id"] == "req-001"

    def test_restore_forbidden_chars_in_file(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "/var/backups/test;rm.tar.gz",
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "Recovery testing with special chars",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_restore_forbidden_chars_in_target(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "/var/backups/clean.tar.gz",
                "restore_target": "/tmp;echo hacked",
                "reason": "Recovery testing with injection",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_restore_short_reason_returns_422(self, test_client, admin_headers):
        """Pydantic min_length=5 validation"""
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "/var/backups/b.tar.gz",
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "ok",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_restore_missing_reason_returns_422(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "backup_file": "/var/backups/b.tar.gz",
                "restore_target": "/var/tmp/adminui-restore",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_restore_missing_backup_file_returns_422(self, test_client, admin_headers):
        resp = test_client.post(
            "/api/backup/restore",
            json={
                "restore_target": "/var/tmp/adminui-restore",
                "reason": "need to restore",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_restore_lookup_error_returns_400(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(side_effect=LookupError("request type not found")),
        ):
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "/var/backups/b.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "testing lookup error handling",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_restore_value_error_returns_400(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(side_effect=ValueError("bad value")),
        ):
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "/var/backups/b.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "testing value error handling",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_restore_generic_exception_returns_503(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "/var/backups/b.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "testing generic exception",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 503

    def test_restore_http_exception_reraise(self, test_client, admin_headers):
        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(
                side_effect=HTTPException(status_code=409, detail="conflict")
            ),
        ):
            resp = test_client.post(
                "/api/backup/restore",
                json={
                    "backup_file": "/var/backups/b.tar.gz",
                    "restore_target": "/var/tmp/adminui-restore",
                    "reason": "testing http exception reraise",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 409


class TestRunScheduleNow:
    """POST /api/backup/schedules/{id}/run-now"""

    def test_run_now_success_202(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps(
                {"schedules": [{"id": sid, "name": "my-sched", "target": "/home"}]}
            )
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(return_value={"request_id": "req-run-001"}),
        ):
            resp = test_client.post(
                f"/api/backup/schedules/{sid}/run-now", headers=admin_headers
            )
            assert resp.status_code == 202
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["schedule_id"] == sid
            assert data["request_id"] == "req-run-001"

    def test_run_now_nonexistent_returns_404(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": []}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        resp = test_client.post(
            "/api/backup/schedules/nonexistent-id/run-now", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_run_now_approval_lookup_error_returns_400(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps({"schedules": [{"id": sid, "name": "s", "target": "/home"}]})
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(side_effect=LookupError("type not supported")),
        ):
            resp = test_client.post(
                f"/api/backup/schedules/{sid}/run-now", headers=admin_headers
            )
            assert resp.status_code == 400

    def test_run_now_generic_exception_returns_503(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps({"schedules": [{"id": sid, "name": "s", "target": "/home"}]})
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            resp = test_client.post(
                f"/api/backup/schedules/{sid}/run-now", headers=admin_headers
            )
            assert resp.status_code == 503

    def test_run_now_http_exception_reraise(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(
            json.dumps({"schedules": [{"id": sid, "name": "s", "target": "/home"}]})
        )
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(
                side_effect=HTTPException(status_code=429, detail="rate limit")
            ),
        ):
            resp = test_client.post(
                f"/api/backup/schedules/{sid}/run-now", headers=admin_headers
            )
            assert resp.status_code == 429

    def test_run_now_schedule_without_target(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        """Schedule entry missing 'target' key uses empty string fallback"""
        import backend.api.routes.backup as mod

        sid = str(uuid.uuid4())
        f = tmp_path / "schedules.json"
        f.write_text(json.dumps({"schedules": [{"id": sid, "name": "no-target"}]}))
        monkeypatch.setattr(mod, "SCHEDULES_FILE", f)

        with patch(
            "backend.api.routes.backup.approval_service.create_request",
            new=AsyncMock(return_value={"request_id": "req-002"}),
        ):
            resp = test_client.post(
                f"/api/backup/schedules/{sid}/run-now", headers=admin_headers
            )
            assert resp.status_code == 202


# ─── Pydantic モデルバリデーション ────────────────────────────────────────────


class TestPydanticModels:
    """ScheduleCreate / RestoreRequest バリデーション"""

    def test_schedule_create_defaults_enabled_true(self):
        from backend.api.routes.backup import ScheduleCreate

        s = ScheduleCreate(name="test", cron="daily", target="/home")
        assert s.enabled is True

    def test_schedule_create_name_too_long(self):
        from pydantic import ValidationError
        from backend.api.routes.backup import ScheduleCreate

        with pytest.raises(ValidationError):
            ScheduleCreate(name="x" * 101, cron="daily", target="/home")

    def test_restore_request_default_target(self):
        from backend.api.routes.backup import RestoreRequest

        r = RestoreRequest(backup_file="b.tar.gz", reason="need to restore data")
        assert r.restore_target == "/var/tmp/adminui-restore"

    def test_restore_request_reason_too_long(self):
        from pydantic import ValidationError
        from backend.api.routes.backup import RestoreRequest

        with pytest.raises(ValidationError):
            RestoreRequest(backup_file="b.tar.gz", reason="x" * 501)

    def test_restore_request_custom_target(self):
        from backend.api.routes.backup import RestoreRequest

        r = RestoreRequest(
            backup_file="b.tar.gz",
            restore_target="/custom/path",
            reason="custom restore target",
        )
        assert r.restore_target == "/custom/path"


# ─── 認証なしのアクセス拒否テスト ─────────────────────────────────────────────


class TestUnauthenticatedAccess:
    """All endpoints reject unauthenticated requests"""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/backup/list"),
            ("GET", "/api/backup/disk-usage"),
            ("GET", "/api/backup/recent-logs"),
            ("GET", "/api/backup/status"),
            ("GET", "/api/backup/storage"),
            ("GET", "/api/backup/history"),
            ("GET", "/api/backup/schedules"),
            ("POST", "/api/backup/schedules"),
            ("DELETE", "/api/backup/schedules/any-id"),
            ("POST", "/api/backup/restore"),
            ("PATCH", "/api/backup/schedules/any-id/toggle"),
            ("POST", "/api/backup/schedules/any-id/run-now"),
        ],
    )
    def test_no_auth_rejected(self, test_client, method, path):
        if method == "GET":
            resp = test_client.get(path)
        elif method == "POST":
            resp = test_client.post(path, json={})
        elif method == "DELETE":
            resp = test_client.delete(path)
        elif method == "PATCH":
            resp = test_client.patch(path)
        assert resp.status_code in (401, 403, 422)
