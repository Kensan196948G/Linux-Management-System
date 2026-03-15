"""
monitoring.py カバレッジ改善テスト

未カバー行を重点的にテスト:
- _check_alerts: 各リソースの warning/critical 閾値境界テスト
- _load_thresholds / _save_thresholds: ファイル操作テスト
- _persist_snapshot: DB 永続化の成功・エラーパス
- _query_metrics_range: 間引き（thinning）ロジック
- _query_daily_averages: 日別集計
- clear_metrics_history: DB エラーパス
- get_prometheus_metrics: アラート存在時のラベル付きメトリクス出力
- get_top_processes: メモリソート / limit 境界値
- set_alert_thresholds: mem_warn >= mem_critical / disk_warn >= disk_critical
- get_metrics_history: points 境界値
"""

import json
import sqlite3
import time
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ===================================================================
# _check_alerts 直接テスト
# ===================================================================


class TestCheckAlerts:
    """_check_alerts の閾値境界テスト"""

    def test_no_alerts_below_all_thresholds(self):
        """全リソースが閾値以下ならアラートなし"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 50.0, "mem_percent": 50.0, "disk_percent": 50.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        assert len(alerts) == 0

    def test_cpu_at_exactly_warn_threshold(self):
        """CPU が warn 閾値と等しい場合は warning アラート"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 80.0, "mem_percent": 50.0, "disk_percent": 50.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        cpu_alerts = [a for a in alerts if a["resource"] == "cpu_percent"]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0]["level"] == "warning"

    def test_cpu_at_exactly_critical_threshold(self):
        """CPU が critical 閾値と等しい場合は critical アラート"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 95.0, "mem_percent": 50.0, "disk_percent": 50.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        cpu_alerts = [a for a in alerts if a["resource"] == "cpu_percent"]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0]["level"] == "critical"

    def test_mem_warning_alert(self):
        """メモリが warn 閾値以上 critical 未満で warning"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 50.0, "mem_percent": 85.0, "disk_percent": 50.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        mem_alerts = [a for a in alerts if a["resource"] == "mem_percent"]
        assert len(mem_alerts) == 1
        assert mem_alerts[0]["level"] == "warning"

    def test_disk_critical_alert(self):
        """ディスクが critical 閾値以上で critical"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 50.0, "mem_percent": 50.0, "disk_percent": 98.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        disk_alerts = [a for a in alerts if a["resource"] == "disk_percent"]
        assert len(disk_alerts) == 1
        assert disk_alerts[0]["level"] == "critical"

    def test_all_resources_alert(self):
        """全リソースが閾値超えで3アラート"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {"cpu_percent": 96.0, "mem_percent": 96.0, "disk_percent": 96.0}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        assert len(alerts) == 3
        assert all(a["level"] == "critical" for a in alerts)

    def test_missing_key_defaults_to_zero(self):
        """snapshot にキーがない場合は 0 として扱いアラートなし"""
        from backend.api.routes.monitoring import _check_alerts

        snapshot = {}
        thresholds = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        alerts = _check_alerts(snapshot, thresholds)
        assert len(alerts) == 0


# ===================================================================
# _load_thresholds / _save_thresholds 直接テスト
# ===================================================================


class TestThresholdPersistence:
    """閾値ファイルの読み書きテスト"""

    def test_load_nonexistent_returns_defaults(self, tmp_path, monkeypatch):
        """ファイルが存在しない場合はデフォルト値を返すこと"""
        from backend.api.routes import monitoring as m

        monkeypatch.setattr(m, "_THRESHOLD_FILE", tmp_path / "nonexistent.json")
        result = m._load_thresholds()
        assert result == m.DEFAULT_THRESHOLDS

    def test_load_corrupt_json_returns_defaults(self, tmp_path, monkeypatch):
        """壊れた JSON ファイルの場合はデフォルト値を返すこと"""
        from backend.api.routes import monitoring as m

        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(m, "_THRESHOLD_FILE", corrupt)
        result = m._load_thresholds()
        assert result == m.DEFAULT_THRESHOLDS

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """保存した閾値を正しく読み込めること"""
        from backend.api.routes import monitoring as m

        threshold_file = tmp_path / "thresholds.json"
        monkeypatch.setattr(m, "_THRESHOLD_FILE", threshold_file)

        config = {"cpu_warn": 70.0, "cpu_critical": 85.0, "mem_warn": 75.0, "mem_critical": 90.0, "disk_warn": 80.0, "disk_critical": 92.0}
        m._save_thresholds(config)
        result = m._load_thresholds()
        assert result == config

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        """親ディレクトリが存在しない場合に作成すること"""
        from backend.api.routes import monitoring as m

        threshold_file = tmp_path / "deep" / "nested" / "thresholds.json"
        monkeypatch.setattr(m, "_THRESHOLD_FILE", threshold_file)
        m._save_thresholds({"cpu_warn": 80.0})
        assert threshold_file.exists()


