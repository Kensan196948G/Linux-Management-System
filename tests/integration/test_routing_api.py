"""
Routing & Gateways モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

from unittest.mock import patch

import pytest

# テスト用ルーティングデータ
SAMPLE_ROUTES_RESPONSE = {
    "status": "success",
    "routes": [
        {"destination": "default", "via": "192.168.1.1", "dev": "eth0", "proto": "static"},
        {"destination": "192.168.1.0/24", "dev": "eth0", "proto": "kernel", "scope": "link"},
        {"destination": "10.0.0.0/8", "via": "10.0.0.1", "dev": "eth1", "metric": "100"},
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_GATEWAYS_RESPONSE = {
    "status": "success",
    "gateways": [
        {"destination": "default", "via": "192.168.1.1", "dev": "eth0", "proto": "static"},
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_ARP_RESPONSE = {
    "status": "success",
    "arp": [
        {"ip": "192.168.1.1", "dev": "eth0", "mac": "00:11:22:33:44:55", "state": "REACHABLE"},
        {"ip": "192.168.1.100", "dev": "eth0", "mac": "aa:bb:cc:dd:ee:ff", "state": "STALE"},
        {"ip": "192.168.1.254", "dev": "eth0", "state": "FAILED"},
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_INTERFACES_RESPONSE = {
    "status": "success",
    "interfaces": [
        {
            "ifindex": 1,
            "ifname": "lo",
            "flags": ["LOOPBACK", "UP", "LOWER_UP"],
            "addr_info": [
                {"family": "inet", "local": "127.0.0.1", "prefixlen": "8", "scope": "host"}
            ],
        },
        {
            "ifindex": 2,
            "ifname": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            "addr_info": [
                {"family": "inet", "local": "192.168.1.50", "prefixlen": "24", "scope": "global"}
            ],
        },
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}


class TestRoutingAuth:
    """認証・権限テスト"""

    def test_anonymous_user_rejected_routes(self, test_client):
        response = test_client.get("/api/routing/routes")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_gateways(self, test_client):
        response = test_client.get("/api/routing/gateways")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_arp(self, test_client):
        response = test_client.get("/api/routing/arp")
        assert response.status_code == 403  # Bearer token required

    def test_anonymous_user_rejected_interfaces(self, test_client):
        response = test_client.get("/api/routing/interfaces")
        assert response.status_code == 403  # Bearer token required

    def test_viewer_can_read_routes(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_routes") as mock:
            mock.return_value = SAMPLE_ROUTES_RESPONSE
            response = test_client.get("/api/routing/routes", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_read_interfaces(self, test_client, viewer_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_interfaces") as mock:
            mock.return_value = SAMPLE_INTERFACES_RESPONSE
            response = test_client.get("/api/routing/interfaces", headers=viewer_headers)
        assert response.status_code == 200


class TestRoutingRoutes:
    """GET /api/routing/routes テスト"""

    def test_get_routes_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_routes") as mock:
            mock.return_value = SAMPLE_ROUTES_RESPONSE
            response = test_client.get("/api/routing/routes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["routes"], list)
        assert len(data["routes"]) == 3
        assert "timestamp" in data

    def test_get_routes_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_routes") as mock:
            mock.return_value = {
                "status": "success",
                "routes": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/routing/routes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["routes"] == []

    def test_get_routes_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_routes") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/routing/routes", headers=auth_headers)
        assert response.status_code == 500

    def test_get_routes_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_routes") as mock:
            mock.return_value = {"status": "error", "message": "ip command failed"}
            response = test_client.get("/api/routing/routes", headers=auth_headers)
        assert response.status_code == 503


class TestRoutingGateways:
    """GET /api/routing/gateways テスト"""

    def test_get_gateways_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_gateways") as mock:
            mock.return_value = SAMPLE_GATEWAYS_RESPONSE
            response = test_client.get("/api/routing/gateways", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["gateways"], list)
        assert len(data["gateways"]) == 1
        assert data["gateways"][0]["via"] == "192.168.1.1"

    def test_get_gateways_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_gateways") as mock:
            mock.return_value = {
                "status": "success",
                "gateways": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/routing/gateways", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["gateways"] == []

    def test_get_gateways_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_gateways") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/routing/gateways", headers=auth_headers)
        assert response.status_code == 500

    def test_get_gateways_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_gateways") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/routing/gateways", headers=auth_headers)
        assert response.status_code == 503


class TestRoutingArp:
    """GET /api/routing/arp テスト"""

    def test_get_arp_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_arp") as mock:
            mock.return_value = SAMPLE_ARP_RESPONSE
            response = test_client.get("/api/routing/arp", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["arp"], list)
        assert len(data["arp"]) == 3

    def test_get_arp_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_arp") as mock:
            mock.return_value = {
                "status": "success",
                "arp": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/routing/arp", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["arp"] == []

    def test_get_arp_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_arp") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/routing/arp", headers=auth_headers)
        assert response.status_code == 500

    def test_get_arp_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_arp") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/routing/arp", headers=auth_headers)
        assert response.status_code == 503


class TestRoutingInterfaces:
    """GET /api/routing/interfaces テスト"""

    def test_get_interfaces_success(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_interfaces") as mock:
            mock.return_value = SAMPLE_INTERFACES_RESPONSE
            response = test_client.get("/api/routing/interfaces", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["interfaces"], list)
        assert len(data["interfaces"]) == 2
        assert data["interfaces"][0]["ifname"] == "lo"

    def test_get_interfaces_empty(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_interfaces") as mock:
            mock.return_value = {
                "status": "success",
                "interfaces": [],
                "timestamp": "2026-01-01T00:00:00Z",
            }
            response = test_client.get("/api/routing/interfaces", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["interfaces"] == []

    def test_get_interfaces_wrapper_error(self, test_client, auth_headers):
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_interfaces") as mock:
            mock.side_effect = SudoWrapperError("wrapper failed")
            response = test_client.get("/api/routing/interfaces", headers=auth_headers)
        assert response.status_code == 500

    def test_get_interfaces_service_error(self, test_client, auth_headers):
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_routing_interfaces") as mock:
            mock.return_value = {"status": "error", "message": "failed"}
            response = test_client.get("/api/routing/interfaces", headers=auth_headers)
        assert response.status_code == 503
