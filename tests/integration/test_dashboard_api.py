"""ダッシュボード設定 API - 統合テスト (25件)"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ==============================================================================
# 未認証アクセス (3件)
# ==============================================================================


class TestDashboardUnauthorized:
    """認証なしアクセスは 403 を返すこと"""

    def test_get_config_no_auth(self, test_client):
        """GET /api/dashboard/config — 認証なしは403"""
        resp = test_client.get("/api/dashboard/config")
        assert resp.status_code == 403

    def test_put_config_no_auth(self, test_client):
        """PUT /api/dashboard/config — 認証なしは403"""
        resp = test_client.put("/api/dashboard/config", json={})
        assert resp.status_code == 403

    def test_get_presets_no_auth(self, test_client):
        """GET /api/dashboard/presets — 認証なしは403"""
        resp = test_client.get("/api/dashboard/presets")
        assert resp.status_code == 403


# ==============================================================================
# 設定取得 (4件)
# ==============================================================================


class TestGetDashboardConfig:
    """GET /api/dashboard/config の正常系テスト"""

    def test_get_config_200_admin(self, test_client, admin_headers, tmp_path):
        """admin ユーザーが設定を取得できること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "config" in data

    def test_get_config_default_structure(self, test_client, admin_headers, tmp_path):
        """設定が存在しない場合はデフォルト構造を返すこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        cfg = resp.json()["config"]
        assert "widget_order" in cfg
        assert "hidden_widgets" in cfg
        assert "theme" in cfg
        assert "refresh_interval" in cfg
        assert "compact_mode" in cfg

    def test_get_config_200_viewer(self, test_client, viewer_headers, tmp_path):
        """viewer ロールでも設定取得が可能なこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.get("/api/dashboard/config", headers=viewer_headers)
        assert resp.status_code == 200

    def test_get_config_default_widget_order(self, test_client, admin_headers, tmp_path):
        """デフォルトの widget_order に既知ウィジェットが含まれること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        order = resp.json()["config"]["widget_order"]
        assert isinstance(order, list)
        assert len(order) > 0
        assert "health-score" in order


# ==============================================================================
# 設定保存 (6件)
# ==============================================================================


class TestPutDashboardConfig:
    """PUT /api/dashboard/config の正常系・異常系テスト"""

    def test_put_config_200(self, test_client, admin_headers, tmp_path):
        """正常な設定を保存できること"""
        payload = {
            "widget_order": ["health-score", "cpu-ring", "mem-bar"],
            "hidden_widgets": ["net-line"],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["config"]["widget_order"] == payload["widget_order"]

    def test_put_config_persists(self, test_client, admin_headers, tmp_path):
        """保存した設定を GET で取得できること"""
        payload = {
            "widget_order": ["cpu-ring", "health-score"],
            "hidden_widgets": ["error-log"],
            "theme": "dark",
            "refresh_interval": 30,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        cfg = resp.json()["config"]
        assert cfg["theme"] == "dark"
        assert cfg["compact_mode"] is True
        assert cfg["refresh_interval"] == 30

    def test_put_config_reject_unknown_widget(self, test_client, admin_headers, tmp_path):
        """allowlist 外のウィジェット ID を含む widget_order は 422 を返すこと"""
        payload = {
            "widget_order": ["health-score", "malicious-widget"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_put_config_reject_unknown_hidden_widget(self, test_client, admin_headers, tmp_path):
        """allowlist 外の hidden_widget ID は 422 を返すこと"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": ["evil-widget"],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_put_config_reject_invalid_theme(self, test_client, admin_headers, tmp_path):
        """不明なテーマは 422 を返すこと"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "hacker",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_put_config_reject_invalid_refresh_interval(self, test_client, admin_headers, tmp_path):
        """許可外のリフレッシュ間隔は 422 を返すこと"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 999,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422


# ==============================================================================
# 設定削除（リセット）(3件)
# ==============================================================================


