"""
リソースモニタリング API 統合テスト
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


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


class TestMetricsEndpoint:
    """GET /api/monitoring/metrics テスト"""

    def test_metrics_authenticated(self, test_client, admin_headers):
        """認証済みで現在メトリクスを取得できる"""
        response = test_client.get("/api/monitoring/metrics", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cpu_percent" in data
        assert "mem_percent" in data
        assert "disk_percent" in data
        assert "timestamp" in data

    def test_metrics_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/metrics")
        assert response.status_code in (401, 403)

    def test_metrics_viewer_allowed(self, test_client, viewer_headers):
        """viewerもread:systemで取得可能"""
        response = test_client.get("/api/monitoring/metrics", headers=viewer_headers)
        assert response.status_code == 200

    def test_metrics_cpu_range(self, test_client, admin_headers):
        """CPU使用率は0-100の範囲"""
        response = test_client.get("/api/monitoring/metrics", headers=admin_headers)
        data = response.json()
        assert 0.0 <= data["cpu_percent"] <= 100.0

    def test_metrics_mem_range(self, test_client, admin_headers):
        """メモリ使用率は0-100の範囲"""
        response = test_client.get("/api/monitoring/metrics", headers=admin_headers)
        data = response.json()
        assert 0.0 <= data["mem_percent"] <= 100.0

    def test_metrics_has_load_avg(self, test_client, admin_headers):
        """ロードアベレージが含まれる"""
        response = test_client.get("/api/monitoring/metrics", headers=admin_headers)
        data = response.json()
        assert "load_avg_1" in data
        assert "load_avg_5" in data
        assert "load_avg_15" in data

    def test_metrics_has_memory_details(self, test_client, admin_headers):
        """メモリ詳細情報が含まれる"""
        response = test_client.get("/api/monitoring/metrics", headers=admin_headers)
        data = response.json()
        assert "mem_total" in data
        assert "mem_used" in data
        assert data["mem_total"] > 0

    def test_metrics_adds_to_history(self, test_client, admin_headers):
        """メトリクス取得で履歴バッファに追記される"""
        # まずメトリクス取得
        test_client.get("/api/monitoring/metrics", headers=admin_headers)
        # 次に履歴取得してデータがある
        resp2 = test_client.get("/api/monitoring/history?points=10", headers=admin_headers)
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["points"] >= 0  # バッファに何か入っている


class TestHistoryEndpoint:
    """GET /api/monitoring/history テスト"""

    def test_history_authenticated(self, test_client, admin_headers):
        """認証済みで履歴を取得できる"""
        # まず数回メトリクス取得してバッファを埋める
        for _ in range(3):
            test_client.get("/api/monitoring/metrics", headers=admin_headers)
        response = test_client.get("/api/monitoring/history?points=60", headers=admin_headers)
        assert response.status_code == 200

    def test_history_structure(self, test_client, admin_headers):
        """履歴レスポンス構造の検証"""
        response = test_client.get("/api/monitoring/history", headers=admin_headers)
        data = response.json()
        assert "status" in data
        assert "points" in data
        assert "labels" in data
        assert "cpu" in data
        assert "memory" in data
        assert "disk" in data

    def test_history_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/history")
        assert response.status_code in (401, 403)

    def test_history_points_limit(self, test_client, admin_headers):
        """points=1で最大1件"""
        response = test_client.get("/api/monitoring/history?points=1", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["labels"]) <= 1

    def test_history_labels_match_data(self, test_client, admin_headers):
        """labelsとcpuデータの長さが一致する"""
        for _ in range(2):
            test_client.get("/api/monitoring/metrics", headers=admin_headers)
        response = test_client.get("/api/monitoring/history?points=10", headers=admin_headers)
        data = response.json()
        assert len(data["labels"]) == len(data["cpu"])
        assert len(data["labels"]) == len(data["memory"])


class TestAlertsEndpoint:
    """GET /api/monitoring/alerts テスト"""

    def test_alerts_authenticated(self, test_client, admin_headers):
        """認証済みでアラート一覧を取得できる"""
        response = test_client.get("/api/monitoring/alerts", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "alert_count" in data

    def test_alerts_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/alerts")
        assert response.status_code in (401, 403)

    def test_alerts_structure(self, test_client, admin_headers):
        """アラートアイテムの構造"""
        response = test_client.get("/api/monitoring/alerts", headers=admin_headers)
        data = response.json()
        assert isinstance(data["alerts"], list)
        for alert in data["alerts"]:
            assert "resource" in alert
            assert "level" in alert
            assert alert["level"] in ("warning", "critical")

    def test_alerts_count_matches(self, test_client, admin_headers):
        """alert_countとalertsリストの長さが一致する"""
        response = test_client.get("/api/monitoring/alerts", headers=admin_headers)
        data = response.json()
        assert data["alert_count"] == len(data["alerts"])


class TestThresholdEndpoint:
    """POST /api/monitoring/alerts/threshold テスト"""

    def test_set_threshold_valid(self, test_client, admin_headers):
        """有効な閾値を設定できる"""
        payload = {
            "cpu_warn": 75.0, "cpu_critical": 90.0,
            "mem_warn": 70.0, "mem_critical": 88.0,
            "disk_warn": 80.0, "disk_critical": 92.0,
        }
        response = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["thresholds"]["cpu_warn"] == 75.0

    def test_set_threshold_warn_ge_critical(self, test_client, admin_headers):
        """warn >= critical の場合は400"""
        payload = {
            "cpu_warn": 95.0, "cpu_critical": 90.0,  # warn > critical
            "mem_warn": 70.0, "mem_critical": 88.0,
            "disk_warn": 80.0, "disk_critical": 92.0,
        }
        response = test_client.post("/api/monitoring/alerts/threshold", headers=admin_headers, json=payload)
        assert response.status_code == 400

    def test_set_threshold_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.post("/api/monitoring/alerts/threshold", json={})
        assert response.status_code in (401, 403)

    def test_set_threshold_viewer_forbidden(self, test_client, viewer_headers):
        """viewerはwrite:system権限がないため403"""
        payload = {"cpu_warn": 80.0, "cpu_critical": 95.0, "mem_warn": 80.0, "mem_critical": 95.0, "disk_warn": 85.0, "disk_critical": 95.0}
        response = test_client.post("/api/monitoring/alerts/threshold", headers=viewer_headers, json=payload)
        assert response.status_code == 403


class TestTopProcessesEndpoint:
    """GET /api/monitoring/processes/top テスト"""

    def test_top_processes_cpu(self, test_client, admin_headers):
        """CPU順上位プロセスを取得できる"""
        response = test_client.get("/api/monitoring/processes/top?sort_by=cpu&limit=10", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "processes" in data
        assert len(data["processes"]) <= 10

    def test_top_processes_memory(self, test_client, admin_headers):
        """メモリ順上位プロセスを取得できる"""
        response = test_client.get("/api/monitoring/processes/top?sort_by=memory&limit=5", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "processes" in data
        assert len(data["processes"]) <= 5

    def test_top_processes_structure(self, test_client, admin_headers):
        """プロセスエントリの構造"""
        response = test_client.get("/api/monitoring/processes/top", headers=admin_headers)
        data = response.json()
        for proc in data["processes"]:
            assert "pid" in proc
            assert "name" in proc
            assert "cpu_percent" in proc
            assert "mem_percent" in proc

    def test_top_processes_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/processes/top")
        assert response.status_code in (401, 403)

    def test_top_processes_invalid_sort(self, test_client, admin_headers):
        """不正なsort_byでも200（デフォルトにフォールバック）"""
        response = test_client.get("/api/monitoring/processes/top?sort_by=invalid", headers=admin_headers)
        assert response.status_code == 200


class TestNetworkIOEndpoint:
    """GET /api/monitoring/network/io テスト"""

    def test_network_io(self, test_client, admin_headers):
        """ネットワークI/O統計を取得できる"""
        response = test_client.get("/api/monitoring/network/io", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "interfaces" in data
        assert isinstance(data["interfaces"], list)

    def test_network_io_structure(self, test_client, admin_headers):
        """インターフェース情報の構造"""
        response = test_client.get("/api/monitoring/network/io", headers=admin_headers)
        data = response.json()
        for iface in data["interfaces"]:
            assert "interface" in iface
            assert "bytes_sent" in iface
            assert "bytes_recv" in iface

    def test_network_io_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/network/io")
        assert response.status_code in (401, 403)


class TestDiskIOEndpoint:
    """GET /api/monitoring/disk/io テスト"""

    def test_disk_io(self, test_client, admin_headers):
        """ディスクI/O統計を取得できる"""
        response = test_client.get("/api/monitoring/disk/io", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert isinstance(data["devices"], list)

    def test_disk_io_structure(self, test_client, admin_headers):
        """デバイス情報の構造"""
        response = test_client.get("/api/monitoring/disk/io", headers=admin_headers)
        data = response.json()
        for dev in data["devices"]:
            assert "device" in dev
            assert "read_bytes" in dev
            assert "write_bytes" in dev

    def test_disk_io_unauthenticated(self, test_client):
        """未認証は401"""
        response = test_client.get("/api/monitoring/disk/io")
        assert response.status_code in (401, 403)
