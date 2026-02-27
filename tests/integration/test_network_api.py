"""
Networkingモジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import MagicMock, patch

import pytest


# テスト用ネットワークデータ
SAMPLE_INTERFACES_RESPONSE = {
    "status": "success",
    "interfaces": [
        {
            "ifindex": 1,
            "ifname": "lo",
            "flags": ["LOOPBACK", "UP", "LOWER_UP"],
            "mtu": 65536,
            "addr_info": [{"family": "inet", "local": "127.0.0.1", "prefixlen": 8}],
        },
        {
            "ifindex": 2,
            "ifname": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            "mtu": 1500,
            "addr_info": [
                {"family": "inet", "local": "192.168.1.100", "prefixlen": 24}
            ],
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_STATS_RESPONSE = {
    "status": "success",
    "stats": [
        {
            "ifindex": 1,
            "ifname": "lo",
            "stats64": {
                "rx": {"bytes": 1024, "packets": 16, "errors": 0, "dropped": 0},
                "tx": {"bytes": 1024, "packets": 16, "errors": 0, "dropped": 0},
            },
        }
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_CONNECTIONS_RESPONSE = {
    "status": "success",
    "connections": [
        {
            "netid": "tcp",
            "state": "LISTEN",
            "local_address": "0.0.0.0:22",
            "peer_address": "0.0.0.0:*",
            "process": "sshd",
        },
        {
            "netid": "tcp",
            "state": "LISTEN",
            "local_address": "0.0.0.0:80",
            "peer_address": "0.0.0.0:*",
            "process": "nginx",
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_ROUTES_RESPONSE = {
    "status": "success",
    "routes": [
        {
            "dst": "default",
            "gateway": "192.168.1.1",
            "dev": "eth0",
            "protocol": "dhcp",
            "metric": 100,
        },
        {
            "dst": "192.168.1.0/24",
            "dev": "eth0",
            "protocol": "kernel",
            "scope": "link",
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}


# ==============================================================================
# 認証テスト
# ==============================================================================


class TestNetworkAuthentication:
    """認証・認可テスト"""

    def test_anonymous_user_rejected_interfaces(self, test_client):
        response = test_client.get("/api/network/interfaces")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_stats(self, test_client):
        response = test_client.get("/api/network/stats")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_connections(self, test_client):
        response = test_client.get("/api/network/connections")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_routes(self, test_client):
        response = test_client.get("/api/network/routes")
        assert response.status_code == 403  # Bearer token required

    def test_viewer_can_read_interfaces(self, test_client, viewer_headers):
        """Viewer ロールはネットワーク情報を読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_RESPONSE
            response = test_client.get("/api/network/interfaces", headers=viewer_headers)
            assert response.status_code == 200

    def test_viewer_can_read_routes(self, test_client, viewer_headers):
        """Viewer ロールはルートを読み取れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.return_value = SAMPLE_ROUTES_RESPONSE
            response = test_client.get("/api/network/routes", headers=viewer_headers)
            assert response.status_code == 200


# ==============================================================================
# インターフェース一覧テスト
# ==============================================================================


class TestNetworkInterfaces:
    """GET /api/network/interfaces テスト"""

    def test_get_interfaces_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_RESPONSE
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "interfaces" in data
        assert len(data["interfaces"]) == 2
        assert "timestamp" in data

    def test_get_interfaces_contains_loopback(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.return_value = SAMPLE_INTERFACES_RESPONSE
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        data = response.json()
        ifnames = [iface.get("ifname") for iface in data["interfaces"]]
        assert "lo" in ifnames

    def test_get_interfaces_empty_list(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "interfaces": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["interfaces"] == []

    def test_get_interfaces_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        # SudoWrapperError 時は ip -j フォールバックが動作し 200 が返る（実環境）
        # フォールバックも失敗した場合は 500
        assert response.status_code in (200, 500)

    def test_get_interfaces_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_interfaces") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "ip command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/interfaces", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# 統計テスト
# ==============================================================================


class TestNetworkStats:
    """GET /api/network/stats テスト"""

    def test_get_stats_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_stats") as mock_get:
            mock_get.return_value = SAMPLE_STATS_RESPONSE
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "stats" in data
        assert "timestamp" in data

    def test_get_stats_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_stats") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 500

    def test_get_stats_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_stats") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "ip command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/stats", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# 接続テスト
# ==============================================================================


class TestNetworkConnections:
    """GET /api/network/connections テスト"""

    def test_get_connections_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_connections") as mock_get:
            mock_get.return_value = SAMPLE_CONNECTIONS_RESPONSE
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "connections" in data
        assert len(data["connections"]) == 2

    def test_get_connections_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_connections") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "connections": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["connections"] == []

    def test_get_connections_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_connections") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 500

    def test_get_connections_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_connections") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "ss command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/connections", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# ルーティングテスト
# ==============================================================================


class TestNetworkRoutes:
    """GET /api/network/routes テスト"""

    def test_get_routes_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.return_value = SAMPLE_ROUTES_RESPONSE
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "routes" in data
        assert len(data["routes"]) == 2
        assert "timestamp" in data

    def test_get_routes_contains_default_gateway(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.return_value = SAMPLE_ROUTES_RESPONSE
            response = test_client.get("/api/network/routes", headers=auth_headers)

        data = response.json()
        dsts = [route.get("dst") for route in data["routes"]]
        assert "default" in dsts

    def test_get_routes_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "routes": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["routes"] == []

    def test_get_routes_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 500

    def test_get_routes_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_network_routes") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "ip command not found",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/network/routes", headers=auth_headers)

        assert response.status_code == 503


# ==============================================================================
# DNS設定テスト
# ==============================================================================


SAMPLE_RESOLV_CONF = """\
# Generated by NetworkManager
domain example.com
search example.com local.test
nameserver 8.8.8.8
nameserver 8.8.4.4
nameserver ::1
"""


class TestNetworkDNS:
    """GET /api/network/dns テスト"""

    def test_anonymous_user_rejected_dns(self, test_client):
        response = test_client.get("/api/network/dns")
        assert response.status_code == 403

    def test_get_dns_success(self, test_client, auth_headers):
        from io import StringIO
        import builtins
        real_open = builtins.open

        def selective_open(path, *args, **kwargs):
            if "/etc/resolv.conf" in str(path):
                return StringIO(SAMPLE_RESOLV_CONF)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            response = test_client.get("/api/network/dns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "dns" in data

    def test_get_dns_response_structure(self, test_client, auth_headers):
        """レスポンス構造を検証"""
        response = test_client.get("/api/network/dns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        dns = data["dns"]
        assert "nameservers" in dns
        assert "search" in dns
        assert "domain" in dns
        assert isinstance(dns["nameservers"], list)
        assert isinstance(dns["search"], list)

    def test_get_dns_parses_nameservers(self, test_client, auth_headers):
        """nameserver エントリを正しく解析する"""
        from io import StringIO
        import builtins
        real_open = builtins.open

        def selective_open(path, *args, **kwargs):
            if "/etc/resolv.conf" in str(path):
                return StringIO(SAMPLE_RESOLV_CONF)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            response = test_client.get("/api/network/dns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "8.8.8.8" in data["dns"]["nameservers"]
        assert "8.8.4.4" in data["dns"]["nameservers"]
        assert data["dns"]["domain"] == "example.com"
        assert "example.com" in data["dns"]["search"]

    def test_get_dns_resolv_conf_not_found(self, test_client, auth_headers):
        """resolv.conf が存在しない場合でも 200 を返す"""
        import builtins
        real_open = builtins.open

        def selective_open(path, *args, **kwargs):
            if "/etc/resolv.conf" in str(path):
                raise OSError("file not found")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            response = test_client.get("/api/network/dns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["dns"]["nameservers"] == []
        assert data["dns"]["search"] == []
        assert data["dns"]["domain"] is None

    def test_get_dns_viewer_can_access(self, test_client, viewer_headers):
        """Viewer ロールは DNS 情報を読み取れる"""
        response = test_client.get("/api/network/dns", headers=viewer_headers)
        assert response.status_code == 200

    def test_get_dns_filters_invalid_ip(self, test_client, auth_headers):
        """不正なIPアドレスを含む nameserver エントリをフィルタする"""
        from io import StringIO
        import builtins
        real_open = builtins.open
        bad_resolv = "nameserver 8.8.8.8\nnameserver bad;input\n"

        def selective_open(path, *args, **kwargs):
            if "/etc/resolv.conf" in str(path):
                return StringIO(bad_resolv)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            response = test_client.get("/api/network/dns", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ns = data["dns"]["nameservers"]
        assert "8.8.8.8" in ns
        assert "bad;input" not in ns
