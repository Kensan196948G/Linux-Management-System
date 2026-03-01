"""
Bandwidth API エンドポイントのユニットテスト

backend/api/routes/bandwidth.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _mock_output(**kwargs):
    """テスト用モックデータ生成ヘルパー"""
    defaults = {"status": "ok", "timestamp": "2026-03-01T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


class TestGetInterfaces:
    """GET /api/bandwidth/interfaces テスト"""

    def test_interfaces_success(self, test_client, auth_headers):
        """正常系: インターフェース一覧取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.return_value = _mock_output(
                interfaces=["eth0", "lo"]
            )
            response = test_client.get("/api/bandwidth/interfaces", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "interfaces" in data

    def test_interfaces_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/interfaces", headers=auth_headers)
        assert response.status_code == 503

    def test_interfaces_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/bandwidth/interfaces")
        assert response.status_code == 403


class TestGetBandwidthSummary:
    """GET /api/bandwidth/summary テスト"""

    def test_summary_success_no_iface(self, test_client, auth_headers):
        """正常系: IF指定なしでサマリ取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.return_value = _mock_output(
                source="vnstat", rx_bytes=1024, tx_bytes=2048
            )
            response = test_client.get("/api/bandwidth/summary", headers=auth_headers)
        assert response.status_code == 200

    def test_summary_success_with_iface(self, test_client, auth_headers):
        """正常系: IF指定ありでサマリ取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.return_value = _mock_output(
                source="vnstat", interface="eth0"
            )
            response = test_client.get(
                "/api/bandwidth/summary?iface=eth0", headers=auth_headers
            )
        assert response.status_code == 200

    def test_summary_invalid_iface(self, test_client, auth_headers):
        """不正なインターフェース名"""
        response = test_client.get(
            "/api/bandwidth/summary?iface=eth0;rm+-rf+/", headers=auth_headers
        )
        assert response.status_code == 422

    def test_summary_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/summary", headers=auth_headers)
        assert response.status_code == 503


class TestGetBandwidthDaily:
    """GET /api/bandwidth/daily テスト"""

    def test_daily_success(self, test_client, auth_headers):
        """正常系: 日別統計取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_daily.return_value = _mock_output(
                source="vnstat", data=[]
            )
            response = test_client.get("/api/bandwidth/daily", headers=auth_headers)
        assert response.status_code == 200

    def test_daily_with_iface(self, test_client, auth_headers):
        """正常系: IF指定ありで日別統計取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_daily.return_value = _mock_output(
                source="vnstat", data=[]
            )
            response = test_client.get(
                "/api/bandwidth/daily?iface=eth0", headers=auth_headers
            )
        assert response.status_code == 200

    def test_daily_invalid_iface(self, test_client, auth_headers):
        """不正なインターフェース名"""
        response = test_client.get(
            "/api/bandwidth/daily?iface=a|b", headers=auth_headers
        )
        assert response.status_code == 422

    def test_daily_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_daily.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/daily", headers=auth_headers)
        assert response.status_code == 503


class TestGetBandwidthHourly:
    """GET /api/bandwidth/hourly テスト"""

    def test_hourly_success(self, test_client, auth_headers):
        """正常系: 時間別統計取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_hourly.return_value = _mock_output(
                source="vnstat", data=[]
            )
            response = test_client.get("/api/bandwidth/hourly", headers=auth_headers)
        assert response.status_code == 200

    def test_hourly_with_iface(self, test_client, auth_headers):
        """正常系: IF指定ありで時間別統計取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_hourly.return_value = _mock_output(
                source="vnstat", data=[]
            )
            response = test_client.get(
                "/api/bandwidth/hourly?iface=wlan0", headers=auth_headers
            )
        assert response.status_code == 200

    def test_hourly_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_hourly.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/hourly", headers=auth_headers)
        assert response.status_code == 503


class TestGetBandwidthLive:
    """GET /api/bandwidth/live テスト"""

    def test_live_success(self, test_client, auth_headers):
        """正常系: リアルタイム帯域幅取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_live.return_value = _mock_output(
                interface="eth0", rx_bps=1000, tx_bps=500, rx_kbps=1, tx_kbps=0
            )
            response = test_client.get("/api/bandwidth/live", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "rx_bps" in data

    def test_live_with_iface(self, test_client, auth_headers):
        """正常系: IF指定ありでライブ取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_live.return_value = _mock_output(
                interface="eth0", rx_bps=0, tx_bps=0, rx_kbps=0, tx_kbps=0
            )
            response = test_client.get(
                "/api/bandwidth/live?iface=eth0", headers=auth_headers
            )
        assert response.status_code == 200

    def test_live_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_live.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/live", headers=auth_headers)
        assert response.status_code == 503


class TestGetBandwidthTop:
    """GET /api/bandwidth/top テスト"""

    def test_top_success(self, test_client, auth_headers):
        """正常系: 全IFトラフィック取得"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_top.return_value = _mock_output(
                interfaces=[{"name": "eth0", "rx": 1000, "tx": 500}]
            )
            response = test_client.get("/api/bandwidth/top", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "interfaces" in data

    def test_top_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_top.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/bandwidth/top", headers=auth_headers)
        assert response.status_code == 503
