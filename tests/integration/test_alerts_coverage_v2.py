"""
alerts.py カバレッジ改善テスト v2

未カバー分岐を重点的にテスト:
- get_current_cpu_usage: /proc/stat読み取り例外パス、diff_t==0パス
- get_current_memory_usage: /proc/meminfo例外パス、パースロジック
- get_disk_usage_pct: total==0パス、statvfs例外パス
- get_load_average: /proc/loadavg例外パス
- get_active_alerts: lte comparison分岐、disabled rule分岐
- get_alerts_summary: 正常パスの全分岐
- stream_alerts: SSEイベント生成の内部例外パス、lte比較パス、val is None パス
- get_unread_count: 既読アラートの除外ロジック、disabled rule分岐
- mark_alert_read: 正常系、不正ID拒否
- mark_all_alerts_read: 正常系
- _read_alerts インメモリセットの状態管理
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch

import pytest

import backend.api.routes.alerts as alerts_module
from backend.api.routes.alerts import (
    DEFAULT_RULES,
    _read_alerts,
    get_current_cpu_usage,
    get_current_memory_usage,
    get_disk_usage_pct,
    get_load_average,
)


# ===================================================================
# get_current_cpu_usage 詳細テスト
# ===================================================================


class TestCpuUsageEdgeCases:
    """get_current_cpu_usage の未カバー分岐"""

    def test_cpu_diff_total_zero_returns_zero(self):
        """diff_t == 0 の場合 0.0 を返すこと (line 86)"""
        # 2回の読み取りで同じ値を返すと diff_t == 0
        fake_stat = "cpu  100 0 50 200 0 0 0 0 0 0\n"
        with patch("builtins.open", mock_open(read_data=fake_stat)):
            with patch("time.sleep"):
                result = get_current_cpu_usage()
        assert result == 0.0

    def test_cpu_proc_stat_exception_returns_zero(self):
        """read_cpu() 内で例外が発生した場合 (0, 0) を返し結果は 0.0 (line 77-78)"""
        with patch("builtins.open", side_effect=PermissionError("denied")):
            with patch("time.sleep"):
                result = get_current_cpu_usage()
        assert result == 0.0

    def test_cpu_normal_calculation(self):
        """正常な計算パス: 2回の /proc/stat 読み取りで使用率を算出"""
        call_count = 0

        def make_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            import io
            if call_count <= 1:
                return io.StringIO("cpu  100 0 50 200 0 0 0 0 0 0\n")
            else:
                return io.StringIO("cpu  200 0 100 300 0 0 0 0 0 0\n")

        with patch("builtins.open", side_effect=make_open):
            with patch("time.sleep"):
                result = get_current_cpu_usage()
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0


# ===================================================================
# get_current_memory_usage 詳細テスト
# ===================================================================


class TestMemoryUsageEdgeCases:
    """get_current_memory_usage の未カバー分岐"""

    def test_memory_exception_returns_zero(self):
        """例外時に 0.0 を返すこと (line 103-104)"""
        with patch("builtins.open", side_effect=OSError("no file")):
            result = get_current_memory_usage()
        assert result == 0.0

    def test_memory_missing_memavailable_uses_total(self):
        """MemAvailable が無い場合は total をフォールバック (line 100)"""
        fake_meminfo = "MemTotal:       8192000 kB\nMemFree:        1024000 kB\n"
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_current_memory_usage()
        # MemAvailable がないので available = total、used = 0、結果 0.0
        assert result == 0.0

    def test_memory_short_line_skipped(self):
        """len(parts) < 2 の行はスキップ (line 97)"""
        fake_meminfo = "SingleField\nMemTotal:       8192000 kB\nMemAvailable:   4096000 kB\n"
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            result = get_current_memory_usage()
        assert isinstance(result, float)
        assert result == 50.0


# ===================================================================
# get_disk_usage_pct 詳細テスト
# ===================================================================


class TestDiskUsageEdgeCases:
    """get_disk_usage_pct の未カバー分岐"""

    def test_disk_total_zero_returns_zero(self):
        """total == 0 の場合 0.0 を返すこと (line 113-114)"""
        mock_stat = MagicMock()
        mock_stat.f_blocks = 0
        mock_stat.f_bfree = 0
        mock_stat.f_frsize = 4096
        with patch("os.statvfs", return_value=mock_stat):
            result = get_disk_usage_pct("/")
        assert result == 0.0

    def test_disk_statvfs_exception_returns_zero(self):
        """statvfs 例外時に 0.0 を返すこと (line 116-117)"""
        with patch("os.statvfs", side_effect=OSError("no device")):
            result = get_disk_usage_pct("/nonexistent")
        assert result == 0.0


# ===================================================================
# get_load_average 詳細テスト
# ===================================================================


class TestLoadAverageEdgeCases:
    """get_load_average の未カバー分岐"""

    def test_load_exception_returns_zero(self):
        """例外時に 0.0 を返すこと (line 125-126)"""
        with patch("builtins.open", side_effect=FileNotFoundError("no proc")):
            result = get_load_average()
        assert result == 0.0


# ===================================================================
# get_active_alerts: lte比較 / disabled rule
# ===================================================================


class TestActiveAlertsComparisonBranches:
    """get_active_alerts の比較演算子分岐"""

    def test_lte_comparison_triggers_when_below(self, test_client, auth_headers):
        """comparison='lte' の場合、現在値が閾値以下でトリガーされること (line 153)"""
        lte_rules = [
            {
                "id": "load-low",
                "resource": "load",
                "threshold": 1.0,
                "comparison": "lte",
                "enabled": True,
                "description": "ロードアベレージ低すぎ",
            },
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", lte_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=20.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.5):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            resp = test_client.get("/api/alerts/active", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["active_alerts"][0]["id"] == "load-low"

    def test_lte_comparison_not_triggered_when_above(self, test_client, auth_headers):
        """comparison='lte' で現在値が閾値超過の場合トリガーされないこと"""
        lte_rules = [
            {
                "id": "load-low",
                "resource": "load",
                "threshold": 1.0,
                "comparison": "lte",
                "enabled": True,
                "description": "ロードアベレージ低すぎ",
            },
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", lte_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=20.0):
                    with patch.object(alerts_module, "get_load_average", return_value=5.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            resp = test_client.get("/api/alerts/active", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_disabled_rule_skipped(self, test_client, auth_headers):
        """enabled=False のルールはスキップされること (line 149)"""
        disabled_rules = [
            {
                "id": "cpu-disabled",
                "resource": "cpu",
                "threshold": 0.0,
                "comparison": "gte",
                "enabled": False,
                "description": "無効化されたルール",
            },
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", disabled_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=99.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            resp = test_client.get("/api/alerts/active", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ===================================================================
# get_unread_count 詳細テスト
# ===================================================================


class TestUnreadCount:
    """GET /api/alerts/unread-count の分岐テスト"""

    def setup_method(self):
        """各テスト前に _read_alerts をクリア"""
        _read_alerts.clear()

    def test_unread_count_all_unread(self, test_client, auth_headers):
        """全アラートが未読の場合の未読カウント"""
        _read_alerts.clear()
        low_rules = [
            {"id": "cpu-test", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "常時発火"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", low_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=50.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_unread_count_after_mark_read(self, test_client, auth_headers):
        """既読アラートは未読カウントに含まれないこと (line 287)"""
        _read_alerts.clear()
        _read_alerts.add("cpu-test")
        low_rules = [
            {"id": "cpu-test", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "常時発火"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", low_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=50.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_unread_count_disabled_rule_skipped(self, test_client, auth_headers):
        """enabled=False のルールは未読カウントに含まれない (line 282)"""
        _read_alerts.clear()
        disabled_rules = [
            {"id": "cpu-off", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": False, "description": "無効ルール"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", disabled_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=99.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_unread_count_lte_triggered_unread(self, test_client, auth_headers):
        """lte比較のルールが未読カウントに含まれること (line 286)"""
        _read_alerts.clear()
        lte_rules = [
            {"id": "load-low", "resource": "load", "threshold": 5.0, "comparison": "lte", "enabled": True, "description": "低負荷"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", lte_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=10.0):
                    with patch.object(alerts_module, "get_load_average", return_value=1.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_unread_count_no_auth(self, test_client):
        """未認証で403"""
        resp = test_client.get("/api/alerts/unread-count")
        assert resp.status_code == 403

    def test_unread_count_503_on_exception(self, test_client, auth_headers):
        """内部例外で503 (line 293-294)"""
        with patch.object(alerts_module, "get_current_cpu_usage", side_effect=RuntimeError("broken")):
            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 503

    def test_unread_count_http_exception_reraise(self, test_client, auth_headers):
        """HTTPException は再送出 (line 291-292)"""
        from fastapi import HTTPException
        with patch.object(alerts_module, "get_current_cpu_usage", side_effect=HTTPException(status_code=503, detail="upstream")):
            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 503


# ===================================================================
# mark_alert_read / mark_all_alerts_read
# ===================================================================


class TestMarkAlertRead:
    """POST /api/alerts/{alert_id}/mark-read テスト"""

    def setup_method(self):
        _read_alerts.clear()

    def test_mark_read_valid_alert(self, test_client, auth_headers):
        """有効なアラートIDで既読にできること (lines 305-312)"""
        resp = test_client.post("/api/alerts/cpu-high/mark-read", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_id"] == "cpu-high"
        assert data["read"] is True
        assert "cpu-high" in _read_alerts

    def test_mark_read_invalid_alert_returns_404(self, test_client, auth_headers):
        """不正なアラートIDで404を返すこと (line 302-303)"""
        resp = test_client.post("/api/alerts/nonexistent-alert/mark-read", headers=auth_headers)
        assert resp.status_code == 404
        body = resp.json()
        error_msg = body.get("detail", body.get("message", ""))
        assert "not found" in error_msg

    def test_mark_read_idempotent(self, test_client, auth_headers):
        """同じアラートを2回既読にしても問題ないこと"""
        test_client.post("/api/alerts/mem-high/mark-read", headers=auth_headers)
        resp = test_client.post("/api/alerts/mem-high/mark-read", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["read"] is True

    def test_mark_read_no_auth(self, test_client):
        """未認証で403"""
        resp = test_client.post("/api/alerts/cpu-high/mark-read")
        assert resp.status_code == 403

    def test_mark_read_all_valid_ids(self, test_client, auth_headers):
        """全ての有効なアラートIDで既読マーク可能"""
        valid_ids = [r["id"] for r in DEFAULT_RULES]
        for alert_id in valid_ids:
            resp = test_client.post(f"/api/alerts/{alert_id}/mark-read", headers=auth_headers)
            assert resp.status_code == 200


class TestMarkAllAlertsRead:
    """POST /api/alerts/mark-all-read テスト"""

    def setup_method(self):
        _read_alerts.clear()

    def test_mark_all_read_success(self, test_client, auth_headers):
        """全アラートを既読にできること (lines 318-326)"""
        resp = test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["marked"] == len(DEFAULT_RULES)
        assert data["read"] is True
        # 全アラートIDが _read_alerts に含まれること
        for rule in DEFAULT_RULES:
            assert rule["id"] in _read_alerts

    def test_mark_all_read_no_auth(self, test_client):
        """未認証で403"""
        resp = test_client.post("/api/alerts/mark-all-read")
        assert resp.status_code == 403

    def test_mark_all_then_unread_count_zero(self, test_client, auth_headers):
        """全既読後に未読カウントが0になること"""
        test_client.post("/api/alerts/mark-all-read", headers=auth_headers)
        # 全ルールを低閾値でトリガーさせても既読なのでカウント0
        low_rules = [
            {"id": "cpu-high", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "test"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", low_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=50.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            resp = test_client.get("/api/alerts/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ===================================================================
# stream_alerts 詳細テスト
# ===================================================================


class TestStreamAlertsDetailed:
    """GET /api/alerts/stream の詳細分岐テスト"""

    def test_stream_event_with_triggered_alerts(self, test_client, auth_headers):
        """SSEストリームでアクティブアラートが含まれること (lines 226-244)"""
        token = auth_headers["Authorization"].split(" ")[1]
        low_rules = [
            {"id": "cpu-test", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "常時発火"},
        ]

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with patch.object(alerts_module, "DEFAULT_RULES", low_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=50.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=20.0):
                    with patch.object(alerts_module, "get_load_average", return_value=1.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_sleep):
                                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        # connected + update イベントが含まれること
        assert "connected" in resp.text
        assert "update" in resp.text
        assert "cpu-test" in resp.text

    def test_stream_lte_comparison_in_generator(self, test_client, auth_headers):
        """SSEストリーム内の lte 比較分岐 (line 233-234)"""
        token = auth_headers["Authorization"].split(" ")[1]
        lte_rules = [
            {"id": "load-low", "resource": "load", "threshold": 5.0, "comparison": "lte", "enabled": True, "description": "低負荷"},
        ]

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with patch.object(alerts_module, "DEFAULT_RULES", lte_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=10.0):
                    with patch.object(alerts_module, "get_load_average", return_value=1.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_sleep):
                                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        assert "load-low" in resp.text

    def test_stream_disabled_rule_skipped_in_generator(self, test_client, auth_headers):
        """SSEストリーム内で disabled ルールがスキップされること (line 227)"""
        token = auth_headers["Authorization"].split(" ")[1]
        disabled_rules = [
            {"id": "cpu-off", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": False, "description": "無効ルール"},
        ]

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with patch.object(alerts_module, "DEFAULT_RULES", disabled_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=99.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=0.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=0.0):
                            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_sleep):
                                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        assert "cpu-off" not in resp.text

    def test_stream_unknown_resource_val_none(self, test_client, auth_headers):
        """SSEストリーム内で未知のresourceがNoneで処理されること (line 231)"""
        token = auth_headers["Authorization"].split(" ")[1]
        unknown_rules = [
            {"id": "unknown-res", "resource": "gpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "不明リソース"},
        ]

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with patch.object(alerts_module, "DEFAULT_RULES", unknown_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=10.0):
                    with patch.object(alerts_module, "get_load_average", return_value=1.0):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_sleep):
                                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        # unknown-res はトリガーされないはず（val is None → continue）
        assert "unknown-res" not in resp.text

    def test_stream_internal_exception_yields_error_event(self, test_client, auth_headers):
        """SSEストリーム内で例外が発生した場合にerrorイベントを送出 (line 255-256)"""
        token = auth_headers["Authorization"].split(" ")[1]

        call_count = 0

        def exploding_cpu():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            return 10.0

        async def _cancel_on_second(_):
            nonlocal call_count
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch.object(alerts_module, "get_current_cpu_usage", side_effect=exploding_cpu):
            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_on_second):
                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        assert "error" in resp.text
        assert "boom" in resp.text

    def test_stream_not_triggered_alert_excluded(self, test_client, auth_headers):
        """SSEストリームで閾値未満のアラートは含まれないこと"""
        token = auth_headers["Authorization"].split(" ")[1]
        high_rules = [
            {"id": "cpu-high", "resource": "cpu", "threshold": 99.0, "comparison": "gte", "enabled": True, "description": "超高閾値"},
        ]

        async def _cancel_sleep(_):
            raise asyncio.CancelledError()

        with patch.object(alerts_module, "DEFAULT_RULES", high_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=10.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=10.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.5):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=5.0):
                            with patch("backend.api.routes.alerts.asyncio.sleep", side_effect=_cancel_sleep):
                                resp = test_client.get(f"/api/alerts/stream?token={token}&interval=5")
        assert resp.status_code == 200
        # update イベントは出るが active_alerts は空
        text = resp.text
        assert "update" in text
        # active_alertsが空配列であることを確認
        for line in text.split("\n"):
            if "update" in line and "data:" in line:
                data_str = line.replace("data: ", "")
                try:
                    payload = json.loads(data_str)
                    if payload.get("type") == "update":
                        assert len(payload["active_alerts"]) == 0
                except (json.JSONDecodeError, KeyError):
                    pass
