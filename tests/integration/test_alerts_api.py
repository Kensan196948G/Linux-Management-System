"""
システムリソースアラート管理 - 統合テスト

APIエンドポイントの統合テスト（/proc 読み取りをモック）
"""

from unittest.mock import MagicMock, patch

import pytest


# ==============================================================================
# 認証なし 403 テスト (3件)
# ==============================================================================


class TestAlertsUnauthorized:
    """認証なしアクセスは 403 を返すこと"""

    def test_rules_no_auth(self, test_client):
        """GET /api/alerts/rules — 認証なしは403"""
        response = test_client.get("/api/alerts/rules")
        assert response.status_code == 403

    def test_active_no_auth(self, test_client):
        """GET /api/alerts/active — 認証なしは403"""
        response = test_client.get("/api/alerts/active")
        assert response.status_code == 403

    def test_summary_no_auth(self, test_client):
        """GET /api/alerts/summary — 認証なしは403"""
        response = test_client.get("/api/alerts/summary")
        assert response.status_code == 403


# ==============================================================================
# 正常系 200 テスト + レスポンス構造確認 (9件)
# ==============================================================================


class TestAlertsSuccess:
    """認証済みアクセスは 200 を返し、正しい構造を持つこと"""

    def test_rules_200(self, test_client, auth_headers):
        """GET /api/alerts/rules — 200 を返すこと"""
        response = test_client.get("/api/alerts/rules", headers=auth_headers)
        assert response.status_code == 200

    def test_rules_structure(self, test_client, auth_headers):
        """GET /api/alerts/rules — rules/count キーを持つこと"""
        response = test_client.get("/api/alerts/rules", headers=auth_headers)
        data = response.json()
        assert "rules" in data
        assert "count" in data
        assert isinstance(data["rules"], list)
        assert data["count"] == len(data["rules"])

    def test_rules_default_count(self, test_client, auth_headers):
        """GET /api/alerts/rules — デフォルトルールが5件あること"""
        response = test_client.get("/api/alerts/rules", headers=auth_headers)
        data = response.json()
        assert data["count"] == 5

    def test_rules_fields(self, test_client, auth_headers):
        """GET /api/alerts/rules — 各ルールに必須フィールドがあること"""
        response = test_client.get("/api/alerts/rules", headers=auth_headers)
        data = response.json()
        for rule in data["rules"]:
            assert "id" in rule
            assert "resource" in rule
            assert "threshold" in rule
            assert "comparison" in rule
            assert "enabled" in rule
            assert "description" in rule

    def test_active_200(self, test_client, auth_headers):
        """GET /api/alerts/active — 200 を返すこと"""
        response = test_client.get("/api/alerts/active", headers=auth_headers)
        assert response.status_code == 200

    def test_active_structure(self, test_client, auth_headers):
        """GET /api/alerts/active — active_alerts/current_values/timestamp キーを持つこと"""
        response = test_client.get("/api/alerts/active", headers=auth_headers)
        data = response.json()
        assert "active_alerts" in data
        assert "count" in data
        assert "current_values" in data
        assert "timestamp" in data
        assert isinstance(data["active_alerts"], list)

    def test_active_current_values_keys(self, test_client, auth_headers):
        """GET /api/alerts/active — current_values に cpu/memory/load が含まれること"""
        response = test_client.get("/api/alerts/active", headers=auth_headers)
        data = response.json()
        cv = data["current_values"]
        assert "cpu" in cv
        assert "memory" in cv
        assert "load" in cv
        assert "disk:/" in cv

    def test_summary_200(self, test_client, auth_headers):
        """GET /api/alerts/summary — 200 を返すこと"""
        response = test_client.get("/api/alerts/summary", headers=auth_headers)
        assert response.status_code == 200

    def test_summary_structure(self, test_client, auth_headers):
        """GET /api/alerts/summary — 必須フィールドを持つこと"""
        response = test_client.get("/api/alerts/summary", headers=auth_headers)
        data = response.json()
        assert "total_rules" in data
        assert "enabled_rules" in data
        assert "current_cpu" in data
        assert "current_memory" in data
        assert "current_load" in data
        assert "timestamp" in data
        assert data["total_rules"] == 5
        assert data["enabled_rules"] == 5


# ==============================================================================
# viewer ロールでのアクセス (2件)
# ==============================================================================


