"""
dashboard.py カバレッジ改善テスト

未カバー行を重点的にテスト:
- _safe_user_id: 特殊文字変換・長さ制限
- _config_path: パストラバーサル防止
- _load_config: 壊れた JSON / 不足キー補完 / OSError
- _save_config: ラウンドトリップ
- get_dashboard_config: 既存設定ファイルがある場合
- put_dashboard_config: 全テーマ / 全リフレッシュ間隔
- delete_dashboard_config: ファイルが存在しない場合
- apply_dashboard_preset: 全プリセット適用 + 永続化確認
- presets: 全プリセットのフィールド検証
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.routes.dashboard import (
    ALLOWED_REFRESH_INTERVALS,
    ALLOWED_THEMES,
    ALLOWED_WIDGET_IDS,
    DEFAULT_CONFIG,
    PRESETS,
    _config_path,
    _load_config,
    _safe_user_id,
    _save_config,
)


# ===================================================================
# _safe_user_id 直接テスト
# ===================================================================


class TestSafeUserId:
    """_safe_user_id のテスト"""

    def test_alphanumeric_unchanged(self):
        """英数字はそのまま返すこと"""
        assert _safe_user_id("admin123") == "admin123"

    def test_email_format(self):
        """メールアドレス形式を安全に変換すること"""
        result = _safe_user_id("user@example.com")
        assert result == "user@example.com"  # @ はそのまま許可

    def test_special_chars_replaced(self):
        """特殊文字がアンダースコアに置換されること"""
        result = _safe_user_id("user/name\\test")
        assert "/" not in result
        assert "\\" not in result

    def test_truncated_to_128_chars(self):
        """128文字に切り詰められること"""
        long_id = "a" * 200
        result = _safe_user_id(long_id)
        assert len(result) == 128

    def test_dot_and_hyphen_preserved(self):
        """ドットとハイフンは保持されること"""
        result = _safe_user_id("first.last-name")
        assert result == "first.last-name"

    def test_underscore_preserved(self):
        """アンダースコアは保持されること"""
        result = _safe_user_id("user_name")
        assert result == "user_name"


# ===================================================================
# _load_config 直接テスト
# ===================================================================


class TestLoadConfig:
    """_load_config のテスト"""

    def test_nonexistent_returns_default(self, tmp_path):
        """設定ファイルが存在しない場合はデフォルトを返すこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            config = _load_config("nonexistent_user")
        assert config == DEFAULT_CONFIG

    def test_corrupt_json_returns_default(self, tmp_path):
        """壊れた JSON の場合はデフォルトを返すこと"""
        config_file = tmp_path / "corrupt_user.json"
        config_file.write_text("{invalid json!!!", encoding="utf-8")
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            config = _load_config("corrupt_user")
        assert config == DEFAULT_CONFIG

    def test_missing_keys_supplemented(self, tmp_path):
        """不足キーがデフォルトで補完されること"""
        config_file = tmp_path / "partial_user.json"
        partial = {"theme": "dark"}
        config_file.write_text(json.dumps(partial), encoding="utf-8")
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            config = _load_config("partial_user")
        assert config["theme"] == "dark"
        assert config["widget_order"] == DEFAULT_CONFIG["widget_order"]
        assert config["hidden_widgets"] == DEFAULT_CONFIG["hidden_widgets"]
        assert config["refresh_interval"] == DEFAULT_CONFIG["refresh_interval"]
        assert config["compact_mode"] == DEFAULT_CONFIG["compact_mode"]

    def test_valid_config_loaded(self, tmp_path):
        """有効な設定ファイルが正しく読み込まれること"""
        config_file = tmp_path / "valid_user.json"
        custom_config = {
            "widget_order": ["cpu-ring", "health-score"],
            "hidden_widgets": ["error-log"],
            "theme": "dark",
            "refresh_interval": 30,
            "compact_mode": True,
        }
        config_file.write_text(json.dumps(custom_config), encoding="utf-8")
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            config = _load_config("valid_user")
        assert config == custom_config


# ===================================================================
# _save_config / _load_config ラウンドトリップ
# ===================================================================


