"""
SSE ストリーミング API のユニットテスト

backend/api/routes/stream.py のカバレッジ向上
- _format_bytes: 純粋関数テスト
- /stream/system エンドポイント: 認証・SSEレスポンステスト
- system_event_generator: ジェネレーターの出力形式・値テスト
- _get_cpu_percent: 非同期ヘルパーテスト
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ========== _format_bytes テスト（純粋関数） ==========


class TestFormatBytes:
    """_format_bytes のユニットテスト"""

    def test_bytes(self):
        """バイト単位の表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        """キロバイト単位の表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        """メガバイト単位の表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        """ギガバイト単位の表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1024**3) == "1.0 GB"

    def test_terabytes(self):
        """テラバイト単位の表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1024**4) == "1.0 TB"

    def test_petabytes(self):
        """ペタバイト単位の表示（TBを超える値）"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1024**5) == "1.0 PB"

    def test_zero(self):
        """0バイトの表示"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(0) == "0.0 B"

    def test_small_kilobytes(self):
        """1KB未満の値"""
        from backend.api.routes.stream import _format_bytes

        assert _format_bytes(1023) == "1023.0 B"

    def test_exact_boundary(self):
        """境界値: ちょうど1024の倍数"""
        from backend.api.routes.stream import _format_bytes

        result = _format_bytes(1024 * 500)
        assert result == "500.0 KB"

    def test_fractional_value(self):
        """小数点以下が出る値"""
        from backend.api.routes.stream import _format_bytes

        result = _format_bytes(1536)  # 1.5 KB
        assert result == "1.5 KB"

    def test_large_gigabytes(self):
        """大きなGB値"""
        from backend.api.routes.stream import _format_bytes

        result = _format_bytes(8 * 1024**3)  # 8GB
        assert result == "8.0 GB"


# ========== /stream/system エンドポイントテスト ==========


class TestStreamSystem:
    """GET /api/stream/system エンドポイントテスト"""

    def test_missing_token_returns_422(self, test_client):
        """トークンなしは422を返す（Query必須パラメータ）"""
        response = test_client.get("/api/stream/system")
        assert response.status_code == 422

    def test_invalid_token_returns_401(self, test_client):
        """無効トークンは401を返す"""
        response = test_client.get("/api/stream/system?token=invalid_token_here")
        assert response.status_code == 401

    def test_valid_token_returns_200_sse(self, test_client, admin_token):
        """有効トークンは200とtext/event-streamを返す"""
        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024 * 1024 * 1024
        mock_mem.total = 8 * 1024 * 1024 * 1024

        # _get_cpu_percent と psutil.virtual_memory をモック
        # asyncio.sleep で StopAsyncIteration を発生させてジェネレーターを停止
        call_count = 0

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=25.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            side_effect=mock_sleep,
        ):
            response = test_client.get(
                f"/api/stream/system?token={admin_token}",
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_valid_token_response_contains_sse_data(self, test_client, admin_token):
        """SSEレスポンスにdata:フィールドが含まれる"""
        mock_mem = MagicMock()
        mock_mem.percent = 65.0
        mock_mem.used = 4 * 1024**3
        mock_mem.total = 16 * 1024**3

        call_count = 0

        async def mock_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=30.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            side_effect=mock_sleep,
        ):
            response = test_client.get(
                f"/api/stream/system?token={admin_token}",
            )

        body = response.text
        assert "data: " in body

        # SSEデータをパースして検証
        for line in body.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert "cpu_percent" in data
                assert "mem_percent" in data
                assert "mem_used" in data
                assert "mem_total" in data
                assert "timestamp" in data
                break

    def test_sse_response_headers(self, test_client, admin_token):
        """SSEレスポンスに適切なヘッダーが設定される"""
        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024**3
        mock_mem.total = 8 * 1024**3

        async def mock_sleep(seconds):
            raise asyncio.CancelledError()

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=10.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            side_effect=mock_sleep,
        ):
            response = test_client.get(
                f"/api/stream/system?token={admin_token}",
            )

        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"
        assert response.headers.get("x-accel-buffering") == "no"

    def test_expired_token_returns_401(self, test_client):
        """期限切れトークンは401を返す"""
        # 明示的に不正なJWT形式のトークン
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0IiwiZXhwIjoxfQ.invalid"
        response = test_client.get(
            f"/api/stream/system?token={expired_token}"
        )
        assert response.status_code == 401

    def test_empty_token_returns_401(self, test_client):
        """空文字トークンは401を返す"""
        response = test_client.get("/api/stream/system?token=")
        assert response.status_code == 401


