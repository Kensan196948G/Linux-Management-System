"""
bandwidth.py カバレッジ改善テスト v2

対象: backend/api/routes/bandwidth.py (全10エンドポイント)
既存テストで不足している分岐を網羅する。

カバー対象:
  - _validate_iface: 正常・異常パターン (parametrize)
  - 全エンドポイントの正常レスポンス構造詳細検証
  - iface 付き/なしの分岐
  - SudoWrapperError / ValueError 例外分岐
  - parse_wrapper_result の JSON パース成功・失敗分岐
  - audit_log 呼び出し検証
  - history/monthly/alert-config の全分岐
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ======================================================================
# ヘルパー
# ======================================================================


def _mock_wrapper_output(**kwargs):
    """sudo_wrapper 形式のモック出力 (output フィールドに JSON 文字列)"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


def _mock_raw_output(**kwargs):
    """parse_wrapper_result がそのまま返す形式（output なし）"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return defaults


# ======================================================================
# _validate_iface テスト
# ======================================================================


class TestValidateIface:
    """_validate_iface のパラメトライズテスト"""

    @pytest.mark.parametrize(
        "valid_iface",
        ["eth0", "wlan0", "enp0s3", "br-lan", "veth_abc.123", "lo"],
    )
    def test_valid_iface_names(self, test_client, admin_headers, valid_iface):
        """正当なインターフェース名は受理される"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.return_value = _mock_wrapper_output()
            resp = test_client.get(
                f"/api/bandwidth/summary?iface={valid_iface}",
                headers=admin_headers,
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "invalid_iface",
        [
            "eth0;rm -rf /",
            "eth0|id",
            "$(whoami)",
            "a" * 33,
            "eth 0",
        ],
    )
    def test_invalid_iface_names(self, test_client, admin_headers, invalid_iface):
        """不正なインターフェース名は 422 で拒否"""
        resp = test_client.get(
            f"/api/bandwidth/summary?iface={invalid_iface}",
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ======================================================================
# interfaces エンドポイント
# ======================================================================


class TestInterfacesCoverageV2:
    """GET /api/bandwidth/interfaces の追加カバレッジ"""

    def test_interfaces_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_interfaces.return_value = _mock_wrapper_output(
                    interfaces=["eth0"]
                )
                resp = test_client.get("/api/bandwidth/interfaces", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "bandwidth_interfaces_read"

    def test_interfaces_empty_list(self, test_client, admin_headers):
        """インターフェースが0件"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.return_value = _mock_wrapper_output(
                interfaces=[]
            )
            resp = test_client.get("/api/bandwidth/interfaces", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interfaces"] == []


# ======================================================================
# summary エンドポイント
# ======================================================================


class TestSummaryCoverageV2:
    """GET /api/bandwidth/summary の追加カバレッジ"""

    def test_summary_no_iface_audit_log(self, test_client, admin_headers):
        """iface未指定時の audit_log target は 'all'"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_summary.return_value = _mock_wrapper_output(
                    source="vnstat"
                )
                resp = test_client.get("/api/bandwidth/summary", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["target"] == "all"

    def test_summary_with_iface_audit_log(self, test_client, admin_headers):
        """iface指定時の audit_log target はインターフェース名"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_summary.return_value = _mock_wrapper_output(
                    source="ip", interface="eth0"
                )
                resp = test_client.get(
                    "/api/bandwidth/summary?iface=eth0", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["target"] == "eth0"

    def test_summary_value_error_503(self, test_client, admin_headers):
        """ValueError でも503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.side_effect = ValueError("bad data")
            resp = test_client.get("/api/bandwidth/summary", headers=admin_headers)
        assert resp.status_code == 503

    def test_summary_response_fields(self, test_client, admin_headers):
        """レスポンスの全フィールドが正しいこと"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_summary.return_value = _mock_wrapper_output(
                source="vnstat", rx_bytes=1024, tx_bytes=2048, message="ok", data={"x": 1}
            )
            resp = test_client.get("/api/bandwidth/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "vnstat"
        assert data["rx_bytes"] == 1024
        assert data["tx_bytes"] == 2048


# ======================================================================
# daily エンドポイント
# ======================================================================


class TestDailyCoverageV2:
    """GET /api/bandwidth/daily の追加カバレッジ"""

    def test_daily_value_error_503(self, test_client, admin_headers):
        """ValueError で503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_daily.side_effect = ValueError("parse error")
            resp = test_client.get("/api/bandwidth/daily", headers=admin_headers)
        assert resp.status_code == 503

    def test_daily_with_iface_audit(self, test_client, admin_headers):
        """iface指定時の audit_log"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_daily.return_value = _mock_wrapper_output(source="vnstat")
                resp = test_client.get(
                    "/api/bandwidth/daily?iface=wlan0", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["target"] == "wlan0"

    def test_daily_no_iface_interface_none(self, test_client, admin_headers):
        """iface未指定時のinterface はNone"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_daily.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get("/api/bandwidth/daily", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interface"] is None


# ======================================================================
# hourly エンドポイント
# ======================================================================


class TestHourlyCoverageV2:
    """GET /api/bandwidth/hourly の追加カバレッジ"""

    def test_hourly_value_error_503(self, test_client, admin_headers):
        """ValueError で503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_hourly.side_effect = ValueError("parse error")
            resp = test_client.get("/api/bandwidth/hourly", headers=admin_headers)
        assert resp.status_code == 503

    def test_hourly_iface_invalid(self, test_client, admin_headers):
        """不正なインターフェース名で422"""
        resp = test_client.get(
            "/api/bandwidth/hourly?iface=a;b", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_hourly_response_interface_field(self, test_client, admin_headers):
        """iface指定時のinterface フィールド"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_hourly.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get(
                "/api/bandwidth/hourly?iface=eth0", headers=admin_headers
            )
        assert resp.status_code == 200
        assert resp.json()["interface"] == "eth0"


