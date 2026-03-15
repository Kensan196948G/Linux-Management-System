"""
SSH Keys モジュール - カバレッジ改善テスト v2

未カバー箇所を集中的にテスト:
  - get_ssh_keys: parse_wrapper_result の output パース分岐
  - get_sshd_config: 正常系の SSHdConfigResponse モデル返却確認
  - get_ssh_host_keys: SSHHostKeysResponse モデル返却確認
  - get_known_hosts_count: SSHKnownHostsCountResponse モデル返却確認
  - 各エンドポイントの audit_log.record 呼び出しパラメータ検証
  - SudoWrapperError / Exception の詳細メッセージ検証
  - admin / operator 各ロールでのアクセス
"""

import json
from unittest.mock import patch

import pytest


# ===================================================================
# テストデータ
# ===================================================================

KEYS_RESPONSE_DATA = {
    "status": "success",
    "keys": [
        {"filename": "ssh_host_rsa_key.pub", "key_type": "ssh-rsa", "comment": "root@host", "size_bytes": 564},
    ],
    "count": 1,
    "ssh_dir": "/etc/ssh",
    "timestamp": "2026-03-01T00:00:00Z",
}

SSHD_CONFIG_DATA = {
    "status": "success",
    "config_path": "/etc/ssh/sshd_config",
    "settings": {"Port": "22", "PermitRootLogin": "no", "PasswordAuthentication": "no"},
    "timestamp": "2026-03-01T00:00:00Z",
}

HOST_KEYS_DATA = {
    "status": "success",
    "host_keys": [
        {
            "key_type": "ed25519",
            "bits": 256,
            "fingerprint": "SHA256:testfp123",
            "algorithm": "ED25519",
            "file": "/etc/ssh/ssh_host_ed25519_key.pub",
        },
    ],
    "count": 1,
    "timestamp": "2026-03-01T00:00:00Z",
}

KNOWN_HOSTS_DATA = {
    "status": "success",
    "count": 42,
    "path": "/etc/ssh/ssh_known_hosts",
    "note": "内容は非表示（セキュリティポリシー）",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# output JSON パーステスト
# ===================================================================


class TestSSHKeysOutputParsing:
    """parse_wrapper_result の output フィールドパース分岐"""

    def test_keys_with_output_json_string(self, test_client, admin_headers):
        """output が JSON 文字列なら中身がパースされる"""
        wrapper_result = {"status": "success", "output": json.dumps(KEYS_RESPONSE_DATA)}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["ssh_dir"] == "/etc/ssh"

    def test_sshd_config_with_output_json_string(self, test_client, admin_headers):
        """sshd_config: output JSON パース"""
        wrapper_result = {"status": "success", "output": json.dumps(SSHD_CONFIG_DATA)}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["settings"]["Port"] == "22"

    def test_host_keys_with_output_json_string(self, test_client, admin_headers):
        """host-keys: output JSON パース"""
        wrapper_result = {"status": "success", "output": json.dumps(HOST_KEYS_DATA)}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_known_hosts_with_output_json_string(self, test_client, admin_headers):
        """known-hosts-count: output JSON パース"""
        wrapper_result = {"status": "success", "output": json.dumps(KNOWN_HOSTS_DATA)}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 42

    def test_keys_with_invalid_output_json(self, test_client, admin_headers):
        """output が不正 JSON の場合は result そのまま"""
        wrapper_result = {
            "status": "success",
            "output": "not-json{{{",
            "keys": [],
            "count": 0,
            "ssh_dir": "/etc/ssh",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=wrapper_result,
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 200


# ===================================================================
# audit_log 呼び出し検証
# ===================================================================


class TestSSHKeysAuditLog:
    """各エンドポイントの audit_log.record パラメータ検証"""

    def test_keys_audit_log_params(self, test_client, admin_headers):
        """get_ssh_keys で audit_log が正しく呼ばれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=KEYS_RESPONSE_DATA,
        ), patch("backend.api.routes.sshkeys.audit_log") as mock_audit:
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        kw = mock_audit.record.call_args[1]
        assert kw["operation"] == "ssh_keys_read"
        assert kw["target"] == "ssh_keys"
        assert kw["status"] == "success"
        assert kw["details"]["count"] == 1

    def test_sshd_config_audit_log_params(self, test_client, admin_headers):
        """get_sshd_config で audit_log が正しく呼ばれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            return_value=SSHD_CONFIG_DATA,
        ), patch("backend.api.routes.sshkeys.audit_log") as mock_audit:
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        kw = mock_audit.record.call_args[1]
        assert kw["operation"] == "sshd_config_read"
        assert kw["target"] == "sshd_config"

    def test_host_keys_audit_log_params(self, test_client, admin_headers):
        """get_ssh_host_keys で audit_log が正しく呼ばれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            return_value=HOST_KEYS_DATA,
        ), patch("backend.api.routes.sshkeys.audit_log") as mock_audit:
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        kw = mock_audit.record.call_args[1]
        assert kw["operation"] == "ssh_host_keys_read"
        assert kw["details"]["count"] == 1

    def test_known_hosts_audit_log_params(self, test_client, admin_headers):
        """get_known_hosts_count で audit_log が正しく呼ばれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            return_value=KNOWN_HOSTS_DATA,
        ), patch("backend.api.routes.sshkeys.audit_log") as mock_audit:
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        kw = mock_audit.record.call_args[1]
        assert kw["operation"] == "ssh_known_hosts_count_read"
        assert kw["details"]["count"] == 42


