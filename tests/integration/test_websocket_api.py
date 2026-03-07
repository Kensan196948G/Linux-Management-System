"""
WebSocket API 統合テスト

/api/ws/system, /api/ws/processes, /api/ws/alerts の各エンドポイントを検証する。
"""

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("ENV", "dev")

from starlette.testclient import TestClient  # noqa: E402

from backend.api.main import app  # noqa: E402
from backend.core.auth import create_access_token  # noqa: E402
from backend.core.config import settings  # noqa: E402


# ===================================================================
# ヘルパー
# ===================================================================


def _make_token(role: str = "Admin", user_id: str = "test_user") -> str:
    """テスト用 JWT トークンを生成する。"""
    return create_access_token({"sub": user_id, "username": "testuser", "role": role, "email": "test@example.com"})


VALID_TOKEN = _make_token()
INVALID_TOKEN = "this.is.not.a.valid.token"


# ===================================================================
# /api/ws/system
# ===================================================================


class TestWsSystem:
    """システム情報 WebSocket エンドポイントのテスト群"""

    def test_ws_system_valid_token_connects(self):
        """/api/ws/system: 有効なトークンで接続でき、初回データを受信できること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert data["type"] == "system_update"

    def test_ws_system_data_has_required_fields(self):
        """/api/ws/system: レスポンスに cpu_percent など必須フィールドが含まれること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert "cpu_percent" in payload
                assert "memory_percent" in payload
                assert "memory_used_gb" in payload
                assert "memory_total_gb" in payload
                assert "disk_percent" in payload
                assert "disk_used_gb" in payload
                assert "disk_total_gb" in payload
                assert "load_avg" in payload
                assert "uptime_seconds" in payload

    def test_ws_system_timestamp_present(self):
        """/api/ws/system: timestamp フィールドが存在すること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert "timestamp" in data
                assert data["timestamp"].endswith("Z")

    def test_ws_system_invalid_token_rejected(self):
        """/api/ws/system: 無効なトークンは 4001 で切断されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(f"/api/ws/system?token={INVALID_TOKEN}") as ws:
                    ws.receive_json()

    def test_ws_system_missing_token_rejected(self):
        """/api/ws/system: トークン未指定は接続拒否されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/api/ws/system") as ws:
                    ws.receive_json()

    def test_ws_system_data_types(self):
        """/api/ws/system: 数値フィールドの型が正しいこと"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert isinstance(payload["cpu_percent"], (int, float))
                assert isinstance(payload["memory_percent"], (int, float))
                assert isinstance(payload["disk_percent"], (int, float))
                assert isinstance(payload["load_avg"], list)
                assert len(payload["load_avg"]) == 3
                assert isinstance(payload["uptime_seconds"], int)

    def test_ws_system_cpu_range(self):
        """/api/ws/system: CPU 使用率が 0〜100 の範囲内であること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                cpu = data["data"]["cpu_percent"]
                assert 0.0 <= cpu <= 100.0

    def test_ws_system_memory_values_positive(self):
        """/api/ws/system: メモリ値が正の数であること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert payload["memory_total_gb"] > 0
                assert payload["memory_used_gb"] >= 0

    def test_ws_system_viewer_role_accepted(self):
        """/api/ws/system: Viewer ロールでも接続できること"""
        token = _make_token(role="Viewer")
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/system?token={token}") as ws:
                data = ws.receive_json()
                assert data["type"] == "system_update"


# ===================================================================
# /api/ws/processes
# ===================================================================