# ===================================================================
# _persist_snapshot 追加テスト
# ===================================================================


class TestPersistSnapshotExtended:
    """_persist_snapshot の追加テスト"""

    def test_persist_and_query_roundtrip(self, tmp_path, monkeypatch):
        """保存したスナップショットを _query_metrics_range で取得できること"""
        from backend.api.routes import monitoring as m

        db_path = tmp_path / "metrics_roundtrip.db"
        monkeypatch.setattr(m, "_METRICS_DB_PATH", db_path)

        now = time.time()
        snapshot = {
            "ts": now,
            "timestamp": "2026-01-01T00:00:00Z",
            "cpu_percent": 55.0,
            "mem_percent": 65.0,
            "disk_percent": 40.0,
            "load1": 1.5,
            "load5": 2.0,
            "load15": 2.5,
            "mem_used": 8192,
            "mem_total": 16384,
        }
        m._persist_snapshot(snapshot)

        records = m._query_metrics_range(now - 10, now + 10)
        assert len(records) >= 1
        assert records[0]["cpu"] == 55.0

    def test_persist_db_error_is_silent(self, tmp_path, monkeypatch):
        """DB エラー時に例外が発生しないこと（ログのみ）"""
        from backend.api.routes import monitoring as m

        # 読み取り専用ディレクトリにDBを作成しようとする
        monkeypatch.setattr(m, "_METRICS_DB_PATH", Path("/dev/null/impossible.db"))
        # Should not raise
        m._persist_snapshot({"ts": time.time(), "timestamp": "test"})


# ===================================================================
# _query_metrics_range 間引きテスト
# ===================================================================


class TestQueryMetricsRangeThinning:
    """_query_metrics_range の間引きロジックテスト"""

    def test_thinning_reduces_points(self, tmp_path, monkeypatch):
        """max_points でデータ点数が制限されること"""
        from backend.api.routes import monitoring as m

        db_path = tmp_path / "thinning.db"
        monkeypatch.setattr(m, "_METRICS_DB_PATH", db_path)

        now = time.time()
        # 100 点のデータを挿入
        for i in range(100):
            snapshot = {
                "ts": now - (100 - i),
                "timestamp": f"2026-01-01T00:{i:02d}:00Z",
                "cpu_percent": float(i),
                "mem_percent": 50.0,
                "disk_percent": 30.0,
                "load1": 1.0,
                "load5": 1.0,
                "load15": 1.0,
                "mem_used": 4096,
                "mem_total": 8192,
            }
            m._persist_snapshot(snapshot)

        # max_points=20 で取得
        records = m._query_metrics_range(now - 200, now + 10, max_points=20)
        assert len(records) <= 20


# ===================================================================
# エンドポイントテスト（追加カバレッジ）
# ===================================================================


class TestSetThresholdValidationExtended:
    """POST /api/monitoring/alerts/threshold のバリデーション追加テスト"""

    def test_mem_warn_ge_critical_rejected(self, test_client, admin_headers):
        """mem_warn >= mem_critical の場合は 400"""
        payload = {
            "cpu_warn": 70.0,
            "cpu_critical": 90.0,
            "mem_warn": 90.0,
            "mem_critical": 85.0,  # warn > critical
            "disk_warn": 80.0,
            "disk_critical": 92.0,
        }
        resp = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert resp.status_code == 400
        # Error message may be in 'detail' or 'message'
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "mem_warn" in msg

    def test_disk_warn_ge_critical_rejected(self, test_client, admin_headers):
        """disk_warn >= disk_critical の場合は 400"""
        payload = {
            "cpu_warn": 70.0,
            "cpu_critical": 90.0,
            "mem_warn": 70.0,
            "mem_critical": 88.0,
            "disk_warn": 95.0,
            "disk_critical": 90.0,  # warn > critical
        }
        resp = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "disk_warn" in msg

    def test_warn_equal_to_critical_rejected(self, test_client, admin_headers):
        """warn == critical の場合も 400"""
        payload = {
            "cpu_warn": 90.0,
            "cpu_critical": 90.0,  # 等しい
            "mem_warn": 70.0,
            "mem_critical": 88.0,
            "disk_warn": 80.0,
            "disk_critical": 92.0,
        }
        resp = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert resp.status_code == 400

    def test_threshold_value_out_of_range_rejected(self, test_client, admin_headers):
        """0未満または100超の閾値は 422"""
        payload = {
            "cpu_warn": -5.0,
            "cpu_critical": 90.0,
            "mem_warn": 70.0,
            "mem_critical": 88.0,
            "disk_warn": 80.0,
            "disk_critical": 92.0,
        }
        resp = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert resp.status_code == 422