# ========== system_event_generator テスト ==========


class TestSystemEventGenerator:
    """system_event_generator ジェネレーターのテスト"""

    @pytest.mark.asyncio
    async def test_generator_yields_sse_format(self, admin_token):
        """ジェネレーターがSSE形式のデータを返す"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024 * 1024 * 1024  # 1GB
        mock_mem.total = 8 * 1024 * 1024 * 1024  # 8GB

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=25.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            gen = system_event_generator(admin_token)
            event = await gen.__anext__()

        # SSE形式の検証
        assert event.startswith("data: ")
        assert event.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_generator_json_structure(self, admin_token):
        """ジェネレーターが正しいJSON構造を返す"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024 * 1024 * 1024
        mock_mem.total = 8 * 1024 * 1024 * 1024

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=25.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            gen = system_event_generator(admin_token)
            event = await gen.__anext__()

        # JSONパース
        data = json.loads(event[6:].strip())
        assert "cpu_percent" in data
        assert "mem_percent" in data
        assert "mem_used" in data
        assert "mem_total" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_generator_json_values(self, admin_token):
        """ジェネレーターの値が正しく反映される"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 75.5
        mock_mem.used = 2 * 1024 * 1024 * 1024  # 2GB
        mock_mem.total = 8 * 1024 * 1024 * 1024  # 8GB

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=42.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            gen = system_event_generator(admin_token)
            event = await gen.__anext__()

        data = json.loads(event[6:].strip())
        assert data["cpu_percent"] == 42.0
        assert data["mem_percent"] == 75.5
        assert data["mem_used"] == "2.0 GB"
        assert data["mem_total"] == "8.0 GB"

    @pytest.mark.asyncio
    async def test_generator_timestamp_format(self, admin_token):
        """タイムスタンプがISO 8601形式"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024**3
        mock_mem.total = 8 * 1024**3

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=10.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            gen = system_event_generator(admin_token)
            event = await gen.__anext__()

        data = json.loads(event[6:].strip())
        timestamp = data["timestamp"]
        # ISO 8601 形式: YYYY-MM-DDTHH:MM:SS+00:00
        assert "T" in timestamp
        assert "+" in timestamp or "Z" in timestamp

    @pytest.mark.asyncio
    async def test_generator_multiple_yields(self, admin_token):
        """複数回yieldされることを確認"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 60.0
        mock_mem.used = 4 * 1024**3
        mock_mem.total = 16 * 1024**3

        yield_count = 0

        async def mock_sleep(seconds):
            nonlocal yield_count
            yield_count += 1
            if yield_count >= 3:
                raise asyncio.CancelledError()

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=35.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            side_effect=mock_sleep,
        ):
            gen = system_event_generator(admin_token)
            events = []
            async for event in gen:
                events.append(event)

        # 3回yieldされてからCancelledErrorで停止
        assert len(events) == 3
        for event in events:
            assert event.startswith("data: ")
            data = json.loads(event[6:].strip())
            assert data["cpu_percent"] == 35.0

    @pytest.mark.asyncio
    async def test_generator_cancelled_error_handled(self, admin_token):
        """CancelledError（クライアント切断）が正常にハンドリングされる"""
        from backend.api.routes.stream import system_event_generator

        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_mem.used = 1024**3
        mock_mem.total = 8 * 1024**3

        with patch(
            "backend.api.routes.stream._get_cpu_percent",
            new_callable=AsyncMock,
            return_value=20.0,
        ), patch(
            "backend.api.routes.stream.psutil.virtual_memory",
            return_value=mock_mem,
        ), patch(
            "backend.api.routes.stream.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            gen = system_event_generator(admin_token)
            events = []
            async for event in gen:
                events.append(event)

        # 1回yieldしてsleepでCancelledError、正常終了
        assert len(events) == 1


# ========== _get_cpu_percent テスト ==========


class TestGetCpuPercent:
    """_get_cpu_percent 非同期ヘルパーのテスト"""

    @pytest.mark.asyncio
    async def test_returns_float(self):
        """CPU使用率をfloatで返す"""
        from backend.api.routes.stream import _get_cpu_percent

        with patch(
            "backend.api.routes.stream.psutil.cpu_percent",
            return_value=45.0,
        ), patch(
            "backend.api.routes.stream.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=45.0,
        ):
            result = await _get_cpu_percent()

        assert isinstance(result, float)
        assert result == 45.0

    @pytest.mark.asyncio
    async def test_returns_zero(self):
        """CPU使用率0%のケース"""
        from backend.api.routes.stream import _get_cpu_percent

        with patch(
            "backend.api.routes.stream.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            result = await _get_cpu_percent()

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_high_usage(self):
        """CPU使用率100%のケース"""
        from backend.api.routes.stream import _get_cpu_percent

        with patch(
            "backend.api.routes.stream.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=100.0,
        ):
            result = await _get_cpu_percent()

        assert result == 100.0


# ========== _read_cpu_times テスト ==========


class TestReadCpuTimes:
    """`_read_cpu_times` のユニットテスト"""

    def test_returns_dict_with_cpu_keys(self):
        """/proc/stat を読み取り CPU タイムのdictを返す"""
        from backend.api.routes.stream import _read_cpu_times

        FAKE_PROC_STAT = "cpu  100 20 30 400 10 5 2 1\ncpu0 50 10 15 200 5 2 1 0\n"
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                readline=MagicMock(return_value="cpu  100 20 30 400 10 5 2 1\n")
            )),
            __exit__=MagicMock(return_value=False),
        )):
            result = _read_cpu_times()

        assert isinstance(result, dict)
        for key in ["user", "nice", "system", "idle"]:
            assert key in result

    def test_values_are_integers(self):
        """取得値が整数であること"""
        from backend.api.routes.stream import _read_cpu_times

        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                readline=MagicMock(return_value="cpu  123 456 789 1000 50 0 0 0\n")
            )),
            __exit__=MagicMock(return_value=False),
        )):
            result = _read_cpu_times()

        assert result["user"] == 123
        assert result["nice"] == 456
        assert result["system"] == 789
        assert result["idle"] == 1000

    def test_missing_fields_padded_with_zero(self):
        """フィールドが不足している場合は0でパディングされる"""
        from backend.api.routes.stream import _read_cpu_times

        # iowait以降が省略されたケース
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                readline=MagicMock(return_value="cpu  100 20 30 400\n")
            )),
            __exit__=MagicMock(return_value=False),
        )):
            result = _read_cpu_times()

        assert result["user"] == 100
        assert result["idle"] == 400
        # 不足分は0
        assert result.get("steal", 0) == 0

    def test_real_proc_stat(self):
        """実際の /proc/stat から読み取れること（統合テスト）"""
        from backend.api.routes.stream import _read_cpu_times

        result = _read_cpu_times()
        assert isinstance(result, dict)
        assert "user" in result
        assert "idle" in result
        assert all(isinstance(v, int) for v in result.values())


# ========== _read_mem_percent エッジケーステスト ==========


class TestReadMemPercentEdgeCases:
    """`_read_mem_percent` のエッジケーステスト"""

    def test_zero_total_returns_zero(self):
        """MemTotal == 0 のとき 0.0 を返す（ゼロ除算回避）"""
        from backend.api.routes.stream import _read_mem_percent

        fake_meminfo = "MemTotal:          0 kB\nMemAvailable:      0 kB\n"
        import io
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=io.StringIO(fake_meminfo)),
            __exit__=MagicMock(return_value=False),
        )):
            result = _read_mem_percent()

        assert result == 0.0

    def test_normal_values(self):
        """通常の値を正しく計算する"""
        from backend.api.routes.stream import _read_mem_percent

        # Total=4096kB, Available=1024kB → 使用=3072kB → 75%
        fake_meminfo = "MemTotal:       4096 kB\nMemAvailable:   1024 kB\nMemFree:         512 kB\n"
        import io
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=io.StringIO(fake_meminfo)),
            __exit__=MagicMock(return_value=False),
        )):
            result = _read_mem_percent()

        assert result == 75.0


# ========== _read_net_bytes エッジケーステスト ==========


class TestReadNetBytesEdgeCases:
    """`_read_net_bytes` のエッジケーステスト"""

    def test_skip_short_lines(self):
        """パーツが10未満の行をスキップする（line 117 カバレッジ）"""
        from backend.api.routes.stream import _read_net_bytes

        # 先頭2行はヘッダとして無視、3行目以降が対象
        # 短い行（パーツ<10）はスキップされる
        fake_net_dev = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets\n"
            " eth0:  short\n"  # パーツ < 10 → スキップ
            "   lo:  100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0\n"  # loopback → スキップ
            " eth1: 1000 10 0 0 0 0 0 0 2000 20 0 0 0 0 0 0\n"  # 有効
        )
        import io
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=io.StringIO(fake_net_dev)),
            __exit__=MagicMock(return_value=False),
        )):
            rx, tx = _read_net_bytes()

        # eth1 のみカウント (eth0はスキップ, loはスキップ)
        assert rx == 1000
        assert tx == 2000

    def test_loopback_excluded(self):
        """ループバックインターフェース (lo) は除外される"""
        from backend.api.routes.stream import _read_net_bytes

        fake_net_dev = (
            "header line 1\n"
            "header line 2\n"
            "   lo:  999 9 0 0 0 0 0 0 999 9 0 0 0 0 0 0\n"  # lo → スキップ
        )
        import io
        with patch("builtins.open", return_value=MagicMock(
            __enter__=MagicMock(return_value=io.StringIO(fake_net_dev)),
            __exit__=MagicMock(return_value=False),
        )):
            rx, tx = _read_net_bytes()

        assert rx == 0
        assert tx == 0


# ========== dashboard_event_generator テスト ==========


class TestDashboardEventGenerator:
    """`dashboard_event_generator` のテスト"""

    @pytest.mark.asyncio
    async def test_generator_yields_sse_format(self, admin_token):
        """ダッシュボードジェネレーターがSSE形式データを返す"""
        from backend.api.routes.stream import dashboard_event_generator

        with patch("backend.api.routes.stream._read_cpu_times", return_value={
            "user": 100, "nice": 0, "system": 10, "idle": 200, "iowait": 0,
            "irq": 0, "softirq": 0, "steal": 0,
        }), patch("backend.api.routes.stream._read_net_bytes", return_value=(5000, 3000)
        ), patch("backend.api.routes.stream._read_mem_percent", return_value=55.0
        ), patch("backend.api.routes.stream.asyncio.sleep", new_callable=AsyncMock,
                 side_effect=[None, asyncio.CancelledError()]):
            gen = dashboard_event_generator(admin_token)
            event = await gen.__anext__()

        assert event.startswith("data: ")
        assert event.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_generator_json_has_required_keys(self, admin_token):
        """cpu / mem / net_in / net_out / timestamp キーを含む"""
        from backend.api.routes.stream import dashboard_event_generator

        with patch("backend.api.routes.stream._read_cpu_times", side_effect=[
            {"user": 100, "nice": 0, "system": 10, "idle": 200, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
            {"user": 120, "nice": 0, "system": 15, "idle": 220, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        ]), patch("backend.api.routes.stream._read_net_bytes", side_effect=[
            (5000, 3000), (6000, 3500),
        ]), patch("backend.api.routes.stream._read_mem_percent", return_value=60.0
        ), patch("backend.api.routes.stream.asyncio.sleep", new_callable=AsyncMock,
                 side_effect=[None, asyncio.CancelledError()]):
            gen = dashboard_event_generator(admin_token)
            event = await gen.__anext__()

        data = json.loads(event[6:].strip())
        for key in ["cpu", "mem", "net_in", "net_out", "timestamp"]:
            assert key in data

    @pytest.mark.asyncio
    async def test_generator_net_values_non_negative(self, admin_token):
        """net_in / net_out は 0 以上（カウンタリセット時も安全）"""
        from backend.api.routes.stream import dashboard_event_generator

        # rx が減少するケース（カウンタリセット） → max(0, ...) で 0
        with patch("backend.api.routes.stream._read_cpu_times", side_effect=[
            {"user": 100, "nice": 0, "system": 0, "idle": 300, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
            {"user": 110, "nice": 0, "system": 0, "idle": 310, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0},
        ]), patch("backend.api.routes.stream._read_net_bytes", side_effect=[
            (5000, 3000), (100, 200),  # rx/tx ともに減少
        ]), patch("backend.api.routes.stream._read_mem_percent", return_value=40.0
        ), patch("backend.api.routes.stream.asyncio.sleep", new_callable=AsyncMock,
                 side_effect=[None, asyncio.CancelledError()]):
            gen = dashboard_event_generator(admin_token)
            event = await gen.__anext__()

        data = json.loads(event[6:].strip())
        assert data["net_in"] >= 0
        assert data["net_out"] >= 0

    @pytest.mark.asyncio
    async def test_generator_cancelled_error_handled(self, admin_token):
        """CancelledError が正常にハンドリングされ例外が伝播しない"""
        from backend.api.routes.stream import dashboard_event_generator

        with patch("backend.api.routes.stream._read_cpu_times", return_value={
            "user": 100, "nice": 0, "system": 0, "idle": 200, "iowait": 0,
            "irq": 0, "softirq": 0, "steal": 0,
        }), patch("backend.api.routes.stream._read_net_bytes", return_value=(0, 0)
        ), patch("backend.api.routes.stream._read_mem_percent", return_value=50.0
        ), patch("backend.api.routes.stream.asyncio.sleep", new_callable=AsyncMock,
                 side_effect=asyncio.CancelledError()):
            gen = dashboard_event_generator(admin_token)
            events = []
            async for event in gen:
                events.append(event)

        # CancelledError で正常終了（例外なし）
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_generator_oserror_handled(self, admin_token):
        """/proc 読み込みエラー (OSError) が正常にハンドリングされる"""
        from backend.api.routes.stream import dashboard_event_generator

        with patch("backend.api.routes.stream._read_cpu_times",
                   side_effect=OSError("No such file")):
            gen = dashboard_event_generator(admin_token)
            events = []
            async for event in gen:
                events.append(event)

        # OSError で0イベント、例外なし
        assert events == []

    @pytest.mark.asyncio
    async def test_generator_multiple_yields(self, admin_token):
        """複数回 yield されることを確認"""
        from backend.api.routes.stream import dashboard_event_generator

        cpu_base = {"user": 100, "nice": 0, "system": 10, "idle": 200, "iowait": 0, "irq": 0, "softirq": 0, "steal": 0}
        call_count = 0

        def make_cpu():
            nonlocal call_count
            call_count += 1
            d = dict(cpu_base)
            d["user"] += call_count * 5
            d["idle"] += call_count * 10
            return d

        sleep_calls = 0

        async def mock_sleep(_):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 4:
                raise asyncio.CancelledError()

        with patch("backend.api.routes.stream._read_cpu_times", side_effect=make_cpu
        ), patch("backend.api.routes.stream._read_net_bytes", return_value=(0, 0)
        ), patch("backend.api.routes.stream._read_mem_percent", return_value=50.0
        ), patch("backend.api.routes.stream.asyncio.sleep", side_effect=mock_sleep):
            gen = dashboard_event_generator(admin_token)
            events = []
            async for event in gen:
                events.append(event)

        # 初回sleep + 3ループ = 4回sleep → 3イベント
        assert len(events) == 3
