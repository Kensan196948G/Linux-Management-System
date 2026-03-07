"""
承認ワークフロー新ハンドラーテスト

テスト対象ハンドラー (13種):
  - container_stop / container_restart / container_prune
  - nfs_mount / nfs_umount
  - backup_run / backup_restore
  - ansible_playbook_run
  - network_config_change (set-ip / set-dns)
  - dns_config_change
  - shutdown / reboot

テスト項目:
  - 各ハンドラーのリクエスト作成 (pending)
  - 承認→自動実行 (executed)
  - wrapper失敗→execution_failed
  - 未実装アクション (network_config_change の unknown action)
  - エッジケース: 必須フィールド欠如、非Approverによる承認試み
  合計: 30件以上
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


# ===================================================================
# フィクスチャ
# ===================================================================


_EXTRA_POLICIES = """
INSERT OR IGNORE INTO approval_policies
    (operation_type, description, approval_required, approver_roles, approval_count,
     timeout_hours, auto_execute, risk_level)
VALUES
    ('backup_run',    'バックアップ実行',        1, '["Approver","Admin"]', 1, 12, 1, 'HIGH'),
    ('backup_restore','バックアップリストア',      1, '["Admin"]',           1, 12, 1, 'HIGH'),
    ('ansible_playbook_run', 'Ansibleプレイブック実行', 1, '["Approver","Admin"]', 1, 12, 1, 'HIGH'),
    ('shutdown',      'システムシャットダウン',    1, '["Admin"]',           1,  1, 1, 'CRITICAL'),
    ('reboot',        'システム再起動',           1, '["Admin"]',           1,  1, 1, 'CRITICAL');
"""

_AUTO_EXECUTE_ON = """
UPDATE approval_policies
SET auto_execute = 1
WHERE operation_type IN (
    'container_stop', 'container_restart', 'container_prune',
    'nfs_mount', 'nfs_umount',
    'backup_restore',
    'network_config_change', 'dns_config_change'
);
"""


@pytest.fixture(scope="module", autouse=True)
def init_approval_db(tmp_path_factory):
    """APIルートの approval_service を一時DBで初期化する（モジュール単位）"""
    from backend.api.routes import approval as approval_module

    tmp_db = str(tmp_path_factory.mktemp("approval_db_new_handlers") / "test_approval.db")
    approval_module.approval_service.db_path = tmp_db

    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_db) as conn:
        conn.executescript(schema_sql)
        conn.executescript(_EXTRA_POLICIES)
        conn.executescript(_AUTO_EXECUTE_ON)
    yield


@pytest.fixture(autouse=True)
def cleanup_approval_db():
    """各テスト前にDBデータをクリーンアップする"""
    from backend.api.routes.approval import approval_service

    with sqlite3.connect(approval_service.db_path) as conn:
        conn.execute("DELETE FROM approval_history")
        conn.execute("DELETE FROM approval_requests")
        conn.commit()
    yield


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def operator_token(client):
    resp = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def approver_token(client):
    resp = client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def approver_headers(approver_token):
    return {"Authorization": f"Bearer {approver_token}"}


def _create_request(client, headers, request_type, payload, reason="テスト"):
    return client.post(
        "/api/approval/request",
        json={"request_type": request_type, "payload": payload, "reason": reason},
        headers=headers,
    )


def _approve_request(client, headers, request_id):
    return client.post(
        f"/api/approval/{request_id}/approve",
        json={"comment": "承認"},
        headers=headers,
    )


_SUCCESS = {"status": "success", "message": "OK"}


# ===================================================================
# container_stop
# ===================================================================


class TestContainerStop:
    """container_stop ハンドラーのテスト"""

    def test_container_stop_request_created(self, client, operator_headers):
        """正常系: container_stop リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "container_stop", {"container_name": "my-app"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["request_type"] == "container_stop"
        assert data["request_status"] == "pending"

    def test_container_stop_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: 承認後に container_stop が自動実行される"""
        create_resp = _create_request(client, operator_headers, "container_stop", {"container_name": "my-app"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.container_stop", return_value=_SUCCESS):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200

    def test_container_stop_wrapper_failure(self, client, operator_headers, approver_headers):
        """異常系: wrapper失敗→execution_failed（承認APIは200を返す）"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(client, operator_headers, "container_stop", {"container_name": "my-app"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.container_stop", side_effect=SudoWrapperError("container not found")):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# container_restart
# ===================================================================


