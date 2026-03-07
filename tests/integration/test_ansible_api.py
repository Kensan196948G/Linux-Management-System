"""
Ansible連携APIモジュール - 統合テスト

APIエンドポイントの統合テスト（ansible wrapperをモック）
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_INVENTORY = {
    "_meta": {
        "hostvars": {
            "web01": {"ansible_host": "192.168.1.10", "ansible_distribution": "Ubuntu"},
            "web02": {"ansible_host": "192.168.1.11", "ansible_distribution": "Ubuntu"},
            "db01":  {"ansible_host": "192.168.1.20", "ansible_distribution": "Debian"},
        }
    },
    "webservers": {
        "hosts": ["web01", "web02"],
        "vars": {},
        "children": [],
    },
    "databases": {
        "hosts": ["db01"],
        "vars": {},
        "children": [],
    },
    "all": {
        "hosts": ["web01", "web02", "db01"],
        "vars": {},
        "children": ["webservers", "databases"],
    },
}

SAMPLE_PING_OUTPUT = (
    "web01 | SUCCESS => {\"changed\": false, \"ping\": \"pong\"}\n"
    "web02 | SUCCESS => {\"changed\": false, \"ping\": \"pong\"}\n"
    "db01 | UNREACHABLE! => {\"changed\": false, \"msg\": \"timed out\"}\n"
)

ANSIBLE_NOT_INSTALLED = {"status": "ansible_not_installed", "hosts": [], "message": "Ansible is not installed"}

SAMPLE_PLAYBOOK_CONTENT = """# Deploy web application
- name: Deploy web app
  hosts: webservers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
    - name: Start nginx
      service:
        name: nginx
        state: started
