"""
Network Configuration UI強化 - 統合テスト (v0.23)

対象エンドポイント:
  GET /api/network/interfaces-detail
  GET /api/network/dns-config
  GET /api/network/active-connections
"""

import sys

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ENV", "dev")


# ==============================================================================
# サンプルデータ
# ==============================================================================

SAMPLE_INTERFACES_DETAIL = {
    "status": "success",
    "interfaces": '[{"ifname":"eth0","operstate":"UP","addr_info":[{"local":"192.168.1.1"}]}]',
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_DNS_CONFIG = {
    "status": "success",
    "resolv_conf": "nameserver 8.8.8.8\nnameserver 8.8.4.4\nsearch example.com\n",
    "hosts": "127.0.0.1 localhost\n::1 localhost\n",
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_ACTIVE_CONNECTIONS = {
    "status": "success",
    "connections": "Netid State  Recv-Q Send-Q Local Address:Port\ntcp   LISTEN 0      128    0.0.0.0:22\n",
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# ローカルフィクスチャ（conftest.py にない viewer_headers）
# ==============================================================================


@pytest.fixture
def viewer_token(test_client):
    """viewer ユーザーの認証トークン"""
    response = test_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def viewer_headers(viewer_token):
    """viewer 認証ヘッダー"""
    return {"Authorization": f"Bearer {viewer_token}"}


# ==============================================================================
# interfaces-detail テスト
# ==============================================================================


class TestInterfacesDetail:
    """GET /api/network/interfaces-detail のテスト"""

    def test_interfaces_detail_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200

    def test_interfaces_detail_response_has_interfaces_key(self, test_client, auth_headers):
        """レスポンスに interfaces キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "interfaces" in data

    def test_interfaces_detail_response_has_timestamp_key(self, test_client, auth_headers):
        """レスポンスに timestamp キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200
        assert "timestamp" in response.json()

    def test_interfaces_detail_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/interfaces-detail")
        assert response.status_code in (401, 403)

    def test_interfaces_detail_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/interfaces-detail",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code in (401, 403)

    def test_interfaces_detail_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "command not found",
            }
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 503

    def test_interfaces_detail_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.side_effect = Exception("unexpected error")
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 503

    def test_interfaces_detail_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能 (read:network)"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# dns-config テスト
# ==============================================================================


class TestDnsConfig:
    """GET /api/network/dns-config のテスト"""

    def test_dns_config_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200

    def test_dns_config_response_has_resolv_conf_key(self, test_client, auth_headers):
        """レスポンスに resolv_conf キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200
        assert "resolv_conf" in response.json()

    def test_dns_config_response_has_hosts_key(self, test_client, auth_headers):
        """レスポンスに hosts キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200
        assert "hosts" in response.json()

    def test_dns_config_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/dns-config")
        assert response.status_code in (401, 403)

    def test_dns_config_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/dns-config",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code in (401, 403)

    def test_dns_config_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "permission denied",
            }
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 503

    def test_dns_config_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.side_effect = RuntimeError("dns error")
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 503

    def test_dns_config_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# active-connections テスト
# ==============================================================================


class TestActiveConnections:
    """GET /api/network/active-connections のテスト"""

    def test_active_connections_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200

    def test_active_connections_response_has_connections_key(self, test_client, auth_headers):
        """レスポンスに connections キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200
        assert "connections" in response.json()

    def test_active_connections_response_has_timestamp(self, test_client, auth_headers):
        """レスポンスに timestamp キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200
        assert "timestamp" in response.json()

    def test_active_connections_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/active-connections")
        assert response.status_code in (401, 403)

    def test_active_connections_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/active-connections",
            headers={"Authorization": "Bearer totally-invalid"},
        )
        assert response.status_code in (401, 403)

    def test_active_connections_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "ss: not found",
            }
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 503

    def test_active_connections_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.side_effect = Exception("connection error")
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 503

    def test_active_connections_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=viewer_headers)
        assert response.status_code == 200