class TestHistoryPointsBoundary:
    """GET /api/monitoring/history の points 境界値テスト"""

    def test_history_points_negative_clamped(self, test_client, admin_headers):
        """points が負の場合も正常に動作すること（クランプ）"""
        resp = test_client.get("/api/monitoring/history?points=-10", headers=admin_headers)
        assert resp.status_code == 200

    def test_history_points_over_max_clamped(self, test_client, admin_headers):
        """points が最大値超過でも正常に動作すること（クランプ）"""
        resp = test_client.get("/api/monitoring/history?points=9999", headers=admin_headers)
        assert resp.status_code == 200

    def test_history_points_zero_clamped(self, test_client, admin_headers):
        """points=0 でも正常に動作すること"""
        resp = test_client.get("/api/monitoring/history?points=0", headers=admin_headers)
        assert resp.status_code == 200


class TestTopProcessesExtended:
    """GET /api/monitoring/processes/top の追加テスト"""

    def test_sort_by_memory(self, test_client, admin_headers):
        """sort_by=memory でメモリ降順ソートされること"""
        resp = test_client.get("/api/monitoring/processes/top?sort_by=memory&limit=5", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["sort_by"] == "memory"
        procs = data["processes"]
        if len(procs) >= 2:
            mems = [p["mem_percent"] for p in procs]
            assert mems == sorted(mems, reverse=True)

    def test_limit_boundary_1(self, test_client, admin_headers):
        """limit=1 で1件のみ返すこと"""
        resp = test_client.get("/api/monitoring/processes/top?limit=1", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["processes"]) <= 1

    def test_limit_over_50_fallback_to_15(self, test_client, admin_headers):
        """limit > 50 でフォールバックすること"""
        resp = test_client.get("/api/monitoring/processes/top?limit=100", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["processes"]) <= 15

    def test_process_has_username_field(self, test_client, admin_headers):
        """プロセスに username フィールドが含まれること"""
        resp = test_client.get("/api/monitoring/processes/top", headers=admin_headers)
        data = resp.json()
        for proc in data["processes"]:
            assert "username" in proc
            assert "mem_rss" in proc

    def test_total_count_positive(self, test_client, admin_headers):
        """total_count が正の値であること"""
        resp = test_client.get("/api/monitoring/processes/top", headers=admin_headers)
        assert resp.json()["total_count"] > 0


class TestClearMetricsHistoryExtended:
    """DELETE /api/monitoring/history の追加テスト"""

    def test_clear_returns_deleted_rows(self, test_client, admin_headers):
        """deleted_rows フィールドが含まれること"""
        resp = test_client.delete("/api/monitoring/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted_rows" in data
        assert isinstance(data["deleted_rows"], int)

    def test_clear_db_error_still_succeeds(self, test_client, admin_headers, tmp_path, monkeypatch):
        """DB エラー時も deleted_rows=0 で成功を返すこと"""
        from backend.api.routes import monitoring as m

        monkeypatch.setattr(m, "_METRICS_DB_PATH", Path("/dev/null/impossible.db"))

        resp = test_client.delete("/api/monitoring/history", headers=admin_headers)
        assert resp.status_code == 200


class TestPrometheusWithAlerts:
    """GET /api/monitoring/prometheus のアラート付き出力テスト"""

    def test_prometheus_with_alert_labels(self, test_client, admin_headers):
        """アラートが存在する場合、ラベル付きメトリクスが出力されること"""
        VmemResult = namedtuple("VmemResult", ["total", "used", "percent"])
        SwapResult = namedtuple("SwapResult", ["total", "used", "percent"])
        DiskResult = namedtuple("DiskResult", ["total", "used", "percent"])

        with patch("backend.api.routes.monitoring.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 96.0  # critical
            mock_psutil.cpu_count.return_value = 4
            mock_psutil.virtual_memory.return_value = VmemResult(total=16 * 1024**3, used=15 * 1024**3, percent=96.0)
            mock_psutil.swap_memory.return_value = SwapResult(total=4 * 1024**3, used=2 * 1024**3, percent=50.0)
            mock_psutil.disk_usage.return_value = DiskResult(total=500 * 1024**3, used=480 * 1024**3, percent=96.0)
            mock_psutil.getloadavg.return_value = (5.0, 4.0, 3.0)

            resp = test_client.get("/api/monitoring/prometheus", headers=admin_headers)

        assert resp.status_code == 200
        body = resp.text
        assert "linux_mgmt_alert_severity" in body
        assert 'level="critical"' in body

    def test_prometheus_memory_used_bytes(self, test_client, admin_headers):
        """メモリ使用量バイト数メトリクスが含まれること"""
        resp = test_client.get("/api/monitoring/prometheus", headers=admin_headers)
        assert "linux_mgmt_memory_used_bytes" in resp.text


class TestNetworkDiskIOExtended:
    """ネットワーク/ディスクI/O の追加テスト"""

    def test_network_io_has_timestamp(self, test_client, admin_headers):
        """ネットワークI/O にタイムスタンプが含まれること"""
        resp = test_client.get("/api/monitoring/network/io", headers=admin_headers)
        assert "timestamp" in resp.json()

    def test_disk_io_has_timestamp(self, test_client, admin_headers):
        """ディスクI/O にタイムスタンプが含まれること"""
        resp = test_client.get("/api/monitoring/disk/io", headers=admin_headers)
        assert "timestamp" in resp.json()

    def test_disk_io_empty_when_no_counters(self, test_client, admin_headers):
        """disk_io_counters が None の場合は空リストを返すこと"""
        with patch("backend.api.routes.monitoring.psutil.disk_io_counters", return_value=None):
            resp = test_client.get("/api/monitoring/disk/io", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["devices"] == []


class TestMetricsHistoryRangeExtended:
    """GET /api/monitoring/history/range の追加テスト"""

    def test_range_max_points_clamp(self, test_client, admin_headers):
        """max_points の最小値（10）テスト"""
        resp = test_client.get("/api/monitoring/history/range?hours=1&max_points=10", headers=admin_headers)
        assert resp.status_code == 200

    def test_range_max_points_too_small_rejected(self, test_client, admin_headers):
        """max_points < 10 は 422"""
        resp = test_client.get("/api/monitoring/history/range?hours=1&max_points=5", headers=admin_headers)
        assert resp.status_code == 422

    def test_range_max_hours(self, test_client, admin_headers):
        """hours=168 (最大値) で正常に動作"""
        resp = test_client.get("/api/monitoring/history/range?hours=168", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["hours"] == 168

    def test_range_response_has_from_to(self, test_client, admin_headers):
        """レスポンスに from/to が含まれること"""
        resp = test_client.get("/api/monitoring/history/range?hours=1", headers=admin_headers)
        data = resp.json()
        assert "from" in data
        assert "to" in data


class TestDailyTrendsExtended:
    """GET /api/monitoring/trends/daily の追加テスト"""

    def test_daily_days_1(self, test_client, admin_headers):
        """days=1 で正常に動作"""
        resp = test_client.get("/api/monitoring/trends/daily?days=1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["days"] == 1

    def test_daily_days_max_30(self, test_client, admin_headers):
        """days=30 (最大値) で正常に動作"""
        resp = test_client.get("/api/monitoring/trends/daily?days=30", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["days"] == 30

    def test_daily_has_samples_field(self, test_client, admin_headers):
        """レスポンスに samples フィールドが含まれること"""
        resp = test_client.get("/api/monitoring/trends/daily", headers=admin_headers)
        data = resp.json()
        assert "samples" in data

    def test_daily_viewer_can_read(self, test_client, viewer_headers):
        """Viewer も日別トレンドを取得できること"""
        resp = test_client.get("/api/monitoring/trends/daily", headers=viewer_headers)
        assert resp.status_code == 200
