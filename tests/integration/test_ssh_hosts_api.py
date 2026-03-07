"""
SSH 踏み台・接続先ホスト管理 API - 統合テスト (20件以上)

テスト対象エンドポイント:
  GET    /api/ssh-hosts/                       - ホスト一覧
  POST   /api/ssh-hosts/                       - ホスト登録
  PUT    /api/ssh-hosts/{id}                   - ホスト更新
  DELETE /api/ssh-hosts/{id}                   - ホスト削除
  POST   /api/ssh-hosts/{id}/test-connection   - 接続テスト
  GET    /api/ssh-hosts/tunnels                - アクティブトンネル
  POST   /api/ssh-hosts/{id}/generate-keypair  - 鍵ペア生成 (承認フロー)
"""

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.environ["ENV"] = "dev"

# テスト用データファイルを一時パスに向ける
_TEST_DATA_FILE = Path("/tmp") / f"ssh_hosts_test_{os.getpid()}.json"


@pytest.fixture(scope="module")
def test_client():
    """FastAPI テストクライアント"""
    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_headers(test_client):
    """Admin ユーザーの認証ヘッダー"""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    """Operator ユーザーの認証ヘッダー"""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    """Viewer ユーザーの認証ヘッダー"""
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_data_file():
    """各テスト前後にデータファイルをクリア"""
    import backend.api.routes.ssh_hosts as mod

    orig = mod._DATA_FILE
    mod._DATA_FILE = _TEST_DATA_FILE
    if _TEST_DATA_FILE.exists():
        _TEST_DATA_FILE.unlink()
    yield
    if _TEST_DATA_FILE.exists():
        _TEST_DATA_FILE.unlink()
    mod._DATA_FILE = orig


# ==============================================================================
# 1. 認証テスト (3件)
# ==============================================================================


class TestSSHHostsAuth:
    """認証なし・不正トークンでのアクセスを拒否すること"""

    def test_list_unauthenticated(self, test_client):
        """認証なしで一覧取得は 403"""
        resp = test_client.get("/api/ssh-hosts/")
        assert resp.status_code == 403

    def test_create_unauthenticated(self, test_client):
        """認証なしで登録は 403"""
        resp = test_client.post("/api/ssh-hosts/", json={
            "name": "test", "hostname": "192.168.1.1", "port": 22, "username": "ubuntu"
        })
        assert resp.status_code == 403

    def test_tunnels_unauthenticated(self, test_client):
        """認証なしでトンネル一覧は 403"""
        resp = test_client.get("/api/ssh-hosts/tunnels")
        assert resp.status_code == 403


# ==============================================================================
# 2. ホスト一覧テスト (2件)
# ==============================================================================


