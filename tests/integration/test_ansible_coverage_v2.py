"""
Ansible API - カバレッジ改善テスト v2

対象: backend/api/routes/ansible.py
目標: 85%以上のカバレッジ

全ヘルパー関数・エンドポイントの分岐を網羅する。
"""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_INVENTORY = {
    "_meta": {
        "hostvars": {
            "web01": {
                "ansible_host": "192.168.1.10",
                "ansible_distribution": "Ubuntu",
                "ansible_password": "secret",
            },
            "web02": {"ansible_ip": "192.168.1.11", "os": "CentOS"},
            "db01": {"ansible_host": "192.168.1.20"},
        }
    },
    "webservers": {"hosts": ["web01", "web02"]},
    "databases": {"hosts": ["db01"]},
    "all": {"hosts": ["web01", "web02", "db01"]},
}

SAMPLE_PING_OUTPUT = (
    "web01 | SUCCESS => {}\n"
    "web02 | UNREACHABLE! => {}\n"
    "db01 | FAILED => {}\n"
    "\n"
    "   \n"
)

SAMPLE_PLAYBOOK_YML = """# Deploy web application
- name: Deploy web app
  hosts: webservers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
    - name: Start nginx
      service:
        name: nginx
        state: started
"""

ANSIBLE_NOT_INSTALLED = {
    "status": "ansible_not_installed",
    "hosts": [],
    "message": "Ansible is not installed",
}


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def operator_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def viewer_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


# ===================================================================
# テスト: _validate_playbook_name ヘルパー
# ===================================================================


class TestValidatePlaybookName:
    """_validate_playbook_name の全分岐テスト"""

    def test_valid_name(self):
        from backend.api.routes.ansible import _validate_playbook_name

        # 正常な名前はエラーなし
        _validate_playbook_name("deploy-web.yml")
        _validate_playbook_name("my_playbook.yml")
        _validate_playbook_name("A123-test_book.yml")

    def test_empty_name_rejected(self):
        from backend.api.routes.ansible import _validate_playbook_name
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_playbook_name("")
        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail.lower()

    def test_too_long_name_rejected(self):
        from backend.api.routes.ansible import _validate_playbook_name
        from fastapi import HTTPException

        long_name = "a" * 125 + ".yml"  # 129 chars
        with pytest.raises(HTTPException) as exc_info:
            _validate_playbook_name(long_name)
        assert exc_info.value.status_code == 400
        assert "too long" in exc_info.value.detail.lower()

    @pytest.mark.parametrize(
        "bad_name",
        [
            "deploy;evil.yml",
            "deploy|cmd.yml",
            "deploy web.yml",
            "deploy$var.yml",
            "deploy`cmd`.yml",
            "no-extension",
            "../traversal.yml",
            "deploy.yaml",  # .yaml not .yml
        ],
    )
    def test_pattern_mismatch_rejected(self, bad_name):
        from backend.api.routes.ansible import _validate_playbook_name
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_playbook_name(bad_name)
        assert exc_info.value.status_code == 400

    def test_path_traversal_double_dot_rejected(self):
        """'..' を含む名前はパターンでも弾かれるがpath traversalチェックも確認"""
        from backend.api.routes.ansible import _validate_playbook_name
        from fastapi import HTTPException

        # '..' を含むが正規表現でも弾かれる
        with pytest.raises(HTTPException):
            _validate_playbook_name("a..b.yml")


# ===================================================================
# テスト: _run_wrapper ヘルパー
# ===================================================================


