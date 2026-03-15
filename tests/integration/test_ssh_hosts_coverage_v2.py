"""SSH ホスト管理API カバレッジ向上テスト v2

ssh_hosts.py の全分岐を網羅的にテスト:
- バリデーション関数 (_validate_hostname, _validate_username, etc.)
- データ永続化ヘルパー (_load_hosts, _save_hosts, _find_host)
- 全エンドポイントの正常系/異常系/エッジケース
- Pydantic field_validator
- 接続テスト (socket mock)
- トンネル一覧 (psutil mock)
- 鍵ペア生成 (承認フロー mock)
"""

import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# テスト用データファイルパス
_TEST_DATA_FILE = Path("/tmp") / f"ssh_hosts_v2_test_{os.getpid()}.json"


@pytest.fixture(autouse=True)
def clean_data_file():
    """各テスト前後にデータファイルをクリア & モジュールのパスを差し替え"""
    import backend.api.routes.ssh_hosts as mod

    orig = mod._DATA_FILE
    mod._DATA_FILE = _TEST_DATA_FILE
    if _TEST_DATA_FILE.exists():
        _TEST_DATA_FILE.unlink()
    yield
    if _TEST_DATA_FILE.exists():
        _TEST_DATA_FILE.unlink()
    mod._DATA_FILE = orig


# =====================================================================
# バリデーション関数テスト
# =====================================================================


class TestValidateHostname:
    """_validate_hostname の全分岐"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.ssh_hosts import _validate_hostname
        self.fn = _validate_hostname

    @pytest.mark.parametrize("hostname", [
        "192.168.1.1",
        "10.0.0.1",
        "255.255.255.255",
        "0.0.0.0",
    ])
    def test_valid_ipv4(self, hostname):
        assert self.fn(hostname) == hostname

    @pytest.mark.parametrize("hostname", [
        "::1",
        "fe80::1",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "::",
    ])
    def test_valid_ipv6(self, hostname):
        assert self.fn(hostname) == hostname

    @pytest.mark.parametrize("hostname", [
        "example.com",
        "server-01.example.com",
        "a",
        "my-host",
    ])
    def test_valid_rfc1123(self, hostname):
        assert self.fn(hostname) == hostname

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            self.fn("")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            self.fn("a" * 254)

    @pytest.mark.parametrize("hostname", [
        "host name",
        "host;cmd",
        "host|pipe",
        "-starts-with-dash.com",
    ])
    def test_invalid_hostname_raises(self, hostname):
        with pytest.raises(ValueError):
            self.fn(hostname)


class TestValidateUsername:
    """_validate_username の全分岐"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.ssh_hosts import _validate_username
        self.fn = _validate_username

    @pytest.mark.parametrize("username", [
        "ubuntu", "ec2-user", "root", "user_123", "a", "A", "a" * 32,
    ])
    def test_valid(self, username):
        assert self.fn(username) == username

    @pytest.mark.parametrize("username", [
        "", "bad user", "user;cmd", "a" * 33, "user@host",
    ])
    def test_invalid(self, username):
        with pytest.raises(ValueError):
            self.fn(username)


class TestValidateDisplayName:
    """_validate_display_name の全分岐"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.ssh_hosts import _validate_display_name
        self.fn = _validate_display_name

    @pytest.mark.parametrize("name", [
        "my-server", "Server 01", "prod.web", "a_b-c.d 1",
    ])
    def test_valid(self, name):
        assert self.fn(name) == name

    @pytest.mark.parametrize("name", [
        "", "bad;name", "name<tag>", "a" * 65,
    ])
    def test_invalid(self, name):
        with pytest.raises(ValueError):
            self.fn(name)


class TestValidateKeyName:
    """_validate_key_name の全分岐"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.ssh_hosts import _validate_key_name
        self.fn = _validate_key_name

    def test_none_returns_none(self):
        assert self.fn(None) is None

    def test_empty_returns_none(self):
        assert self.fn("") is None

    @pytest.mark.parametrize("key_name", [
        "id_ed25519", "id_rsa.pub", "my-key_123",
    ])
    def test_valid(self, key_name):
        assert self.fn(key_name) == key_name

    @pytest.mark.parametrize("key_name", [
        "../../etc/passwd", "key name", "key;cmd",
    ])
    def test_invalid(self, key_name):
        with pytest.raises(ValueError):
            self.fn(key_name)


# =====================================================================
# データ永続化ヘルパーテスト
# =====================================================================


