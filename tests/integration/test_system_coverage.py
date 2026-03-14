"""
system.py カバレッジ改善テスト

対象: backend/api/routes/system.py
既存テストと重複しない、ヘルパー関数・エンドポイントのエッジケースを網羅
"""

from unittest.mock import MagicMock, patch

import pytest


# =====================================================================
# ヘルパー関数 単体テスト
# =====================================================================


class TestScoreForUsage:
    """_score_for_usage ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_usage

        self.fn = _score_for_usage

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 100),
            (40.0, 80),
            (80.0, 60),
        ],
    )
    def test_below_warn_threshold(self, value, expected):
        """warn_threshold 以下でスコア 60-100"""
        assert self.fn(value, warn_threshold=80.0, critical_threshold=95.0) == expected

    @pytest.mark.parametrize("value", [81.0, 87.5, 94.9])
    def test_between_warn_and_critical(self, value):
        """warn < value <= critical でスコア 20-60"""
        score = self.fn(value, warn_threshold=80.0, critical_threshold=95.0)
        assert 0 <= score <= 60

    @pytest.mark.parametrize("value", [95.0, 97.0, 100.0])
    def test_above_critical(self, value):
        """critical 超でスコア 0-20"""
        score = self.fn(value, warn_threshold=80.0, critical_threshold=95.0)
        assert 0 <= score <= 20

    def test_extreme_value_returns_zero(self):
        """極端な値でスコア 0"""
        score = self.fn(110.0, warn_threshold=80.0, critical_threshold=95.0)
        assert score == 0

    def test_zero_usage_returns_100(self):
        """使用率 0% でスコア 100"""
        assert self.fn(0.0, warn_threshold=80.0, critical_threshold=95.0) == 100


class TestScoreForAlerts:
    """_score_for_alerts ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_alerts

        self.fn = _score_for_alerts

    @pytest.mark.parametrize(
        "count,expected",
        [
            (0, 100),
            (1, 70),
            (2, 50),
            (3, 50),
            (4, 40),
            (5, 30),
            (8, 0),
        ],
    )
    def test_alert_counts(self, count, expected):
        assert self.fn(count) == expected

    def test_large_count_clamps_to_zero(self):
        """大量アラートでスコア 0"""
        assert self.fn(100) == 0


class TestScoreForFailedServices:
    """_score_for_failed_services ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _score_for_failed_services

        self.fn = _score_for_failed_services

    @pytest.mark.parametrize(
        "count,expected",
        [
            (0, 100),
            (1, 60),
            (2, 40),
            (3, 20),
            (4, 0),
            (10, 0),
        ],
    )
    def test_failed_service_counts(self, count, expected):
        assert self.fn(count) == expected


class TestStatusLabel:
    """_status_label ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _status_label

        self.fn = _status_label

    @pytest.mark.parametrize(
        "score,label",
        [
            (100, "excellent"),
            (90, "excellent"),
            (89, "good"),
            (70, "good"),
            (69, "warning"),
            (50, "warning"),
            (49, "critical"),
            (0, "critical"),
        ],
    )
    def test_label_boundaries(self, score, label):
        assert self.fn(score) == label


class TestCountFailedServices:
    """_count_failed_services ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.system import _count_failed_services

        self.fn = _count_failed_services

    @patch("backend.api.routes.system.subprocess.run")
    def test_no_failed_services(self, mock_run):
        """失敗サービスなし → 0"""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_two_failed_services(self, mock_run):
        """2つの失敗サービス → 2"""
        mock_run.return_value = MagicMock(
            stdout="  nginx.service loaded failed failed\n  sshd.service loaded failed failed\n",
            returncode=0,
        )
        assert self.fn() == 2

    @patch("backend.api.routes.system.subprocess.run")
    def test_exception_returns_zero(self, mock_run):
        """例外時は 0 を返す"""
        mock_run.side_effect = OSError("systemctl not found")
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_timeout_returns_zero(self, mock_run):
        """タイムアウト時は 0 を返す"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl", timeout=10)
        assert self.fn() == 0

    @patch("backend.api.routes.system.subprocess.run")
    def test_blank_lines_ignored(self, mock_run):
        """空行は無視される"""
        mock_run.return_value = MagicMock(
            stdout="  nginx.service loaded failed failed\n\n\n",
            returncode=0,
        )
        assert self.fn() == 1


