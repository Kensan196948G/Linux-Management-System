"""system.py カバレッジ向上テスト v2

対象: backend/api/routes/system.py
全エンドポイント・ヘルパー関数の未カバー分岐を網羅的にテスト:
- _score_for_usage 境界値
- _count_failed_services 全分岐
- GET /api/system/status 正常系/異常系
- GET /api/system/detailed 全セクション（CPU温度/メモリ/NIC/アップタイム）
- GET /api/system/health-score 全コンポーネント組み合わせ
"""

import builtins
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch

import pytest


# =====================================================================
# ヘルパー関数テスト（境界値追加）
# =====================================================================


class TestScoreForUsageV2:
    """_score_for_usage の境界値・エッジケース追加"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_usage
        self.fn = _score_for_usage

    @pytest.mark.parametrize("value,warn,crit,expected_min,expected_max", [
        (0.0, 80.0, 95.0, 100, 100),      # 使用率0
        (40.0, 80.0, 95.0, 60, 100),       # 中間
        (80.0, 80.0, 95.0, 60, 60),        # ちょうどwarn
        (80.1, 80.0, 95.0, 20, 60),        # warn超え
        (87.5, 80.0, 95.0, 20, 60),        # warn~crit中間
        (95.0, 80.0, 95.0, 0, 20),         # ちょうどcrit
        (100.0, 80.0, 95.0, 0, 20),        # 100%
        (110.0, 80.0, 95.0, 0, 0),         # 超過
    ])
    def test_boundary_values(self, value, warn, crit, expected_min, expected_max):
        score = self.fn(value, warn_threshold=warn, critical_threshold=crit)
        assert expected_min <= score <= expected_max

    def test_different_thresholds(self):
        """異なる閾値パラメータ"""
        score = self.fn(50.0, warn_threshold=60.0, critical_threshold=80.0)
        assert 0 <= score <= 100

    def test_very_low_threshold(self):
        """非常に低い閾値"""
        score = self.fn(5.0, warn_threshold=10.0, critical_threshold=20.0)
        assert 60 <= score <= 100


class TestScoreForAlertsV2:
    """_score_for_alerts 追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_alerts
        self.fn = _score_for_alerts

    @pytest.mark.parametrize("count,expected", [
        (0, 100),
        (1, 70),
        (2, 50),
        (3, 50),
        (4, 40),
        (5, 30),
        (6, 20),
        (7, 10),
        (8, 0),
        (10, 0),
        (100, 0),
    ])
    def test_all_ranges(self, count, expected):
        assert self.fn(count) == expected


class TestScoreForFailedServicesV2:
    """_score_for_failed_services 追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_failed_services
        self.fn = _score_for_failed_services

    @pytest.mark.parametrize("count,expected", [
        (0, 100),
        (1, 60),
        (2, 40),
        (3, 20),
        (4, 0),
        (5, 0),
        (100, 0),
    ])
    def test_all_ranges(self, count, expected):
        assert self.fn(count) == expected


class TestStatusLabelV2:
    """_status_label 追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _status_label
        self.fn = _status_label

    @pytest.mark.parametrize("score,label", [
        (100, "excellent"),
        (95, "excellent"),
        (90, "excellent"),
        (89, "good"),
        (75, "good"),
        (70, "good"),
        (69, "warning"),
        (55, "warning"),
        (50, "warning"),
        (49, "critical"),
        (25, "critical"),
        (0, "critical"),
    ])
    def test_all_boundaries(self, score, label):
        assert self.fn(score) == label