class TestLoadHosts:
    """_load_hosts の全分岐"""

    def test_file_not_exists_returns_empty(self):
        from backend.api.routes.ssh_hosts import _load_hosts
        result = _load_hosts()
        assert result == []

    def test_valid_json_list(self):
        from backend.api.routes.ssh_hosts import _load_hosts
        data = [{"id": "abc", "name": "test"}]
        _TEST_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_DATA_FILE.write_text(json.dumps(data), encoding="utf-8")
        result = _load_hosts()
        assert result == data

    def test_json_is_dict_returns_empty(self):
        """JSON が辞書の場合は空リストを返す"""
        from backend.api.routes.ssh_hosts import _load_hosts
        _TEST_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_DATA_FILE.write_text('{"key": "value"}', encoding="utf-8")
        result = _load_hosts()
        assert result == []

    def test_invalid_json_returns_empty(self):
        from backend.api.routes.ssh_hosts import _load_hosts
        _TEST_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_DATA_FILE.write_text("not json!", encoding="utf-8")
        result = _load_hosts()
        assert result == []


class TestSaveHosts:
    """_save_hosts の全分岐"""

    def test_save_and_reload(self):
        from backend.api.routes.ssh_hosts import _load_hosts, _save_hosts
        data = [{"id": "x", "name": "host1"}]
        _save_hosts(data)
        result = _load_hosts()
        assert result == data

    def test_creates_parent_dir(self):
        import backend.api.routes.ssh_hosts as mod
        orig = mod._DATA_FILE
        new_path = Path("/tmp") / f"ssh_v2_subdir_{os.getpid()}" / "hosts.json"
        mod._DATA_FILE = new_path
        try:
            mod._save_hosts([{"id": "y"}])
            assert new_path.exists()
        finally:
            if new_path.exists():
                new_path.unlink()
            if new_path.parent.exists():
                new_path.parent.rmdir()
            mod._DATA_FILE = orig


class TestFindHost:
    """_find_host の全分岐"""

    def test_found(self):
        from backend.api.routes.ssh_hosts import _find_host, _save_hosts
        hid = str(uuid.uuid4())
        _save_hosts([{"id": hid, "name": "found-host"}])
        result = _find_host(hid)
        assert result is not None
        assert result["name"] == "found-host"

    def test_not_found(self):
        from backend.api.routes.ssh_hosts import _find_host
        result = _find_host(str(uuid.uuid4()))
        assert result is None


# =====================================================================
# エンドポイント: GET / (一覧)
# =====================================================================


class TestListHostsV2:
    """GET /api/ssh-hosts/ 追加テスト"""

    def test_empty_list(self, test_client, admin_headers):
        resp = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["hosts"] == []
        assert body["status"] == "success"
        assert "timestamp" in body

    def test_list_with_data(self, test_client, admin_headers):
        """ホスト登録後に一覧に含まれる"""
        test_client.post("/api/ssh-hosts/", json={
            "name": "list-test-host", "hostname": "10.0.0.1", "port": 22, "username": "user",
        }, headers=admin_headers)
        resp = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/ssh-hosts/")
        assert resp.status_code == 403


# =====================================================================
# エンドポイント: POST / (登録)
# =====================================================================


