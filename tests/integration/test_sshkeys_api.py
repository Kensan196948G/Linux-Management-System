"""
SSH Keys モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest

# ==============================================================================
# テスト用サンプルデータ
# ==============================================================================

SAMPLE_KEYS_RESPONSE = {
    "status": "success",
    "keys": [
        {"filename": "ssh_host_rsa_key.pub", "key_type": "ssh-rsa", "comment": "root@server", "size_bytes": 564},
        {"filename": "ssh_host_ed25519_key.pub", "key_type": "ssh-ed25519", "comment": "root@server", "size_bytes": 82},
    ],
    "count": 2,
    "ssh_dir": "/etc/ssh",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SSHD_CONFIG_RESPONSE = {
    "status": "success",
    "config_path": "/etc/ssh/sshd_config",
    "settings": {
        "Port": "22",
        "PermitRootLogin": "prohibit-password",
        "PasswordAuthentication": "no",
        "PubkeyAuthentication": "yes",
        "MaxAuthTries": "6",
        "X11Forwarding": "no",
    },
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_HOST_KEYS_RESPONSE = {
    "status": "success",
    "host_keys": [
        {
            "key_type": "rsa",
            "bits": 3072,
            "fingerprint": "SHA256:abcdefghij1234567890",
            "algorithm": "RSA",
            "file": "/etc/ssh/ssh_host_rsa_key.pub",
        },
        {
            "key_type": "ed25519",
            "bits": 256,
            "fingerprint": "SHA256:zyxwvutsrq0987654321",
            "algorithm": "ED25519",
            "file": "/etc/ssh/ssh_host_ed25519_key.pub",
        },
    ],
    "count": 2,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_KNOWN_HOSTS_RESPONSE = {
    "status": "success",
    "authorized_keys_files": [],
    "count": 0,
    "note": "内容は非表示（セキュリティポリシー）",
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# 認証テスト（4件）
# ==============================================================================


class TestSSHKeysAuth:
    """認証なしアクセスのテスト（4件）"""

    def test_anonymous_keys_rejected(self, test_client):
        """認証なしで /api/ssh/keys は拒否される"""
        response = test_client.get("/api/ssh/keys")
        assert response.status_code == 403

    def test_anonymous_sshd_config_rejected(self, test_client):
        """認証なしで /api/ssh/sshd-config は拒否される"""
        response = test_client.get("/api/ssh/sshd-config")
        assert response.status_code == 403

    def test_anonymous_host_keys_rejected(self, test_client):
        """認証なしで /api/ssh/host-keys は拒否される"""
        response = test_client.get("/api/ssh/host-keys")
        assert response.status_code == 403

    def test_anonymous_known_hosts_count_rejected(self, test_client):
        """認証なしで /api/ssh/known-hosts-count は拒否される"""
        response = test_client.get("/api/ssh/known-hosts-count")
        assert response.status_code == 403


# ==============================================================================
# 公開鍵一覧テスト
# ==============================================================================


class TestSSHKeys:
    """GET /api/ssh/keys テスト"""

    def test_get_ssh_keys_success(self, test_client, auth_headers):
        """正常な公開鍵一覧取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys") as mock:
            mock.return_value = SAMPLE_KEYS_RESPONSE
            response = test_client.get("/api/ssh/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "keys" in data
        assert "count" in data
        assert data["count"] == 2
        assert "timestamp" in data

    def test_get_ssh_keys_viewer_access(self, test_client, viewer_headers):
        """viewer ロールは公開鍵一覧を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys") as mock:
            mock.return_value = SAMPLE_KEYS_RESPONSE
            response = test_client.get("/api/ssh/keys", headers=viewer_headers)
        assert response.status_code == 200

    def test_get_ssh_keys_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 時は 503 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/ssh/keys", headers=auth_headers)
        assert response.status_code == 503

    def test_get_ssh_keys_no_private_key_content(self, test_client, auth_headers):
        """公開鍵レスポンスに秘密鍵情報が含まれないこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys") as mock:
            mock.return_value = SAMPLE_KEYS_RESPONSE
            response = test_client.get("/api/ssh/keys", headers=auth_headers)
        assert response.status_code == 200
        response_text = response.text
        # 秘密鍵のヘッダーが含まれていないこと
        assert "BEGIN RSA PRIVATE KEY" not in response_text
        assert "BEGIN OPENSSH PRIVATE KEY" not in response_text
        assert "BEGIN EC PRIVATE KEY" not in response_text

    def test_get_ssh_keys_structure(self, test_client, auth_headers):
        """公開鍵エントリの構造が正しいこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_keys") as mock:
            mock.return_value = SAMPLE_KEYS_RESPONSE
            response = test_client.get("/api/ssh/keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for key in data["keys"]:
            assert "filename" in key
            assert "key_type" in key


# ==============================================================================
# sshd_config テスト
# ==============================================================================


class TestSSHdConfig:
    """GET /api/ssh/sshd-config テスト"""

    def test_get_sshd_config_success(self, test_client, auth_headers):
        """正常な sshd_config 設定取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config") as mock:
            mock.return_value = SAMPLE_SSHD_CONFIG_RESPONSE
            response = test_client.get("/api/ssh/sshd-config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "settings" in data
        assert "config_path" in data
        assert "timestamp" in data

    def test_sshd_config_no_passwords(self, test_client, auth_headers):
        """sshd_config に実際のパスワードや秘密情報が含まれないこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config") as mock:
            mock.return_value = SAMPLE_SSHD_CONFIG_RESPONSE
            response = test_client.get("/api/ssh/sshd-config", headers=auth_headers)
        assert response.status_code == 200
        response_text = response.text
        # パスワードハッシュ等の秘密情報が含まれていないこと
        assert "BEGIN RSA PRIVATE KEY" not in response_text
        assert "$6$" not in response_text  # shadow パスワードハッシュ形式

    def test_sshd_config_contains_safe_params(self, test_client, auth_headers):
        """sshd_config レスポンスに安全なパラメータが含まれること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config") as mock:
            mock.return_value = SAMPLE_SSHD_CONFIG_RESPONSE
            response = test_client.get("/api/ssh/sshd-config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        settings = data.get("settings", {})
        assert "Port" in settings

    def test_get_sshd_config_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 時は 503 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/ssh/sshd-config", headers=auth_headers)
        assert response.status_code == 503

    def test_get_sshd_config_viewer_access(self, test_client, viewer_headers):
        """viewer ロールは sshd_config を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_sshd_config") as mock:
            mock.return_value = SAMPLE_SSHD_CONFIG_RESPONSE
            response = test_client.get("/api/ssh/sshd-config", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# ホスト鍵フィンガープリントテスト
# ==============================================================================


class TestSSHHostKeys:
    """GET /api/ssh/host-keys テスト"""

    def test_get_host_keys_success(self, test_client, auth_headers):
        """正常なホスト鍵フィンガープリント取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys") as mock:
            mock.return_value = SAMPLE_HOST_KEYS_RESPONSE
            response = test_client.get("/api/ssh/host-keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "host_keys" in data
        assert "count" in data
        assert data["count"] == 2
        assert "timestamp" in data

    def test_host_keys_no_private_key(self, test_client, auth_headers):
        """ホスト鍵レスポンスに秘密鍵が含まれないこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys") as mock:
            mock.return_value = SAMPLE_HOST_KEYS_RESPONSE
            response = test_client.get("/api/ssh/host-keys", headers=auth_headers)
        assert response.status_code == 200
        response_text = response.text
        assert "BEGIN RSA PRIVATE KEY" not in response_text
        assert "BEGIN OPENSSH PRIVATE KEY" not in response_text

    def test_host_keys_fingerprint_structure(self, test_client, auth_headers):
        """フィンガープリントエントリの構造が正しいこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys") as mock:
            mock.return_value = SAMPLE_HOST_KEYS_RESPONSE
            response = test_client.get("/api/ssh/host-keys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for hk in data["host_keys"]:
            assert "key_type" in hk
            assert "fingerprint" in hk

    def test_get_host_keys_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 時は 503 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/ssh/host-keys", headers=auth_headers)
        assert response.status_code == 503

    def test_get_host_keys_viewer_access(self, test_client, viewer_headers):
        """viewer ロールはホスト鍵フィンガープリントを読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_ssh_host_keys") as mock:
            mock.return_value = SAMPLE_HOST_KEYS_RESPONSE
            response = test_client.get("/api/ssh/host-keys", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# known-hosts カウントテスト
# ==============================================================================


class TestSSHKnownHostsCount:
    """GET /api/ssh/known-hosts-count テスト"""

    def test_get_known_hosts_count_success(self, test_client, auth_headers):
        """正常な known-hosts カウント取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.return_value = SAMPLE_KNOWN_HOSTS_RESPONSE
            response = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "count" in data
        assert "timestamp" in data

    def test_known_hosts_count_only_no_content(self, test_client, auth_headers):
        """known-hosts は件数のみ返し、内容を返さないこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.return_value = SAMPLE_KNOWN_HOSTS_RESPONSE
            response = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # 「count」フィールドは存在するが「content」や「entries」フィールドはない
        assert "count" in data
        assert "content" not in data
        assert "entries" not in data
        assert "lines" not in data

    def test_known_hosts_note_present(self, test_client, auth_headers):
        """known-hosts レスポンスにセキュリティ注記が含まれること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.return_value = SAMPLE_KNOWN_HOSTS_RESPONSE
            response = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "note" in data

    def test_get_known_hosts_count_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 時は 503 を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert response.status_code == 503

    def test_get_known_hosts_count_viewer_access(self, test_client, viewer_headers):
        """viewer ロールは known-hosts カウントを読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.return_value = SAMPLE_KNOWN_HOSTS_RESPONSE
            response = test_client.get("/api/ssh/known-hosts-count", headers=viewer_headers)
        assert response.status_code == 200

    def test_known_hosts_count_is_integer(self, test_client, auth_headers):
        """カウントが整数値であること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_known_hosts_count") as mock:
            mock.return_value = SAMPLE_KNOWN_HOSTS_RESPONSE
            response = test_client.get("/api/ssh/known-hosts-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["count"], int)
