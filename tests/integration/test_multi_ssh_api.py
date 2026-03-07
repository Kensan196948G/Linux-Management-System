"""
マルチサーバーSSH並列実行 API - 統合テスト

テスト対象エンドポイント:
  GET  /api/multi-ssh/commands
  POST /api/multi-ssh/execute
  GET  /api/multi-ssh/results/{job_id}
  GET  /api/multi-ssh/history
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_HOSTS = [
    {
        "id": "host-1",
        "name": "Web Server 1",
        "hostname": "web01.example.com",
        "host": "web01.example.com",
        "ip": "192.168.1.10",
        "port": 22,
        "username": "svc-adminui",
    },
    {
        "id": "host-2",
        "name": "Web Server 2",
        "hostname": "web02.example.com",
        "host": "web02.example.com",
        "ip": "192.168.1.11",
        "port": 22,
        "username": "svc-adminui",
    },
    {
        "id": "host-3",
        "name": "DB Server",
        "hostname": "db01.example.com",
        "host": "db01.example.com",
        "ip": "192.168.1.20",
        "port": 22,
        "username": "svc-adminui",
    },
]


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def test_client():
    """テストクライアント"""
    from backend.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    """管理者認証ヘッダー"""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    """閲覧者認証ヘッダー"""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    if resp.status_code != 200:
        pytest.skip("Viewer user not available")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_ssh_hosts(tmp_path, monkeypatch):
    """ssh_hosts.json をモックデータで差し替える"""
    hosts_file = tmp_path / "ssh_hosts.json"
    hosts_file.write_text(json.dumps(SAMPLE_HOSTS), encoding="utf-8")

    import backend.api.routes.multi_ssh as module

    monkeypatch.setattr(module, "_SSH_HOSTS_FILE", hosts_file)
    # _job_results をクリア（テスト間の干渉防止）
    module._job_results.clear()
    yield
    module._job_results.clear()


# ===================================================================
# 許可コマンド一覧取得テスト
# ===================================================================


class TestListCommands:
    def test_list_commands_ok(self, test_client, admin_headers):
        """許可コマンド一覧を正常取得できる"""
        resp = test_client.get("/api/multi-ssh/commands", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["commands"], list)
        assert len(data["commands"]) > 0

    def test_list_commands_contains_expected(self, test_client, admin_headers):
        """uptime, hostname が含まれている"""
        resp = test_client.get("/api/multi-ssh/commands", headers=admin_headers)
        commands = resp.json()["commands"]
        assert "uptime" in commands
        assert "hostname" in commands

    def test_list_commands_has_total(self, test_client, admin_headers):
        """total フィールドがある"""
        resp = test_client.get("/api/multi-ssh/commands", headers=admin_headers)
        data = resp.json()
        assert "total" in data
        assert data["total"] == len(data["commands"])

    def test_list_commands_readonly_subset(self, test_client, admin_headers):
        """readonly_commands が commands のサブセット"""
        resp = test_client.get("/api/multi-ssh/commands", headers=admin_headers)
        data = resp.json()
        cmds = set(data["commands"])
        ro = set(data["readonly_commands"])
        assert ro.issubset(cmds)

    def test_list_commands_unauthenticated(self, test_client):
        """未認証では 401/403 が返る"""
        resp = test_client.get("/api/multi-ssh/commands")
        assert resp.status_code in (401, 403)


# ===================================================================
# コマンド実行テスト
# ===================================================================


class TestExecute:
    def _mock_run(self, *args, **kwargs):
        """subprocess.run のモック（成功）"""
        m = MagicMock()
        m.returncode = 0
        m.stdout = "web01.example.com"
        m.stderr = ""
        return m

    def _mock_run_fail(self, *args, **kwargs):
        """subprocess.run のモック（失敗）"""
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        m.stderr = "Connection refused"
        return m

    def test_execute_readonly_command_accepted(self, test_client, admin_headers):
        """read-only コマンドは即時実行（202）"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-1"], "command": "uptime", "reason": "定期確認"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "started"
        assert "job_id" in data

    def test_execute_multiple_hosts(self, test_client, admin_headers):
        """複数ホストへの並列実行"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={
                    "host_ids": ["host-1", "host-2", "host-3"],
                    "command": "hostname",
                    "reason": "一括確認",
                },
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["total_hosts"] == 3

    def test_execute_command_not_in_allowlist(self, test_client, admin_headers):
        """allowlist 外コマンドは 422 エラー"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "cat /etc/passwd", "reason": "test"},
        )
        assert resp.status_code == 422

    def test_execute_command_with_shell_injection(self, test_client, admin_headers):
        """シェルインジェクション文字を含むコマンドは拒否"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "uptime; rm -rf /", "reason": "test"},
        )
        assert resp.status_code == 422

    def test_execute_command_with_pipe(self, test_client, admin_headers):
        """パイプ文字を含むコマンドは拒否"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "uptime | grep up", "reason": "test"},
        )
        assert resp.status_code == 422

    def test_execute_unknown_host_id(self, test_client, admin_headers):
        """存在しない host_id を含む場合 422 エラー"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["nonexistent-999"], "command": "uptime", "reason": "test"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "nonexistent-999" in (body.get("detail", "") or body.get("message", ""))

    def test_execute_mixed_host_ids(self, test_client, admin_headers):
        """有効+無効の host_id 混在は 422"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1", "bad-id"], "command": "uptime", "reason": "test"},
        )
        assert resp.status_code == 422

    def test_execute_empty_host_ids(self, test_client, admin_headers):
        """空の host_ids は 422"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": [], "command": "uptime", "reason": "test"},
        )
        assert resp.status_code == 422

    def test_execute_reason_with_forbidden_chars(self, test_client, admin_headers):
        """reason に禁止文字が含まれる場合は拒否"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "uptime", "reason": "test; echo hack"},
        )
        assert resp.status_code == 422

    def test_execute_unauthenticated(self, test_client):
        """未認証では 401/403"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            json={"host_ids": ["host-1"], "command": "uptime", "reason": "test"},
        )
        assert resp.status_code in (401, 403)

    def test_execute_returns_job_id(self, test_client, admin_headers):
        """job_id が UUID 形式で返る"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-1"], "command": "date", "reason": "確認"},
            )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        # UUID 形式の検証
        uuid.UUID(job_id)  # raises ValueError if invalid

    def test_execute_df_h_command(self, test_client, admin_headers):
        """'df -h' コマンドは allowlist に含まれ実行できる"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-2"], "command": "df -h", "reason": "ディスク確認"},
            )
        assert resp.status_code == 202

    def test_execute_systemctl_nginx(self, test_client, admin_headers):
        """systemctl is-active nginx は即時実行可能"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={
                    "host_ids": ["host-1"],
                    "command": "systemctl is-active nginx",
                    "reason": "nginx状態確認",
                },
            )
        assert resp.status_code == 202