class TestDeleteDashboardConfig:
    """DELETE /api/dashboard/config のテスト"""

    def test_delete_config_200(self, test_client, admin_headers, tmp_path):
        """DELETE でリセットが成功し 200 を返すこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.delete("/api/dashboard/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_delete_config_returns_default(self, test_client, admin_headers, tmp_path):
        """DELETE 後にデフォルト設定を返すこと"""
        payload = {
            "widget_order": ["cpu-ring"],
            "hidden_widgets": [],
            "theme": "dark",
            "refresh_interval": 60,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
            resp = test_client.delete("/api/dashboard/config", headers=admin_headers)
        cfg = resp.json()["config"]
        assert cfg["theme"] == "default"
        assert cfg["compact_mode"] is False

    def test_delete_config_resets_to_default_on_next_get(self, test_client, admin_headers, tmp_path):
        """DELETE 後に GET するとデフォルト設定が返ること"""
        payload = {
            "widget_order": ["mem-bar"],
            "hidden_widgets": ["nic-stats"],
            "theme": "compact",
            "refresh_interval": 60,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
            test_client.delete("/api/dashboard/config", headers=admin_headers)
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        cfg = resp.json()["config"]
        assert cfg["theme"] == "default"
        assert cfg["refresh_interval"] == 10


# ==============================================================================
# プリセット (4件)
# ==============================================================================


class TestDashboardPresets:
    """プリセット API のテスト"""

    def test_get_presets_200(self, test_client, admin_headers):
        """プリセット一覧が取得できること"""
        resp = test_client.get("/api/dashboard/presets", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "presets" in data
        assert len(data["presets"]) >= 3

    def test_get_presets_structure(self, test_client, admin_headers):
        """各プリセットに id, name, description が含まれること"""
        resp = test_client.get("/api/dashboard/presets", headers=admin_headers)
        for preset in resp.json()["presets"]:
            assert "id" in preset
            assert "name" in preset
            assert "description" in preset

    def test_apply_preset_200(self, test_client, admin_headers, tmp_path):
        """既存プリセットを適用できること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.post("/api/dashboard/presets/sysadmin/apply", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["preset_id"] == "sysadmin"

    def test_apply_preset_404(self, test_client, admin_headers, tmp_path):
        """存在しないプリセットは 404 を返すこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.post("/api/dashboard/presets/nonexistent/apply", headers=admin_headers)
        assert resp.status_code == 404


# ==============================================================================
# ユーザー別設定の分離確認 (3件)
# ==============================================================================


class TestDashboardConfigIsolation:
    """ユーザー設定が他ユーザーに漏れないこと"""

    def test_admin_config_not_visible_to_viewer(self, test_client, admin_headers, viewer_headers, tmp_path):
        """admin の設定が viewer に見えないこと（設定は独立）"""
        admin_payload = {
            "widget_order": ["net-line", "health-score"],
            "hidden_widgets": ["error-log"],
            "theme": "dark",
            "refresh_interval": 5,
            "compact_mode": True,
        }
        viewer_payload = {
            "widget_order": ["health-score", "cpu-ring"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 30,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=admin_payload, headers=admin_headers)
            test_client.put("/api/dashboard/config", json=viewer_payload, headers=viewer_headers)
            admin_resp = test_client.get("/api/dashboard/config", headers=admin_headers)
            viewer_resp = test_client.get("/api/dashboard/config", headers=viewer_headers)
        admin_cfg = admin_resp.json()["config"]
        viewer_cfg = viewer_resp.json()["config"]
        assert admin_cfg["theme"] == "dark"
        assert viewer_cfg["theme"] == "default"
        assert admin_cfg["compact_mode"] is True
        assert viewer_cfg["compact_mode"] is False

    def test_separate_config_files_created(self, test_client, admin_headers, viewer_headers, tmp_path):
        """admin と viewer で別々のファイルが作成されること"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
            test_client.put("/api/dashboard/config", json=payload, headers=viewer_headers)
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 2

    def test_viewer_delete_does_not_affect_admin(self, test_client, admin_headers, viewer_headers, tmp_path):
        """viewer の DELETE が admin 設定に影響しないこと"""
        admin_payload = {
            "widget_order": ["net-line", "mem-bar"],
            "hidden_widgets": [],
            "theme": "dark",
            "refresh_interval": 5,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=admin_payload, headers=admin_headers)
            # viewer がリセットを実行
            test_client.delete("/api/dashboard/config", headers=viewer_headers)
            # admin の設定はそのまま残っているはず
            admin_resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        assert admin_resp.json()["config"]["theme"] == "dark"


# ==============================================================================
# セキュリティ: インジェクション拒否 (2件)
# ==============================================================================


class TestDashboardSecurity:
    """不正な入力が拒否されること"""

    def test_shell_injection_in_widget_order_rejected(self, test_client, admin_headers, tmp_path):
        """シェルインジェクション文字を含む widget_id は 422 で拒否されること"""
        payload = {
            "widget_order": ["health-score; rm -rf /"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_path_traversal_in_theme_rejected(self, test_client, admin_headers, tmp_path):
        """パストラバーサルのような不正なテーマ値は 422 で拒否されること"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "../../etc/passwd",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 422
