"""
SSH サーバー設定モジュール - 統合テスト

テスト項目:
  - GET /api/ssh/status (8件)
  - GET /api/ssh/config (12件)
  合計: 20件以上
"""

from unittest.mock import patch

import pytest


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_STATUS_RESPONSE = {
    "status": "success",
    "service": "sshd",
    "active_state": "active",
    "enabled_state": "enabled",
    "pid": "1234",
    "port": "22",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_STATUS_SSH_SERVICE = {
    "status": "success",
    "service": "ssh",
    "active_state": "active",
    "enabled_state": "enabled",
    "pid": "5678",
    "port": "2222",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_CONFIG_SAFE = {
    "status": "success",
    "config_path": "/etc/ssh/sshd_config",
    "settings": {
        "Port": "2222",
        "PermitRootLogin": "no",
        "PasswordAuthentication": "no",
        "PermitEmptyPasswords": "no",
        "PubkeyAuthentication": "yes",
        "AuthorizedKeysFile": ".ssh/authorized_keys",
    },
    "warnings": [],
    "warning_count": 0,
    "critical_count": 0,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_CONFIG_DANGEROUS = {
    "status": "success",
    "config_path": "/etc/ssh/sshd_config",
    "settings": {
        "Port": "22",
        "PermitRootLogin": "yes",
        "PasswordAuthentication": "yes",
        "PermitEmptyPasswords": "yes",
        "X11Forwarding": "yes",
    },
    "warnings": [
        {
            "key": "PermitRootLogin",
            "value": "yes",
            "level": "CRITICAL",
            "message": "rootログインが許可されています。",
        },
        {
            "key": "PasswordAuthentication",
            "value": "yes",
            "level": "WARNING",
            "message": "パスワード認証が有効です。",
        },
        {
            "key": "PermitEmptyPasswords",
            "value": "yes",
            "level": "CRITICAL",
            "message": "空パスワードが許可されています。",
        },
        {
            "key": "Port",
            "value": "22",
            "level": "LOW",
            "message": "デフォルトポート22を使用しています。",
        },
    ],
    "warning_count": 4,
    "critical_count": 2,
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_CONFIG_PERMISSION_ERROR = {
    "status": "error",
    "config_path": "/etc/ssh/sshd_config",
    "settings": {},
    "warnings": [],
    "warning_count": 0,
    "critical_count": 0,
    "message": "Permission denied reading sshd_config",
    "timestamp": "2026-01-01T00:00:00Z",
}


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def viewer_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


# ===================================================================
# GET /api/ssh/status
# ===================================================================


class TestSSHStatus:
    """SSHサービス状態取得テスト"""

    def test_status_success_active(self, client, auth_headers):
        """正常系: SSH稼働中"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value=SAMPLE_STATUS_RESPONSE,
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "sshd"
        assert data["active_state"] == "active"
        assert data["port"] == "22"

    def test_status_ssh_service(self, client, auth_headers):
        """正常系: ssh サービス名（Ubuntu）"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value=SAMPLE_STATUS_SSH_SERVICE,
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "ssh"
        assert data["port"] == "2222"

    def test_status_inactive(self, client, auth_headers):
        """正常系: SSH停止中"""
        inactive = {
            **SAMPLE_STATUS_RESPONSE,
            "active_state": "inactive",
            "pid": "0",
        }
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value=inactive,
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["active_state"] == "inactive"

    def test_status_no_auth(self, client):
        """異常系: 認証なし"""
        resp = client.get("/api/ssh/status")
        assert resp.status_code == 403

    def test_status_viewer_allowed(self, client, viewer_headers):
        """正常系: Viewerロールでもアクセス可能"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value=SAMPLE_STATUS_RESPONSE,
        ):
            resp = client.get("/api/ssh/status", headers=viewer_headers)
        assert resp.status_code == 200

    def test_status_wrapper_error(self, client, auth_headers):
        """異常系: wrapperエラー → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 503

    def test_status_unexpected_error(self, client, auth_headers):
        """異常系: 予期しないエラー → 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 500

    def test_status_response_fields(self, client, auth_headers):
        """正常系: レスポンスに必須フィールドが存在する"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value=SAMPLE_STATUS_RESPONSE,
        ):
            resp = client.get("/api/ssh/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for field in ["status", "service", "active_state", "enabled_state", "pid", "port", "timestamp"]:
            assert field in data, f"フィールド '{field}' がレスポンスに存在しない"


# ===================================================================
# GET /api/ssh/config
# ===================================================================


class TestSSHConfig:
    """SSH設定確認テスト"""

    def test_config_safe_settings(self, client, auth_headers):
        """正常系: 安全な設定（警告なし）"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_SAFE,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["warning_count"] == 0
        assert data["critical_count"] == 0
        assert len(data["warnings"]) == 0

    def test_config_dangerous_settings(self, client, auth_headers):
        """正常系: 危険設定あり（警告あり）"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_DANGEROUS,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["warning_count"] == 4
        assert data["critical_count"] == 2
        assert len(data["warnings"]) == 4

    def test_config_permit_root_login_warning(self, client, auth_headers):
        """正常系: PermitRootLogin=yes の警告がCRITICAL"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_DANGEROUS,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        root_login_warning = next(
            (w for w in warnings if w["key"] == "PermitRootLogin"), None
        )
        assert root_login_warning is not None
        assert root_login_warning["level"] == "CRITICAL"

    def test_config_password_auth_warning(self, client, auth_headers):
        """正常系: PasswordAuthentication=yes の警告がWARNING"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_DANGEROUS,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        warnings = resp.json()["warnings"]
        pw_warning = next(
            (w for w in warnings if w["key"] == "PasswordAuthentication"), None
        )
        assert pw_warning is not None
        assert pw_warning["level"] == "WARNING"

    def test_config_permission_error(self, client, auth_headers):
        """正常系: sshd_config 読み取り権限なし（エラーメッセージ返却）"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_PERMISSION_ERROR,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["message"] is not None

    def test_config_settings_content(self, client, auth_headers):
        """正常系: 設定内容にPort, PermitRootLoginが含まれる"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_SAFE,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        settings = resp.json()["settings"]
        assert "Port" in settings
        assert "PermitRootLogin" in settings

    def test_config_no_auth(self, client):
        """異常系: 認証なし"""
        resp = client.get("/api/ssh/config")
        assert resp.status_code == 403

    def test_config_viewer_allowed(self, client, viewer_headers):
        """正常系: ViewerロールもSSH設定読み取り可能"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_SAFE,
        ):
            resp = client.get("/api/ssh/config", headers=viewer_headers)
        assert resp.status_code == 200

    def test_config_wrapper_error(self, client, auth_headers):
        """異常系: wrapperエラー → 503"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 503

    def test_config_unexpected_error(self, client, auth_headers):
        """異常系: 予期しないエラー → 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 500

    def test_config_response_fields(self, client, auth_headers):
        """正常系: レスポンス必須フィールド確認"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_SAFE,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for field in ["status", "config_path", "settings", "warnings", "warning_count", "critical_count", "timestamp"]:
            assert field in data, f"フィールド '{field}' がレスポンスに存在しない"

    def test_config_config_path_returned(self, client, auth_headers):
        """正常系: config_pathが/etc/ssh/sshd_config"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value=SAMPLE_CONFIG_SAFE,
        ):
            resp = client.get("/api/ssh/config", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["config_path"] == "/etc/ssh/sshd_config"
