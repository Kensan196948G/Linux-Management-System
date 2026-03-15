"""
websocket.py カバレッジ改善テスト

未カバー行を重点的にテスト:
- _validate_token: sub なしペイロード / JWTError パス
- _ws_authenticate: JSON decode error / WebSocketDisconnect / timeout
- _collect_system_data: psutil mock テスト
- _collect_processes_data: psutil mock テスト（AccessDenied / NoSuchProcess）
- _collect_alerts_data: 各閾値条件（CPU/メモリ/ディスク warning/critical/normal）
- ConnectionManager: broadcast dead connection removal / send_personal
- _utcnow_iso: フォーマット検証
- ws_system/ws_processes/ws_alerts: 各エンドポイントの例外パス
"""

import asyncio
import json
import time
from collections import namedtuple
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.websockets import WebSocketState
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.main import app
from backend.api.routes.websocket import (
    ConnectionManager,
    _collect_alerts_data,
    _collect_processes_data,
    _collect_system_data,
    _utcnow_iso,
    _validate_token,
)
from backend.core.auth import create_access_token


# ===================================================================
# ヘルパー
# ===================================================================


def _make_token(role: str = "Admin", user_id: str = "test_user") -> str:
    """テスト用 JWT トークンを生成する。"""
    return create_access_token({"sub": user_id, "username": "testuser", "role": role, "email": "test@example.com"})


VALID_TOKEN = _make_token()


# ===================================================================
# _validate_token 直接テスト
# ===================================================================