class TestInterfacesDetail:
    """GET /api/network/interfaces-detail のテスト"""

    def test_interfaces_detail_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200

    def test_interfaces_detail_response_has_interfaces_key(self, test_client, auth_headers):
        """レスポンスに interfaces キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "interfaces" in data

    def test_interfaces_detail_response_has_timestamp_key(self, test_client, auth_headers):
        """レスポンスに timestamp キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 200
        assert "timestamp" in response.json()

    def test_interfaces_detail_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/interfaces-detail")
        assert response.status_code in (401, 403)

    def test_interfaces_detail_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/interfaces-detail",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code in (401, 403)

    def test_interfaces_detail_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "command not found",
            }
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 503

    def test_interfaces_detail_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.side_effect = Exception("unexpected error")
            response = test_client.get("/api/network/interfaces-detail", headers=auth_headers)
        assert response.status_code == 503

    def test_interfaces_detail_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能 (read:network)"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces_detail"
        ) as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_DETAIL
            response = test_client.get("/api/network/interfaces-detail", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# dns-config テスト
# ==============================================================================


class TestDnsConfig:
    """GET /api/network/dns-config のテスト"""

    def test_dns_config_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200

    def test_dns_config_response_has_resolv_conf_key(self, test_client, auth_headers):
        """レスポンスに resolv_conf キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200
        assert "resolv_conf" in response.json()

    def test_dns_config_response_has_hosts_key(self, test_client, auth_headers):
        """レスポンスに hosts キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 200
        assert "hosts" in response.json()

    def test_dns_config_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/dns-config")
        assert response.status_code in (401, 403)

    def test_dns_config_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/dns-config",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code in (401, 403)

    def test_dns_config_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "permission denied",
            }
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 503

    def test_dns_config_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.side_effect = RuntimeError("dns error")
            response = test_client.get("/api/network/dns-config", headers=auth_headers)
        assert response.status_code == 503

    def test_dns_config_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_dns_config"
        ) as mock_get:
            mock_get.return_value = SAMPLE_DNS_CONFIG
            response = test_client.get("/api/network/dns-config", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# active-connections テスト
# ==============================================================================


class TestActiveConnections:
    """GET /api/network/active-connections のテスト"""

    def test_active_connections_200_with_auth(self, test_client, auth_headers):
        """認証済みユーザーは 200 を受け取る"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200

    def test_active_connections_response_has_connections_key(self, test_client, auth_headers):
        """レスポンスに connections キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200
        assert "connections" in response.json()

    def test_active_connections_response_has_timestamp(self, test_client, auth_headers):
        """レスポンスに timestamp キーが含まれる"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 200
        assert "timestamp" in response.json()

    def test_active_connections_401_without_auth(self, test_client):
        """認証なしは 401/403 を返す"""
        response = test_client.get("/api/network/active-connections")
        assert response.status_code in (401, 403)

    def test_active_connections_401_invalid_token(self, test_client):
        """不正トークンは 401/403 を返す"""
        response = test_client.get(
            "/api/network/active-connections",
            headers={"Authorization": "Bearer totally-invalid"},
        )
        assert response.status_code in (401, 403)

    def test_active_connections_503_on_command_failure(self, test_client, auth_headers):
        """コマンド失敗時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = {
                "status": "error",
                "returncode": 1,
                "stdout": "",
                "stderr": "ss: not found",
            }
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 503

    def test_active_connections_503_on_exception(self, test_client, auth_headers):
        """例外発生時は 503 を返す"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.side_effect = Exception("connection error")
            response = test_client.get("/api/network/active-connections", headers=auth_headers)
        assert response.status_code == 503

    def test_active_connections_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_network_active_connections"
        ) as mock_get:
            mock_get.return_value = SAMPLE_ACTIVE_CONNECTIONS
            response = test_client.get("/api/network/active-connections", headers=viewer_headers)
        assert response.status_code == 200
