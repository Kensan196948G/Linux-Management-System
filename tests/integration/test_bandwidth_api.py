"""
帯域幅監視モジュール - 統合テスト

テストケース数: 20件
- 正常系: interfaces/summary/daily/hourly/live/top エンドポイント
- 異常系: 権限不足、未認証、不正インターフェース名
- セキュリティ: インジェクション拒否
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

IFACE_LIST = {
    "status": "ok",
    "interfaces": ["eth0", "eth1", "lo"],
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_SUMMARY_VNSTAT = {
    "status": "ok",
    "source": "vnstat",
    "data": {"interfaces": [{"name": "eth0", "traffic": {"total": {"rx": 1024, "tx": 512}}}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_SUMMARY_IP = {
    "status": "ok",
    "source": "ip",
    "interface": "eth0",
    "rx_bytes": 1073741824,
    "tx_bytes": 536870912,
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_DAILY = {
    "status": "ok",
    "source": "vnstat",
    "period": "daily",
    "data": {"interfaces": [{"name": "eth0", "traffic": {"day": []}}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_HOURLY = {
    "status": "ok",
    "source": "vnstat",
    "period": "hourly",
    "data": {"interfaces": [{"name": "eth0", "traffic": {"hour": []}}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_LIVE = {
    "status": "ok",
    "interface": "eth0",
    "rx_bps": 102400,
    "tx_bps": 51200,
    "rx_kbps": 100,
    "tx_kbps": 50,
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_TOP = {
    "status": "ok",
    "interfaces": [
        {"interface": "eth0", "rx_bytes": 1073741824, "tx_bytes": 536870912},
        {"interface": "eth1", "rx_bytes": 10240, "tx_bytes": 5120},
    ],
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_UNAVAILABLE = {
    "status": "unavailable",
    "message": "vnstat not installed. Install with: sudo apt-get install vnstat",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestBandwidthInterfaces:
    """GET /api/bandwidth/interfaces のテスト"""

    def test_list_interfaces_viewer(self, test_client, viewer_token):
        """TC_BW_001: Viewer ロールでインターフェース一覧取得成功"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_interfaces",
            return_value=IFACE_LIST,
        ):
            resp = test_client.get(
                "/api/bandwidth/interfaces",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["interfaces"], list)

    def test_interfaces_unauthenticated(self, test_client):
        """TC_BW_002: 未認証でインターフェース一覧拒否"""
        resp = test_client.get("/api/bandwidth/interfaces")
        assert resp.status_code in (401, 403)