class TestListHosts:
    """GET /api/ssh-hosts/ の動作テスト"""

    def test_list_empty(self, test_client, admin_headers):
        """空リスト: hosts=[], count=0, status=success"""
        resp = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["hosts"] == []
        assert body["count"] == 0

    def test_list_viewer_allowed(self, test_client, viewer_headers):
        """Viewer ロールも一覧取得可能 (read:ssh_hosts)"""
        resp = test_client.get("/api/ssh-hosts/", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# 3. ホスト登録テスト (5件)
# ==============================================================================


class TestCreateHost:
    """POST /api/ssh-hosts/ の動作テスト"""

    def test_create_valid_ipv4(self, test_client, admin_headers):
        """IPv4 アドレスで正常登録 → 201"""
        payload = {
            "name": "prod-server",
            "hostname": "192.168.10.1",
            "port": 22,
            "username": "ubuntu",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "success"
        assert body["host"]["hostname"] == "192.168.10.1"
        assert body["host"]["port"] == 22
        assert "id" in body["host"]

    def test_create_valid_hostname(self, test_client, admin_headers):
        """RFC1123 ホスト名で正常登録"""
        payload = {
            "name": "staging-web",
            "hostname": "staging.example.com",
            "port": 2222,
            "username": "deploy",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        assert resp.json()["host"]["hostname"] == "staging.example.com"

    def test_create_duplicate_name_rejected(self, test_client, admin_headers):
        """同名ホストの重複登録は 409"""
        payload = {"name": "dup-test", "hostname": "10.0.0.1", "port": 22, "username": "ubuntu"}
        test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 409

    def test_create_viewer_forbidden(self, test_client, viewer_headers):
        """Viewer は登録不可 (write:ssh_hosts なし) → 403"""
        payload = {"name": "test", "hostname": "1.2.3.4", "port": 22, "username": "user"}
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=viewer_headers)
        assert resp.status_code == 403

    def test_create_operator_allowed(self, test_client, operator_headers):
        """Operator は登録可能 (write:ssh_hosts あり)"""
        payload = {
            "name": "op-server",
            "hostname": "10.10.10.10",
            "port": 22,
            "username": "ec2-user",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=operator_headers)
        assert resp.status_code == 201


# ==============================================================================
# 4. セキュリティ: 入力バリデーションテスト (6件)
# ==============================================================================


class TestInputValidation:
    """不正入力の拒否テスト"""

    def test_reject_shell_injection_in_hostname(self, test_client, admin_headers):
        """ホスト名にセミコロンを含む入力を拒否"""
        payload = {
            "name": "evil-host",
            "hostname": "192.168.1.1; rm -rf /",
            "port": 22,
            "username": "ubuntu",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_pipe_in_hostname(self, test_client, admin_headers):
        """ホスト名にパイプを含む入力を拒否"""
        payload = {
            "name": "evil2",
            "hostname": "host | cat /etc/passwd",
            "port": 22,
            "username": "ubuntu",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_invalid_username(self, test_client, admin_headers):
        """ユーザー名にスペースや特殊文字を含む入力を拒否"""
        payload = {
            "name": "user-test",
            "hostname": "10.0.0.1",
            "port": 22,
            "username": "bad user;ls",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_port_out_of_range(self, test_client, admin_headers):
        """ポートが範囲外(65536)の入力を拒否"""
        payload = {
            "name": "port-test",
            "hostname": "10.0.0.2",
            "port": 65536,
            "username": "ubuntu",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_port_zero(self, test_client, admin_headers):
        """ポートが 0 の入力を拒否"""
        payload = {
            "name": "port-zero",
            "hostname": "10.0.0.3",
            "port": 0,
            "username": "ubuntu",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_invalid_key_name(self, test_client, admin_headers):
        """鍵名に禁止文字が含まれる入力を拒否"""
        payload = {
            "name": "key-test",
            "hostname": "10.0.0.4",
            "port": 22,
            "username": "ubuntu",
            "key_name": "../../etc/passwd",
        }
        resp = test_client.post("/api/ssh-hosts/", json=payload, headers=admin_headers)
        assert resp.status_code == 422


# ==============================================================================
# 5. ホスト更新テスト (3件)
# ==============================================================================


class TestUpdateHost:
    """PUT /api/ssh-hosts/{id} の動作テスト"""

    def _create(self, client, headers, suffix=""):
        r = client.post("/api/ssh-hosts/", json={
            "name": f"update-target{suffix}",
            "hostname": "172.16.0.1",
            "port": 22,
            "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_update_port(self, test_client, admin_headers):
        """ポートの更新"""
        host_id = self._create(test_client, admin_headers, "-port")
        resp = test_client.put(
            f"/api/ssh-hosts/{host_id}", json={"port": 2222}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["host"]["port"] == 2222

    def test_update_nonexistent(self, test_client, admin_headers):
        """存在しないホストの更新は 404"""
        fake_id = str(uuid.uuid4())
        resp = test_client.put(
            f"/api/ssh-hosts/{fake_id}", json={"port": 2222}, headers=admin_headers
        )
        assert resp.status_code == 404

    def test_update_invalid_uuid(self, test_client, admin_headers):
        """不正な UUID は 400"""
        resp = test_client.put(
            "/api/ssh-hosts/not-a-uuid", json={"port": 22}, headers=admin_headers
        )
        assert resp.status_code == 400


# ==============================================================================
# 6. ホスト削除テスト (3件)
# ==============================================================================


class TestDeleteHost:
    """DELETE /api/ssh-hosts/{id} の動作テスト"""

    def _create(self, client, headers, name):
        r = client.post("/api/ssh-hosts/", json={
            "name": name,
            "hostname": "172.16.1.1",
            "port": 22,
            "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_delete_success(self, test_client, admin_headers):
        """正常削除 → 204、その後 GET では一覧に含まれない"""
        host_id = self._create(test_client, admin_headers, "del-target")
        resp = test_client.delete(f"/api/ssh-hosts/{host_id}", headers=admin_headers)
        assert resp.status_code == 204
        # 一覧に含まれないことを確認
        list_resp = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        ids = [h["id"] for h in list_resp.json()["hosts"]]
        assert host_id not in ids

    def test_delete_nonexistent(self, test_client, admin_headers):
        """存在しないホストの削除は 404"""
        resp = test_client.delete(f"/api/ssh-hosts/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 404

    def test_delete_bastion_in_use_rejected(self, test_client, admin_headers):
        """踏み台として使用中のホストを削除しようとすると 409"""
        bastion_id = self._create(test_client, admin_headers, "bastion-host")
        # bastion_id を踏み台として使うホストを登録
        r = test_client.post("/api/ssh-hosts/", json={
            "name": "depends-on-bastion",
            "hostname": "10.20.30.40",
            "port": 22,
            "username": "user",
            "bastion_host": bastion_id,
        }, headers=admin_headers)
        assert r.status_code == 201
        # 踏み台ホストの削除は 409
        resp = test_client.delete(f"/api/ssh-hosts/{bastion_id}", headers=admin_headers)
        assert resp.status_code == 409


# ==============================================================================
# 7. 接続テストエンドポイント (3件)
# ==============================================================================


class TestConnectionTest:
    """POST /api/ssh-hosts/{id}/test-connection の動作テスト"""

    def _create(self, client, headers, name, hostname):
        r = client.post("/api/ssh-hosts/", json={
            "name": name,
            "hostname": hostname,
            "port": 22,
            "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_connection_unreachable_returns_200(self, test_client, admin_headers):
        """到達不能なホストでも 200 を返し reachable=False を返すこと"""
        host_id = self._create(test_client, admin_headers, "unreachable", "240.0.0.1")
        resp = test_client.post(
            f"/api/ssh-hosts/{host_id}/test-connection", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert body["error"] is not None

    def test_connection_nonexistent_host_404(self, test_client, admin_headers):
        """存在しないホスト ID は 404"""
        resp = test_client.post(
            f"/api/ssh-hosts/{uuid.uuid4()}/test-connection", headers=admin_headers
        )
        assert resp.status_code == 404

    def test_connection_invalid_uuid_400(self, test_client, admin_headers):
        """不正な UUID は 400"""
        resp = test_client.post(
            "/api/ssh-hosts/not-uuid/test-connection", headers=admin_headers
        )
        assert resp.status_code == 400


# ==============================================================================
# 8. 鍵ペア生成 (承認フロー) テスト (2件)
# ==============================================================================


class TestGenerateKeypair:
    """POST /api/ssh-hosts/{id}/generate-keypair の動作テスト"""

    def _create(self, client, headers, name):
        r = client.post("/api/ssh-hosts/", json={
            "name": name,
            "hostname": "192.168.100.1",
            "port": 22,
            "username": "ubuntu",
        }, headers=headers)
        assert r.status_code == 201
        return r.json()["host"]["id"]

    def test_generate_keypair_returns_202(self, test_client, admin_headers):
        """鍵ペア生成リクエストは 202 Accepted を返す"""
        host_id = self._create(test_client, admin_headers, "keygen-host")
        resp = test_client.post(
            f"/api/ssh-hosts/{host_id}/generate-keypair",
            json={"key_type": "ed25519", "reason": "新規サーバー接続テスト"},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert "request_id" in body

    def test_generate_keypair_invalid_key_type(self, test_client, admin_headers):
        """不正な key_type は 422"""
        host_id = self._create(test_client, admin_headers, "keygen-badtype")
        resp = test_client.post(
            f"/api/ssh-hosts/{host_id}/generate-keypair",
            json={"key_type": "dsa", "reason": "テスト"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ==============================================================================
# 9. アクティブトンネル一覧テスト (2件)
# ==============================================================================


class TestActiveTunnels:
    """GET /api/ssh-hosts/tunnels の動作テスト"""

    def test_tunnels_success(self, test_client, admin_headers):
        """トンネル一覧が status=success で返ること"""
        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "tunnels" in body
        assert isinstance(body["tunnels"], list)

    def test_tunnels_viewer_allowed(self, test_client, viewer_headers):
        """Viewer もトンネル一覧取得可能 (read:ssh_hosts)"""
        with patch("backend.api.routes.ssh_hosts.psutil.process_iter", return_value=[]):
            resp = test_client.get("/api/ssh-hosts/tunnels", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# 10. CRUD フル操作テスト (1件)
# ==============================================================================


class TestFullCRUD:
    """登録→取得→更新→削除 の一連操作テスト"""

    def test_full_lifecycle(self, test_client, admin_headers):
        """ホストの CRUD サイクルが正しく動作すること"""
        # 1. 登録
        create_resp = test_client.post("/api/ssh-hosts/", json={
            "name": "lifecycle-host",
            "hostname": "10.99.99.99",
            "port": 22,
            "username": "lifecycle_user",
            "description": "フルCRUDテスト用",
        }, headers=admin_headers)
        assert create_resp.status_code == 201
        host_id = create_resp.json()["host"]["id"]

        # 2. 一覧に含まれることを確認
        list_resp = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        ids = [h["id"] for h in list_resp.json()["hosts"]]
        assert host_id in ids

        # 3. 更新
        upd_resp = test_client.put(
            f"/api/ssh-hosts/{host_id}",
            json={"description": "更新後の説明", "port": 2222},
            headers=admin_headers,
        )
        assert upd_resp.status_code == 200
        assert upd_resp.json()["host"]["description"] == "更新後の説明"

        # 4. 削除
        del_resp = test_client.delete(f"/api/ssh-hosts/{host_id}", headers=admin_headers)
        assert del_resp.status_code == 204

        # 5. 削除後は一覧に含まれない
        list_resp2 = test_client.get("/api/ssh-hosts/", headers=admin_headers)
        ids2 = [h["id"] for h in list_resp2.json()["hosts"]]
        assert host_id not in ids2