class TestCreateHostV2:
    """POST /api/ssh-hosts/ 追加テスト"""

    def test_create_minimal(self, test_client, admin_headers):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "min-host", "hostname": "10.0.0.2", "port": 22, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 201
        host = resp.json()["host"]
        assert host["key_name"] is None
        assert host["bastion_host"] is None
        assert host["description"] == ""

    def test_create_with_all_fields(self, test_client, admin_headers):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "full-host",
            "hostname": "192.168.1.100",
            "port": 2222,
            "username": "deploy",
            "key_name": "id_ed25519",
            "description": "Full featured host",
        }, headers=admin_headers)
        assert resp.status_code == 201
        host = resp.json()["host"]
        assert host["port"] == 2222
        assert host["key_name"] == "id_ed25519"
        assert host["description"] == "Full featured host"

    def test_create_with_bastion(self, test_client, admin_headers):
        """踏み台ホスト指定での登録"""
        # まず踏み台を登録
        r1 = test_client.post("/api/ssh-hosts/", json={
            "name": "bastion-v2", "hostname": "10.0.0.10", "port": 22, "username": "bastion",
        }, headers=admin_headers)
        bastion_id = r1.json()["host"]["id"]

        r2 = test_client.post("/api/ssh-hosts/", json={
            "name": "behind-bastion", "hostname": "10.0.1.1", "port": 22,
            "username": "user", "bastion_host": bastion_id,
        }, headers=admin_headers)
        assert r2.status_code == 201
        assert r2.json()["host"]["bastion_host"] == bastion_id

    def test_create_bastion_not_found(self, test_client, admin_headers):
        """存在しない踏み台ホストIDは404"""
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "bad-bastion", "hostname": "10.0.0.11", "port": 22,
            "username": "user", "bastion_host": str(uuid.uuid4()),
        }, headers=admin_headers)
        assert resp.status_code == 404

    def test_create_duplicate_name(self, test_client, admin_headers):
        test_client.post("/api/ssh-hosts/", json={
            "name": "dup-v2", "hostname": "10.0.0.3", "port": 22, "username": "user",
        }, headers=admin_headers)
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "dup-v2", "hostname": "10.0.0.4", "port": 22, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 409

    @pytest.mark.parametrize("bad_hostname", [
        "host;cmd", "host | pipe", "", "a" * 254,
    ])
    def test_create_invalid_hostname(self, test_client, admin_headers, bad_hostname):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": f"bad-{bad_hostname[:5]}", "hostname": bad_hostname,
            "port": 22, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 422

    @pytest.mark.parametrize("bad_username", [
        "bad user", "user;cmd", "",
    ])
    def test_create_invalid_username(self, test_client, admin_headers, bad_username):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "bad-user-test", "hostname": "10.0.0.5",
            "port": 22, "username": bad_username,
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_create_invalid_bastion_uuid(self, test_client, admin_headers):
        """bastion_host が UUID 形式でない場合 422"""
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "bad-bastion-fmt", "hostname": "10.0.0.6",
            "port": 22, "username": "user", "bastion_host": "not-a-uuid",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_create_bastion_empty_string_is_none(self, test_client, admin_headers):
        """bastion_host が空文字列の場合 None として扱う"""
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "empty-bastion", "hostname": "10.0.0.7",
            "port": 22, "username": "user", "bastion_host": "",
        }, headers=admin_headers)
        assert resp.status_code == 201
        assert resp.json()["host"]["bastion_host"] is None

    def test_viewer_cannot_create(self, test_client, viewer_headers):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "no-write", "hostname": "10.0.0.8",
            "port": 22, "username": "user",
        }, headers=viewer_headers)
        assert resp.status_code == 403


# =====================================================================
# エンドポイント: PUT /{id} (更新)
# =====================================================================


class TestUpdateHostV2:
    """PUT /api/ssh-hosts/{id} 追加テスト"""

    def _create(self, client, headers, name="upd-target"):
        r = client.post("/api/ssh-hosts/", json={
            "name": name, "hostname": "172.16.0.1", "port": 22, "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_update_single_field(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "upd-single")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={"port": 3333}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["host"]["port"] == 3333

    def test_update_multiple_fields(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "upd-multi")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={
            "hostname": "172.16.0.2", "username": "newuser", "description": "updated",
        }, headers=admin_headers)
        assert resp.status_code == 200
        host = resp.json()["host"]
        assert host["hostname"] == "172.16.0.2"
        assert host["username"] == "newuser"

    def test_update_name_duplicate_rejected(self, test_client, admin_headers):
        """他のホストと同名に更新しようとすると409"""
        self._create(test_client, admin_headers, "existing-name")
        hid = self._create(test_client, admin_headers, "other-name")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={"name": "existing-name"}, headers=admin_headers)
        assert resp.status_code == 409

    def test_update_name_same_as_self_ok(self, test_client, admin_headers):
        """自分自身の名前に更新はOK"""
        hid = self._create(test_client, admin_headers, "self-name")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={"name": "self-name"}, headers=admin_headers)
        assert resp.status_code == 200

    def test_update_bastion_self_reference(self, test_client, admin_headers):
        """自分自身を踏み台に設定は400"""
        hid = self._create(test_client, admin_headers, "self-bastion")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={"bastion_host": hid}, headers=admin_headers)
        assert resp.status_code == 400

    def test_update_bastion_not_found(self, test_client, admin_headers):
        """存在しない踏み台ホストIDで更新は404"""
        hid = self._create(test_client, admin_headers, "bastion-missing")
        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={
            "bastion_host": str(uuid.uuid4()),
        }, headers=admin_headers)
        assert resp.status_code == 404

    def test_update_not_found(self, test_client, admin_headers):
        resp = test_client.put(f"/api/ssh-hosts/{uuid.uuid4()}", json={"port": 22}, headers=admin_headers)
        assert resp.status_code == 404

    def test_update_invalid_uuid(self, test_client, admin_headers):
        resp = test_client.put("/api/ssh-hosts/not-uuid", json={"port": 22}, headers=admin_headers)
        assert resp.status_code == 400