# ===================================================================
# 結果取得テスト
# ===================================================================


class TestGetResult:
    def _mock_run(self, *args, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "up 10 days"
        m.stderr = ""
        return m

    def test_get_result_not_found(self, test_client, admin_headers):
        """存在しない job_id は 404"""
        resp = test_client.get(
            "/api/multi-ssh/results/nonexistent-job-id-not-found",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    def test_get_result_exists(self, test_client, admin_headers):
        """実行後に結果が取得できる"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "uptime",
            "status": "completed",
            "created_at": "2025-01-01T00:00:00",
            "completed_at": "2025-01-01T00:00:01",
            "results": [
                {
                    "host_id": "host-1",
                    "hostname": "web01.example.com",
                    "ip": "192.168.1.10",
                    "success": True,
                    "output": "up 5 days",
                    "elapsed_ms": 120,
                }
            ],
            "total_hosts": 1,
            "success_count": 1,
            "failure_count": 0,
            "requester": "admin@example.com",
            "reason": "確認",
        }

        resp = test_client.get(f"/api/multi-ssh/results/{job_id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["job"]["job_id"] == job_id
        assert data["job"]["status"] == "completed"

    def test_get_result_unauthenticated(self, test_client):
        """未認証では 401/403"""
        resp = test_client.get("/api/multi-ssh/results/some-id")
        assert resp.status_code in (401, 403)

    def test_get_result_has_results_list(self, test_client, admin_headers):
        """結果に results リストが含まれる"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "hostname",
            "status": "completed",
            "created_at": "2025-01-01T00:00:00",
            "completed_at": "2025-01-01T00:00:01",
            "results": [],
            "total_hosts": 0,
            "success_count": 0,
            "failure_count": 0,
            "requester": "admin@example.com",
            "reason": "テスト",
        }
        resp = test_client.get(f"/api/multi-ssh/results/{job_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert "results" in resp.json()["job"]


# ===================================================================
# 実行履歴テスト
# ===================================================================


class TestHistory:
    def test_history_empty(self, test_client, admin_headers):
        """ジョブなしの場合は空リスト"""
        resp = test_client.get("/api/multi-ssh/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["history"], list)
        assert data["total"] == 0

    def test_history_has_entries_after_execute(self, test_client, admin_headers):
        """実行後は履歴が増える"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "uptime",
            "status": "completed",
            "created_at": "2025-06-01T00:00:00",
            "completed_at": "2025-06-01T00:00:01",
            "results": [],
            "total_hosts": 2,
            "success_count": 2,
            "failure_count": 0,
            "requester": "admin@example.com",
            "reason": "履歴テスト",
        }

        resp = test_client.get("/api/multi-ssh/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        entry = next(e for e in data["history"] if e["job_id"] == job_id)
        assert entry["command"] == "uptime"
        assert entry["host_count"] == 2

    def test_history_unauthenticated(self, test_client):
        """未認証では 401/403"""
        resp = test_client.get("/api/multi-ssh/history")
        assert resp.status_code in (401, 403)

    def test_history_fields(self, test_client, admin_headers):
        """履歴エントリに必須フィールドが存在する"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "date",
            "status": "completed",
            "created_at": "2025-06-01T10:00:00",
            "completed_at": "2025-06-01T10:00:01",
            "results": [],
            "total_hosts": 1,
            "success_count": 1,
            "failure_count": 0,
            "requester": "admin@example.com",
            "reason": "フィールドテスト",
        }

        resp = test_client.get("/api/multi-ssh/history", headers=admin_headers)
        entry = next(e for e in resp.json()["history"] if e["job_id"] == job_id)
        for field in ("job_id", "command", "host_count", "success_count", "failure_count",
                      "created_at", "status", "requester", "reason"):
            assert field in entry, f"Missing field: {field}"