class TestWsProcesses:
    """プロセス監視 WebSocket エンドポイントのテスト群"""

    def test_ws_processes_valid_token_connects(self):
        """/api/ws/processes: 有効なトークンで接続でき、初回データを受信できること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/processes?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert data["type"] == "processes_update"

    def test_ws_processes_data_structure(self):
        """/api/ws/processes: processes リストと total_count を含むこと"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/processes?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert "processes" in payload
                assert "total_count" in payload
                assert isinstance(payload["processes"], list)
                assert isinstance(payload["total_count"], int)

    def test_ws_processes_top10_limit(self):
        """/api/ws/processes: 返却プロセス数が最大 10 件であること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/processes?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert len(data["data"]["processes"]) <= 10

    def test_ws_processes_process_fields(self):
        """/api/ws/processes: 各プロセスに必須フィールドが含まれること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/processes?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                for proc in data["data"]["processes"]:
                    assert "pid" in proc
                    assert "name" in proc
                    assert "cpu_percent" in proc
                    assert "memory_percent" in proc
                    assert "status" in proc

    def test_ws_processes_invalid_token_rejected(self):
        """/api/ws/processes: 無効なトークンは拒否されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(f"/api/ws/processes?token={INVALID_TOKEN}") as ws:
                    ws.receive_json()

    def test_ws_processes_missing_token_rejected(self):
        """/api/ws/processes: トークン未指定は拒否されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/api/ws/processes") as ws:
                    ws.receive_json()

    def test_ws_processes_total_count_positive(self):
        """/api/ws/processes: total_count が正の整数であること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/processes?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert data["data"]["total_count"] > 0


# ===================================================================
# /api/ws/alerts
# ===================================================================


class TestWsAlerts:
    """アラート WebSocket エンドポイントのテスト群"""

    def test_ws_alerts_valid_token_connects(self):
        """/api/ws/alerts: 有効なトークンで接続でき、初回データを受信できること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/alerts?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert data["type"] == "alerts_update"

    def test_ws_alerts_data_structure(self):
        """/api/ws/alerts: alerts リストと count を含むこと"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/alerts?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert "alerts" in payload
                assert "count" in payload
                assert isinstance(payload["alerts"], list)
                assert isinstance(payload["count"], int)

    def test_ws_alerts_count_matches_list(self):
        """/api/ws/alerts: count が alerts リストの長さと一致すること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/alerts?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                payload = data["data"]
                assert payload["count"] == len(payload["alerts"])

    def test_ws_alerts_invalid_token_rejected(self):
        """/api/ws/alerts: 無効なトークンは拒否されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect(f"/api/ws/alerts?token={INVALID_TOKEN}") as ws:
                    ws.receive_json()

    def test_ws_alerts_missing_token_rejected(self):
        """/api/ws/alerts: トークン未指定は拒否されること"""
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/api/ws/alerts") as ws:
                    ws.receive_json()

    def test_ws_alerts_timestamp_present(self):
        """/api/ws/alerts: timestamp フィールドが存在すること"""
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/ws/alerts?token={VALID_TOKEN}") as ws:
                data = ws.receive_json()
                assert "timestamp" in data


# ===================================================================
# ConnectionManager
# ===================================================================


class TestConnectionManager:
    """ConnectionManager の単体テスト群"""

    @pytest.mark.asyncio
    async def test_manager_broadcast_sends_to_all(self):
        """broadcast: topic に接続中の全クライアントにメッセージを送信すること"""
        import asyncio

        from backend.api.routes.websocket import ConnectionManager

        mgr = ConnectionManager()

        # モック WebSocket を作成
        class MockWS:
            def __init__(self):
                self.sent = []
                self.client_state = None

        from fastapi.websockets import WebSocketState

        ws1, ws2 = MockWS(), MockWS()
        ws1.client_state = WebSocketState.CONNECTED
        ws2.client_state = WebSocketState.CONNECTED

        async def mock_send_json_1(msg):
            ws1.sent.append(msg)

        async def mock_send_json_2(msg):
            ws2.sent.append(msg)

        ws1.send_json = mock_send_json_1
        ws2.send_json = mock_send_json_2

        mgr.active_connections["test"] = [ws1, ws2]
        await mgr.broadcast("test", {"hello": "world"})

        assert ws1.sent == [{"hello": "world"}]
        assert ws2.sent == [{"hello": "world"}]

    @pytest.mark.asyncio
    async def test_manager_disconnect_removes_ws(self):
        """disconnect: topic から WebSocket が除去されること"""
        from backend.api.routes.websocket import ConnectionManager

        mgr = ConnectionManager()

        class MockWS:
            pass

        ws = MockWS()
        mgr.active_connections["topic"] = [ws]
        await mgr.disconnect(ws, "topic")
        assert ws not in mgr.active_connections.get("topic", [])

    @pytest.mark.asyncio
    async def test_manager_broadcast_unknown_topic(self):
        """broadcast: 未知の topic でもエラーにならないこと"""
        from backend.api.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        # Should not raise
        await mgr.broadcast("nonexistent_topic", {"msg": "test"})