# =====================================================================
# エンドポイント: DELETE /{id} (削除)
# =====================================================================


class TestDeleteHostV2:
    """DELETE /api/ssh-hosts/{id} 追加テスト"""

    def _create(self, client, headers, name):
        r = client.post("/api/ssh-hosts/", json={
            "name": name, "hostname": "172.16.1.1", "port": 22, "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_delete_success(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "del-v2")
        resp = test_client.delete(f"/api/ssh-hosts/{hid}", headers=admin_headers)
        assert resp.status_code == 204

    def test_delete_not_found(self, test_client, admin_headers):
        resp = test_client.delete(f"/api/ssh-hosts/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 404

    def test_delete_invalid_uuid(self, test_client, admin_headers):
        resp = test_client.delete("/api/ssh-hosts/bad-id", headers=admin_headers)
        assert resp.status_code == 400

    def test_delete_bastion_in_use(self, test_client, admin_headers):
        """踏み台として使用中のホスト削除は409"""
        bastion_id = self._create(test_client, admin_headers, "bastion-del")
        test_client.post("/api/ssh-hosts/", json={
            "name": "dep-host-del", "hostname": "10.0.0.20", "port": 22,
            "username": "user", "bastion_host": bastion_id,
        }, headers=admin_headers)
        resp = test_client.delete(f"/api/ssh-hosts/{bastion_id}", headers=admin_headers)
        assert resp.status_code == 409


# =====================================================================
# エンドポイント: POST /{id}/test-connection (接続テスト)
# =====================================================================


class TestConnectionTestV2:
    """POST /api/ssh-hosts/{id}/test-connection 追加テスト"""

    def _create(self, client, headers, name, hostname="10.0.0.50"):
        r = client.post("/api/ssh-hosts/", json={
            "name": name, "hostname": hostname, "port": 22, "username": "user",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    @patch("backend.api.routes.ssh_hosts.socket.create_connection")
    def test_reachable(self, mock_conn, test_client, admin_headers):
        """接続成功"""
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        hid = self._create(test_client, admin_headers, "reach-test")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/test-connection", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is True
        assert body["latency_ms"] is not None
        assert body["error"] is None

    @patch("backend.api.routes.ssh_hosts.socket.create_connection")
    def test_timeout(self, mock_conn, test_client, admin_headers):
        """タイムアウト"""
        import socket as _socket
        mock_conn.side_effect = _socket.timeout("timed out")
        hid = self._create(test_client, admin_headers, "timeout-test")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/test-connection", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert "タイムアウト" in body["error"]

    @patch("backend.api.routes.ssh_hosts.socket.create_connection")
    def test_connection_refused(self, mock_conn, test_client, admin_headers):
        """接続拒否"""
        mock_conn.side_effect = ConnectionRefusedError("refused")
        hid = self._create(test_client, admin_headers, "refused-test")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/test-connection", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert "接続拒否" in body["error"]

    @patch("backend.api.routes.ssh_hosts.socket.create_connection")
    def test_os_error(self, mock_conn, test_client, admin_headers):
        """OSError"""
        mock_conn.side_effect = OSError("network unreachable")
        hid = self._create(test_client, admin_headers, "oserror-test")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/test-connection", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert "network unreachable" in body["error"]

    def test_not_found(self, test_client, admin_headers):
        resp = test_client.post(f"/api/ssh-hosts/{uuid.uuid4()}/test-connection", headers=admin_headers)
        assert resp.status_code == 404

    def test_invalid_uuid(self, test_client, admin_headers):
        resp = test_client.post("/api/ssh-hosts/bad-uuid/test-connection", headers=admin_headers)
        assert resp.status_code == 400


# =====================================================================
# エンドポイント: GET /tunnels (アクティブトンネル)
# =====================================================================


class TestActiveTunnelsV2:
    """GET /api/ssh-hosts/tunnels 追加テスト"""

    def test_empty_tunnels(self, test_client, admin_headers):
        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["tunnels"] == []
        assert resp.json()["count"] == 0

    def test_with_ssh_process(self, test_client, admin_headers):
        """SSH プロセスが存在する場合"""
        mock_laddr = MagicMock(ip="127.0.0.1", port=8080)
        mock_raddr = MagicMock(ip="10.0.0.1", port=22)
        mock_conn = MagicMock(laddr=mock_laddr, raddr=mock_raddr, status="ESTABLISHED")

        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 12345,
            "name": "ssh",
            "cmdline": ["ssh", "-L", "8080:10.0.0.1:22", "user@10.0.0.1"],
        }
        mock_proc.connections.return_value = [mock_conn]

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        tunnels = resp.json()["tunnels"]
        assert len(tunnels) == 1
        assert tunnels[0]["pid"] == 12345
        assert tunnels[0]["local_port"] == 8080
        assert tunnels[0]["remote_port"] == 22

    def test_non_ssh_process_skipped(self, test_client, admin_headers):
        """SSH以外のプロセスはスキップ"""
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 100, "name": "nginx", "cmdline": ["nginx"]}

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_connection_without_raddr_skipped(self, test_client, admin_headers):
        """raddr がない接続はスキップ"""
        mock_conn = MagicMock(laddr=MagicMock(ip="127.0.0.1", port=8080), raddr=None)

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 200, "name": "ssh", "cmdline": ["ssh"]}
        mock_proc.connections.return_value = [mock_conn]

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_connection_without_laddr_skipped(self, test_client, admin_headers):
        """laddr がない接続はスキップ"""
        mock_conn = MagicMock(laddr=None, raddr=MagicMock(ip="10.0.0.1", port=22))

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 300, "name": "ssh", "cmdline": ["ssh"]}
        mock_proc.connections.return_value = [mock_conn]

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_no_such_process_handled(self, test_client, admin_headers):
        """NoSuchProcess が発生してもエラーにならない"""
        import psutil as _psutil

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 400, "name": "ssh", "cmdline": ["ssh"]}
        mock_proc.connections.side_effect = _psutil.NoSuchProcess(400)

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_access_denied_handled(self, test_client, admin_headers):
        """AccessDenied が発生してもエラーにならない"""
        import psutil as _psutil

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 500, "name": "ssh", "cmdline": ["ssh"]}
        mock_proc.connections.side_effect = _psutil.AccessDenied(500)

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_process_iter_exception(self, test_client, admin_headers):
        """process_iter 自体がエラーでも正常応答"""
        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", side_effect=RuntimeError("psutil fail")):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_name_none_skipped(self, test_client, admin_headers):
        """プロセス名がNoneの場合スキップ"""
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 600, "name": None, "cmdline": None}

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_cmdline_none_handled(self, test_client, admin_headers):
        """cmdline がNoneでも空文字で処理"""
        mock_laddr = MagicMock(ip="127.0.0.1", port=9090)
        mock_raddr = MagicMock(ip="10.0.0.2", port=22)
        mock_conn = MagicMock(laddr=mock_laddr, raddr=mock_raddr, status="ESTABLISHED")

        mock_proc = MagicMock()
        mock_proc.info = {"pid": 700, "name": "ssh", "cmdline": None}
        mock_proc.connections.return_value = [mock_conn]

        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[mock_proc]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# =====================================================================