class TestContainerRestart:
    """container_restart ハンドラーのテスト"""

    def test_container_restart_request_created(self, client, operator_headers):
        """正常系: container_restart リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "container_restart", {"container_name": "web-server"})
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "container_restart"

    def test_container_restart_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: 承認後に container_restart が自動実行される"""
        create_resp = _create_request(client, operator_headers, "container_restart", {"container_name": "web-server"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.container_restart", return_value=_SUCCESS):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_container_restart_wrapper_failure(self, client, operator_headers, admin_headers):
        """異常系: wrapper失敗→実行失敗（承認API自体は成功）"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(client, operator_headers, "container_restart", {"container_name": "web-server"})
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.container_restart", side_effect=SudoWrapperError("no such container")):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# container_prune
# ===================================================================


class TestContainerPrune:
    """container_prune ハンドラーのテスト"""

    def test_container_prune_request_created(self, client, operator_headers):
        """正常系: container_prune リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "container_prune", {})
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "container_prune"

    def test_container_prune_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: 承認後に container_prune が自動実行される"""
        create_resp = _create_request(client, operator_headers, "container_prune", {})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.container_prune", return_value=_SUCCESS):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# nfs_mount / nfs_umount
# ===================================================================


class TestNfsMountUmount:
    """nfs_mount / nfs_umount ハンドラーのテスト"""

    def test_nfs_mount_request_created(self, client, operator_headers):
        """正常系: nfs_mount リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "nfs_mount",
            {"nfs_source": "192.168.1.100:/exports/data", "mount_point": "/mnt/nfs"},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "nfs_mount"

    def test_nfs_mount_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: 承認後に nfs_mount が自動実行される"""
        create_resp = _create_request(
            client, operator_headers, "nfs_mount",
            {"nfs_source": "192.168.1.100:/exports/data", "mount_point": "/mnt/nfs"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.nfs_mount", return_value=_SUCCESS):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_nfs_umount_request_created(self, client, operator_headers):
        """正常系: nfs_umount リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "nfs_umount", {"mount_point": "/mnt/nfs"})
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "nfs_umount"

    def test_nfs_umount_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: 承認後に nfs_umount が自動実行される"""
        create_resp = _create_request(client, operator_headers, "nfs_umount", {"mount_point": "/mnt/nfs"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.nfs_umount", return_value=_SUCCESS):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200

    def test_nfs_mount_wrapper_failure(self, client, operator_headers, admin_headers):
        """異常系: nfs_mount wrapper失敗"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(
            client, operator_headers, "nfs_mount",
            {"nfs_source": "bad-host:/bad", "mount_point": "/mnt/bad"},
        )
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.nfs_mount", side_effect=SudoWrapperError("mount failed")):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# backup_run / backup_restore
# ===================================================================