# ======================================================================
# live エンドポイント
# ======================================================================


class TestLiveCoverageV2:
    """GET /api/bandwidth/live の追加カバレッジ"""

    def test_live_value_error_503(self, test_client, admin_headers):
        """ValueError で503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_live.side_effect = ValueError("parse error")
            resp = test_client.get("/api/bandwidth/live", headers=admin_headers)
        assert resp.status_code == 503

    def test_live_response_fields(self, test_client, admin_headers):
        """全レスポンスフィールドの確認"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_live.return_value = _mock_wrapper_output(
                interface="eth0", rx_bps=5000, tx_bps=3000, rx_kbps=5, tx_kbps=3
            )
            resp = test_client.get("/api/bandwidth/live", headers=admin_headers)
        data = resp.json()
        assert data["interface"] == "eth0"
        assert data["rx_bps"] == 5000
        assert data["tx_bps"] == 3000
        assert data["rx_kbps"] == 5
        assert data["tx_kbps"] == 3

    def test_live_invalid_iface(self, test_client, admin_headers):
        """不正なインターフェース名"""
        resp = test_client.get(
            "/api/bandwidth/live?iface=eth0$(id)", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_live_no_iface_audit_target(self, test_client, admin_headers):
        """iface未指定時のaudit target は 'default'"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_live.return_value = _mock_wrapper_output(
                    interface="", rx_bps=0, tx_bps=0, rx_kbps=0, tx_kbps=0
                )
                resp = test_client.get("/api/bandwidth/live", headers=admin_headers)
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["target"] == "default"


# ======================================================================
# top エンドポイント
# ======================================================================


class TestTopCoverageV2:
    """GET /api/bandwidth/top の追加カバレッジ"""

    def test_top_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_top.return_value = _mock_wrapper_output(
                    interfaces=[]
                )
                resp = test_client.get("/api/bandwidth/top", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "bandwidth_top_read"
        assert call_kwargs["target"] == "all"

    def test_top_empty_interfaces(self, test_client, admin_headers):
        """interfaces が空リストの場合"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_top.return_value = _mock_wrapper_output(interfaces=[])
            resp = test_client.get("/api/bandwidth/top", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interfaces"] == []


# ======================================================================
# history エンドポイント
# ======================================================================


class TestHistoryCoverageV2:
    """GET /api/bandwidth/history の追加カバレッジ"""

    def test_history_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_history.return_value = _mock_wrapper_output(
                    source="vnstat", data={}
                )
                resp = test_client.get(
                    "/api/bandwidth/history?interface=eth0", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "bandwidth_history_read"
        assert call_kwargs["target"] == "eth0"

    def test_history_value_error_503(self, test_client, admin_headers):
        """ValueError で503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_history.side_effect = ValueError("bad")
            resp = test_client.get(
                "/api/bandwidth/history?interface=eth0", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_history_response_interface_field(self, test_client, admin_headers):
        """interface フィールドがパラメータと一致"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_history.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get(
                "/api/bandwidth/history?interface=wlan0", headers=admin_headers
            )
        assert resp.status_code == 200
        assert resp.json()["interface"] == "wlan0"

    def test_history_default_interface(self, test_client, admin_headers):
        """デフォルトinterface (eth0)"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_history.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get("/api/bandwidth/history", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interface"] == "eth0"


# ======================================================================
# monthly エンドポイント
# ======================================================================


class TestMonthlyCoverageV2:
    """GET /api/bandwidth/monthly の追加カバレッジ"""

    def test_monthly_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_monthly.return_value = _mock_wrapper_output(
                    source="vnstat"
                )
                resp = test_client.get(
                    "/api/bandwidth/monthly?interface=eth0", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "bandwidth_monthly_read"

    def test_monthly_value_error_503(self, test_client, admin_headers):
        """ValueError で503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_monthly.side_effect = ValueError("bad")
            resp = test_client.get(
                "/api/bandwidth/monthly?interface=eth0", headers=admin_headers
            )
        assert resp.status_code == 503

    def test_monthly_response_interface(self, test_client, admin_headers):
        """interface フィールド"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_monthly.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get(
                "/api/bandwidth/monthly?interface=enp0s3", headers=admin_headers
            )
        assert resp.status_code == 200
        assert resp.json()["interface"] == "enp0s3"

    def test_monthly_default_interface(self, test_client, admin_headers):
        """デフォルトinterface (eth0)"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_monthly.return_value = _mock_wrapper_output(source="vnstat")
            resp = test_client.get("/api/bandwidth/monthly", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interface"] == "eth0"


# ======================================================================
# alert-config エンドポイント
# ======================================================================


class TestAlertConfigCoverageV2:
    """GET /api/bandwidth/alert-config の追加カバレッジ"""

    def test_alert_config_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.bandwidth.audit_log") as mock_audit:
            with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
                mock_sw.get_bandwidth_alert_config.return_value = _mock_wrapper_output(
                    threshold_gb=100, alert_email="", enabled=False
                )
                resp = test_client.get(
                    "/api/bandwidth/alert-config", headers=admin_headers
                )
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "bandwidth_alert_config_read"
        assert call_kwargs["target"] == "alert-config"

    def test_alert_config_all_fields(self, test_client, admin_headers):
        """全フィールドの確認"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_alert_config.return_value = _mock_wrapper_output(
                threshold_gb=500, alert_email="ops@example.com", enabled=True
            )
            resp = test_client.get(
                "/api/bandwidth/alert-config", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["threshold_gb"] == 500
        assert data["alert_email"] == "ops@example.com"
        assert data["enabled"] is True

    def test_alert_config_defaults(self, test_client, admin_headers):
        """デフォルト値の確認（キーが無い場合）"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_alert_config.return_value = _mock_wrapper_output()
            resp = test_client.get(
                "/api/bandwidth/alert-config", headers=admin_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold_gb"] == 100  # default
        assert data["enabled"] is False  # default


# ======================================================================
# パラメトライズ: 全エンドポイントの SudoWrapperError テスト
# ======================================================================


class TestBandwidthAllEndpointErrors:
    """全エンドポイントの SudoWrapperError テスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/bandwidth/interfaces", "get_bandwidth_interfaces"),
            ("/api/bandwidth/summary", "get_bandwidth_summary"),
            ("/api/bandwidth/daily", "get_bandwidth_daily"),
            ("/api/bandwidth/hourly", "get_bandwidth_hourly"),
            ("/api/bandwidth/live", "get_bandwidth_live"),
            ("/api/bandwidth/top", "get_bandwidth_top"),
            ("/api/bandwidth/history?interface=eth0", "get_bandwidth_history"),
            ("/api/bandwidth/monthly?interface=eth0", "get_bandwidth_monthly"),
            ("/api/bandwidth/alert-config", "get_bandwidth_alert_config"),
        ],
    )
    def test_sudo_wrapper_error_returns_503(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).side_effect = SudoWrapperError("fail")
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/bandwidth/interfaces",
            "/api/bandwidth/summary",
            "/api/bandwidth/daily",
            "/api/bandwidth/hourly",
            "/api/bandwidth/live",
            "/api/bandwidth/top",
            "/api/bandwidth/history",
            "/api/bandwidth/monthly",
            "/api/bandwidth/alert-config",
        ],
    )
    def test_unauthenticated(self, test_client, endpoint):
        """未認証で拒否"""
        resp = test_client.get(endpoint)
        assert resp.status_code in (401, 403)


# ======================================================================
# parse_wrapper_result 分岐カバレッジ
# ======================================================================


class TestParseWrapperResultIntegration:
    """parse_wrapper_result の JSON パース成功・失敗分岐"""

    def test_json_output_parsed(self, test_client, admin_headers):
        """output フィールドに正しい JSON がある場合パースされること"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.return_value = {
                "status": "success",
                "output": json.dumps(
                    {"status": "ok", "interfaces": ["eth0"], "timestamp": "2026-03-15T00:00:00Z"}
                ),
            }
            resp = test_client.get("/api/bandwidth/interfaces", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["interfaces"] == ["eth0"]

    def test_non_json_output_returns_raw(self, test_client, admin_headers):
        """output が不正な JSON の場合、result をそのまま返す"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.return_value = {
                "status": "ok",
                "output": "not-valid-json{{{",
                "interfaces": ["lo"],
                "timestamp": "2026-03-15T00:00:00Z",
            }
            resp = test_client.get("/api/bandwidth/interfaces", headers=admin_headers)
        assert resp.status_code == 200

    def test_no_output_field_returns_raw(self, test_client, admin_headers):
        """output フィールドがない場合、result をそのまま返す"""
        with patch("backend.api.routes.bandwidth.sudo_wrapper") as mock_sw:
            mock_sw.get_bandwidth_interfaces.return_value = {
                "status": "ok",
                "interfaces": ["eth0"],
                "timestamp": "2026-03-15T00:00:00Z",
            }
            resp = test_client.get("/api/bandwidth/interfaces", headers=admin_headers)
        assert resp.status_code == 200
