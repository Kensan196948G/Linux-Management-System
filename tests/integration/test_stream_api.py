"""
SSE ストリーミング API の統合テスト
"""

import json
from unittest.mock import patch, MagicMock

import pytest


class TestStreamSystemEndpoint:
    """GET /api/stream/system エンドポイント"""

    def test_stream_system_no_token_returns_422(self, test_client):
        """トークンなしは 422 (必須クエリパラメータ欠如)"""
        response = test_client.get("/api/stream/system")
        assert response.status_code == 422

    def test_stream_system_invalid_token_returns_401(self, test_client):
        """不正トークンは 401"""
        response = test_client.get("/api/stream/system?token=invalid.token.here")
        assert response.status_code == 401

    def test_stream_system_valid_token_returns_event_stream(self, test_client, auth_token):
        """有効トークンは text/event-stream を返す"""
        with test_client.stream("GET", f"/api/stream/system?token={auth_token}") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_system_response_contains_data(self, test_client, auth_token):
        """SSE レスポンスに data: フィールドが含まれる"""
        with test_client.stream("GET", f"/api/stream/system?token={auth_token}") as resp:
            assert resp.status_code == 200
            chunk = next(resp.iter_text())
            assert "data:" in chunk

    def test_stream_system_json_has_cpu_percent(self, test_client, auth_token):
        """SSE ペイロードに cpu_percent キーが含まれる"""
        with test_client.stream("GET", f"/api/stream/system?token={auth_token}") as resp:
            for chunk in resp.iter_text():
                if chunk.startswith("data:"):
                    payload = json.loads(chunk.removeprefix("data:").strip())
                    assert "cpu_percent" in payload
                    break


class TestStreamDashboardEndpoint:
    """GET /api/stream/dashboard エンドポイント"""

    def test_stream_dashboard_no_token_returns_422(self, test_client):
        """トークンなしは 422 (必須クエリパラメータ欠如)"""
        response = test_client.get("/api/stream/dashboard")
        assert response.status_code == 422

    def test_stream_dashboard_invalid_token_returns_401(self, test_client):
        """不正トークンは 401"""
        response = test_client.get("/api/stream/dashboard?token=invalid.token.here")
        assert response.status_code == 401

    def test_stream_dashboard_valid_token_returns_event_stream(self, test_client, auth_token):
        """有効トークンは text/event-stream を返す"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_dashboard_response_contains_data(self, test_client, auth_token):
        """SSE レスポンスに data: フィールドが含まれる"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            assert resp.status_code == 200
            chunk = next(resp.iter_text())
            assert "data:" in chunk

    def test_stream_dashboard_json_has_required_keys(self, test_client, auth_token):
        """SSE ペイロードに cpu / mem / net_in / net_out キーが含まれる"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            for chunk in resp.iter_text():
                if chunk.startswith("data:"):
                    payload = json.loads(chunk.removeprefix("data:").strip())
                    assert "cpu" in payload
                    assert "mem" in payload
                    assert "net_in" in payload
                    assert "net_out" in payload
                    break

    def test_stream_dashboard_cpu_is_float(self, test_client, auth_token):
        """cpu フィールドは数値型 (float/int)"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            for chunk in resp.iter_text():
                if chunk.startswith("data:"):
                    payload = json.loads(chunk.removeprefix("data:").strip())
                    assert isinstance(payload["cpu"], (int, float))
                    assert 0.0 <= payload["cpu"] <= 100.0
                    break

    def test_stream_dashboard_mem_is_float(self, test_client, auth_token):
        """mem フィールドは数値型 (0-100)"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            for chunk in resp.iter_text():
                if chunk.startswith("data:"):
                    payload = json.loads(chunk.removeprefix("data:").strip())
                    assert isinstance(payload["mem"], (int, float))
                    assert 0.0 <= payload["mem"] <= 100.0
                    break

    def test_stream_dashboard_net_in_non_negative(self, test_client, auth_token):
        """net_in は 0 以上の整数"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            for chunk in resp.iter_text():
                if chunk.startswith("data:"):
                    payload = json.loads(chunk.removeprefix("data:").strip())
                    assert payload["net_in"] >= 0
                    break

    def test_stream_dashboard_no_cache_headers(self, test_client, auth_token):
        """Cache-Control: no-cache ヘッダーが含まれる"""
        with test_client.stream("GET", f"/api/stream/dashboard?token={auth_token}") as resp:
            assert resp.headers.get("cache-control") == "no-cache"


class TestProcHelpers:
    """``/proc/`` 読み込みヘルパー関数のユニットテスト"""

    def test_calc_cpu_percent_idle(self):
        """idle が全 diff の場合 0%"""
        from backend.api.routes.stream import _calc_cpu_percent

        prev = {"user": 100, "nice": 0, "system": 0, "idle": 200, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}
        curr = {"user": 100, "nice": 0, "system": 0, "idle": 300, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}
        assert _calc_cpu_percent(prev, curr) == 0.0

    def test_calc_cpu_percent_full_load(self):
        """idle 変化なしの場合 100%"""
        from backend.api.routes.stream import _calc_cpu_percent

        prev = {"user": 0, "nice": 0, "system": 0, "idle": 100, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}
        curr = {"user": 200, "nice": 0, "system": 0, "idle": 100, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}
        assert _calc_cpu_percent(prev, curr) == 100.0

    def test_read_mem_percent_returns_float(self):
        """/proc/meminfo を読み取り 0-100 の float を返す"""
        from backend.api.routes.stream import _read_mem_percent

        result = _read_mem_percent()
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_read_net_bytes_returns_tuple(self):
        """/proc/net/dev を読み取り (rx, tx) タプルを返す"""
        from backend.api.routes.stream import _read_net_bytes

        rx, tx = _read_net_bytes()
        assert isinstance(rx, int)
        assert isinstance(tx, int)
        assert rx >= 0
        assert tx >= 0