# ===================================================================
# SudoWrapperError 詳細メッセージ検証
# ===================================================================


class TestSSHKeysSudoWrapperErrorDetail:
    """SudoWrapperError のメッセージが detail に含まれる"""

    def test_keys_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            side_effect=SudoWrapperError("keys sudo failed"),
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 503
        assert "keys sudo failed" in resp.json().get("detail", resp.json().get("message", ""))

    def test_sshd_config_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            side_effect=SudoWrapperError("sshd sudo failed"),
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 503
        assert "sshd sudo failed" in resp.json().get("detail", resp.json().get("message", ""))

    def test_host_keys_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            side_effect=SudoWrapperError("host keys sudo failed"),
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 503
        assert "host keys sudo failed" in resp.json().get("detail", resp.json().get("message", ""))

    def test_known_hosts_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            side_effect=SudoWrapperError("known hosts sudo failed"),
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 503
        assert "known hosts sudo failed" in resp.json().get("detail", resp.json().get("message", ""))


# ===================================================================
# Exception (500) 詳細メッセージ検証
# ===================================================================


class TestSSHKeysExceptionDetail:
    """Exception のメッセージが detail に含まれる"""

    def test_keys_exception_detail(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            side_effect=TypeError("type error in keys"),
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 500
        assert "type error in keys" in resp.json().get("detail", resp.json().get("message", ""))

    def test_sshd_config_exception_detail(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            side_effect=ValueError("value error in sshd"),
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 500
        assert "value error in sshd" in resp.json().get("detail", resp.json().get("message", ""))

    def test_host_keys_exception_detail(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            side_effect=OSError("os error in host keys"),
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 500
        assert "os error in host keys" in resp.json().get("detail", resp.json().get("message", ""))

    def test_known_hosts_exception_detail(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            side_effect=IOError("io error in known hosts"),
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 500
        assert "io error in known hosts" in resp.json().get("detail", resp.json().get("message", ""))


# ===================================================================
# operator ロールのアクセステスト
# ===================================================================


class TestSSHKeysOperatorAccess:
    """operator ロールでの各エンドポイントアクセス"""

    def test_operator_keys(self, test_client, auth_headers):
        """operator は keys を取得できる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=KEYS_RESPONSE_DATA,
        ):
            resp = test_client.get("/api/ssh/keys", headers=auth_headers)
        assert resp.status_code == 200

    def test_operator_sshd_config(self, test_client, auth_headers):
        """operator は sshd-config を取得できる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            return_value=SSHD_CONFIG_DATA,
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=auth_headers)
        assert resp.status_code == 200

    def test_operator_host_keys(self, test_client, auth_headers):
        """operator は host-keys を取得できる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            return_value=HOST_KEYS_DATA,
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=auth_headers)
        assert resp.status_code == 200

    def test_operator_known_hosts_count(self, test_client, auth_headers):
        """operator は known-hosts-count を取得できる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            return_value=KNOWN_HOSTS_DATA,
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert resp.status_code == 200


# ===================================================================
# レスポンスモデルフィールド検証
# ===================================================================


class TestSSHKeysResponseModelFields:
    """レスポンスモデルの全フィールドが返される"""

    def test_keys_response_all_fields(self, test_client, admin_headers):
        """SSHKeysResponse: status, keys, count, ssh_dir, timestamp"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=KEYS_RESPONSE_DATA,
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "keys" in data
        assert "count" in data
        assert "ssh_dir" in data
        assert "timestamp" in data
        assert data["ssh_dir"] == "/etc/ssh"

    def test_sshd_config_response_all_fields(self, test_client, admin_headers):
        """SSHdConfigResponse: status, config_path, settings, timestamp"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            return_value=SSHD_CONFIG_DATA,
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["config_path"] == "/etc/ssh/sshd_config"
        assert isinstance(data["settings"], dict)

    def test_host_keys_response_all_fields(self, test_client, admin_headers):
        """SSHHostKeysResponse: status, host_keys, count, timestamp"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            return_value=HOST_KEYS_DATA,
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "host_keys" in data
        assert isinstance(data["host_keys"], list)
        hk = data["host_keys"][0]
        assert "key_type" in hk
        assert "bits" in hk
        assert "fingerprint" in hk
        assert "algorithm" in hk
        assert "file" in hk

    def test_known_hosts_response_all_fields(self, test_client, admin_headers):
        """SSHKnownHostsCountResponse: status, count, path, note, timestamp"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            return_value=KNOWN_HOSTS_DATA,
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "/etc/ssh/ssh_known_hosts"
        assert data["note"] == "内容は非表示（セキュリティポリシー）"
        assert data["count"] == 42


# ===================================================================
# admin ロールでの全エンドポイントテスト
# ===================================================================


class TestSSHKeysAdminAccess:
    """admin ロールでの各エンドポイントアクセス"""

    def test_admin_keys(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys",
            return_value=KEYS_RESPONSE_DATA,
        ):
            resp = test_client.get("/api/ssh/keys", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_sshd_config(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config",
            return_value=SSHD_CONFIG_DATA,
        ):
            resp = test_client.get("/api/ssh/sshd-config", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_host_keys(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys",
            return_value=HOST_KEYS_DATA,
        ):
            resp = test_client.get("/api/ssh/host-keys", headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_known_hosts_count(self, test_client, admin_headers):
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count",
            return_value=KNOWN_HOSTS_DATA,
        ):
            resp = test_client.get("/api/ssh/known-hosts-count", headers=admin_headers)
        assert resp.status_code == 200
