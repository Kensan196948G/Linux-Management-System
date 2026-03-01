"""Netstat API テスト (TC_NST_001〜020)"""

import pytest
from unittest.mock import patch

from backend.core.sudo_wrapper import SudoWrapperError


class TestNetstatConnections:
    """アクティブ接続取得テスト"""

    def test_TC_NST_001_connections_success_admin(self, test_client, admin_token):
        """TC_NST_001: 接続一覧取得成功（admin）"""
        mock_data = {"connections": "State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port\n", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_connections", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "connections" in body["data"]

    def test_TC_NST_002_connections_viewer(self, test_client, viewer_token):
        """TC_NST_002: viewer でも接続一覧取得可能"""
        mock_data = {"connections": "", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_connections", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/connections",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_NST_003_connections_unauthenticated(self, test_client):
        """TC_NST_003: 未認証は拒否"""
        resp = test_client.get("/api/netstat/connections")
        assert resp.status_code in (401, 403)

    def test_TC_NST_004_connections_wrapper_error(self, test_client, admin_token):
        """TC_NST_004: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_connections",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/netstat/connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_NST_005_connections_tool_netstat(self, test_client, admin_token):
        """TC_NST_005: netstat ツール使用時のレスポンス"""
        mock_data = {"connections": "Active Internet connections...\n", "tool": "netstat"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_connections", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["tool"] == "netstat"


class TestNetstatListening:
    """リスニングポート取得テスト"""

    def test_TC_NST_006_listening_success(self, test_client, admin_token):
        """TC_NST_006: リスニングポート取得成功"""
        mock_data = {"listening": "Netid  State  Recv-Q  Send-Q  Local Address:Port\n", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_listening", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/listening",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "listening" in body["data"]

    def test_TC_NST_007_listening_viewer(self, test_client, viewer_token):
        """TC_NST_007: viewer でもリスニングポート取得可能"""
        mock_data = {"listening": "", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_listening", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/listening",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_NST_008_listening_unauthenticated(self, test_client):
        """TC_NST_008: 未認証は拒否"""
        resp = test_client.get("/api/netstat/listening")
        assert resp.status_code in (401, 403)

    def test_TC_NST_009_listening_wrapper_error(self, test_client, admin_token):
        """TC_NST_009: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_listening",
            side_effect=SudoWrapperError("listening error"),
        ):
            resp = test_client.get(
                "/api/netstat/listening",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_NST_010_listening_operator(self, test_client, auth_token):
        """TC_NST_010: operator でもリスニングポート取得可能"""
        mock_data = {"listening": "tcp   LISTEN  0  128  0.0.0.0:22  0.0.0.0:*\n", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_listening", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/listening",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200


class TestNetstatStats:
    """ネットワーク統計テスト"""

    def test_TC_NST_011_stats_success(self, test_client, admin_token):
        """TC_NST_011: 統計サマリ取得成功"""
        mock_data = {"stats": "Total: inet 10\nTCP:  estab 3, closed 7\n", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_stats", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/stats",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "stats" in body["data"]

    def test_TC_NST_012_stats_unauthenticated(self, test_client):
        """TC_NST_012: 未認証は拒否"""
        resp = test_client.get("/api/netstat/stats")
        assert resp.status_code in (401, 403)

    def test_TC_NST_013_stats_wrapper_error(self, test_client, admin_token):
        """TC_NST_013: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_stats",
            side_effect=SudoWrapperError("stats error"),
        ):
            resp = test_client.get(
                "/api/netstat/stats",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestNetstatRoutes:
    """ルーティングテーブルテスト"""

    def test_TC_NST_014_routes_success(self, test_client, admin_token):
        """TC_NST_014: ルーティングテーブル取得成功"""
        mock_data = {"routes": "default via 192.168.1.1 dev eth0\n192.168.1.0/24 dev eth0\n", "tool": "ip"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_routes", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/routes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "routes" in body["data"]

    def test_TC_NST_015_routes_viewer(self, test_client, viewer_token):
        """TC_NST_015: viewer でもルーティングテーブル取得可能"""
        mock_data = {"routes": "default via 10.0.0.1 dev ens3\n", "tool": "ip"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_routes", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/routes",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_NST_016_routes_unauthenticated(self, test_client):
        """TC_NST_016: 未認証は拒否"""
        resp = test_client.get("/api/netstat/routes")
        assert resp.status_code in (401, 403)

    def test_TC_NST_017_routes_wrapper_error(self, test_client, admin_token):
        """TC_NST_017: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.netstat.sudo_wrapper.get_netstat_routes",
            side_effect=SudoWrapperError("routes error"),
        ):
            resp = test_client.get(
                "/api/netstat/routes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_NST_018_routes_with_multiple_entries(self, test_client, admin_token):
        """TC_NST_018: 複数ルートエントリのレスポンス"""
        mock_data = {
            "routes": "default via 192.168.1.1 dev eth0\n10.0.0.0/8 via 10.0.0.1 dev eth1\n172.16.0.0/12 via 172.16.0.1 dev eth2\n",
            "tool": "ip",
        }
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_routes", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/routes",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "routes" in body["data"]

    def test_TC_NST_019_connections_empty(self, test_client, admin_token):
        """TC_NST_019: 接続一覧が空の場合"""
        mock_data = {"connections": "", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_connections", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["connections"] == ""

    def test_TC_NST_020_stats_approver(self, test_client, approver_token):
        """TC_NST_020: approver でも統計取得可能"""
        mock_data = {"stats": "Total: inet 5\n", "tool": "ss"}
        with patch("backend.api.routes.netstat.sudo_wrapper.get_netstat_stats", return_value=mock_data):
            resp = test_client.get(
                "/api/netstat/stats",
                headers={"Authorization": f"Bearer {approver_token}"},
            )
        assert resp.status_code == 200
