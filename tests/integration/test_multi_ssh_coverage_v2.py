"""
multi_ssh.py カバレッジ改善テスト v2

対象: backend/api/routes/multi_ssh.py (48% -> 85%+)
未カバー箇所を重点的にテスト:
  - _load_ssh_hosts: ファイル不在・不正JSON・list/dict形式
  - _run_ssh_command_sync: 成功・失敗・タイムアウト・一般例外
  - _execute_parallel: 並列実行・結果格納
  - execute_multi_ssh: read-only即時実行・承認フロー・ValidationError
  - get_job_result: 存在するジョブ
  - get_history: ソート・フィールド
  - ExecuteRequest: field_validator（host_ids, command）
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


SAMPLE_HOSTS = [
    {"id": "host-1", "hostname": "web01.example.com", "host": "web01.example.com", "ip": "192.168.1.10", "port": 22},
    {"id": "host-2", "hostname": "web02.example.com", "host": "web02.example.com", "ip": "192.168.1.11", "port": 22},
]

SAMPLE_HOSTS_DICT_FORMAT = {"hosts": SAMPLE_HOSTS}


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def mock_ssh_hosts(tmp_path, monkeypatch):
    """ssh_hosts.json をモックデータで差し替え"""
    hosts_file = tmp_path / "ssh_hosts.json"
    hosts_file.write_text(json.dumps(SAMPLE_HOSTS), encoding="utf-8")
    import backend.api.routes.multi_ssh as module
    monkeypatch.setattr(module, "_SSH_HOSTS_FILE", hosts_file)
    module._job_results.clear()
    yield
    module._job_results.clear()


# ===================================================================
# _load_ssh_hosts ヘルパーテスト
# ===================================================================


class TestLoadSshHosts:
    """_load_ssh_hosts の全分岐テスト"""

    def test_load_list_format(self, tmp_path):
        from backend.api.routes.multi_ssh import _load_ssh_hosts, _SSH_HOSTS_FILE

        hosts_file = tmp_path / "hosts.json"
        hosts_file.write_text(json.dumps(SAMPLE_HOSTS))

        import backend.api.routes.multi_ssh as mod
        original = mod._SSH_HOSTS_FILE
        try:
            mod._SSH_HOSTS_FILE = hosts_file
            result = _load_ssh_hosts()
            assert "host-1" in result
            assert "host-2" in result
            assert result["host-1"]["hostname"] == "web01.example.com"
        finally:
            mod._SSH_HOSTS_FILE = original

    def test_load_dict_format(self, tmp_path):
        from backend.api.routes.multi_ssh import _load_ssh_hosts

        hosts_file = tmp_path / "hosts.json"
        hosts_file.write_text(json.dumps(SAMPLE_HOSTS_DICT_FORMAT))

        import backend.api.routes.multi_ssh as mod
        original = mod._SSH_HOSTS_FILE
        try:
            mod._SSH_HOSTS_FILE = hosts_file
            result = _load_ssh_hosts()
            assert "host-1" in result
        finally:
            mod._SSH_HOSTS_FILE = original

    def test_load_nonexistent_file(self, tmp_path):
        from backend.api.routes.multi_ssh import _load_ssh_hosts

        import backend.api.routes.multi_ssh as mod
        original = mod._SSH_HOSTS_FILE
        try:
            mod._SSH_HOSTS_FILE = tmp_path / "nonexistent.json"
            result = _load_ssh_hosts()
            assert result == {}
        finally:
            mod._SSH_HOSTS_FILE = original

    def test_load_invalid_json(self, tmp_path):
        from backend.api.routes.multi_ssh import _load_ssh_hosts

        hosts_file = tmp_path / "bad.json"
        hosts_file.write_text("not valid json {{{")

        import backend.api.routes.multi_ssh as mod
        original = mod._SSH_HOSTS_FILE
        try:
            mod._SSH_HOSTS_FILE = hosts_file
            result = _load_ssh_hosts()
            assert result == {}
        finally:
            mod._SSH_HOSTS_FILE = original

    def test_load_hosts_without_id(self, tmp_path):
        """id フィールドがないホストはスキップされる"""
        from backend.api.routes.multi_ssh import _load_ssh_hosts

        hosts = [{"hostname": "no-id-host", "ip": "10.0.0.1"}]
        hosts_file = tmp_path / "noid.json"
        hosts_file.write_text(json.dumps(hosts))

        import backend.api.routes.multi_ssh as mod
        original = mod._SSH_HOSTS_FILE
        try:
            mod._SSH_HOSTS_FILE = hosts_file
            result = _load_ssh_hosts()
            assert result == {}
        finally:
            mod._SSH_HOSTS_FILE = original


# ===================================================================
# _run_ssh_command_sync ヘルパーテスト
# ===================================================================


class TestRunSshCommandSync:
    """_run_ssh_command_sync の全分岐テスト"""

    def test_success(self):
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "up 10 days"
        mock_result.stderr = ""

        host = {"id": "h1", "hostname": "server1", "host": "server1", "ip": "10.0.0.1"}

        with patch("subprocess.run", return_value=mock_result):
            result = _run_ssh_command_sync(host, "uptime")

        assert result.success is True
        assert result.output == "up 10 days"
        assert result.host_id == "h1"
        assert result.hostname == "server1"
        assert result.ip == "10.0.0.1"
        assert result.elapsed_ms >= 0

    def test_failure(self):
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Connection refused"

        host = {"id": "h1", "hostname": "server1", "ip": "10.0.0.1"}

        with patch("subprocess.run", return_value=mock_result):
            result = _run_ssh_command_sync(host, "uptime")

        assert result.success is False
        assert "Connection refused" in result.output

    def test_failure_stdout_fallback(self):
        """stderr 空の場合は stdout にフォールバック"""
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "error via stdout"
        mock_result.stderr = ""

        host = {"id": "h1", "hostname": "server1", "ip": "10.0.0.1"}

        with patch("subprocess.run", return_value=mock_result):
            result = _run_ssh_command_sync(host, "uptime")

        assert result.success is False
        assert result.output == "error via stdout"

    def test_timeout(self):
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        host = {"id": "h1", "hostname": "server1", "ip": "10.0.0.1"}

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=15)):
            result = _run_ssh_command_sync(host, "uptime")

        assert result.success is False
        assert "timed out" in result.output.lower()

    def test_general_exception(self):
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        host = {"id": "h1", "hostname": "server1", "ip": "10.0.0.1"}

        with patch("subprocess.run", side_effect=OSError("file not found")):
            result = _run_ssh_command_sync(host, "uptime")

        assert result.success is False
        assert "Execution error" in result.output

    def test_host_without_hostname_uses_ip(self):
        """hostname がない場合は ip を使用"""
        from backend.api.routes.multi_ssh import _run_ssh_command_sync

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        host = {"id": "h1", "ip": "10.0.0.1"}

        with patch("subprocess.run", return_value=mock_result):
            result = _run_ssh_command_sync(host, "hostname")

        assert result.hostname == ""
        assert result.ip == "10.0.0.1"


# ===================================================================
# ExecuteRequest バリデーションテスト
# ===================================================================


class TestExecuteRequestValidation:
    """ExecuteRequest の field_validator テスト"""

    def test_valid_request(self):
        from backend.api.routes.multi_ssh import ExecuteRequest
        req = ExecuteRequest(host_ids=["host-1"], command="uptime", reason="test")
        assert req.command == "uptime"

    def test_empty_host_ids_rejected(self):
        from backend.api.routes.multi_ssh import ExecuteRequest
        with pytest.raises(Exception):
            ExecuteRequest(host_ids=[], command="uptime", reason="test")

    def test_invalid_command_rejected(self):
        from backend.api.routes.multi_ssh import ExecuteRequest
        with pytest.raises(Exception):
            ExecuteRequest(host_ids=["host-1"], command="cat /etc/shadow", reason="test")

    @pytest.mark.parametrize("cmd", [
        "uptime", "hostname", "df -h", "free -m", "uname -a", "date",
        "systemctl is-active nginx", "systemctl is-active postgresql",
        "systemctl is-active redis", "systemctl is-active sshd",
        "cat /etc/os-release",
    ])
    def test_all_allowed_commands(self, cmd):
        from backend.api.routes.multi_ssh import ExecuteRequest
        req = ExecuteRequest(host_ids=["host-1"], command=cmd, reason="test")
        assert req.command == cmd


# ===================================================================
# execute エンドポイント 追加テスト
# ===================================================================


class TestExecuteV2:
    """POST /api/multi-ssh/execute の追加カバレッジ"""

    def _mock_run(self, *args, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "ok"
        m.stderr = ""
        return m

    def test_execute_reason_with_pipe_rejected(self, test_client, admin_headers):
        """reason にパイプ文字を含む場合は 422"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "uptime", "reason": "test|hack"},
        )
        assert resp.status_code == 422

    def test_execute_reason_with_backtick_rejected(self, test_client, admin_headers):
        """reason にバックティックを含む場合は 422"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=admin_headers,
            json={"host_ids": ["host-1"], "command": "uptime", "reason": "test`cmd`"},
        )
        assert resp.status_code == 422

    def test_execute_viewer_cannot_execute(self, test_client, viewer_headers):
        """Viewer は write:ssh_hosts を持たない"""
        resp = test_client.post(
            "/api/multi-ssh/execute",
            headers=viewer_headers,
            json={"host_ids": ["host-1"], "command": "uptime", "reason": "test"},
        )
        assert resp.status_code == 403

    def test_execute_all_hosts(self, test_client, admin_headers):
        """全ホストへの実行"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-1", "host-2"], "command": "date", "reason": "全ホスト確認"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["total_hosts"] == 2
        assert data["status"] == "started"

    def test_execute_free_m_command(self, test_client, admin_headers):
        """'free -m' コマンド実行"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-1"], "command": "free -m", "reason": "メモリ確認"},
            )
        assert resp.status_code == 202

    def test_execute_uname_command(self, test_client, admin_headers):
        """'uname -a' コマンド実行"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-1"], "command": "uname -a", "reason": "OS確認"},
            )
        assert resp.status_code == 202

    def test_execute_cat_os_release(self, test_client, admin_headers):
        """'cat /etc/os-release' コマンド実行"""
        with patch("backend.api.routes.multi_ssh.subprocess.run", side_effect=self._mock_run):
            resp = test_client.post(
                "/api/multi-ssh/execute",
                headers=admin_headers,
                json={"host_ids": ["host-2"], "command": "cat /etc/os-release", "reason": "OS情報"},
            )
        assert resp.status_code == 202