"""


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def client():
    """テストクライアント"""
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    """管理者トークン"""
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_token(client):
    """閲覧者トークン"""
    resp = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def operator_token(client):
    """オペレータートークン"""
    resp = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


def _mock_run_wrapper_inventory(args, timeout=60):
    """インベントリコマンドのモック"""
    if args[0] == "inventory-list":
        return {"stdout": json.dumps(SAMPLE_INVENTORY)}
    return {"status": "error", "message": "Unknown subcommand"}


def _mock_run_wrapper_ping(args, timeout=60):
    """Pingコマンドのモック"""
    if args[0] == "ping-all":
        return {"status": "success", "stdout": SAMPLE_PING_OUTPUT}
    return {"status": "error", "message": "Unknown subcommand"}


def _mock_run_wrapper_not_installed(args, timeout=60):
    """Ansibleが未インストールのモック"""
    return {"status": "ansible_not_installed", "hosts": [], "message": "Ansible is not installed"}


# ===================================================================
# テスト1: 認証なしアクセス拒否
# ===================================================================


def test_inventory_no_auth(client):
    """インベントリ取得: 認証なしは401/403"""
    resp = client.get("/api/ansible/inventory")
    assert resp.status_code in (401, 403)


def test_hosts_no_auth(client):
    """ホスト一覧: 認証なしは401/403"""
    resp = client.get("/api/ansible/hosts")
    assert resp.status_code in (401, 403)


def test_ping_no_auth(client):
    """Ping実行: 認証なしは401/403"""
    resp = client.post("/api/ansible/ping")
    assert resp.status_code in (401, 403)


def test_playbooks_no_auth(client):
    """Playbook一覧: 認証なしは401/403"""
    resp = client.get("/api/ansible/playbooks")
    assert resp.status_code in (401, 403)


def test_history_no_auth(client):
    """実行履歴: 認証なしは401/403"""
    resp = client.get("/api/ansible/history")
    assert resp.status_code in (401, 403)


# ===================================================================
# テスト2: インベントリ一覧 GET /api/ansible/inventory
# ===================================================================


def test_inventory_with_auth(client, admin_headers):
    """インベントリ取得: 認証ありは200"""
    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_inventory):
        resp = client.get("/api/ansible/inventory", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "hosts" in data
    assert "total_hosts" in data
    assert data["total_hosts"] > 0


def test_inventory_ansible_not_installed(client, admin_headers):
    """インベントリ取得: Ansible未インストールは ansible_not_installed"""
    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_not_installed):
        resp = client.get("/api/ansible/inventory", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ansible_not_installed"
    assert data["hosts"] == []


def test_inventory_viewer_can_read(client, viewer_headers):
    """インベントリ取得: Viewerロールはread:ansible権限あり"""
    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_not_installed):
        resp = client.get("/api/ansible/inventory", headers=viewer_headers)
    assert resp.status_code == 200


# ===================================================================
# テスト3: ホスト一覧 GET /api/ansible/hosts
# ===================================================================


def test_hosts_with_auth(client, admin_headers):
    """ホスト一覧: 認証ありは200"""
    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_inventory):
        resp = client.get("/api/ansible/hosts", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "hosts" in data
    assert "total" in data
    assert "online" in data
    assert "offline" in data
    assert "unknown" in data


def test_hosts_ansible_not_installed(client, admin_headers):
    """ホスト一覧: Ansible未インストール時は ansible_not_installed"""
    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_not_installed):
        resp = client.get("/api/ansible/hosts", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ansible_not_installed"
    assert data["total"] == 0


def test_hosts_ping_status_from_cache(client, admin_headers):
    """ホスト一覧: pingキャッシュからステータスが反映される"""
    import backend.api.routes.ansible as ansible_mod
    ansible_mod._ping_cache["web01"] = {"status": "online", "last_seen": "2025-01-01T00:00:00"}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=_mock_run_wrapper_inventory):
        resp = client.get("/api/ansible/hosts", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    web01 = next((h for h in data["hosts"] if h["hostname"] == "web01"), None)
    assert web01 is not None
    assert web01["ping_status"] == "online"

    # キャッシュをクリア
    ansible_mod._ping_cache.clear()


# ===================================================================
# テスト4: Ping実行 POST /api/ansible/ping
# ===================================================================


def test_ping_requires_write_permission(client, viewer_headers):
    """Ping実行: ViewerはPOST /api/ansible/pingに書き込み権限がない（403）"""
    resp = client.post("/api/ansible/ping", headers=viewer_headers)
    assert resp.status_code == 403


def test_ping_accepted_by_operator(client, operator_headers):
    """Ping実行: Operatorは202 Accepted"""
    with patch("backend.api.routes.ansible._ping_running", False):
        resp = client.post("/api/ansible/ping", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("accepted", "already_running")


def test_ping_admin_can_execute(client, admin_headers):
    """Ping実行: AdminはPingを実行できる"""
    import backend.api.routes.ansible as ansible_mod
    ansible_mod._ping_running = False
    resp = client.post("/api/ansible/ping", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("accepted", "already_running")


# ===================================================================
# テスト5: Playbook一覧 GET /api/ansible/playbooks
# ===================================================================


def test_playbooks_list(client, admin_headers, tmp_path):
    """Playbook一覧: 正常取得"""
    # tmp_pathにPlaybookファイルを作成してモック
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "deploy-web.yml").write_text(SAMPLE_PLAYBOOK_CONTENT)
    (playbook_dir / "backup.yml").write_text("# Backup playbook\n- name: Backup\n  hosts: all\n  tasks:\n    - name: Create backup\n      command: tar -czf /backup.tar.gz /data\n")

    with patch("backend.api.routes.ansible.Path") as mock_path:
        # playbook_dir.exists() → True
        mock_dir = MagicMock()
        mock_dir.exists.return_value = True
        mock_dir.glob.return_value = list(playbook_dir.glob("*.yml"))
        mock_path.return_value = mock_dir

        # 直接 Path("/etc/ansible/playbooks") をパッチ
        resp = client.get("/api/ansible/playbooks", headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "playbooks" in data
    assert "count" in data


def test_playbooks_list_no_directory(client, admin_headers):
    """Playbook一覧: ディレクトリが存在しない場合は空リスト"""
    with patch("backend.api.routes.ansible.Path") as mock_path:
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_path.return_value = mock_dir
        resp = client.get("/api/ansible/playbooks", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["playbooks"] == []


def test_playbooks_viewer_can_list(client, viewer_headers):
    """Playbook一覧: Viewerも閲覧可能"""
    with patch("backend.api.routes.ansible.Path") as mock_path:
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_path.return_value = mock_dir
        resp = client.get("/api/ansible/playbooks", headers=viewer_headers)
    assert resp.status_code == 200


# ===================================================================
# テスト6: Playbookコンテンツ GET /api/ansible/playbooks/{name}
# ===================================================================


def test_playbook_content_found(client, admin_headers):
    """Playbookコンテンツ: 存在するPlaybookは200"""
    def mock_wrapper(args, timeout=60):
        if args[0] == "show-playbook" and args[1] == "deploy-web.yml":
            return {"status": "success", "stdout": SAMPLE_PLAYBOOK_CONTENT}
        return {"status": "error", "message": "not found"}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
        resp = client.get("/api/ansible/playbooks/deploy-web.yml", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["name"] == "deploy-web.yml"
    assert "content" in data


def test_playbook_content_not_found(client, admin_headers):
    """Playbookコンテンツ: 存在しないPlaybookは404"""
    def mock_wrapper(args, timeout=60):
        return {"status": "error", "message": "Playbook not found: nonexistent.yml"}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
        resp = client.get("/api/ansible/playbooks/nonexistent.yml", headers=admin_headers)
    assert resp.status_code == 404


def test_playbook_content_invalid_name_rejected(client, admin_headers):
    """Playbookコンテンツ: 不正なPlaybook名は400"""
    resp = client.get("/api/ansible/playbooks/../../etc/passwd.yml", headers=admin_headers)
    assert resp.status_code in (400, 404, 422)


def test_playbook_content_injection_rejected(client, admin_headers):
    """Playbookコンテンツ: shell injection文字を含む名前は400"""
    resp = client.get("/api/ansible/playbooks/deploy;rm-rf.yml", headers=admin_headers)
    assert resp.status_code in (400, 404, 422)


# ===================================================================
# テスト7: Playbook実行 POST /api/ansible/playbooks/{name}/run
# ===================================================================


def test_playbook_run_returns_202(client, admin_headers):
    """Playbook実行: 承認フロー経由で202 Accepted"""
    def mock_wrapper(args, timeout=60):
        if args[0] == "show-playbook":
            return {"status": "success", "stdout": SAMPLE_PLAYBOOK_CONTENT}
        return {"status": "error", "message": "Unknown"}

    async def mock_create_request(**kwargs):
        return {"request_id": "test-req-001", "status": "pending"}

    mock_approval = MagicMock()
    mock_approval.create_request = mock_create_request

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper), \
         patch("backend.api.routes.ansible._approval_service", mock_approval):
        resp = client.post(
            "/api/ansible/playbooks/deploy-web.yml/run",
            json={"reason": "定期デプロイ"},
            headers=admin_headers,
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert "request_id" in data
    assert data["playbook"] == "deploy-web.yml"


def test_playbook_run_viewer_forbidden(client, viewer_headers):
    """Playbook実行: Viewerはwrite:ansible権限なし（403）"""
    resp = client.post(
        "/api/ansible/playbooks/deploy-web.yml/run",
        json={"reason": "test"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403


def test_playbook_run_invalid_name(client, admin_headers):
    """Playbook実行: 不正なPlaybook名は400"""
    resp = client.post(
        "/api/ansible/playbooks/invalid!name.yml/run",
        json={"reason": "test"},
        headers=admin_headers,
    )
    assert resp.status_code in (400, 422)


def test_playbook_run_empty_reason(client, admin_headers):
    """Playbook実行: 理由が空は422"""
    def mock_wrapper(args, timeout=60):
        return {"status": "success", "stdout": SAMPLE_PLAYBOOK_CONTENT}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
        resp = client.post(
            "/api/ansible/playbooks/deploy-web.yml/run",
            json={"reason": ""},
            headers=admin_headers,
        )
    assert resp.status_code == 422


def test_playbook_run_not_found(client, admin_headers):
    """Playbook実行: 存在しないPlaybookは404"""
    def mock_wrapper(args, timeout=60):
        return {"status": "error", "message": "Playbook not found: ghost.yml"}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
        resp = client.post(
            "/api/ansible/playbooks/ghost.yml/run",
            json={"reason": "テスト"},
            headers=admin_headers,
        )
    assert resp.status_code == 404


# ===================================================================
# テスト8: 実行履歴 GET /api/ansible/history
# ===================================================================


def test_history_with_auth(client, admin_headers):
    """実行履歴: 認証ありは200"""
    with patch("backend.api.routes.ansible.Path") as mock_path:
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_path.return_value = mock_dir
        resp = client.get("/api/ansible/history", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "history" in data
    assert "count" in data


def test_history_viewer_can_read(client, viewer_headers):
    """実行履歴: Viewerも閲覧可能"""
    with patch("backend.api.routes.ansible.Path") as mock_path:
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_path.return_value = mock_dir
        resp = client.get("/api/ansible/history", headers=viewer_headers)
    assert resp.status_code == 200


def test_history_reads_audit_logs(client, admin_headers, tmp_path):
    """実行履歴: 監査ログからansible操作を抽出する"""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    log_file = audit_dir / "audit_20250101.json"
    log_file.write_text(
        json.dumps({
            "timestamp": "2025-01-01T10:00:00",
            "operation": "ansible_playbook_run_requested",
            "user_id": "admin@example.com",
            "target": "deploy-web.yml",
            "status": "pending_approval",
            "details": {"request_id": "req-001"},
        }) + "\n" +
        json.dumps({
            "timestamp": "2025-01-01T09:00:00",
            "operation": "service_restart",
            "user_id": "admin@example.com",
            "target": "nginx",
            "status": "success",
            "details": {},
        }) + "\n"
    )

    with patch("backend.api.routes.ansible.Path") as mock_path_cls:
        # settings.logging.file のパスをモック
        def path_side_effect(arg):
            if "logging" in str(arg) or "logs" in str(arg):
                mock_p = MagicMock()
                mock_p.parent = tmp_path
                return mock_p
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = list(audit_dir.glob("audit_*.json"))
            return mock_dir

        from unittest.mock import call
        mock_path_cls.side_effect = path_side_effect

        resp = client.get("/api/ansible/history", headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "history" in data


# ===================================================================
# テスト9: セキュリティ - 不正入力拒否
# ===================================================================


def test_playbook_name_with_semicolon_rejected(client, admin_headers):
    """セキュリティ: セミコロンを含むPlaybook名を拒否"""
    resp = client.get("/api/ansible/playbooks/deploy;evil.yml", headers=admin_headers)
    assert resp.status_code in (400, 404, 422)


def test_playbook_name_with_pipe_rejected(client, admin_headers):
    """セキュリティ: パイプを含むPlaybook名を拒否"""
    resp = client.get("/api/ansible/playbooks/deploy|evil.yml", headers=admin_headers)
    assert resp.status_code in (400, 404, 422)


def test_playbook_name_without_yml_extension_rejected(client, admin_headers):
    """セキュリティ: .yml拡張子なしのPlaybook名を拒否"""
    def mock_wrapper(args, timeout=60):
        return {"status": "success", "stdout": "content"}

    with patch("backend.api.routes.ansible._run_wrapper", side_effect=mock_wrapper):
        resp = client.get("/api/ansible/playbooks/deploy-no-extension", headers=admin_headers)
    assert resp.status_code == 400


def test_wrapper_path_not_list(client, admin_headers):
    """セキュリティ: wrapperはリスト形式でコマンドを実行（shell=True禁止確認）"""
    import backend.api.routes.ansible as ansible_mod
    import inspect
    source = inspect.getsource(ansible_mod._run_wrapper)
    assert "shell=True" not in source, "shell=True は禁止されています"
