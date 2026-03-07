"""
システムヘルススコア API 統合テスト（/api/system/health-score）
"""

import sys
import os

sys.path.insert(0, "/mnt/LinuxHDD/Linux-Management-Systm")
os.environ["ENV"] = "dev"

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture(scope="module")
def client():
    """FastAPI テストクライアント"""
    return TestClient(app)


def _get_auth_headers(client: TestClient, role: str = "admin") -> dict:
    """認証ヘッダーを取得するヘルパー。"""
    credentials = {
        "admin": ("admin@example.com", "admin123"),
        "viewer": ("viewer@example.com", "viewer123"),
        "operator": ("operator@example.com", "operator123"),
    }
    email, password = credentials[role]
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ===================================================================
# 認証テスト
# ===================================================================


class TestHealthScoreAuth:
    """認証・認可テスト"""

    def test_requires_auth(self, client):
        """認証なしで 401/403 を返す"""
        resp = client.get("/api/system/health-score")
        assert resp.status_code in (401, 403)

    def test_returns_200_with_admin(self, client):
        """Admin ユーザーで 200 を返す"""
        headers = _get_auth_headers(client, "admin")
        resp = client.get("/api/system/health-score", headers=headers)
        assert resp.status_code == 200

    def test_returns_200_with_viewer(self, client):
        """Viewer ユーザーでも 200 を返す（read:status 権限あり）"""
        headers = _get_auth_headers(client, "viewer")
        resp = client.get("/api/system/health-score", headers=headers)
        assert resp.status_code == 200

    def test_returns_200_with_operator(self, client):
        """Operator ユーザーでも 200 を返す"""
        headers = _get_auth_headers(client, "operator")
        resp = client.get("/api/system/health-score", headers=headers)
        assert resp.status_code == 200


# ===================================================================
# レスポンス構造テスト
# ===================================================================


class TestHealthScoreResponse:
    """レスポンス構造テスト"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        """各テスト用のレスポンスを取得する。"""
        headers = _get_auth_headers(client)
        resp = client.get("/api/system/health-score", headers=headers)
        assert resp.status_code == 200
        self.data = resp.json()

    def test_score_field_present(self):
        """score フィールドが存在する"""
        assert "score" in self.data

    def test_score_is_integer(self):
        """score は整数型"""
        assert isinstance(self.data["score"], int)

    def test_score_in_valid_range(self):
        """score は 0-100 の範囲"""
        assert 0 <= self.data["score"] <= 100

    def test_status_field_present(self):
        """status フィールドが存在する"""
        assert "status" in self.data

    def test_status_is_valid_value(self):
        """status は有効な値（excellent/good/warning/critical）"""
        assert self.data["status"] in ("excellent", "good", "warning", "critical")

    def test_components_field_present(self):
        """components フィールドが存在する"""
        assert "components" in self.data

    def test_all_components_present(self):
        """全コンポーネント（cpu/memory/disk/alerts/services）が存在する"""
        comps = self.data["components"]
        for key in ("cpu", "memory", "disk", "alerts", "services"):
            assert key in comps, f"{key} コンポーネントが見つかりません"

    def test_each_component_has_score(self):
        """各コンポーネントに score フィールドがある"""
        for key, comp in self.data["components"].items():
            assert "score" in comp, f"{key}.score が見つかりません"
            assert isinstance(comp["score"], int)
            assert 0 <= comp["score"] <= 100

    def test_each_component_has_value(self):
        """各コンポーネントに value フィールドがある"""
        for key, comp in self.data["components"].items():
            assert "value" in comp, f"{key}.value が見つかりません"

    def test_each_component_has_status(self):
        """各コンポーネントに status フィールドがある"""
        valid_statuses = {"excellent", "good", "warning", "critical"}
        for key, comp in self.data["components"].items():
            assert "status" in comp, f"{key}.status が見つかりません"
            assert comp["status"] in valid_statuses

    def test_generated_at_present(self):
        """generated_at フィールドが存在する"""
        assert "generated_at" in self.data

    def test_generated_at_is_iso_format(self):
        """generated_at は ISO 8601 形式"""
        gen_at = self.data["generated_at"]
        assert isinstance(gen_at, str)
        assert "T" in gen_at
        assert gen_at.endswith("Z")


# ===================================================================
# スコアロジックテスト
# ===================================================================


class TestHealthScoreLogic:
    """スコア計算ロジックテスト"""

    def test_score_calculation_weights(self, client):
        """スコアが重み付き平均で計算されることを確認する（全スコア100のとき overall=100）"""
        headers = _get_auth_headers(client)
        with (
            patch("psutil.cpu_percent", return_value=0.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch(
                "backend.api.routes.system._count_failed_services",
                return_value=0,
            ),
        ):
            mock_mem.return_value = MagicMock(percent=0.0)
            mock_disk.return_value = MagicMock(percent=0.0)
            resp = client.get("/api/system/health-score", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["score"] == 100
            assert data["status"] == "excellent"

    def test_high_cpu_lowers_score(self, client):
        """CPU 高使用率でスコアが下がる"""
        headers = _get_auth_headers(client)
        with (
            patch("psutil.cpu_percent", return_value=96.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
        ):
            mock_mem.return_value = MagicMock(percent=0.0)
            mock_disk.return_value = MagicMock(percent=0.0)
            resp = client.get("/api/system/health-score", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["score"] < 100
            assert data["components"]["cpu"]["score"] < 60

    def test_failed_services_lowers_score(self, client):
        """失敗サービスありでサービスコンポーネントが下がる"""
        headers = _get_auth_headers(client)
        with (
            patch("psutil.cpu_percent", return_value=0.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=1),
        ):
            mock_mem.return_value = MagicMock(percent=0.0)
            mock_disk.return_value = MagicMock(percent=0.0)
            resp = client.get("/api/system/health-score", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["components"]["services"]["score"] < 100
            assert data["components"]["services"]["value"] == 1

    def test_status_excellent_for_high_score(self, client):
        """スコア 90+ で status=excellent"""
        headers = _get_auth_headers(client)
        with (
            patch("psutil.cpu_percent", return_value=10.0),
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.disk_usage") as mock_disk,
            patch("backend.api.routes.system._count_failed_services", return_value=0),
        ):
            mock_mem.return_value = MagicMock(percent=10.0)
            mock_disk.return_value = MagicMock(percent=10.0)
            resp = client.get("/api/system/health-score", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "excellent"
            assert data["score"] >= 90