# ===================================================================
# get_job_result 追加テスト
# ===================================================================


class TestGetResultV2:
    """GET /api/multi-ssh/results/{job_id} の追加カバレッジ"""

    def test_result_with_failures(self, test_client, admin_headers):
        """失敗したホストを含む結果"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "uptime",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T00:00:01",
            "results": [
                {"host_id": "host-1", "hostname": "web01", "ip": "10.0.0.1",
                 "success": True, "output": "up 5 days", "elapsed_ms": 100},
                {"host_id": "host-2", "hostname": "web02", "ip": "10.0.0.2",
                 "success": False, "output": "Connection refused", "elapsed_ms": 50},
            ],
            "total_hosts": 2,
            "success_count": 1,
            "failure_count": 1,
            "requester": "admin@example.com",
            "reason": "テスト",
        }

        resp = test_client.get(f"/api/multi-ssh/results/{job_id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job"]["success_count"] == 1
        assert data["job"]["failure_count"] == 1

    def test_result_running_status(self, test_client, admin_headers):
        """running 状態のジョブ"""
        import backend.api.routes.multi_ssh as module

        job_id = str(uuid.uuid4())
        module._job_results[job_id] = {
            "job_id": job_id,
            "command": "df -h",
            "status": "running",
            "created_at": "2026-01-01T00:00:00",
            "completed_at": None,
            "results": [],
            "total_hosts": 3,
            "success_count": 0,
            "failure_count": 0,
            "requester": "admin@example.com",
            "reason": "実行中",
        }

        resp = test_client.get(f"/api/multi-ssh/results/{job_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["job"]["status"] == "running"


# ===================================================================
# get_history 追加テスト
# ===================================================================


class TestHistoryV2:
    """GET /api/multi-ssh/history の追加カバレッジ"""

    def test_history_sorted_by_created_at(self, test_client, admin_headers):
        """履歴が created_at 降順でソートされる"""
        import backend.api.routes.multi_ssh as module

        for i, ts in enumerate(["2026-01-01", "2026-01-03", "2026-01-02"]):
            jid = str(uuid.uuid4())
            module._job_results[jid] = {
                "job_id": jid,
                "command": "uptime",
                "status": "completed",
                "created_at": f"{ts}T00:00:00",
                "completed_at": f"{ts}T00:00:01",
                "results": [],
                "total_hosts": 1,
                "success_count": 1,
                "failure_count": 0,
                "requester": "admin",
                "reason": f"test {i}",
            }

        resp = test_client.get("/api/multi-ssh/history", headers=admin_headers)
        assert resp.status_code == 200
        history = resp.json()["history"]
        # 降順チェック
        dates = [e["created_at"] for e in history]
        assert dates == sorted(dates, reverse=True)

    def test_history_viewer_can_read(self, test_client, viewer_headers):
        """Viewer は履歴を読める (read:ssh_hosts)"""
        resp = test_client.get("/api/multi-ssh/history", headers=viewer_headers)
        assert resp.status_code == 200

    def test_history_viewer_can_read_commands(self, test_client, viewer_headers):
        """Viewer はコマンド一覧を読める"""
        resp = test_client.get("/api/multi-ssh/commands", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# Pydantic モデルテスト
# ===================================================================


class TestMultiSshModels:
    """Pydantic モデルのテスト"""

    def test_host_result_model(self):
        from backend.api.routes.multi_ssh import HostResult
        hr = HostResult(
            host_id="h1", hostname="server", ip="10.0.0.1",
            success=True, output="ok", elapsed_ms=100,
        )
        assert hr.success is True

    def test_job_result_model(self):
        from backend.api.routes.multi_ssh import JobResult
        jr = JobResult(
            job_id="j1", command="uptime", status="completed",
            created_at="2026-01-01T00:00:00",
        )
        assert jr.results == []
        assert jr.total_hosts == 0

    def test_history_entry_model(self):
        from backend.api.routes.multi_ssh import HistoryEntry
        he = HistoryEntry(
            job_id="j1", command="uptime", host_count=2,
            success_count=2, failure_count=0,
            created_at="2026-01-01", status="completed",
            requester="admin", reason="test",
        )
        assert he.completed_at is None

    def test_allowed_commands_constant(self):
        from backend.api.routes.multi_ssh import ALLOWED_COMMANDS, READONLY_COMMANDS
        assert isinstance(ALLOWED_COMMANDS, frozenset)
        assert isinstance(READONLY_COMMANDS, frozenset)
        assert READONLY_COMMANDS.issubset(ALLOWED_COMMANDS)