# エンドポイント: POST /{id}/generate-keypair (鍵ペア生成)
# =====================================================================


class TestGenerateKeypairV2:
    """POST /api/ssh-hosts/{id}/generate-keypair 追加テスト"""

    def _create(self, client, headers, name):
        r = client.post("/api/ssh-hosts/", json={
            "name": name, "hostname": "192.168.50.1", "port": 22, "username": "user",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_success_ed25519(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-ed")
        with patch("backend.api.routes.ssh_hosts._approval_service") as mock_svc:
            mock_svc.create_request = AsyncMock(return_value={"request_id": "req-ed"})
            resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
                "key_type": "ed25519", "reason": "Testing ed25519 key generation",
            }, headers=admin_headers)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert body["request_id"] == "req-ed"

    def test_success_rsa(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-rsa")
        with patch("backend.api.routes.ssh_hosts._approval_service") as mock_svc:
            mock_svc.create_request = AsyncMock(return_value={"request_id": "req-rsa"})
            resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
                "key_type": "rsa", "reason": "Testing RSA key generation",
            }, headers=admin_headers)
        assert resp.status_code == 202

    def test_success_with_comment(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-comment")
        with patch("backend.api.routes.ssh_hosts._approval_service") as mock_svc:
            mock_svc.create_request = AsyncMock(return_value={"request_id": "req-c"})
            resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
                "key_type": "ed25519",
                "key_comment": "user@example.com",
                "reason": "Testing with custom comment",
            }, headers=admin_headers)
        assert resp.status_code == 202

    def test_invalid_key_type(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-bad-type")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
            "key_type": "dsa", "reason": "Should fail validation",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_invalid_key_comment(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-bad-comment")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
            "key_type": "ed25519",
            "key_comment": "bad comment with spaces!",
            "reason": "Should fail comment validation",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_reason_required(self, test_client, admin_headers):
        hid = self._create(test_client, admin_headers, "keygen-no-reason")
        resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
            "key_type": "ed25519",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_host_not_found(self, test_client, admin_headers):
        resp = test_client.post(f"/api/ssh-hosts/{uuid.uuid4()}/generate-keypair", json={
            "key_type": "ed25519", "reason": "Host does not exist",
        }, headers=admin_headers)
        assert resp.status_code == 404

    def test_invalid_uuid(self, test_client, admin_headers):
        resp = test_client.post("/api/ssh-hosts/bad-id/generate-keypair", json={
            "key_type": "ed25519", "reason": "Bad UUID format",
        }, headers=admin_headers)
        assert resp.status_code == 400

    def test_lookup_error_fallback(self, test_client, admin_headers):
        """承認ポリシー未登録時のLookupErrorフォールバック"""
        hid = self._create(test_client, admin_headers, "keygen-lookup")
        with patch("backend.api.routes.ssh_hosts._approval_service") as mock_svc:
            mock_svc.create_request = AsyncMock(side_effect=LookupError("no policy"))
            resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
                "key_type": "ed25519", "reason": "Testing LookupError fallback",
            }, headers=admin_headers)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        # request_id は UUID フォールバック
        assert len(body["request_id"]) > 0

    def test_approval_returns_non_dict(self, test_client, admin_headers):
        """approval_service.create_request が dict でない場合"""
        hid = self._create(test_client, admin_headers, "keygen-nondict")
        with patch("backend.api.routes.ssh_hosts._approval_service") as mock_svc:
            mock_svc.create_request = AsyncMock(return_value="some-string-id")
            resp = test_client.post(f"/api/ssh-hosts/{hid}/generate-keypair", json={
                "key_type": "ed25519", "reason": "Testing non-dict return",
            }, headers=admin_headers)
        assert resp.status_code == 202


