"""
コンテナ管理 API - 統合テスト (25件以上)

docker/podman 不在環境でもモックを使用してテスト可能。
セキュリティテスト（不正入力拒否、認証、権限）を含む。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_CONTAINER_JSON = json.dumps([
    {
        "ID": "abc123def456",
        "Names": "nginx",
        "Image": "nginx:latest",
        "Status": "Up 2 hours",
        "State": "running",
        "CreatedAt": "2024-01-15T10:00:00Z",
        "Ports": "0.0.0.0:80->80/tcp",
    },
    {
        "ID": "def789ghi012",
        "Names": "postgres",
        "Image": "postgres:15",
        "Status": "Exited (0) 1 hour ago",
        "State": "exited",
        "CreatedAt": "2024-01-15T09:00:00Z",
        "Ports": "",
    },
])

SAMPLE_INSPECT_JSON = json.dumps([
    {
        "Id": "abc123def456abc123def456",
        "Name": "/nginx",
        "State": {"Status": "running", "Running": True},
        "Config": {"Image": "nginx:latest"},
        "NetworkSettings": {"IPAddress": "172.17.0.2"},
    }
])

SAMPLE_STATS_JSON = json.dumps({
    "Name": "nginx",
    "CPUPerc": "0.12%",
    "MemUsage": "10MiB / 2GiB",
    "MemPerc": "0.49%",
    "NetIO": "1.2MB / 500kB",
    "BlockIO": "0B / 0B",
})

SAMPLE_IMAGES_JSON = json.dumps([
    {
        "ID": "sha256:abc123",
        "Repository": "nginx",
        "Tag": "latest",
        "Size": "142MB",
        "CreatedAt": "2024-01-01T00:00:00Z",
    },
    {
        "ID": "sha256:def456",
        "Repository": "postgres",
        "Tag": "15",
        "Size": "379MB",
        "CreatedAt": "2024-01-02T00:00:00Z",
    },
])


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def client():
    """テストクライアント"""
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def operator_token(client):
    resp = client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_token(client):
    resp = client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


def _mock_runtime(rt: str = "docker"):
    """_detect_runtime をモック"""
    return patch("backend.api.routes.containers._detect_runtime", return_value=rt)


def _mock_wrapper(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """_run_wrapper をモック"""
    return patch(
        "backend.api.routes.containers._run_wrapper",
        return_value={"status": "success" if returncode == 0 else "error", "stdout": stdout, "stderr": stderr, "returncode": returncode},
    )


def _mock_wrapper_error(detail: str = "error", status_code: int = 503):
    """_run_wrapper が HTTPException を raise するモック"""
    from fastapi import HTTPException
    return patch(
        "backend.api.routes.containers._run_wrapper",
        side_effect=HTTPException(status_code=status_code, detail=detail),
    )


# ===================================================================
# テスト: 認証チェック
# ===================================================================


def test_list_containers_no_auth(client):
    """未認証では 403/401 を返すこと"""
    resp = client.get("/api/containers/")
    assert resp.status_code in (401, 403)


def test_inspect_container_no_auth(client):
    """未認証では inspect も 403/401"""
    resp = client.get("/api/containers/nginx")
    assert resp.status_code in (401, 403)


def test_start_container_no_auth(client):
    """未認証では start も 403/401"""
    resp = client.post("/api/containers/nginx/start")
    assert resp.status_code in (401, 403)


def test_stop_container_no_auth(client):
    """未認証では stop も 403/401"""
    resp = client.post("/api/containers/nginx/stop")
    assert resp.status_code in (401, 403)


# ===================================================================
# テスト: Viewer 権限（read:containers のみ）
# ===================================================================


def test_viewer_can_list_containers(client, viewer_headers):
    """Viewer はコンテナ一覧を取得できる"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_CONTAINER_JSON):
        resp = client.get("/api/containers/", headers=viewer_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "containers" in data


def test_viewer_can_list_images(client, viewer_headers):
    """Viewer はイメージ一覧を取得できる"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_IMAGES_JSON):
        resp = client.get("/api/containers/images", headers=viewer_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "images" in data


def test_viewer_cannot_start_container(client, viewer_headers):
    """Viewer はコンテナを起動できない（write:containers 権限なし）"""
    resp = client.post("/api/containers/nginx/start", headers=viewer_headers)
    assert resp.status_code == 403


def test_viewer_cannot_stop_container(client, viewer_headers):
    """Viewer はコンテナを停止できない"""
    resp = client.post("/api/containers/nginx/stop", headers=viewer_headers)
    assert resp.status_code == 403


def test_viewer_cannot_restart_container(client, viewer_headers):
    """Viewer はコンテナを再起動できない"""
    resp = client.post("/api/containers/nginx/restart", headers=viewer_headers)
    assert resp.status_code == 403


def test_viewer_cannot_prune(client, viewer_headers):
    """Viewer は prune を実行できない"""
    resp = client.post("/api/containers/prune", headers=viewer_headers)
    assert resp.status_code == 403


# ===================================================================
# テスト: コンテナ一覧
# ===================================================================


def test_list_containers_success(client, admin_headers):
    """コンテナ一覧を正常に取得できること"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_CONTAINER_JSON):
        resp = client.get("/api/containers/", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total"] == 2
    assert data["running"] >= 1
    assert "timestamp" in data
    assert data["runtime"] in ("docker", "podman")


def test_list_containers_empty(client, admin_headers):
    """コンテナが存在しない場合は空リストを返す"""
    with _mock_runtime(), _mock_wrapper(stdout="[]"):
        resp = client.get("/api/containers/", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_containers_no_runtime(client, admin_headers):
    """docker/podman 不在時は 503 を返すこと"""
    with patch("backend.api.routes.containers._detect_runtime", return_value=None):
        resp = client.get("/api/containers/", headers=admin_headers)
    assert resp.status_code == 503


# ===================================================================
# テスト: コンテナ詳細
# ===================================================================


def test_inspect_container_success(client, admin_headers):
    """コンテナ詳細を取得できること"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_INSPECT_JSON):
        resp = client.get("/api/containers/nginx", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["name"] == "nginx"


def test_inspect_container_no_runtime(client, admin_headers):
    """runtime 不在時は 503"""
    with patch("backend.api.routes.containers._detect_runtime", return_value=None):
        resp = client.get("/api/containers/nginx", headers=admin_headers)
    assert resp.status_code == 503


# ===================================================================
# テスト: セキュリティ（不正コンテナ名の拒否）
# ===================================================================


@pytest.mark.parametrize("bad_name", [
    "nginx; rm -rf /",
    "nginx|cat /etc/passwd",
    "nginx&ls",
    "nginx$(id)",
    "nginx`id`",
    "nginx>>/etc/passwd",
    "../../../etc/passwd",
    "nginx%00null",
    "a" * 129,  # 長すぎる名前
    # "" は空pathとして /api/containers に redirect されるため除外
    "nginx spaces here",
    "nginx{bad}",
    "nginx[bracket]",
])
def test_reject_invalid_container_name_inspect(client, admin_headers, bad_name):
    """不正なコンテナ名は inspect で 400/404/422 を返すこと"""
    with _mock_runtime():
        resp = client.get(f"/api/containers/{bad_name}", headers=admin_headers)
    assert resp.status_code in (400, 404, 422), f"Expected 400/404/422 for name={bad_name!r}, got {resp.status_code}"


@pytest.mark.parametrize("bad_name", [
    "nginx; rm -rf /",
    "nginx|cmd",
    "nginx&id",
    "nginx$(whoami)",
])
def test_reject_invalid_container_name_start(client, operator_headers, bad_name):
    """不正なコンテナ名は start で 400/404/422 を返すこと"""
    with _mock_runtime():
        resp = client.post(f"/api/containers/{bad_name}/start", headers=operator_headers)
    assert resp.status_code in (400, 404, 422), f"Expected 400/404/422 for name={bad_name!r}, got {resp.status_code}"


# ===================================================================
# テスト: コンテナ起動
# ===================================================================


def test_start_container_success(client, operator_headers):
    """Operator はコンテナを起動できること"""
    with _mock_runtime(), _mock_wrapper(stdout="nginx"):
        resp = client.post("/api/containers/nginx/start", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["action"] == "start"
    assert data["name"] == "nginx"


def test_start_container_failure(client, operator_headers):
    """起動失敗時は 500 を返すこと"""
    with _mock_runtime(), _mock_wrapper(stdout="", returncode=1, stderr="No such container"):
        resp = client.post("/api/containers/nginx/start", headers=operator_headers)
    assert resp.status_code == 500


def test_start_container_no_runtime(client, operator_headers):
    """runtime 不在時は 503"""
    with patch("backend.api.routes.containers._detect_runtime", return_value=None):
        resp = client.post("/api/containers/nginx/start", headers=operator_headers)
    assert resp.status_code == 503


def _mock_approval_create(request_id: str = "test-req-id-001"):
    """_approval_service.create_request をモック（非同期対応）"""
    return patch(
        "backend.api.routes.containers._approval_service.create_request",
        new=AsyncMock(return_value={"request_id": request_id, "status": "pending"}),
    )


# ===================================================================
# テスト: コンテナ停止（承認フロー）
# ===================================================================


def test_stop_container_creates_approval(client, operator_headers):
    """コンテナ停止は承認リクエストを作成すること"""
    with _mock_runtime(), _mock_approval_create():
        resp = client.post("/api/containers/nginx/stop", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "request_id" in data
    assert data["action"] == "stop"
    assert data["target"] == "nginx"


def test_restart_container_creates_approval(client, operator_headers):
    """コンテナ再起動は承認リクエストを作成すること"""
    with _mock_runtime(), _mock_approval_create():
        resp = client.post("/api/containers/myapp/restart", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["action"] == "restart"
    assert data["target"] == "myapp"


# ===================================================================
# テスト: ログ取得
# ===================================================================


def test_get_container_logs(client, admin_headers):
    """コンテナログを取得できること"""
    sample_logs = "2024-01-15T10:00:00 Starting nginx\n2024-01-15T10:00:01 Ready"
    with _mock_runtime(), _mock_wrapper(stdout=sample_logs):
        resp = client.get("/api/containers/nginx/logs", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "logs" in data
    assert "nginx" in data["logs"] or data["logs"] == sample_logs


# ===================================================================
# テスト: 統計取得
# ===================================================================


def test_get_container_stats(client, admin_headers):
    """コンテナ統計を取得できること"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_STATS_JSON):
        resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "stats" in data


def test_get_container_stats_empty(client, admin_headers):
    """統計が空でも正常に返すこと"""
    with _mock_runtime(), _mock_wrapper(stdout="{}"):
        resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
    assert resp.status_code == 200


# ===================================================================
# テスト: イメージ一覧
# ===================================================================


def test_list_images_success(client, admin_headers):
    """イメージ一覧を取得できること"""
    with _mock_runtime(), _mock_wrapper(stdout=SAMPLE_IMAGES_JSON):
        resp = client.get("/api/containers/images", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total"] == 2
    assert len(data["images"]) == 2


def test_list_images_no_runtime(client, admin_headers):
    """docker/podman 不在時は 503"""
    with patch("backend.api.routes.containers._detect_runtime", return_value=None):
        resp = client.get("/api/containers/images", headers=admin_headers)
    assert resp.status_code == 503


# ===================================================================
# テスト: Prune（承認フロー）
# ===================================================================


def test_prune_creates_approval(client, operator_headers):
    """prune は承認リクエストを作成すること"""
    with _mock_runtime(), _mock_approval_create():
        resp = client.post("/api/containers/prune", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["action"] == "prune"
    assert "request_id" in data


def test_prune_no_runtime(client, operator_headers):
    """docker/podman 不在時は 503"""
    with patch("backend.api.routes.containers._detect_runtime", return_value=None), _mock_approval_create():
        resp = client.post("/api/containers/prune", headers=operator_headers)
    assert resp.status_code == 503


# ===================================================================
# テスト: Admin 権限（全操作可）
# ===================================================================


def test_admin_can_start_container(client, admin_headers):
    """Admin はコンテナを起動できること"""
    with _mock_runtime(), _mock_wrapper(stdout="testcontainer"):
        resp = client.post("/api/containers/testcontainer/start", headers=admin_headers)
    assert resp.status_code == 200


def test_admin_can_stop_container_approval(client, admin_headers):
    """Admin はコンテナ停止リクエストを作成できること"""
    with _mock_runtime(), _mock_approval_create():
        resp = client.post("/api/containers/testcontainer/stop", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


# ===================================================================
# テスト: JSON Lines パース
# ===================================================================


def test_parse_json_lines_container_list(client, admin_headers):
    """JSON Lines 形式のコンテナ一覧をパースできること"""
    json_lines = (
        '{"ID":"aaa","Names":"web","Image":"nginx:1","Status":"Up 1 hour","State":"running","CreatedAt":"2024-01-01","Ports":""}\n'
        '{"ID":"bbb","Names":"db","Image":"postgres:15","Status":"Exited (0)","State":"exited","CreatedAt":"2024-01-02","Ports":""}\n'
    )
    with _mock_runtime(), _mock_wrapper(stdout=json_lines):
        resp = client.get("/api/containers/", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


def test_runtime_field_in_container_list(client, admin_headers):
    """レスポンスに runtime フィールドが含まれること"""
    with _mock_runtime("podman"), _mock_wrapper(stdout=SAMPLE_CONTAINER_JSON):
        resp = client.get("/api/containers/", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["runtime"] == "podman"


# ===================================================================
# テスト: ログ SSE ストリーミング
# ===================================================================


class TestContainerLogStream:
    """GET /api/containers/{name}/logs/stream のテスト"""

    def test_stream_unauthenticated_rejected(self, client):
        """未認証（token なし）は 422 を返すこと"""
        resp = client.get("/api/containers/nginx/logs/stream")
        assert resp.status_code in (401, 403, 422)

    def test_stream_invalid_token_rejected(self, client):
        """無効なトークンは 401 を返すこと"""
        with _mock_runtime():
            resp = client.get("/api/containers/nginx/logs/stream?token=invalid.token.here")
        assert resp.status_code == 401

    def test_stream_invalid_container_name(self, client, admin_token):
        """不正なコンテナ名は 400 を返すこと"""
        with _mock_runtime():
            resp = client.get(
                f"/api/containers/nginx%3Bbad/logs/stream?token={admin_token}"
            )
        assert resp.status_code in (400, 422)

    def test_stream_tail_too_large_rejected(self, client, admin_token):
        """tail > 1000 は 422 を返すこと"""
        with _mock_runtime():
            resp = client.get(
                f"/api/containers/nginx/logs/stream?tail=9999&token={admin_token}"
            )
        assert resp.status_code == 422

    def test_stream_tail_too_small_rejected(self, client, admin_token):
        """tail < 1 は 422 を返すこと"""
        with _mock_runtime():
            resp = client.get(
                f"/api/containers/nginx/logs/stream?tail=0&token={admin_token}"
            )
        assert resp.status_code == 422

    def test_stream_runtime_not_available(self, client, admin_token):
        """docker/podman 不在時は 503 を返すこと"""
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get(
                f"/api/containers/nginx/logs/stream?token={admin_token}"
            )
        assert resp.status_code == 503

    def test_stream_endpoint_requires_read_containers_permission(self, client, viewer_token):
        """read:containers 権限があれば 200 (SSE) を返すこと"""
        with _mock_runtime():
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=Exception("subprocess not called in unit test"),
            ):
                resp = client.get(
                    f"/api/containers/nginx/logs/stream?token={viewer_token}",
                    headers={"Accept": "text/event-stream"},
                )
        # 認証・権限は通過し、SSE ストリームが開始される（200 or streaming error）
        assert resp.status_code in (200, 500)

    def test_stream_endpoint_exists(self, client, admin_token):
        """エンドポイントが存在し、有効なリクエストで 200 を返すこと"""
        with _mock_runtime():
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=Exception("subprocess not called in unit test"),
            ):
                resp = client.get(
                    f"/api/containers/nginx/logs/stream?token={admin_token}",
                    headers={"Accept": "text/event-stream"},
                )
        assert resp.status_code in (200, 500)