class TestCountFailedServicesV2:
    """_count_failed_services 追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _count_failed_services
        self.fn = _count_failed_services

    @patch("backend.api.routes.system.subprocess.run")
    def test_multiple_services(self, mock_run):
        """3つの失敗サービス"""
        mock_run.return_value = MagicMock(
            stdout="a.service\nb.service\nc.service\n",
            returncode=1,
        )
        assert self.fn() == 3

    @patch("backend.api.routes.system.subprocess.run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_only_blank_lines(self, mock_run):
        mock_run.return_value = MagicMock(stdout="\n\n\n", returncode=0)
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_runtime_error(self, mock_run):
        mock_run.side_effect = RuntimeError("no systemctl")
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_file_not_found_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError("systemctl not found")
        assert self.fn() == 0


# =====================================================================
# GET /api/system/status テスト追加
# =====================================================================


class TestSystemStatusEndpointV2:
    """GET /api/system/status 追加テスト"""

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/system/status")
        assert resp.status_code in (401, 403)

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_returns_all_fields(self, mock_sw, test_client, admin_headers):
        mock_sw.get_system_status.return_value = {
            "cpu_usage": 15.5,
            "memory_usage": 42.3,
            "disk_usage": 60.0,
            "uptime": "5 days",
        }
        resp = test_client.get("/api/system/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_usage"] == 15.5
        assert data["memory_usage"] == 42.3

    @patch("backend.api.routes.system.sudo_wrapper")
    @patch("backend.api.routes.system.audit_log")
    def test_audit_log_on_success(self, mock_audit, mock_sw, test_client, admin_headers):
        mock_sw.get_system_status.return_value = {"cpu_usage": 1.0}
        resp = test_client.get("/api/system/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        kwargs = mock_audit.record.call_args[1]
        assert kwargs["status"] == "success"
        assert kwargs["operation"] == "system_status_view"

    @patch("backend.api.routes.system.sudo_wrapper")
    @patch("backend.api.routes.system.audit_log")
    def test_audit_log_on_failure(self, mock_audit, mock_sw, test_client, admin_headers):
        mock_sw.get_system_status.side_effect = RuntimeError("fail")
        with pytest.raises(RuntimeError):
            test_client.get("/api/system/status", headers=admin_headers)
        # failure record should exist
        found_failure = False
        for call in mock_audit.record.call_args_list:
            if call[1].get("status") == "failure":
                found_failure = True
                assert "error" in call[1].get("details", {})
        assert found_failure

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_operator_access(self, mock_sw, test_client, auth_headers):
        """operator ロールでアクセス可"""
        mock_sw.get_system_status.return_value = {"cpu_usage": 2.0}
        resp = test_client.get("/api/system/status", headers=auth_headers)
        assert resp.status_code == 200


# =====================================================================
# GET /api/system/detailed テスト
# =====================================================================


class TestDetailedSystemInfo:
    """GET /api/system/detailed エンドポイントテスト"""

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/system/detailed")
        assert resp.status_code in (401, 403)

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_success_all_sections(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """全セクション（CPU温度/メモリ/NIC/アップタイム）が含まれる"""
        # CPU温度用のglob結果
        mock_glob.return_value = ["/sys/class/thermal/thermal_zone0/temp"]

        # open をコンテキストに応じて返す
        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if "thermal_zone0/temp" in path_str:
                return StringIO("45000\n")
            elif "/type" in path_str:
                return StringIO("x86_pkg_temp\n")
            elif path_str == "/proc/meminfo":
                return StringIO(
                    "MemTotal:       16000000 kB\n"
                    "MemFree:         8000000 kB\n"
                    "MemAvailable:   12000000 kB\n"
                    "Buffers:          500000 kB\n"
                    "Cached:          3000000 kB\n"
                    "SwapTotal:       2000000 kB\n"
                    "SwapFree:        1500000 kB\n"
                )
            elif path_str == "/proc/net/dev":
                return StringIO(
                    "Inter-|   Receive\n"
                    " face |bytes\n"
                    "  eth0: 1000 200 0 0 0 0 0 0 2000 300 0 0 0 0 0 0 0\n"
                    "    lo: 500 100 0 0 0 0 0 0 500 100 0 0 0 0 0 0 0\n"
                )
            elif path_str == "/proc/uptime":
                return StringIO("90061.5 180000.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # CPU temperatures
        assert len(data["cpu_temperatures"]) == 1
        assert data["cpu_temperatures"][0]["temp_c"] == 45.0
        assert data["cpu_temperatures"][0]["zone"] == "x86_pkg_temp"

        # Memory detail
        assert data["memory_detail"]["total_kb"] == 16000000
        assert data["memory_detail"]["free_kb"] == 8000000

        # Network interfaces (lo should be excluded)
        assert len(data["network_interfaces"]) == 1
        assert data["network_interfaces"][0]["interface"] == "eth0"

        # Uptime
        assert data["uptime"]["days"] == 1
        assert data["uptime"]["hours"] == 1

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_cpu_temp_read_error(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """CPU温度読み取りエラーでも他のセクションは正常"""
        mock_glob.return_value = ["/sys/class/thermal/thermal_zone0/temp"]

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if "thermal_zone" in path_str:
                raise PermissionError("no access")
            elif path_str == "/proc/meminfo":
                return StringIO("MemTotal: 8000000 kB\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                return StringIO("3600.0 7200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["cpu_temperatures"] == []

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_zone_type_read_error(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """zone type 読み取りエラーでも zone=unknown で登録"""
        mock_glob.return_value = ["/sys/class/thermal/thermal_zone0/temp"]

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if "thermal_zone0/temp" in path_str:
                return StringIO("50000\n")
            elif "/type" in path_str:
                raise PermissionError("no access")
            elif path_str == "/proc/meminfo":
                return StringIO("MemTotal: 4000000 kB\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                return StringIO("100.0 200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["cpu_temperatures"][0]["zone"] == "unknown"
        assert data["cpu_temperatures"][0]["temp_c"] == 50.0

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_meminfo_read_error(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """/proc/meminfo 読み取りエラーでもエラーレスポンスが入る"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                raise PermissionError("no access to meminfo")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                return StringIO("7200.0 14400.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "error" in data["memory_detail"]

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_net_dev_read_error(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """/proc/net/dev 読み取りエラーでもエラーが返る"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                return StringIO("MemTotal: 4000000 kB\n")
            elif path_str == "/proc/net/dev":
                raise PermissionError("no access to net/dev")
            elif path_str == "/proc/uptime":
                return StringIO("100.0 200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["network_interfaces"]) == 1
        assert "error" in data["network_interfaces"][0]

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_uptime_read_error(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """/proc/uptime 読み取りエラーでもuptime={}"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                return StringIO("MemTotal: 4000000 kB\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                raise PermissionError("no access")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["uptime"] == {}

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_no_thermal_zones(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """thermal zone がない場合は空リスト"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                return StringIO("MemTotal: 4000000 kB\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                return StringIO("3600.0 7200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["cpu_temperatures"] == []

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_nic_short_line_skipped(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """NIC行がフィールド不足の場合スキップ"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                return StringIO("MemTotal: 4000000 kB\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n  eth0: 100 200\n")
            elif path_str == "/proc/uptime":
                return StringIO("100.0 200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["network_interfaces"] == []

    @patch("backend.api.routes.system.audit_log")
    @patch("backend.api.routes.system._glob.glob")
    @patch("builtins.open")
    def test_meminfo_short_lines_handled(self, mock_builtin_open, mock_glob, mock_audit, test_client, admin_headers):
        """meminfo で1フィールドの行は無視される"""
        mock_glob.return_value = []

        def open_side_effect(path, *args, **kwargs):
            path_str = str(path)
            if path_str == "/proc/meminfo":
                return StringIO("MemTotal:       16000000 kB\nShortLine\n")
            elif path_str == "/proc/net/dev":
                return StringIO("Inter-|\n face|\n")
            elif path_str == "/proc/uptime":
                return StringIO("100.0 200.0\n")
            raise FileNotFoundError(f"Mock: {path_str}")

        mock_builtin_open.side_effect = open_side_effect

        resp = test_client.get("/api/system/detailed", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["memory_detail"]["total_kb"] == 16000000


# =====================================================================
# GET /api/system/health-score テスト追加
# =====================================================================


class TestHealthScoreV2:
    """GET /api/system/health-score 追加テスト"""

    def test_no_auth_returns_403(self, test_client):
        resp = test_client.get("/api/system/health-score")
        assert resp.status_code in (401, 403)

    def _make_request(self, test_client, admin_headers, cpu=10.0, mem=20.0, disk=30.0, failed=0):
        with (
            patch("psutil.cpu_percent", return_value=cpu),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=failed),
            patch("backend.api.routes.system.audit_log"),
        ):
            mock_mem.return_value = MagicMock(percent=mem)
            mock_disk.return_value = MagicMock(percent=disk)
            return test_client.get("/api/system/health-score", headers=admin_headers)

    def test_all_low_excellent(self, test_client, admin_headers):
        """全て低負荷ならexcellent"""
        resp = self._make_request(test_client, admin_headers, 5.0, 10.0, 20.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] >= 90
        assert data["status"] == "excellent"

    def test_high_cpu_only(self, test_client, admin_headers):
        """CPU高負荷のみ"""
        resp = self._make_request(test_client, admin_headers, 96.0, 30.0, 30.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["cpu"]["score"] < 20

    def test_high_memory_only(self, test_client, admin_headers):
        """メモリ高負荷のみ"""
        resp = self._make_request(test_client, admin_headers, 10.0, 95.0, 30.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["memory"]["score"] < 20

    def test_high_disk_only(self, test_client, admin_headers):
        """ディスク高負荷のみ"""
        resp = self._make_request(test_client, admin_headers, 10.0, 30.0, 98.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["disk"]["score"] < 20

    def test_failed_services_impact(self, test_client, admin_headers):
        """失敗サービスのスコアへの影響"""
        resp = self._make_request(test_client, admin_headers, 10.0, 30.0, 30.0, 3)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["services"]["value"] == 3
        assert data["components"]["services"]["score"] == 20

    def test_all_alerts_triggered(self, test_client, admin_headers):
        """全指標が90超でアラート3"""
        resp = self._make_request(test_client, admin_headers, 95.0, 95.0, 95.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["alerts"]["value"] == 3

    def test_partial_alerts(self, test_client, admin_headers):
        """CPU のみ90超でアラート1"""
        resp = self._make_request(test_client, admin_headers, 95.0, 50.0, 50.0, 0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["components"]["alerts"]["value"] == 1
        assert data["components"]["alerts"]["score"] == 70

    def test_response_has_generated_at(self, test_client, admin_headers):
        """generated_at フィールドが含まれる"""
        resp = self._make_request(test_client, admin_headers)
        assert resp.status_code == 200
        assert "generated_at" in resp.json()

    def test_all_components_have_status(self, test_client, admin_headers):
        """各コンポーネントに status ラベルが含まれる"""
        resp = self._make_request(test_client, admin_headers)
        assert resp.status_code == 200
        components = resp.json()["components"]
        for key in ["cpu", "memory", "disk", "alerts", "services"]:
            assert "status" in components[key]
            assert components[key]["status"] in ("excellent", "good", "warning", "critical")

    def test_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可"""
        with (
            patch("psutil.cpu_percent", return_value=10.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
            patch("backend.api.routes.system.audit_log"),
        ):
            mock_mem.return_value = MagicMock(percent=20.0)
            mock_disk.return_value = MagicMock(percent=30.0)
            resp = test_client.get("/api/system/health-score", headers=viewer_headers)
        assert resp.status_code == 200