# =====================================================================
# Pydantic モデル バリデーション追加テスト
# =====================================================================


class TestPydanticModelsV2:
    """Pydantic モデルのバリデーション追加テスト"""

    def test_ssh_host_create_port_range(self, test_client, admin_headers):
        """ポート範囲外"""
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "port-test", "hostname": "10.0.0.1",
            "port": 0, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 422

        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "port-test", "hostname": "10.0.0.1",
            "port": 65536, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_ssh_host_create_name_too_long(self, test_client, admin_headers):
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "a" * 65, "hostname": "10.0.0.1",
            "port": 22, "username": "user",
        }, headers=admin_headers)
        assert resp.status_code == 422

    def test_ssh_host_update_none_fields_ignored(self, test_client, admin_headers):
        """SSHHostUpdate で None フィールドは更新されない"""
        r = test_client.post("/api/ssh-hosts/", json={
            "name": "no-change", "hostname": "10.0.0.99",
            "port": 22, "username": "user", "description": "original",
        }, headers=admin_headers)
        assert r.status_code == 201
        hid = r.json()["host"]["id"]

        resp = test_client.put(f"/api/ssh-hosts/{hid}", json={"port": 3000}, headers=admin_headers)
        assert resp.status_code == 200
        host = resp.json()["host"]
        assert host["port"] == 3000
        assert host["description"] == "original"  # not changed

    def test_keypair_key_comment_valid_chars(self):
        """KeypairGenerateRequest の key_comment バリデーション"""
        from backend.api.routes.ssh_hosts import KeypairGenerateRequest

        req = KeypairGenerateRequest(key_type="ed25519", key_comment="user@host.com", reason="test")
        assert req.key_comment == "user@host.com"

    def test_keypair_empty_comment_allowed(self):
        from backend.api.routes.ssh_hosts import KeypairGenerateRequest
        req = KeypairGenerateRequest(key_type="ed25519", key_comment="", reason="test")
        assert req.key_comment == ""
