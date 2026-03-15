"""
nginx.py カバレッジ改善テスト v2

対象: backend/api/routes/nginx.py (47% -> 85%+)
未カバー箇所を重点的にテスト:
  - 全5エンドポイント (status/config/vhosts/connections/logs)
  - SudoWrapperError 例外ハンドリング
  - parse_wrapper_result 経由のデータ返却
  - logs エンドポイントの status=="error" 分岐
  - 各レスポンスモデルのフィールド検証
  - Viewer/Admin/Operator の権限テスト
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# テストデータ
STATUS_OK = {
    "status": "success",
    "service": "nginx",
    "active": "active",
    "enabled": "enabled",
    "version": "nginx/1.24.0",
    "timestamp": "2026-03-15T00:00:00Z",
}

STATUS_INACTIVE = {
    "status": "success",
    "service": "nginx",
    "active": "inactive",
    "enabled": "disabled",
    "version": "nginx/1.24.0",
    "timestamp": "2026-03-15T00:00:00Z",
}

CONFIG_OK = {
    "status": "success",
    "config": "worker_processes auto;\nevents { worker_connections 1024; }\n",
    "timestamp": "2026-03-15T00:00:00Z",
}

VHOSTS_MULTIPLE = {
    "status": "success",
    "vhosts": [
        {"name": "default", "path": "/etc/nginx/sites-enabled/default", "is_symlink": True},
        {"name": "api.example.com", "path": "/etc/nginx/sites-enabled/api.example.com", "is_symlink": True},
    ],
    "timestamp": "2026-03-15T00:00:00Z",
}

CONNECTIONS_MULTIPLE = {
    "status": "success",
    "connections_raw": "ESTAB  0  0  0.0.0.0:80  client1:1234\nESTAB  0  0  0.0.0.0:443  client2:5678\n",
    "timestamp": "2026-03-15T00:00:00Z",
}

LOGS_MULTIPLE = {
    "status": "success",
    "logs": '127.0.0.1 - - [15/Mar/2026] "GET / HTTP/1.1" 200\n10.0.0.1 - - [15/Mar/2026] "POST /api HTTP/1.1" 201\n',
    "lines": 2,
    "timestamp": "2026-03-15T00:00:00Z",
}

LOGS_ERROR = {
    "status": "error",
    "message": "permission denied",
    "timestamp": "2026-03-15T00:00:00Z",
}


def _patch_sudo(method_name, return_value=None, side_effect=None):
    """sudo_wrapper メソッドをパッチするヘルパー"""
    target = f"backend.core.sudo_wrapper.sudo_wrapper.{method_name}"
    if side_effect:
        return patch(target, side_effect=side_effect)
    return patch(target, return_value=return_value)


# ===================================================================
# GET /api/nginx/status 追加テスト
# ===================================================================


class TestNginxStatusV2:
    """GET /api/nginx/status の追加カバレッジ"""

    def test_status_active_fields(self, test_client, admin_headers):
        """全フィールドが正しく返される"""
        with _patch_sudo("get_nginx_status", STATUS_OK):
            resp = test_client.get("/api/nginx/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "nginx"
        assert data["active"] == "active"
        assert data["enabled"] == "enabled"
        assert data["version"] == "nginx/1.24.0"
        assert "timestamp" in data

    def test_status_inactive(self, test_client, admin_headers):
        """inactive 状態が返される"""
        with _patch_sudo("get_nginx_status", STATUS_INACTIVE):
            resp = test_client.get("/api/nginx/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] == "inactive"
        assert data["enabled"] == "disabled"

    def test_status_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のエラー詳細が 503 レスポンスに含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with _patch_sudo("get_nginx_status", side_effect=SudoWrapperError("nginx not found")):
            resp = test_client.get("/api/nginx/status", headers=admin_headers)
        assert resp.status_code == 503
        assert "nginx not found" in resp.json().get("detail", resp.json().get("message", ""))

    def test_status_operator_can_read(self, test_client, operator_headers):
        """Operator も read:nginx を持つ"""
        with _patch_sudo("get_nginx_status", STATUS_OK):
            resp = test_client.get("/api/nginx/status", headers=operator_headers)
        assert resp.status_code == 200

    def test_status_viewer_can_read(self, test_client, viewer_headers):
        """Viewer も read:nginx を持つ"""
        with _patch_sudo("get_nginx_status", STATUS_OK):
            resp = test_client.get("/api/nginx/status", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# GET /api/nginx/config 追加テスト
# ===================================================================


class TestNginxConfigV2:
    """GET /api/nginx/config の追加カバレッジ"""

    def test_config_content(self, test_client, admin_headers):
        """設定内容が返される"""
        with _patch_sudo("get_nginx_config", CONFIG_OK):
            resp = test_client.get("/api/nginx/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "worker_processes" in data.get("config", "")

    def test_config_wrapper_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError
        with _patch_sudo("get_nginx_config", side_effect=SudoWrapperError("permission denied")):
            resp = test_client.get("/api/nginx/config", headers=admin_headers)
        assert resp.status_code == 503

    def test_config_operator(self, test_client, operator_headers):
        with _patch_sudo("get_nginx_config", CONFIG_OK):
            resp = test_client.get("/api/nginx/config", headers=operator_headers)
        assert resp.status_code == 200

    def test_config_viewer(self, test_client, viewer_headers):
        with _patch_sudo("get_nginx_config", CONFIG_OK):
            resp = test_client.get("/api/nginx/config", headers=viewer_headers)
        assert resp.status_code == 200

    def test_config_unauthenticated(self, test_client):
        resp = test_client.get("/api/nginx/config")
        assert resp.status_code == 403


# ===================================================================
# GET /api/nginx/vhosts 追加テスト
# ===================================================================


class TestNginxVhostsV2:
    """GET /api/nginx/vhosts の追加カバレッジ"""

    def test_vhosts_multiple(self, test_client, admin_headers):
        """複数 vhost が返される"""
        with _patch_sudo("get_nginx_vhosts", VHOSTS_MULTIPLE):
            resp = test_client.get("/api/nginx/vhosts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["vhosts"]) == 2

    def test_vhosts_wrapper_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError
        with _patch_sudo("get_nginx_vhosts", side_effect=SudoWrapperError("failed")):
            resp = test_client.get("/api/nginx/vhosts", headers=admin_headers)
        assert resp.status_code == 503

    def test_vhosts_operator(self, test_client, operator_headers):
        with _patch_sudo("get_nginx_vhosts", VHOSTS_MULTIPLE):
            resp = test_client.get("/api/nginx/vhosts", headers=operator_headers)
        assert resp.status_code == 200

    def test_vhosts_unauthenticated(self, test_client):
        resp = test_client.get("/api/nginx/vhosts")
        assert resp.status_code == 403


# ===================================================================
# GET /api/nginx/connections 追加テスト
# ===================================================================


class TestNginxConnectionsV2:
    """GET /api/nginx/connections の追加カバレッジ"""

    def test_connections_multiple(self, test_client, admin_headers):
        """複数接続が返される"""
        with _patch_sudo("get_nginx_connections", CONNECTIONS_MULTIPLE):
            resp = test_client.get("/api/nginx/connections", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "connections_raw" in data
        assert "client1" in data["connections_raw"]

    def test_connections_wrapper_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError
        with _patch_sudo("get_nginx_connections", side_effect=SudoWrapperError("failed")):
            resp = test_client.get("/api/nginx/connections", headers=admin_headers)
        assert resp.status_code == 503

    def test_connections_operator(self, test_client, operator_headers):
        with _patch_sudo("get_nginx_connections", CONNECTIONS_MULTIPLE):
            resp = test_client.get("/api/nginx/connections", headers=operator_headers)
        assert resp.status_code == 200

    def test_connections_unauthenticated(self, test_client):
        resp = test_client.get("/api/nginx/connections")
        assert resp.status_code == 403


# ===================================================================
# GET /api/nginx/logs 追加テスト
# ===================================================================


class TestNginxLogsV2:
    """GET /api/nginx/logs の追加カバレッジ"""

    def test_logs_multiple_lines(self, test_client, admin_headers):
        """複数行のログが返される"""
        with _patch_sudo("get_nginx_logs", LOGS_MULTIPLE):
            resp = test_client.get("/api/nginx/logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 2

    def test_logs_error_status_returns_503(self, test_client, admin_headers):
        """logs が status=error を返した場合 503"""
        with _patch_sudo("get_nginx_logs", LOGS_ERROR):
            resp = test_client.get("/api/nginx/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "permission denied" in resp.json().get("detail", resp.json().get("message", ""))

    def test_logs_error_status_default_message(self, test_client, admin_headers):
        """logs が status=error で message なしの場合デフォルトメッセージ"""
        with _patch_sudo("get_nginx_logs", {"status": "error", "timestamp": "2026-01-01T00:00:00Z"}):
            resp = test_client.get("/api/nginx/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "unavailable" in resp.json().get("detail", resp.json().get("message", "")).lower()

    def test_logs_wrapper_error_detail(self, test_client, admin_headers):
        from backend.core.sudo_wrapper import SudoWrapperError
        with _patch_sudo("get_nginx_logs", side_effect=SudoWrapperError("log read failed")):
            resp = test_client.get("/api/nginx/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "log read failed" in resp.json().get("detail", resp.json().get("message", ""))

    def test_logs_lines_0(self, test_client, admin_headers):
        """lines=0 は 422 (ge=1 制約)"""
        resp = test_client.get("/api/nginx/logs?lines=0", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_lines_negative(self, test_client, admin_headers):
        """lines=-1 は 422"""
        resp = test_client.get("/api/nginx/logs?lines=-1", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_operator(self, test_client, operator_headers):
        with _patch_sudo("get_nginx_logs", LOGS_MULTIPLE):
            resp = test_client.get("/api/nginx/logs", headers=operator_headers)
        assert resp.status_code == 200

    def test_logs_viewer(self, test_client, viewer_headers):
        with _patch_sudo("get_nginx_logs", LOGS_MULTIPLE):
            resp = test_client.get("/api/nginx/logs", headers=viewer_headers)
        assert resp.status_code == 200

    def test_logs_unauthenticated(self, test_client):
        resp = test_client.get("/api/nginx/logs")
        assert resp.status_code == 403

    @pytest.mark.parametrize("lines", [1, 50, 100, 200])
    def test_logs_valid_lines_param(self, test_client, admin_headers, lines):
        """有効な lines パラメータ"""
        with _patch_sudo("get_nginx_logs", LOGS_MULTIPLE):
            resp = test_client.get(f"/api/nginx/logs?lines={lines}", headers=admin_headers)
        assert resp.status_code == 200


# ===================================================================
# parse_wrapper_result ヘルパーテスト
# ===================================================================


class TestParseWrapperResult:
    """_utils.parse_wrapper_result の全分岐テスト"""

    def test_parse_json_output(self):
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success", "output": '{"key": "value"}'}
        parsed = parse_wrapper_result(result)
        assert parsed == {"key": "value"}

    def test_parse_non_json_output(self):
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success", "output": "not json"}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_parse_no_output(self):
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success"}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_parse_none_output(self):
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success", "output": None}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_parse_empty_output(self):
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success", "output": ""}
        parsed = parse_wrapper_result(result)
        assert parsed == result

    def test_parse_dict_already(self):
        """output がすでに dict の場合（str ではない）"""
        from backend.api.routes._utils import parse_wrapper_result
        result = {"status": "success", "output": {"already": "parsed"}}
        parsed = parse_wrapper_result(result)
        assert parsed == result


# ===================================================================
# レスポンスモデルテスト
# ===================================================================


class TestNginxResponseModels:
    """Nginx レスポンスモデルのテスト"""

    def test_status_response_model(self):
        from backend.api.routes.nginx import NginxStatusResponse
        resp = NginxStatusResponse(
            status="success", service="nginx", active="active",
            enabled="enabled", version="1.24", timestamp="2026-01-01T00:00:00Z"
        )
        assert resp.status == "success"
        assert resp.message is None

    def test_config_response_model(self):
        from backend.api.routes.nginx import NginxConfigResponse
        resp = NginxConfigResponse(status="success", config="test config", timestamp="2026-01-01T00:00:00Z")
        assert resp.config == "test config"

    def test_vhosts_response_model(self):
        from backend.api.routes.nginx import NginxVhostsResponse
        resp = NginxVhostsResponse(status="success", vhosts=[], timestamp="2026-01-01T00:00:00Z")
        assert resp.vhosts == []

    def test_connections_response_model(self):
        from backend.api.routes.nginx import NginxConnectionsResponse
        resp = NginxConnectionsResponse(status="success", connections_raw="data", timestamp="2026-01-01T00:00:00Z")
        assert resp.connections_raw == "data"

    def test_logs_response_model(self):
        from backend.api.routes.nginx import NginxLogsResponse
        resp = NginxLogsResponse(status="success", logs="log data", lines=10, timestamp="2026-01-01T00:00:00Z")
        assert resp.lines == 10
        assert resp.message is None