class TestRunWrapper:
    """_run_wrapper の全分岐テスト"""

    def test_success_json_response(self):
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "success", "data": "ok"})
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["inventory-list"])
        assert result["status"] == "success"
        assert result["data"] == "ok"

    def test_ansible_not_installed_json(self):
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = json.dumps(ANSIBLE_NOT_INSTALLED)
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["inventory-list"])
        assert result["status"] == "ansible_not_installed"

    def test_non_json_stdout_success(self):
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = "plain text output"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["some-cmd"])
        assert result["status"] == "success"
        assert result["stdout"] == "plain text output"

    def test_non_json_stdout_error(self):
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = "error output"
        mock_result.stderr = "some error"
        mock_result.returncode = 1

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["some-cmd"])
        assert result["status"] == "error"
        assert result["returncode"] == 1

    def test_empty_stdout(self):
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["some-cmd"])
        assert result["status"] == "success"

    def test_file_not_found(self):
        from backend.api.routes.ansible import _run_wrapper

        with patch(
            "backend.api.routes.ansible.subprocess.run",
            side_effect=FileNotFoundError("not found"),
        ):
            result = _run_wrapper(["some-cmd"])
        assert result["status"] == "ansible_not_installed"

    def test_timeout_expired(self):
        from backend.api.routes.ansible import _run_wrapper

        with patch(
            "backend.api.routes.ansible.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=60),
        ):
            result = _run_wrapper(["some-cmd"], timeout=60)
        assert result["status"] == "error"
        assert "timed out" in result["message"]

    def test_generic_exception(self):
        from backend.api.routes.ansible import _run_wrapper

        with patch(
            "backend.api.routes.ansible.subprocess.run",
            side_effect=RuntimeError("unexpected error"),
        ):
            result = _run_wrapper(["some-cmd"])
        assert result["status"] == "error"
        assert "unexpected error" in result["message"]

    def test_invalid_json_stdout(self):
        """JSON パース失敗時のフォールバック"""
        from backend.api.routes.ansible import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = "{invalid json"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.ansible.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["some-cmd"])
        # JSON パース失敗 -> フォールバック
        assert result["status"] == "success"
        assert result["stdout"] == "{invalid json"


# ===================================================================
# テスト: _parse_ping_output ヘルパー
# ===================================================================


class TestParsePingOutput:
    """_parse_ping_output の全分岐テスト"""

    def test_success_and_unreachable(self):
        from backend.api.routes.ansible import _parse_ping_output

        result = _parse_ping_output(SAMPLE_PING_OUTPUT)
        assert result["web01"] == "online"
        assert result["web02"] == "offline"
        assert result["db01"] == "offline"

    def test_empty_string(self):
        from backend.api.routes.ansible import _parse_ping_output

        result = _parse_ping_output("")
        assert result == {}

    def test_blank_lines_only(self):
        from backend.api.routes.ansible import _parse_ping_output

        result = _parse_ping_output("\n\n  \n")
        assert result == {}

    def test_non_matching_lines_skipped(self):
        from backend.api.routes.ansible import _parse_ping_output

        stdout = "Some random output\nAnother line\n"
        result = _parse_ping_output(stdout)
        assert result == {}

    def test_mixed_output(self):
        from backend.api.routes.ansible import _parse_ping_output

        stdout = (
            "PLAY RECAP\n"
            "server1 | SUCCESS => {}\n"
            "garbage line\n"
            "server2 | FAILED => {}\n"
        )
        result = _parse_ping_output(stdout)
        assert result["server1"] == "online"
        assert result["server2"] == "offline"


# ===================================================================
# テスト: _parse_inventory_hosts ヘルパー
# ===================================================================