# =====================================================================
# GET /api/system/status テスト
# =====================================================================


class TestSystemStatusEndpoint:
    """GET /api/system/status エンドポイントテスト"""

    def test_status_requires_auth(self, test_client):
        """認証なしで 401/403"""
        resp = test_client.get("/api/system/status")
        assert resp.status_code in (401, 403)

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_status_success(self, mock_sw, test_client, admin_headers):
        """正常取得"""
        mock_sw.get_system_status.return_value = {
            "cpu_usage": 10.0,
            "memory_usage": 30.0,
            "disk_usage": 50.0,
            "uptime": "1 day",
        }
        resp = test_client.get("/api/system/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu_usage" in data

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_status_exception_raises(self, mock_sw, test_client, admin_headers):
        """sudo_wrapper 例外で 500"""
        mock_sw.get_system_status.side_effect = RuntimeError("system check failed")
        with pytest.raises(RuntimeError):
            test_client.get("/api/system/status", headers=admin_headers)

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_status_audit_logged_on_success(self, mock_sw, test_client, admin_headers):
        """成功時に audit_log.record が呼ばれる"""
        mock_sw.get_system_status.return_value = {"cpu_usage": 5.0}
        with patch("backend.api.routes.system.audit_log") as mock_audit:
            resp = test_client.get("/api/system/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["status"] == "success"

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_status_audit_logged_on_failure(self, mock_sw, test_client, admin_headers):
        """失敗時にも audit_log.record が呼ばれる（failure status）"""
        mock_sw.get_system_status.side_effect = RuntimeError("fail")
        with patch("backend.api.routes.system.audit_log") as mock_audit:
            with pytest.raises(RuntimeError):
                test_client.get("/api/system/status", headers=admin_headers)
        assert mock_audit.record.call_count >= 1
        # 失敗の record が呼ばれている
        for call in mock_audit.record.call_args_list:
            if call[1].get("status") == "failure":
                break
        else:
            pytest.fail("failure audit record not found")

    @patch("backend.api.routes.system.sudo_wrapper")
    def test_status_viewer_can_access(self, mock_sw, test_client, viewer_headers):
        """viewer ロールでもアクセス可能"""
        mock_sw.get_system_status.return_value = {"cpu_usage": 1.0}
        resp = test_client.get("/api/system/status", headers=viewer_headers)
        assert resp.status_code == 200


# =====================================================================
# GET /api/system/health-score 追加エッジケース
# =====================================================================


class TestHealthScoreEdgeCases:
    """health-score の追加エッジケース"""

    def test_all_critical_values(self, test_client, admin_headers):
        """全コンポーネントがクリティカルの場合"""
        with (
            patch("psutil.cpu_percent", return_value=99.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=5),
        ):
            mock_mem.return_value = MagicMock(percent=99.0)
            mock_disk.return_value = MagicMock(percent=99.0)
            resp = test_client.get("/api/system/health-score", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] < 30
        assert data["status"] == "critical"

    def test_medium_load_warning(self, test_client, admin_headers):
        """中程度の負荷で warning"""
        with (
            patch("psutil.cpu_percent", return_value=85.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
        ):
            mock_mem.return_value = MagicMock(percent=85.0)
            mock_disk.return_value = MagicMock(percent=85.0)
            resp = test_client.get("/api/system/health-score", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] < 90

    def test_alerts_count_with_high_usage(self, test_client, admin_headers):
        """CPU/メモリ/ディスクが全て90超の場合にアラート3"""
        with (
            patch("psutil.cpu_percent", return_value=95.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
        ):
            mock_mem.return_value = MagicMock(percent=95.0)
            mock_disk.return_value = MagicMock(percent=95.0)
            resp = test_client.get("/api/system/health-score", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["components"]["alerts"]["value"] == 3

    def test_no_alerts_below_threshold(self, test_client, admin_headers):
        """全て90以下ならアラート0"""
        with (
            patch("psutil.cpu_percent", return_value=50.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
        ):
            mock_mem.return_value = MagicMock(percent=50.0)
            mock_disk.return_value = MagicMock(percent=50.0)
            resp = test_client.get("/api/system/health-score", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["components"]["alerts"]["value"] == 0