class TestBandwidthSummary:
    """GET /api/bandwidth/summary のテスト"""

    def test_summary_vnstat(self, test_client, viewer_token):
        """TC_BW_003: vnstat でのサマリ取得成功"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_summary",
            return_value=BANDWIDTH_SUMMARY_VNSTAT,
        ):
            resp = test_client.get(
                "/api/bandwidth/summary",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["source"] == "vnstat"

    def test_summary_ip_fallback(self, test_client, viewer_token):
        """TC_BW_004: ip -s link フォールバックでのサマリ取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_summary",
            return_value=BANDWIDTH_SUMMARY_IP,
        ):
            resp = test_client.get(
                "/api/bandwidth/summary?iface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["rx_bytes"] is not None

    def test_summary_unavailable(self, test_client, viewer_token):
        """TC_BW_005: vnstat 未インストール時 unavailable を返す"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_summary",
            return_value=BANDWIDTH_UNAVAILABLE,
        ):
            resp = test_client.get(
                "/api/bandwidth/summary",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_summary_invalid_iface(self, test_client, viewer_token):
        """TC_BW_006: 不正なインターフェース名で 422 を返す"""
        resp = test_client.get(
            "/api/bandwidth/summary?iface=eth0;rm -rf /",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_summary_no_auth(self, test_client):
        """TC_BW_007: 未認証でサマリ拒否"""
        resp = test_client.get("/api/bandwidth/summary")
        assert resp.status_code in (401, 403)


class TestBandwidthDaily:
    """GET /api/bandwidth/daily のテスト"""

    def test_daily_all_interfaces(self, test_client, viewer_token):
        """TC_BW_008: 全インターフェースの日別統計取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_daily",
            return_value=BANDWIDTH_DAILY,
        ):
            resp = test_client.get(
                "/api/bandwidth/daily",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_daily_no_auth(self, test_client):
        """TC_BW_009: 未認証で日別統計拒否"""
        resp = test_client.get("/api/bandwidth/daily")
        assert resp.status_code in (401, 403)


class TestBandwidthHourly:
    """GET /api/bandwidth/hourly のテスト"""

    def test_hourly_all_interfaces(self, test_client, viewer_token):
        """TC_BW_010: 全インターフェースの時間別統計取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_hourly",
            return_value=BANDWIDTH_HOURLY,
        ):
            resp = test_client.get(
                "/api/bandwidth/hourly",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_hourly_no_auth(self, test_client):
        """TC_BW_011: 未認証で時間別統計拒否"""
        resp = test_client.get("/api/bandwidth/hourly")
        assert resp.status_code in (401, 403)


class TestBandwidthLive:
    """GET /api/bandwidth/live のテスト"""

    def test_live_default_iface(self, test_client, viewer_token):
        """TC_BW_012: デフォルトIFのリアルタイム帯域幅取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_live",
            return_value=BANDWIDTH_LIVE,
        ):
            resp = test_client.get(
                "/api/bandwidth/live",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "rx_bps" in data
        assert "tx_bps" in data

    def test_live_specific_iface(self, test_client, viewer_token):
        """TC_BW_013: 特定IFのリアルタイム帯域幅取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_live",
            return_value=BANDWIDTH_LIVE,
        ):
            resp = test_client.get(
                "/api/bandwidth/live?iface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_live_no_auth(self, test_client):
        """TC_BW_014: 未認証でリアルタイム帯域幅拒否"""
        resp = test_client.get("/api/bandwidth/live")
        assert resp.status_code in (401, 403)


class TestBandwidthTop:
    """GET /api/bandwidth/top のテスト"""

    def test_top_all_interfaces(self, test_client, viewer_token):
        """TC_BW_015: 全IF累積トラフィック取得"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_top",
            return_value=BANDWIDTH_TOP,
        ):
            resp = test_client.get(
                "/api/bandwidth/top",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert isinstance(data["interfaces"], list)

    def test_top_no_auth(self, test_client):
        """TC_BW_016: 未認証でトップトラフィック拒否"""
        resp = test_client.get("/api/bandwidth/top")
        assert resp.status_code in (401, 403)


class TestBandwidthSecurity:
    """セキュリティテスト"""

    def test_injection_iface_semicolon(self, test_client, viewer_token):
        """TC_BW_017: セミコロン注入を含む iface パラメータを拒否"""
        resp = test_client.get(
            "/api/bandwidth/summary?iface=eth0;whoami",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_injection_iface_pipe(self, test_client, viewer_token):
        """TC_BW_018: パイプ注入を含む iface パラメータを拒否"""
        resp = test_client.get(
            "/api/bandwidth/live?iface=eth0|id",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_injection_iface_dollar(self, test_client, viewer_token):
        """TC_BW_019: $ 注入を含む iface パラメータを拒否"""
        resp = test_client.get(
            "/api/bandwidth/daily?iface=$(cat /etc/passwd)",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_iface_too_long(self, test_client, viewer_token):
        """TC_BW_020: 長すぎるインターフェース名を拒否"""
        long_iface = "a" * 100
        resp = test_client.get(
            f"/api/bandwidth/summary?iface={long_iface}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


# ===================================================================
# 新規エンドポイント: history / monthly / alert-config
# ===================================================================

BANDWIDTH_HISTORY = {
    "status": "ok",
    "period": "history",
    "source": "vnstat",
    "data": {"interfaces": [{"name": "eth0", "traffic": {"total": {"rx": 10240, "tx": 5120}}}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_MONTHLY = {
    "status": "ok",
    "period": "monthly",
    "source": "vnstat",
    "data": {"interfaces": [{"name": "eth0", "traffic": {"month": []}}]},
    "timestamp": "2026-03-01T00:00:00Z",
}

BANDWIDTH_ALERT_CONFIG = {
    "threshold_gb": 100,
    "alert_email": "",
    "enabled": False,
}


class TestBandwidthHistory:
    """GET /api/bandwidth/history のテスト"""

    def test_history_success(self, test_client, viewer_token):
        """TC_BW_021: Viewer で帯域使用履歴取得成功"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_history",
            return_value=BANDWIDTH_HISTORY,
        ):
            resp = test_client.get(
                "/api/bandwidth/history?interface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_history_no_auth(self, test_client):
        """TC_BW_022: 未認証で帯域使用履歴拒否"""
        resp = test_client.get("/api/bandwidth/history")
        assert resp.status_code in (401, 403)

    def test_history_injection(self, test_client, viewer_token):
        """TC_BW_023: インジェクション文字を含むinterfaceパラメータを拒否"""
        resp = test_client.get(
            "/api/bandwidth/history?interface=eth0;evil",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_history_service_error(self, test_client, viewer_token):
        """TC_BW_024: コマンド失敗時に503を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_history",
            side_effect=SudoWrapperError("command failed"),
        ):
            resp = test_client.get(
                "/api/bandwidth/history?interface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_history_interface_too_long(self, test_client, viewer_token):
        """TC_BW_025: 長すぎるinterfaceパラメータを拒否"""
        long_iface = "a" * 100
        resp = test_client.get(
            f"/api/bandwidth/history?interface={long_iface}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422


class TestBandwidthMonthly:
    """GET /api/bandwidth/monthly のテスト"""

    def test_monthly_success(self, test_client, viewer_token):
        """TC_BW_026: Viewer で月次帯域使用量取得成功"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_monthly",
            return_value=BANDWIDTH_MONTHLY,
        ):
            resp = test_client.get(
                "/api/bandwidth/monthly?interface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_monthly_no_auth(self, test_client):
        """TC_BW_027: 未認証で月次帯域使用量拒否"""
        resp = test_client.get("/api/bandwidth/monthly")
        assert resp.status_code in (401, 403)

    def test_monthly_injection(self, test_client, viewer_token):
        """TC_BW_028: パイプ注入を含むinterfaceパラメータを拒否"""
        resp = test_client.get(
            "/api/bandwidth/monthly?interface=eth0|ls",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 422

    def test_monthly_service_error(self, test_client, viewer_token):
        """TC_BW_029: コマンド失敗時に503を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_monthly",
            side_effect=SudoWrapperError("command failed"),
        ):
            resp = test_client.get(
                "/api/bandwidth/monthly?interface=eth0",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503


class TestBandwidthAlertConfig:
    """GET /api/bandwidth/alert-config のテスト"""

    def test_alert_config_success(self, test_client, viewer_token):
        """TC_BW_030: Viewer でアラート設定取得成功"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_alert_config",
            return_value=BANDWIDTH_ALERT_CONFIG,
        ):
            resp = test_client.get(
                "/api/bandwidth/alert-config",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "threshold_gb" in data
        assert "enabled" in data

    def test_alert_config_no_auth(self, test_client):
        """TC_BW_031: 未認証でアラート設定拒否"""
        resp = test_client.get("/api/bandwidth/alert-config")
        assert resp.status_code in (401, 403)

    def test_alert_config_service_error(self, test_client, viewer_token):
        """TC_BW_032: コマンド失敗時に503を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_alert_config",
            side_effect=SudoWrapperError("command failed"),
        ):
            resp = test_client.get(
                "/api/bandwidth/alert-config",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 503

    def test_alert_config_response_structure(self, test_client, viewer_token):
        """TC_BW_033: アラート設定のレスポンス構造確認"""
        with patch(
            "backend.api.routes.bandwidth.sudo_wrapper.get_bandwidth_alert_config",
            return_value={"threshold_gb": 200, "alert_email": "admin@example.com", "enabled": True},
        ):
            resp = test_client.get(
                "/api/bandwidth/alert-config",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold_gb"] == 200
        assert data["alert_email"] == "admin@example.com"
        assert data["enabled"] is True