class TestParseInventoryHosts:
    """_parse_inventory_hosts の全分岐テスト"""

    def test_normal_inventory(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        hosts = _parse_inventory_hosts(SAMPLE_INVENTORY)
        assert len(hosts) == 3
        hostnames = {h.hostname for h in hosts}
        assert "web01" in hostnames
        assert "web02" in hostnames
        assert "db01" in hostnames

    def test_password_fields_excluded(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        hosts = _parse_inventory_hosts(SAMPLE_INVENTORY)
        web01 = next(h for h in hosts if h.hostname == "web01")
        assert "ansible_password" not in web01.variables
        assert "ansible_ssh_pass" not in web01.variables

    def test_ansible_ip_fallback(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        hosts = _parse_inventory_hosts(SAMPLE_INVENTORY)
        web02 = next(h for h in hosts if h.hostname == "web02")
        assert web02.ip == "192.168.1.11"

    def test_os_fallback(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        hosts = _parse_inventory_hosts(SAMPLE_INVENTORY)
        web02 = next(h for h in hosts if h.hostname == "web02")
        assert web02.os == "CentOS"

    def test_empty_inventory(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        hosts = _parse_inventory_hosts({})
        assert hosts == []

    def test_inventory_with_no_hosts_key(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        data = {"_meta": {"hostvars": {}}, "mygroup": {"vars": {}}}
        hosts = _parse_inventory_hosts(data)
        assert hosts == []

    def test_non_dict_group_data_skipped(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        data = {
            "_meta": {"hostvars": {}},
            "badgroup": "not a dict",
            "listgroup": ["not", "a", "dict"],
        }
        hosts = _parse_inventory_hosts(data)
        assert hosts == []

    def test_duplicate_hosts_deduplicated(self):
        from backend.api.routes.ansible import _parse_inventory_hosts

        data = {
            "_meta": {"hostvars": {"server1": {"ansible_host": "1.2.3.4"}}},
            "group1": {"hosts": ["server1"]},
            "group2": {"hosts": ["server1"]},
        }
        hosts = _parse_inventory_hosts(data)
        assert len(hosts) == 1

    def test_ping_cache_status_reflected(self):
        import backend.api.routes.ansible as mod

        old_cache = mod._ping_cache.copy()
        try:
            mod._ping_cache["testhost"] = {
                "status": "online",
                "last_seen": "2025-01-01T00:00:00",
            }
            data = {
                "_meta": {"hostvars": {"testhost": {}}},
                "grp": {"hosts": ["testhost"]},
            }
            hosts = mod._parse_inventory_hosts(data)
            assert hosts[0].ping_status == "online"
            assert hosts[0].last_seen == "2025-01-01T00:00:00"
        finally:
            mod._ping_cache.clear()
            mod._ping_cache.update(old_cache)


# ===================================================================
# テスト: _count_tasks_in_playbook ヘルパー
# ===================================================================


class TestCountTasksInPlaybook:
    """_count_tasks_in_playbook の分岐テスト"""

    def test_count_tasks(self):
        from backend.api.routes.ansible import _count_tasks_in_playbook

        # "- name:" appears 3 times: play level + 2 tasks
        assert _count_tasks_in_playbook(SAMPLE_PLAYBOOK_YML) == 3

    def test_no_tasks(self):
        from backend.api.routes.ansible import _count_tasks_in_playbook

        assert _count_tasks_in_playbook("---\nhosts: all\n") == 0

    def test_empty_content(self):
        from backend.api.routes.ansible import _count_tasks_in_playbook

        assert _count_tasks_in_playbook("") == 0


# ===================================================================
# テスト: _run_ping_background ヘルパー
# ===================================================================


class TestRunPingBackground:
    """_run_ping_background の全分岐テスト"""

    @pytest.mark.asyncio
    async def test_ping_success_updates_cache(self):
        import backend.api.routes.ansible as mod

        old_cache = mod._ping_cache.copy()
        old_running = mod._ping_running

        mock_result = {
            "status": "success",
            "stdout": "host1 | SUCCESS => {}\nhost2 | UNREACHABLE! => {}",
        }

        try:
            with patch.object(mod, "_run_wrapper", return_value=mock_result), patch.object(
                mod, "audit_log"
            ):
                await mod._run_ping_background("testuser")
            assert mod._ping_cache["host1"]["status"] == "online"
            assert mod._ping_cache["host2"]["status"] == "offline"
            assert mod._ping_running is False
        finally:
            mod._ping_cache.clear()
            mod._ping_cache.update(old_cache)
            mod._ping_running = old_running

    @pytest.mark.asyncio
    async def test_ping_ansible_not_installed(self):
        import backend.api.routes.ansible as mod

        try:
            with patch.object(
                mod,
                "_run_wrapper",
                return_value={"status": "ansible_not_installed"},
            ):
                await mod._run_ping_background("testuser")
            assert mod._ping_running is False
        finally:
            mod._ping_running = False

    @pytest.mark.asyncio
    async def test_ping_error_result(self):
        import backend.api.routes.ansible as mod

        try:
            with patch.object(
                mod,
                "_run_wrapper",
                return_value={"status": "error", "message": "some error"},
            ):
                await mod._run_ping_background("testuser")
            assert mod._ping_running is False
        finally:
            mod._ping_running = False

    @pytest.mark.asyncio
    async def test_ping_exception(self):
        import backend.api.routes.ansible as mod

        try:
            with patch.object(
                mod,
                "_run_wrapper",
                side_effect=RuntimeError("boom"),
            ):
                await mod._run_ping_background("testuser")
            assert mod._ping_running is False
        finally:
            mod._ping_running = False

    @pytest.mark.asyncio
    async def test_ping_online_host_last_seen_updated(self):
        """online ホストの last_seen が更新される"""
        import backend.api.routes.ansible as mod

        old_cache = mod._ping_cache.copy()
        mock_result = {
            "status": "success",
            "stdout": "myhost | SUCCESS => {}",
        }
        try:
            with patch.object(mod, "_run_wrapper", return_value=mock_result), patch.object(
                mod, "audit_log"
            ):
                await mod._run_ping_background("user1")
            assert mod._ping_cache["myhost"]["last_seen"] is not None
        finally:
            mod._ping_cache.clear()
            mod._ping_cache.update(old_cache)

    @pytest.mark.asyncio
    async def test_ping_offline_host_preserves_last_seen(self):
        """offline ホストの last_seen が既存値を保持する"""
        import backend.api.routes.ansible as mod

        old_cache = mod._ping_cache.copy()
        mod._ping_cache["offhost"] = {
            "status": "online",
            "last_seen": "2025-01-01T00:00:00",
        }
        mock_result = {
            "status": "success",
            "stdout": "offhost | UNREACHABLE! => {}",
        }
        try:
            with patch.object(mod, "_run_wrapper", return_value=mock_result), patch.object(
                mod, "audit_log"
            ):
                await mod._run_ping_background("user1")
            assert mod._ping_cache["offhost"]["status"] == "offline"
            assert mod._ping_cache["offhost"]["last_seen"] == "2025-01-01T00:00:00"
        finally:
            mod._ping_cache.clear()
            mod._ping_cache.update(old_cache)


# ===================================================================
# テスト: PlaybookRunRequest バリデーション
# ===================================================================


class TestPlaybookRunRequestValidation:
    """PlaybookRunRequest モデルバリデーション"""

    def test_valid_request(self):
        from backend.api.routes.ansible import PlaybookRunRequest

        req = PlaybookRunRequest(reason="Deploy update")
        assert req.reason == "Deploy update"

    def test_empty_reason_rejected(self):
        from backend.api.routes.ansible import PlaybookRunRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookRunRequest(reason="")

    def test_whitespace_only_reason_rejected(self):
        from backend.api.routes.ansible import PlaybookRunRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlaybookRunRequest(reason="   ")

    def test_reason_stripped(self):
        from backend.api.routes.ansible import PlaybookRunRequest

        req = PlaybookRunRequest(reason="  hello  ")
        assert req.reason == "hello"

    def test_extra_vars_default(self):
        from backend.api.routes.ansible import PlaybookRunRequest

        req = PlaybookRunRequest(reason="test")
        assert req.extra_vars == {}

    def test_extra_vars_provided(self):
        from backend.api.routes.ansible import PlaybookRunRequest

        req = PlaybookRunRequest(reason="test", extra_vars={"env": "prod"})
        assert req.extra_vars == {"env": "prod"}


# ===================================================================
# テスト: GET /api/ansible/inventory エンドポイント
# ===================================================================


class TestInventoryEndpoint:
    """GET /api/ansible/inventory の全分岐テスト"""

    def test_success_with_inventory_data(self, client, admin_headers):
        def mock_wrapper(args, timeout=60):
            return {"stdout": json.dumps(SAMPLE_INVENTORY)}

        with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
            resp = client.get("/api/ansible/inventory", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_hosts"] == 3

    def test_ansible_not_installed(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value=ANSIBLE_NOT_INSTALLED,
        ):
            resp = client.get("/api/ansible/inventory", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ansible_not_installed"

    def test_error_returns_500(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "wrapper failed"},
        ):
            resp = client.get("/api/ansible/inventory", headers=admin_headers)
        assert resp.status_code == 500

    def test_inventory_with_meta_directly(self, client, admin_headers):
        """_meta を直接含む結果（stdout なし）"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value=SAMPLE_INVENTORY,
        ):
            resp = client.get("/api/ansible/inventory", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_inventory_invalid_json_stdout(self, client, admin_headers):
        """stdout が不正 JSON の場合"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"stdout": "not json", "status": "success"},
        ):
            resp = client.get("/api/ansible/inventory", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hosts"] == 0


# ===================================================================
# テスト: GET /api/ansible/hosts エンドポイント
# ===================================================================


class TestHostsEndpoint:
    """GET /api/ansible/hosts の全分岐テスト"""

    def test_success(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"stdout": json.dumps(SAMPLE_INVENTORY)},
        ):
            resp = client.get("/api/ansible/hosts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total"] == 3

    def test_ansible_not_installed(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value=ANSIBLE_NOT_INSTALLED,
        ):
            resp = client.get("/api/ansible/hosts", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ansible_not_installed"

    def test_invalid_json_stdout(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"stdout": "bad json", "status": "success"},
        ):
            resp = client.get("/api/ansible/hosts", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_meta_in_result_directly(self, client, admin_headers):
        """stdout なしで _meta が直接結果に含まれる"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value=SAMPLE_INVENTORY,
        ):
            resp = client.get("/api/ansible/hosts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    def test_online_offline_unknown_counts(self, client, admin_headers):
        import backend.api.routes.ansible as mod

        old = mod._ping_cache.copy()
        try:
            mod._ping_cache["web01"] = {"status": "online", "last_seen": "x"}
            mod._ping_cache["web02"] = {"status": "offline", "last_seen": None}
            with patch(
                "backend.api.routes.ansible._run_wrapper",
                return_value={"stdout": json.dumps(SAMPLE_INVENTORY)},
            ):
                resp = client.get("/api/ansible/hosts", headers=admin_headers)
            data = resp.json()
            assert data["online"] >= 1
            assert data["offline"] >= 1
            assert data["unknown"] >= 0
        finally:
            mod._ping_cache.clear()
            mod._ping_cache.update(old)


# ===================================================================
# テスト: POST /api/ansible/ping エンドポイント
# ===================================================================


class TestPingEndpoint:
    """POST /api/ansible/ping の全分岐テスト"""

    def test_accepted(self, client, admin_headers):
        import backend.api.routes.ansible as mod

        mod._ping_running = False
        resp = client.post("/api/ansible/ping", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("accepted", "already_running")

    def test_already_running(self, client, admin_headers):
        import backend.api.routes.ansible as mod

        old = mod._ping_running
        try:
            mod._ping_running = True
            resp = client.post("/api/ansible/ping", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "already_running"
        finally:
            mod._ping_running = old

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/ansible/ping", headers=viewer_headers)
        assert resp.status_code == 403


# ===================================================================
# テスト: GET /api/ansible/playbooks エンドポイント
# ===================================================================


class TestPlaybooksEndpoint:
    """GET /api/ansible/playbooks の全分岐テスト"""

    def test_no_directory(self, client, admin_headers):
        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = False
            mock_path.return_value = mock_dir
            resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_with_playbook_files(self, client, admin_headers, tmp_path):
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        (pb_dir / "deploy.yml").write_text(SAMPLE_PLAYBOOK_YML)
        (pb_dir / "backup.yml").write_text("---\n- name: Backup\n  hosts: all\n  tasks:\n    - name: Run backup\n      command: echo ok\n")

        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = sorted(pb_dir.glob("*.yml"))
            mock_path.return_value = mock_dir
            resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_playbook_with_comment_description(self, client, admin_headers, tmp_path):
        """先頭コメント行から description を抽出"""
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        (pb_dir / "test.yml").write_text("# My description\n- name: Test\n  hosts: all\n  tasks:\n    - name: Do something\n      command: echo hi\n")

        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = sorted(pb_dir.glob("*.yml"))
            mock_path.return_value = mock_dir
            resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        pbs = resp.json()["playbooks"]
        assert len(pbs) == 1
        assert pbs[0]["description"] == "My description"

    def test_playbook_no_comment(self, client, admin_headers, tmp_path):
        """コメント行なし -> description 空"""
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        (pb_dir / "nodesc.yml").write_text("---\n- name: No desc\n  hosts: all\n  tasks:\n    - name: Task1\n      command: echo\n")

        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = sorted(pb_dir.glob("*.yml"))
            mock_path.return_value = mock_dir
            resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        pbs = resp.json()["playbooks"]
        assert pbs[0]["description"] == ""

    def test_playbook_read_error_skipped(self, client, admin_headers, tmp_path):
        """ファイル読み込みエラーはスキップ"""
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()

        mock_yml = MagicMock(spec=Path)
        mock_yml.name = "broken.yml"
        mock_yml.read_text.side_effect = PermissionError("denied")

        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = [mock_yml]
            mock_path.return_value = mock_dir
            with patch("backend.api.routes.ansible._PLAYBOOK_NAME_PATTERN") as mock_pat:
                mock_pat.match.return_value = True
                resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_unsafe_playbook_name_skipped(self, client, admin_headers, tmp_path):
        """安全でないファイル名はスキップ"""
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        # ファイル名に空白（パターン不一致）
        bad_file = pb_dir / "bad file.yml"
        bad_file.write_text("---\n")

        with patch("backend.api.routes.ansible.Path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = [bad_file]
            mock_path.return_value = mock_dir
            resp = client.get("/api/ansible/playbooks", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ===================================================================
# テスト: GET /api/ansible/playbooks/{name} エンドポイント
# ===================================================================


class TestPlaybookContentEndpoint:
    """GET /api/ansible/playbooks/{name} の全分岐テスト"""

    def test_success(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "success", "stdout": SAMPLE_PLAYBOOK_YML},
        ):
            resp = client.get("/api/ansible/playbooks/deploy.yml", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "deploy.yml"

    def test_ansible_not_installed(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value=ANSIBLE_NOT_INSTALLED,
        ):
            resp = client.get("/api/ansible/playbooks/deploy.yml", headers=admin_headers)
        assert resp.status_code == 503

    def test_not_found(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "Playbook not found"},
        ):
            resp = client.get("/api/ansible/playbooks/missing.yml", headers=admin_headers)
        assert resp.status_code == 404

    def test_generic_error(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "Internal error"},
        ):
            resp = client.get("/api/ansible/playbooks/deploy.yml", headers=admin_headers)
        assert resp.status_code == 500

    def test_invalid_name(self, client, admin_headers):
        resp = client.get("/api/ansible/playbooks/bad;name.yml", headers=admin_headers)
        assert resp.status_code in (400, 422)


# ===================================================================
# テスト: POST /api/ansible/playbooks/{name}/run エンドポイント
# ===================================================================


class TestPlaybookRunEndpoint:
    """POST /api/ansible/playbooks/{name}/run の全分岐テスト"""

    def test_success(self, client, admin_headers):
        async def mock_create(**kwargs):
            return {"request_id": "req-123", "status": "pending"}

        mock_approval = MagicMock()
        mock_approval.create_request = mock_create

        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "success", "stdout": SAMPLE_PLAYBOOK_YML},
        ), patch("backend.api.routes.ansible._approval_service", mock_approval):
            resp = client.post(
                "/api/ansible/playbooks/deploy.yml/run",
                json={"reason": "Deploy update"},
                headers=admin_headers,
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending_approval"
        assert data["request_id"] == "req-123"

    def test_playbook_not_found(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "not found"},
        ):
            resp = client.post(
                "/api/ansible/playbooks/ghost.yml/run",
                json={"reason": "test"},
                headers=admin_headers,
            )
        assert resp.status_code == 404

    def test_approval_service_exception(self, client, admin_headers):
        async def mock_create(**kwargs):
            raise RuntimeError("DB error")

        mock_approval = MagicMock()
        mock_approval.create_request = mock_create

        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "success", "stdout": "ok"},
        ), patch("backend.api.routes.ansible._approval_service", mock_approval):
            resp = client.post(
                "/api/ansible/playbooks/deploy.yml/run",
                json={"reason": "Deploy"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post(
            "/api/ansible/playbooks/deploy.yml/run",
            json={"reason": "test"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_invalid_name(self, client, admin_headers):
        resp = client.post(
            "/api/ansible/playbooks/bad!name.yml/run",
            json={"reason": "test"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_empty_reason(self, client, admin_headers):
        resp = client.post(
            "/api/ansible/playbooks/deploy.yml/run",
            json={"reason": ""},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_with_extra_vars(self, client, admin_headers):
        async def mock_create(**kwargs):
            return {"request_id": "req-456", "status": "pending"}

        mock_approval = MagicMock()
        mock_approval.create_request = mock_create

        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "success", "stdout": "ok"},
        ), patch("backend.api.routes.ansible._approval_service", mock_approval):
            resp = client.post(
                "/api/ansible/playbooks/deploy.yml/run",
                json={"reason": "Deploy", "extra_vars": {"env": "staging"}},
                headers=admin_headers,
            )
        assert resp.status_code == 202

    def test_check_result_non_not_found_error(self, client, admin_headers):
        """show-playbook がエラーだが 'not found' を含まない場合"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "permission denied"},
        ):
            # エラーだが "not found" を含まないので 404 にならない
            # 次に approval_service.create_request に進む
            async def mock_create(**kwargs):
                return {"request_id": "req-789", "status": "pending"}

            mock_approval = MagicMock()
            mock_approval.create_request = mock_create

            with patch("backend.api.routes.ansible._approval_service", mock_approval):
                resp = client.post(
                    "/api/ansible/playbooks/deploy.yml/run",
                    json={"reason": "test run"},
                    headers=admin_headers,
                )
            assert resp.status_code == 202


# ===================================================================
# テスト: GET /api/ansible/history エンドポイント
# ===================================================================


class TestHistoryEndpoint:
    """GET /api/ansible/history の全分岐テスト"""

    def test_no_audit_dir(self, client, admin_headers, tmp_path):
        with patch("backend.api.routes.ansible.settings") as mock_settings:
            mock_settings.logging.file = str(tmp_path / "app.log")
            resp = client.get("/api/ansible/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_with_audit_logs(self, client, admin_headers, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        log_file = audit_dir / "audit_20250101.json"
        entries = [
            json.dumps({
                "timestamp": "2025-01-01T10:00:00",
                "operation": "ansible_playbook_run_requested",
                "user_id": "admin",
                "target": "deploy.yml",
                "status": "pending",
                "details": {},
            }),
            json.dumps({
                "timestamp": "2025-01-01T09:00:00",
                "operation": "ansible_ping_all",
                "user_id": "admin",
                "target": "all",
                "status": "success",
                "details": {},
            }),
            json.dumps({
                "timestamp": "2025-01-01T08:00:00",
                "operation": "service_restart",  # non-ansible, should be skipped
                "user_id": "admin",
                "target": "nginx",
                "status": "success",
                "details": {},
            }),
            "",  # empty line
            "bad json line",  # invalid JSON
        ]
        log_file.write_text("\n".join(entries))

        with patch("backend.api.routes.ansible.settings") as mock_settings:
            mock_settings.logging.file = str(tmp_path / "app.log")
            resp = client.get("/api/ansible/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # 2 ansible entries
        assert data["count"] == 2

    def test_history_limit_clamped(self, client, admin_headers, tmp_path):
        """limit < 1 or > 500 は 50 にリセット"""
        with patch("backend.api.routes.ansible.settings") as mock_settings:
            mock_settings.logging.file = str(tmp_path / "app.log")
            resp = client.get("/api/ansible/history?limit=0", headers=admin_headers)
        assert resp.status_code == 200

        with patch("backend.api.routes.ansible.settings") as mock_settings:
            mock_settings.logging.file = str(tmp_path / "app.log")
            resp = client.get("/api/ansible/history?limit=9999", headers=admin_headers)
        assert resp.status_code == 200

    def test_history_log_read_error(self, client, admin_headers, tmp_path):
        """監査ログ読み込みエラーはスキップ"""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        mock_log_file = MagicMock()
        mock_log_file.read_text.side_effect = PermissionError("denied")

        with patch("backend.api.routes.ansible.settings") as mock_settings:
            mock_settings.logging.file = str(tmp_path / "app.log")
            # log_dir.exists() -> True, log_dir.glob() -> [mock_log_file]
            real_path = Path
            def path_side(p):
                result = real_path(p)
                return result

            with patch("backend.api.routes.ansible.Path") as mock_path_cls:
                mock_log_dir = MagicMock()
                mock_log_dir.exists.return_value = True
                mock_log_dir.glob.return_value = [mock_log_file]

                # settings.logging.file -> parent -> / "audit"
                mock_file_path = MagicMock()
                mock_file_path.parent.__truediv__ = lambda self, x: mock_log_dir

                mock_path_cls.side_effect = lambda x: mock_file_path
                resp = client.get("/api/ansible/history", headers=admin_headers)
        assert resp.status_code == 200


# ===================================================================
# テスト: POST /api/ansible/playbooks/{name}/validate エンドポイント
# ===================================================================


class TestValidateEndpoint:
    """POST /api/ansible/playbooks/{name}/validate の全分岐テスト"""

    def test_success(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "success", "message": "Syntax OK", "stdout": ""},
        ):
            resp = client.post("/api/ansible/playbooks/site.yml/validate", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["playbook"] == "site.yml"

    def test_not_found(self, client, admin_headers):
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "not found", "stdout": ""},
        ):
            resp = client.post("/api/ansible/playbooks/ghost.yml/validate", headers=admin_headers)
        assert resp.status_code == 404

    def test_error_but_not_not_found(self, client, admin_headers):
        """エラーだが 'not found' を含まない"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"status": "error", "message": "lint error", "stdout": "warnings..."},
        ):
            resp = client.post("/api/ansible/playbooks/site.yml/validate", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_invalid_name(self, client, admin_headers):
        resp = client.post("/api/ansible/playbooks/bad;name.yml/validate", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_unknown_status(self, client, admin_headers):
        """status が含まれない場合は 'unknown'"""
        with patch(
            "backend.api.routes.ansible._run_wrapper",
            return_value={"stdout": "output", "message": ""},
        ):
            resp = client.post("/api/ansible/playbooks/site.yml/validate", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unknown"