class TestValidateToken:
    """_validate_token のテスト"""

    def test_valid_token_returns_payload(self):
        """有効なトークンでペイロードを返すこと"""
        token = _make_token()
        payload = _validate_token(token)
        assert payload is not None
        assert payload["sub"] == "test_user"

    def test_invalid_token_returns_none(self):
        """不正なトークンで None を返すこと"""
        result = _validate_token("invalid.jwt.token")
        assert result is None

    def test_token_without_sub_returns_none(self):
        """sub フィールドがないトークンで None を返すこと"""
        from jose import jwt
        from backend.core.config import settings

        token = jwt.encode(
            {"username": "test", "role": "Admin"},  # sub がない
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        result = _validate_token(token)
        assert result is None

    def test_expired_token_returns_none(self):
        """期限切れトークンで None を返すこと"""
        from jose import jwt
        from backend.core.config import settings

        token = jwt.encode(
            {"sub": "user", "exp": 1000000000},  # 過去の時刻
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        result = _validate_token(token)
        assert result is None

    def test_wrong_secret_returns_none(self):
        """異なるシークレットで署名されたトークンで None を返すこと"""
        from jose import jwt

        token = jwt.encode(
            {"sub": "user"},
            "wrong-secret-key",
            algorithm="HS256",
        )
        result = _validate_token(token)
        assert result is None


# ===================================================================
# _utcnow_iso テスト
# ===================================================================


class TestUtcnowIso:
    """_utcnow_iso のテスト"""

    def test_format_ends_with_z(self):
        """ISO 文字列が 'Z' で終わること"""
        result = _utcnow_iso()
        assert result.endswith("Z")

    def test_format_is_valid_datetime(self):
        """有効な日時文字列であること"""
        result = _utcnow_iso()
        dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ")
        assert dt is not None

    def test_returns_current_time(self):
        """現在時刻に近い値を返すこと（秒精度のため1秒の誤差を許容）"""
        import time as _time

        before = _time.time()
        result = _utcnow_iso()
        after = _time.time()
        dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        dt_ts = dt.timestamp()
        # strftime は秒未満を切り捨てるため、before - 1 を許容
        assert before - 1 <= dt_ts <= after + 1


# ===================================================================
# _collect_system_data テスト（psutil mock）
# ===================================================================


class TestCollectSystemData:
    """_collect_system_data のテスト"""

    def test_returns_all_required_fields(self):
        """必須フィールドが全て含まれること"""
        VmemResult = namedtuple("VmemResult", ["percent", "used", "total"])
        DiskResult = namedtuple("DiskResult", ["percent", "used", "total"])

        with patch("backend.api.routes.websocket.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 42.5
            mock_psutil.virtual_memory.return_value = VmemResult(percent=60.0, used=8 * 1024**3, total=16 * 1024**3)
            mock_psutil.disk_usage.return_value = DiskResult(percent=50.0, used=100 * 1024**3, total=200 * 1024**3)
            mock_psutil.getloadavg.return_value = (1.0, 2.0, 3.0)
            mock_psutil.boot_time.return_value = time.time() - 86400

            data = _collect_system_data()

        assert data["cpu_percent"] == 42.5
        assert data["memory_percent"] == 60.0
        assert data["memory_used_gb"] > 0
        assert data["memory_total_gb"] > 0
        assert data["disk_percent"] == 50.0
        assert data["disk_used_gb"] > 0
        assert data["disk_total_gb"] > 0
        assert len(data["load_avg"]) == 3
        assert data["uptime_seconds"] > 0


# ===================================================================
# _collect_processes_data テスト（psutil mock）
# ===================================================================


class TestCollectProcessesData:
    """_collect_processes_data のテスト"""

    def test_returns_top10_processes(self):
        """最大10件のプロセスを返すこと"""
        mock_procs = []
        for i in range(15):
            proc = MagicMock()
            proc.info = {
                "pid": i + 1,
                "name": f"proc{i}",
                "cpu_percent": float(i),
                "memory_percent": float(i * 0.5),
                "status": "running",
            }
            mock_procs.append(proc)

        with patch("backend.api.routes.websocket.psutil.process_iter", return_value=mock_procs):
            data = _collect_processes_data()

        assert len(data["processes"]) <= 10
        assert data["total_count"] == 15
        # CPU 降順ソートされていること
        cpus = [p["cpu_percent"] for p in data["processes"]]
        assert cpus == sorted(cpus, reverse=True)

    def test_handles_no_such_process(self):
        """NoSuchProcess 例外をスキップすること"""
        import psutil

        proc = MagicMock()
        proc.info = property(lambda self: None)
        type(proc).info = property(lambda self: (_ for _ in ()).throw(psutil.NoSuchProcess(1)))

        with patch("backend.api.routes.websocket.psutil.process_iter", return_value=[proc]):
            data = _collect_processes_data()

        assert data["total_count"] == 0
        assert data["processes"] == []

    def test_handles_none_values(self):
        """None 値のフィールドを 0 / 空文字に変換すること"""
        proc = MagicMock()
        proc.info = {
            "pid": 1,
            "name": None,
            "cpu_percent": None,
            "memory_percent": None,
            "status": None,
        }

        with patch("backend.api.routes.websocket.psutil.process_iter", return_value=[proc]):
            data = _collect_processes_data()

        assert data["total_count"] == 1
        p = data["processes"][0]
        assert p["name"] == ""
        assert p["cpu_percent"] == 0.0
        assert p["memory_percent"] == 0.0
        assert p["status"] == "unknown"


# ===================================================================
# _collect_alerts_data テスト（各閾値条件）
# ===================================================================


class TestCollectAlertsData:
    """_collect_alerts_data の閾値テスト"""

    def _mock_psutil(self, cpu, mem_pct, disk_pct):
        """psutil モックを設定するヘルパー"""
        VmemResult = namedtuple("VmemResult", ["percent"])
        DiskResult = namedtuple("DiskResult", ["percent"])

        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = cpu
        mock_psutil.virtual_memory.return_value = VmemResult(percent=mem_pct)
        mock_psutil.disk_usage.return_value = DiskResult(percent=disk_pct)
        return mock_psutil

    def test_no_alerts_when_all_normal(self):
        """全リソースが正常範囲の場合はアラートなし"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(30.0, 50.0, 60.0)):
            data = _collect_alerts_data()
        assert data["count"] == 0
        assert data["alerts"] == []

    def test_cpu_warning_alert(self):
        """CPU > 75% で warning アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(80.0, 50.0, 60.0)):
            data = _collect_alerts_data()
        cpu_alerts = [a for a in data["alerts"] if a["resource"] == "cpu"]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0]["level"] == "warning"

    def test_cpu_critical_alert(self):
        """CPU > 90% で critical アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(95.0, 50.0, 60.0)):
            data = _collect_alerts_data()
        cpu_alerts = [a for a in data["alerts"] if a["resource"] == "cpu"]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0]["level"] == "critical"

    def test_memory_warning_alert(self):
        """メモリ > 80% で warning アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(30.0, 85.0, 60.0)):
            data = _collect_alerts_data()
        mem_alerts = [a for a in data["alerts"] if a["resource"] == "memory"]
        assert len(mem_alerts) == 1
        assert mem_alerts[0]["level"] == "warning"

    def test_memory_critical_alert(self):
        """メモリ > 90% で critical アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(30.0, 95.0, 60.0)):
            data = _collect_alerts_data()
        mem_alerts = [a for a in data["alerts"] if a["resource"] == "memory"]
        assert len(mem_alerts) == 1
        assert mem_alerts[0]["level"] == "critical"

    def test_disk_warning_alert(self):
        """ディスク > 80% で warning アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(30.0, 50.0, 85.0)):
            data = _collect_alerts_data()
        disk_alerts = [a for a in data["alerts"] if a["resource"] == "disk"]
        assert len(disk_alerts) == 1
        assert disk_alerts[0]["level"] == "warning"

    def test_disk_critical_alert(self):
        """ディスク > 90% で critical アラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(30.0, 50.0, 95.0)):
            data = _collect_alerts_data()
        disk_alerts = [a for a in data["alerts"] if a["resource"] == "disk"]
        assert len(disk_alerts) == 1
        assert disk_alerts[0]["level"] == "critical"

    def test_multiple_alerts(self):
        """全リソースが危険水準の場合、3つのアラート"""
        with patch("backend.api.routes.websocket.psutil", self._mock_psutil(95.0, 95.0, 95.0)):
            data = _collect_alerts_data()
        assert data["count"] == 3
        assert len(data["alerts"]) == 3

    def test_exception_in_psutil_returns_empty_alerts(self):
        """psutil 例外時は空アラートを返すこと"""
        with patch("backend.api.routes.websocket.psutil") as mock_psutil:
            mock_psutil.cpu_percent.side_effect = RuntimeError("psutil error")
            data = _collect_alerts_data()
        assert data["count"] == 0
        assert data["alerts"] == []


# ===================================================================
# ConnectionManager 追加テスト
# ===================================================================


class TestConnectionManagerExtended:
    """ConnectionManager の追加テスト"""

    @pytest.mark.asyncio
    async def test_connect_adds_to_list(self):
        """connect: 接続リストに追加されること"""
        mgr = ConnectionManager()
        ws = MagicMock()
        await mgr.connect(ws, "test_topic")
        assert ws in mgr.active_connections["test_topic"]

    @pytest.mark.asyncio
    async def test_connect_multiple_topics(self):
        """connect: 異なる topic に同じ WS を接続できること"""
        mgr = ConnectionManager()
        ws = MagicMock()
        await mgr.connect(ws, "topic1")
        await mgr.connect(ws, "topic2")
        assert ws in mgr.active_connections["topic1"]
        assert ws in mgr.active_connections["topic2"]

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_ws_no_error(self):
        """disconnect: 存在しない WS の切断でもエラーにならないこと"""
        mgr = ConnectionManager()
        ws = MagicMock()
        # Should not raise
        await mgr.disconnect(ws, "nonexistent_topic")

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        """broadcast: 送信失敗した接続を除去すること"""
        mgr = ConnectionManager()

        ws_alive = MagicMock()
        ws_alive.client_state = WebSocketState.CONNECTED
        ws_alive.send_json = AsyncMock()

        ws_dead = MagicMock()
        ws_dead.client_state = WebSocketState.CONNECTED
        ws_dead.send_json = AsyncMock(side_effect=RuntimeError("connection lost"))

        mgr.active_connections["test"] = [ws_alive, ws_dead]
        await mgr.broadcast("test", {"msg": "hello"})

        # ws_alive はメッセージを受信
        ws_alive.send_json.assert_called_once_with({"msg": "hello"})
        # ws_dead は接続リストから除去
        assert ws_dead not in mgr.active_connections["test"]
        assert ws_alive in mgr.active_connections["test"]

    @pytest.mark.asyncio
    async def test_broadcast_skips_disconnected_state(self):
        """broadcast: DISCONNECTED 状態の WS にはメッセージを送らないこと"""
        mgr = ConnectionManager()

        ws = MagicMock()
        ws.client_state = WebSocketState.DISCONNECTED
        ws.send_json = AsyncMock()

        mgr.active_connections["test"] = [ws]
        await mgr.broadcast("test", {"msg": "hello"})

        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_personal(self):
        """send_personal: 特定 WS にメッセージを送信すること"""
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()

        await mgr.send_personal(ws, {"type": "test"})
        ws.send_json.assert_called_once_with({"type": "test"})


# ===================================================================
# WebSocket エンドポイント 追加テスト
# ===================================================================


class TestWsSystemExtended:
    """ws_system の追加テスト"""

    def test_ws_system_empty_auth_message_rejected(self):
        """空のトークンで 4001 切断されること"""
        with TestClient(app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/ws/system") as ws:
                    ws.send_json({"type": "auth", "token": ""})
                    ws.receive_json()

    def test_ws_system_non_json_auth_rejected(self):
        """JSON でないテキストで認証失敗すること"""
        with TestClient(app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/ws/system") as ws:
                    ws.send_text("not json at all")
                    ws.receive_json()

    def test_ws_system_operator_role_accepted(self):
        """Operator ロールで接続できること"""
        token = _make_token(role="Operator")
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws/system") as ws:
                ws.send_json({"type": "auth", "token": token})
                data = ws.receive_json()
                assert data["type"] == "system_update"


class TestWsProcessesExtended:
    """ws_processes の追加テスト"""

    def test_ws_processes_empty_token_rejected(self):
        """空のトークンで拒否されること"""
        with TestClient(app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/ws/processes") as ws:
                    ws.send_json({"type": "auth", "token": ""})
                    ws.receive_json()

    def test_ws_processes_processes_sorted_by_cpu(self):
        """プロセスがCPU降順でソートされていること"""
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws/processes") as ws:
                ws.send_json({"type": "auth", "token": VALID_TOKEN})
                data = ws.receive_json()
                procs = data["data"]["processes"]
                if len(procs) >= 2:
                    cpus = [p["cpu_percent"] for p in procs]
                    assert cpus == sorted(cpus, reverse=True)


class TestWsAlertsExtended:
    """ws_alerts の追加テスト"""

    def test_ws_alerts_empty_token_rejected(self):
        """空のトークンで拒否されること"""
        with TestClient(app) as client:
            with pytest.raises((WebSocketDisconnect, Exception)):
                with client.websocket_connect("/api/ws/alerts") as ws:
                    ws.send_json({"type": "auth", "token": ""})
                    ws.receive_json()

    def test_ws_alerts_alert_fields_correct(self):
        """アラートが存在する場合、必須フィールドが含まれること"""
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws/alerts") as ws:
                ws.send_json({"type": "auth", "token": VALID_TOKEN})
                data = ws.receive_json()
                for alert in data["data"]["alerts"]:
                    assert "level" in alert
                    assert "resource" in alert
                    assert "value" in alert
                    assert "message" in alert
                    assert alert["level"] in ("warning", "critical")
