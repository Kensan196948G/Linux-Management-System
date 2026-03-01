"""
モジュール管理 API - 統合テスト

エンドポイントの統合テスト
  - GET /api/modules          (認証不要)
  - GET /api/modules/status   (認証必要)
  - GET /api/modules/{name}   (認証不要)
"""

import pytest


# ==============================================================================
# 定数
# ==============================================================================

EXPECTED_CATEGORIES = {"system", "servers", "networking", "hardware", "system_management"}
EXPECTED_CATEGORY_LABELS = {
    "system": "System",
    "servers": "Servers",
    "networking": "Networking",
    "hardware": "Hardware",
    "system_management": "Linux Management System",
}


# ==============================================================================
# GET /api/modules — 認証不要テスト (5件)
# ==============================================================================


class TestModulesListAnonymous:
    """認証なしで /api/modules にアクセスできること（5件）"""

    def test_anonymous_access_allowed(self, test_client):
        """認証なしで GET /api/modules が 200 を返す"""
        response = test_client.get("/api/modules")
        assert response.status_code == 200

    def test_response_has_categories_key(self, test_client):
        """レスポンスに categories キーが存在する"""
        response = test_client.get("/api/modules")
        data = response.json()
        assert "categories" in data

    def test_response_has_all_five_categories(self, test_client):
        """レスポンスに全5カテゴリが含まれる"""
        response = test_client.get("/api/modules")
        data = response.json()
        assert set(data["categories"].keys()) == EXPECTED_CATEGORIES

    def test_response_has_total_modules(self, test_client):
        """レスポンスに total_modules キーが存在する"""
        response = test_client.get("/api/modules")
        data = response.json()
        assert "total_modules" in data
        assert isinstance(data["total_modules"], int)
        assert data["total_modules"] >= 30

    def test_total_modules_matches_sum(self, test_client):
        """total_modules の値が各カテゴリの合計と一致する"""
        response = test_client.get("/api/modules")
        data = response.json()
        total_from_categories = sum(len(cat["modules"]) for cat in data["categories"].values())
        assert data["total_modules"] == total_from_categories


# ==============================================================================
# カテゴリ構造テスト (5件)
# ==============================================================================


class TestModulesCategoryStructure:
    """各カテゴリが正しい構造を持つこと（5件）"""

    def test_each_category_has_label(self, test_client):
        """全カテゴリに label キーが存在する"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        for cat_key, cat_val in categories.items():
            assert "label" in cat_val, f"category '{cat_key}' has no label"

    def test_each_category_has_modules(self, test_client):
        """全カテゴリに modules キーが存在する"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        for cat_key, cat_val in categories.items():
            assert "modules" in cat_val, f"category '{cat_key}' has no modules"
            assert isinstance(cat_val["modules"], list)
            assert len(cat_val["modules"]) > 0

    def test_category_labels_are_correct(self, test_client):
        """各カテゴリのラベルが正しい値である"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        for cat_key, expected_label in EXPECTED_CATEGORY_LABELS.items():
            assert categories[cat_key]["label"] == expected_label

    def test_each_module_has_required_fields(self, test_client):
        """各モジュールエントリに id, name, endpoint, icon フィールドが存在する"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        for cat_val in categories.values():
            for mod in cat_val["modules"]:
                for field in ("id", "name", "endpoint", "icon"):
                    assert field in mod, f"module missing field '{field}': {mod}"

    def test_module_endpoints_start_with_api(self, test_client):
        """全モジュールの endpoint が /api/ で始まる"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        for cat_val in categories.values():
            for mod in cat_val["modules"]:
                assert mod["endpoint"].startswith("/api/"), f"invalid endpoint: {mod['endpoint']}"


# ==============================================================================
# GET /api/modules/status — 認証テスト (3件)
# ==============================================================================


class TestModulesStatusAuth:
    """/api/modules/status の認証テスト（3件）"""

    def test_anonymous_status_rejected(self, test_client):
        """認証なしで GET /api/modules/status は 401/403 を返す"""
        response = test_client.get("/api/modules/status")
        assert response.status_code in (401, 403)

    def test_viewer_can_access_status(self, test_client, viewer_headers):
        """Viewer ロールで GET /api/modules/status にアクセスできる"""
        response = test_client.get("/api/modules/status", headers=viewer_headers)
        assert response.status_code == 200

    def test_status_response_structure(self, test_client, auth_headers):
        """ステータスレスポンスに statuses と total キーが存在する"""
        response = test_client.get("/api/modules/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "total" in data
        assert isinstance(data["statuses"], list)
        assert data["total"] == len(data["statuses"])


# ==============================================================================
# GET /api/modules/{module_name} — 詳細テスト (5件)
# ==============================================================================


class TestModuleDetail:
    """GET /api/modules/{module_name} の正常系・異常系テスト（5件）"""

    def test_existing_module_returns_200(self, test_client):
        """存在するモジュール名で 200 が返る（認証不要）"""
        response = test_client.get("/api/modules/processes")
        assert response.status_code == 200

    def test_module_detail_has_required_fields(self, test_client):
        """モジュール詳細レスポンスに id, name, endpoint, icon, category, category_label が含まれる"""
        response = test_client.get("/api/modules/processes")
        data = response.json()
        for field in ("id", "name", "endpoint", "icon", "category", "category_label"):
            assert field in data, f"missing field: {field}"

    def test_module_detail_id_matches(self, test_client):
        """モジュール詳細の id がリクエストしたモジュール名と一致する"""
        response = test_client.get("/api/modules/nginx")
        data = response.json()
        assert data["id"] == "nginx"

    def test_nonexistent_module_returns_404(self, test_client):
        """存在しないモジュール名で 404 が返る"""
        response = test_client.get("/api/modules/nonexistent_module_xyz")
        assert response.status_code == 404

    def test_module_category_is_valid(self, test_client):
        """モジュール詳細の category が有効なカテゴリキーである"""
        response = test_client.get("/api/modules/firewall")
        data = response.json()
        assert data["category"] in EXPECTED_CATEGORIES


# ==============================================================================
# モジュール内容の整合性テスト (2件)
# ==============================================================================


class TestModulesContent:
    """モジュール内容の整合性テスト（2件）"""

    def test_system_management_has_approval(self, test_client):
        """system_management カテゴリに approval モジュールが含まれる"""
        response = test_client.get("/api/modules")
        modules = response.json()["categories"]["system_management"]["modules"]
        module_ids = [m["id"] for m in modules]
        assert "approval" in module_ids

    def test_all_module_ids_are_unique(self, test_client):
        """全モジュールの id がユニークである"""
        response = test_client.get("/api/modules")
        categories = response.json()["categories"]
        all_ids = [mod["id"] for cat in categories.values() for mod in cat["modules"]]
        assert len(all_ids) == len(set(all_ids)), "Duplicate module IDs found"