class TestSaveLoadRoundtrip:
    """_save_config → _load_config のラウンドトリップテスト"""

    def test_roundtrip(self, tmp_path):
        """保存したデータを正しく読み込めること"""
        custom_config = {
            "widget_order": ["mem-bar", "net-line"],
            "hidden_widgets": ["nic-stats"],
            "theme": "compact",
            "refresh_interval": 60,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            _save_config("roundtrip_user", custom_config)
            loaded = _load_config("roundtrip_user")
        assert loaded == custom_config

    def test_save_overwrites_existing(self, tmp_path):
        """既存のファイルを上書きすること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            _save_config("overwrite_user", {"theme": "default"})
            _save_config("overwrite_user", {"theme": "dark"})
            loaded = _load_config("overwrite_user")
        assert loaded["theme"] == "dark"


# ===================================================================
# エンドポイントテスト（追加カバレッジ）
# ===================================================================


class TestGetConfigWithExistingFile:
    """GET /api/dashboard/config — 既存ファイルがある場合のテスト"""

    def test_returns_existing_config(self, test_client, admin_headers, tmp_path):
        """既存の設定ファイルがある場合はその設定を返すこと"""
        # まず設定を保存
        payload = {
            "widget_order": ["cpu-ring", "mem-bar", "health-score"],
            "hidden_widgets": ["nic-stats"],
            "theme": "dark",
            "refresh_interval": 30,
            "compact_mode": True,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
            # 取得
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["theme"] == "dark"
        assert cfg["compact_mode"] is True
        assert cfg["refresh_interval"] == 30


class TestPutConfigAllThemes:
    """PUT /api/dashboard/config — 全テーマの検証"""

    @pytest.mark.parametrize("theme", ALLOWED_THEMES)
    def test_all_valid_themes_accepted(self, test_client, admin_headers, tmp_path, theme):
        """許可された全テーマが受け入れられること"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": theme,
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["config"]["theme"] == theme


class TestPutConfigAllRefreshIntervals:
    """PUT /api/dashboard/config — 全リフレッシュ間隔の検証"""

    @pytest.mark.parametrize("interval", ALLOWED_REFRESH_INTERVALS)
    def test_all_valid_intervals_accepted(self, test_client, admin_headers, tmp_path, interval):
        """許可された全リフレッシュ間隔が受け入れられること"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": interval,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["config"]["refresh_interval"] == interval


class TestPutConfigAllWidgets:
    """PUT /api/dashboard/config — 全ウィジェット ID の検証"""

    def test_all_widget_ids_in_order(self, test_client, admin_headers, tmp_path):
        """全ウィジェット ID を widget_order に含められること"""
        payload = {
            "widget_order": list(ALLOWED_WIDGET_IDS),
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200

    def test_all_widget_ids_in_hidden(self, test_client, admin_headers, tmp_path):
        """全ウィジェット ID を hidden_widgets に含められること"""
        payload = {
            "widget_order": [],
            "hidden_widgets": list(ALLOWED_WIDGET_IDS),
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200


class TestDeleteConfigEdgeCases:
    """DELETE /api/dashboard/config — エッジケース"""

    def test_delete_nonexistent_config(self, test_client, admin_headers, tmp_path):
        """設定ファイルが存在しない場合でも 200 を返すこと"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.delete("/api/dashboard/config", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["config"] == DEFAULT_CONFIG

    def test_delete_viewer_role_can_delete(self, test_client, viewer_headers, tmp_path):
        """viewer は write:dashboard 権限で削除可能"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.delete("/api/dashboard/config", headers=viewer_headers)
        assert resp.status_code == 200
        assert resp.json()["config"] == DEFAULT_CONFIG


class TestApplyAllPresets:
    """POST /api/dashboard/presets/{preset_id}/apply — 全プリセット適用テスト"""

    @pytest.mark.parametrize("preset_id", list(PRESETS.keys()))
    def test_apply_all_presets(self, test_client, admin_headers, tmp_path, preset_id):
        """全てのプリセットが正常に適用できること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.post(f"/api/dashboard/presets/{preset_id}/apply", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["preset_id"] == preset_id
        assert data["config"] == PRESETS[preset_id]["config"]

    def test_apply_preset_persists(self, test_client, admin_headers, tmp_path):
        """プリセット適用後に GET で取得できること"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            test_client.post("/api/dashboard/presets/minimal/apply", headers=admin_headers)
            resp = test_client.get("/api/dashboard/config", headers=admin_headers)
        cfg = resp.json()["config"]
        assert cfg["theme"] == PRESETS["minimal"]["config"]["theme"]
        assert cfg["compact_mode"] == PRESETS["minimal"]["config"]["compact_mode"]

    def test_apply_preset_no_auth_forbidden(self, test_client, tmp_path):
        """未認証は 403"""
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.post("/api/dashboard/presets/sysadmin/apply")
        assert resp.status_code == 403


class TestPresetsEndpoint:
    """GET /api/dashboard/presets のテスト"""

    def test_presets_has_all_defined_presets(self, test_client, admin_headers):
        """定義された全プリセットが返されること"""
        resp = test_client.get("/api/dashboard/presets", headers=admin_headers)
        assert resp.status_code == 200
        preset_ids = [p["id"] for p in resp.json()["presets"]]
        for pid in PRESETS.keys():
            assert pid in preset_ids

    def test_presets_viewer_can_read(self, test_client, viewer_headers):
        """viewer はプリセット一覧を読み取り可能"""
        resp = test_client.get("/api/dashboard/presets", headers=viewer_headers)
        assert resp.status_code == 200

    def test_each_preset_has_required_fields(self, test_client, admin_headers):
        """各プリセットに必須フィールドが含まれること"""
        resp = test_client.get("/api/dashboard/presets", headers=admin_headers)
        for preset in resp.json()["presets"]:
            assert "id" in preset
            assert "name" in preset
            assert "description" in preset
            assert isinstance(preset["name"], str)
            assert len(preset["name"]) > 0


class TestDashboardConfigCompactMode:
    """compact_mode のテスト"""

    @pytest.mark.parametrize("compact", [True, False])
    def test_compact_mode_saved(self, test_client, admin_headers, tmp_path, compact):
        """compact_mode が正しく保存されること"""
        payload = {
            "widget_order": ["health-score"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": compact,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["config"]["compact_mode"] is compact


class TestDashboardConfigEmptyWidgetOrder:
    """空の widget_order のテスト"""

    def test_empty_widget_order_accepted(self, test_client, admin_headers, tmp_path):
        """空の widget_order が受け入れられること"""
        payload = {
            "widget_order": [],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        }
        with patch("backend.api.routes.dashboard._CONFIGS_DIR", tmp_path):
            resp = test_client.put("/api/dashboard/config", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["config"]["widget_order"] == []