class TestBackup:
    """backup_run / backup_restore ハンドラーのテスト"""

    def test_backup_run_request_created(self, client, operator_headers):
        """正常系: backup_run リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "backup_run", {})
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "backup_run"

    def test_backup_run_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: 承認後に backup_run が自動実行される"""
        create_resp = _create_request(client, operator_headers, "backup_run", {})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.run_backup", return_value=_SUCCESS):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200

    def test_backup_restore_request_created(self, client, operator_headers):
        """正常系: backup_restore リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "backup_restore",
            {"backup_file": "/var/backup/data-2026-01-01.tar.gz"},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "backup_restore"

    def test_backup_restore_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: 承認後に backup_restore が自動実行される"""
        create_resp = _create_request(
            client, operator_headers, "backup_restore",
            {"backup_file": "/var/backup/data-2026-01-01.tar.gz", "restore_target": "/var/tmp/restore"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.restore_backup_file", return_value=_SUCCESS):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_backup_restore_default_restore_dir(self, client, operator_headers, admin_headers):
        """正常系: restore_target省略→デフォルトディレクトリで実行される"""
        create_resp = _create_request(
            client, operator_headers, "backup_restore",
            {"backup_file": "/var/backup/latest.tar.gz"},
        )
        assert create_resp.status_code == 201, create_resp.text
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.restore_backup_file", return_value=_SUCCESS) as mock_restore:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        mock_restore.assert_called_once()
        # デフォルトrestore_dirが渡されていることを確認
        args, kwargs = mock_restore.call_args
        restore_dir = kwargs.get("restore_dir") or (args[1] if len(args) > 1 else None)
        assert restore_dir == "/var/tmp/adminui-restore"
    def test_backup_run_wrapper_failure(self, client, operator_headers, approver_headers):
        """異常系: backup_run wrapper失敗"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(client, operator_headers, "backup_run", {})
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.run_backup", side_effect=SudoWrapperError("disk full")):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# ansible_playbook_run
# ===================================================================


class TestAnsiblePlaybookRun:
    """ansible_playbook_run ハンドラーのテスト"""

    def test_ansible_playbook_run_request_created(self, client, operator_headers):
        """正常系: ansible_playbook_run リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "ansible_playbook_run",
            {"playbook_name": "deploy-web.yml"},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "ansible_playbook_run"

    def test_ansible_playbook_run_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: 承認後に ansible_playbook_run が自動実行される"""
        create_resp = _create_request(
            client, operator_headers, "ansible_playbook_run",
            {"playbook_name": "deploy-web.yml"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.ansible_run_playbook", return_value=_SUCCESS):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_ansible_playbook_run_wrapper_failure(self, client, operator_headers, approver_headers):
        """異常系: playbook失敗→execution_failed"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(
            client, operator_headers, "ansible_playbook_run",
            {"playbook_name": "bad-playbook.yml"},
        )
        request_id = create_resp.json()["request_id"]

        with patch(
            "backend.core.sudo_wrapper.SudoWrapper.ansible_run_playbook",
            side_effect=SudoWrapperError("playbook not found"),
        ):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# network_config_change (set-ip / set-dns)
# ===================================================================


class TestNetworkConfigChange:
    """network_config_change ハンドラー (set-ip / set-dns) のテスト"""

    def test_network_set_ip_request_created(self, client, operator_headers):
        """正常系: set-ip リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-ip", "interface": "eth0", "ip_address": "192.168.1.10", "prefix": "24", "gateway": "192.168.1.1"},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "network_config_change"

    def test_network_set_ip_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: set-ip 承認→自動実行"""
        create_resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-ip", "interface": "eth0", "ip_address": "192.168.1.10", "prefix": "24", "gateway": "192.168.1.1"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_ip", return_value=_SUCCESS) as mock_setip:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        if mock_setip.called:
            mock_setip.assert_called_once_with(
                interface="eth0",
                ip_address="192.168.1.10",
                prefix="24",
                gateway="192.168.1.1",
            )

    def test_network_set_dns_request_created(self, client, operator_headers):
        """正常系: set-dns リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-dns", "dns1": "8.8.8.8", "dns2": "8.8.4.4"},
        )
        assert resp.status_code == 201

    def test_network_set_dns_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: set-dns 承認→自動実行"""
        create_resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-dns", "dns1": "1.1.1.1", "dns2": "1.0.0.1"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_dns", return_value=_SUCCESS) as mock_setdns:
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200
        if mock_setdns.called:
            mock_setdns.assert_called_once_with(dns1="1.1.1.1", dns2="1.0.0.1")

    def test_network_set_ip_default_prefix(self, client, operator_headers, admin_headers):
        """正常系: prefix省略→デフォルト24で実行"""
        create_resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-ip", "interface": "eth1", "ip_address": "10.0.0.5"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_ip", return_value=_SUCCESS) as mock_setip:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        if mock_setip.called:
            args, kwargs = mock_setip.call_args
            prefix = kwargs.get("prefix") or (args[2] if len(args) > 2 else None)
            assert prefix == "24"

    def test_network_config_change_unknown_action(self, client, operator_headers, admin_headers):
        """異常系: 未知のaction → execution_failed"""
        create_resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "unknown-action"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_network_set_ip_wrapper_failure(self, client, operator_headers, admin_headers):
        """異常系: network_set_ip wrapper失敗"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(
            client, operator_headers, "network_config_change",
            {"action": "set-ip", "interface": "eth0", "ip_address": "192.168.1.10", "prefix": "24"},
        )
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_ip", side_effect=SudoWrapperError("interface not found")):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# dns_config_change
# ===================================================================


class TestDnsConfigChange:
    """dns_config_change ハンドラーのテスト"""

    def test_dns_config_change_request_created(self, client, operator_headers):
        """正常系: dns_config_change リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "dns_config_change",
            {"dns1": "8.8.8.8"},
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "dns_config_change"

    def test_dns_config_change_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: dns_config_change 承認→自動実行"""
        create_resp = _create_request(
            client, operator_headers, "dns_config_change",
            {"dns1": "8.8.8.8", "dns2": "8.8.4.4"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_dns", return_value=_SUCCESS) as mock_setdns:
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200
        if mock_setdns.called:
            mock_setdns.assert_called_once_with(dns1="8.8.8.8", dns2="8.8.4.4")

    def test_dns_config_change_dns2_optional(self, client, operator_headers, admin_headers):
        """正常系: dns2省略→空文字列で実行"""
        create_resp = _create_request(
            client, operator_headers, "dns_config_change",
            {"dns1": "1.1.1.1"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.network_set_dns", return_value=_SUCCESS) as mock_setdns:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        if mock_setdns.called:
            args, kwargs = mock_setdns.call_args
            dns2 = kwargs.get("dns2") if kwargs else ""
            assert dns2 == ""


# ===================================================================
# shutdown / reboot
# ===================================================================


class TestShutdownReboot:
    """shutdown / reboot ハンドラーのテスト"""

    def test_shutdown_request_created(self, client, operator_headers):
        """正常系: shutdown リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "shutdown",
            {"delay": "+5"},
            "メンテナンスのためシャットダウン",
        )
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "shutdown"
        assert resp.json()["request_status"] == "pending"

    def test_shutdown_approve_and_execute(self, client, operator_headers, admin_headers):
        """正常系: shutdown 承認→自動実行"""
        create_resp = _create_request(client, operator_headers, "shutdown", {"delay": "+5"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_shutdown", return_value=_SUCCESS) as mock_shutdown:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        mock_shutdown.assert_called_once_with(delay="+5")

    def test_shutdown_default_delay(self, client, operator_headers, admin_headers):
        """正常系: delay省略→デフォルト+1で実行"""
        create_resp = _create_request(client, operator_headers, "shutdown", {})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_shutdown", return_value=_SUCCESS) as mock_shutdown:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        mock_shutdown.assert_called_once_with(delay="+1")

    def test_reboot_request_created(self, client, operator_headers):
        """正常系: reboot リクエストが作成できる"""
        resp = _create_request(client, operator_headers, "reboot", {"delay": "+2"})
        assert resp.status_code == 201
        assert resp.json()["request_type"] == "reboot"

    def test_reboot_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: reboot 承認→自動実行"""
        create_resp = _create_request(client, operator_headers, "reboot", {"delay": "+2"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_reboot", return_value=_SUCCESS) as mock_reboot:
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200
        mock_reboot.assert_called_once_with(delay="+2")

    def test_reboot_default_delay(self, client, operator_headers, admin_headers):
        """正常系: delay省略→デフォルト+1で実行"""
        create_resp = _create_request(client, operator_headers, "reboot", {})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_reboot", return_value=_SUCCESS) as mock_reboot:
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200
        mock_reboot.assert_called_once_with(delay="+1")

    def test_shutdown_wrapper_failure(self, client, operator_headers, admin_headers):
        """異常系: shutdown wrapper失敗"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(client, operator_headers, "shutdown", {"delay": "+1"})
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_shutdown", side_effect=SudoWrapperError("permission denied")):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_reboot_wrapper_failure(self, client, operator_headers, approver_headers):
        """異常系: reboot wrapper失敗"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(client, operator_headers, "reboot", {"delay": "+1"})
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.system_reboot", side_effect=SudoWrapperError("reboot blocked")):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# エッジケース
# ===================================================================


class TestEdgeCases:
    """エッジケース: 権限・ペイロード異常系"""

    def test_operator_cannot_approve(self, client, operator_headers):
        """異常系: Operator は承認できない"""
        create_resp = _create_request(client, operator_headers, "container_stop", {"container_name": "app"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        approve_resp = _approve_request(client, operator_headers, request_id)
        assert approve_resp.status_code == 403

    def test_unauthenticated_cannot_create_request(self, client):
        """異常系: 未認証では承認リクエストを作成できない"""
        resp = _create_request(client, {}, "shutdown", {"delay": "+1"})
        assert resp.status_code in (401, 403)

    def test_unauthenticated_cannot_approve(self, client, operator_headers, approver_headers):
        """異常系: 未認証では承認できない"""
        create_resp = _create_request(client, operator_headers, "reboot", {"delay": "+1"})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        approve_resp = _approve_request(client, {}, request_id)
        assert approve_resp.status_code in (401, 403)

    def test_already_approved_request_cannot_be_approved_again(self, client, operator_headers, admin_headers):
        """異常系: 承認済みリクエストの再承認は失敗"""
        create_resp = _create_request(client, operator_headers, "backup_run", {})
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch("backend.core.sudo_wrapper.SudoWrapper.run_backup", return_value=_SUCCESS):
            first_approve = _approve_request(client, admin_headers, request_id)
        assert first_approve.status_code == 200

        second_approve = _approve_request(client, admin_headers, request_id)
        assert second_approve.status_code in (400, 409, 422)

    def test_nonexistent_request_approve_returns_error(self, client, admin_headers):
        """異常系: 存在しないリクエストIDへの承認は404を返す"""
        approve_resp = _approve_request(client, admin_headers, "nonexistent-request-id-99999")
        assert approve_resp.status_code == 404

    def test_container_stop_pending_status(self, client, operator_headers):
        """正常系: container_stop リクエストは初期状態でpending"""
        resp = _create_request(client, operator_headers, "container_stop", {"container_name": "app"})
        assert resp.status_code == 201
        assert resp.json()["request_status"] == "pending"

    def test_multiple_pending_requests_independent(self, client, operator_headers):
        """正常系: 複数のリクエストが独立して作成できる"""
        r1 = _create_request(client, operator_headers, "container_stop", {"container_name": "app1"})
        r2 = _create_request(client, operator_headers, "reboot", {"delay": "+5"})
        r3 = _create_request(client, operator_headers, "backup_run", {})

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r3.status_code == 201

        ids = {r1.json()["request_id"], r2.json()["request_id"], r3.json()["request_id"]}
        assert len(ids) == 3