class TestAlertsViewerRole:
    """viewer ロールでも read:alerts が許可されていること"""

    def test_rules_viewer(self, test_client, viewer_headers):
        """GET /api/alerts/rules — viewer は 200"""
        response = test_client.get("/api/alerts/rules", headers=viewer_headers)
        assert response.status_code == 200

    def test_active_viewer(self, test_client, viewer_headers):
        """GET /api/alerts/active — viewer は 200"""
        response = test_client.get("/api/alerts/active", headers=viewer_headers)
        assert response.status_code == 200


# ==============================================================================
# アクティブアラート発火テスト (2件)
# ==============================================================================


class TestAlertsTriggered:
    """閾値を低く設定するとアラートが発火すること"""

    def test_alert_triggered_when_cpu_high(self, test_client, auth_headers):
        """CPU が閾値超過したとき active_alerts にエントリが入ること"""
        import backend.api.routes.alerts as alerts_module

        original_rules = alerts_module.DEFAULT_RULES
        low_threshold_rules = [
            {"id": "cpu-test", "resource": "cpu", "threshold": 0.0, "comparison": "gte", "enabled": True, "description": "テスト用: 常に発火"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", low_threshold_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=1.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=50.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.5):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=10.0):
                            response = test_client.get("/api/alerts/active", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert len(data["active_alerts"]) >= 1
        assert data["active_alerts"][0]["id"] == "cpu-test"

    def test_alert_not_triggered_when_below_threshold(self, test_client, auth_headers):
        """現在値が閾値未満のときアラートが発火しないこと"""
        import backend.api.routes.alerts as alerts_module

        high_threshold_rules = [
            {"id": "cpu-high", "resource": "cpu", "threshold": 99.9, "comparison": "gte", "enabled": True, "description": "テスト用: ほぼ発火しない"},
        ]
        with patch.object(alerts_module, "DEFAULT_RULES", high_threshold_rules):
            with patch.object(alerts_module, "get_current_cpu_usage", return_value=1.0):
                with patch.object(alerts_module, "get_current_memory_usage", return_value=10.0):
                    with patch.object(alerts_module, "get_load_average", return_value=0.1):
                        with patch.object(alerts_module, "get_disk_usage_pct", return_value=5.0):
                            response = test_client.get("/api/alerts/active", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0


# ==============================================================================
# ヘルパー関数の単体テスト (3件)
# ==============================================================================


class TestAlertHelperFunctions:
    """CPU/メモリ/ディスク取得関数の単体テスト"""

    def test_get_current_cpu_usage_returns_float(self):
        """get_current_cpu_usage() は float を返すこと"""
        from backend.api.routes.alerts import get_current_cpu_usage

        result = get_current_cpu_usage()
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_get_current_memory_usage_returns_float(self):
        """get_current_memory_usage() は float を返すこと"""
        from backend.api.routes.alerts import get_current_memory_usage

        result = get_current_memory_usage()
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_get_disk_usage_pct_root(self):
        """get_disk_usage_pct('/') は 0-100 の float を返すこと"""
        from backend.api.routes.alerts import get_disk_usage_pct

        result = get_disk_usage_pct("/")
        assert isinstance(result, float)
        assert 0.0 <= result <= 100.0

    def test_get_load_average_returns_float(self):
        """get_load_average() は非負の float を返すこと"""
        from backend.api.routes.alerts import get_load_average

        result = get_load_average()
        assert isinstance(result, float)
        assert result >= 0.0

    def test_get_disk_usage_pct_invalid_path(self):
        """存在しないパスを渡すと 0.0 を返すこと"""
        from backend.api.routes.alerts import get_disk_usage_pct

        result = get_disk_usage_pct("/nonexistent/path/that/does/not/exist")
        assert result == 0.0


# ==============================================================================
# 503 エラーレスポンステスト (2件)
# ==============================================================================


class TestAlerts503:
    """内部エラー時に 503 を返すこと"""

    def test_active_503_on_exception(self, test_client, auth_headers):
        """GET /api/alerts/active — 内部エラーで 503"""
        import backend.api.routes.alerts as alerts_module

        with patch.object(alerts_module, "get_current_cpu_usage", side_effect=RuntimeError("proc error")):
            response = test_client.get("/api/alerts/active", headers=auth_headers)
        assert response.status_code == 503

    def test_summary_503_on_exception(self, test_client, auth_headers):
        """GET /api/alerts/summary — 内部エラーで 503"""
        import backend.api.routes.alerts as alerts_module

        with patch.object(alerts_module, "get_current_cpu_usage", side_effect=RuntimeError("proc error")):
            response = test_client.get("/api/alerts/summary", headers=auth_headers)
        assert response.status_code == 503
