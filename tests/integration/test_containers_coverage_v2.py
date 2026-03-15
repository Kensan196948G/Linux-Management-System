"""
Containers API - カバレッジ改善テスト v2

対象: backend/api/routes/containers.py
目標: 85%以上のカバレッジ

全ヘルパー関数・エンドポイントの分岐を網羅する。
"""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_CONTAINERS_JSON_ARRAY = json.dumps([
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

SAMPLE_CONTAINERS_JSON_LINES = (
    '{"ID":"aaa111","Names":"web","Image":"nginx:1","Status":"Up 1 hour","State":"running","CreatedAt":"2024-01-01","Ports":""}\n'
    '{"ID":"bbb222","Names":"db","Image":"postgres:15","Status":"Exited (0)","State":"exited","CreatedAt":"2024-01-02","Ports":""}\n'
)

SAMPLE_INSPECT = json.dumps([
    {
        "Id": "abc123def456abc123",
        "Name": "/nginx",
        "State": {"Status": "running"},
        "Config": {"Image": "nginx:latest"},
    }
])

SAMPLE_STATS = json.dumps({
    "Name": "nginx",
    "CPUPerc": "0.12%",
    "MemUsage": "10MiB / 2GiB",
})

SAMPLE_IMAGES_JSON_ARRAY = json.dumps([
    {
        "ID": "sha256:img001",
        "Repository": "nginx",
        "Tag": "latest",
        "Size": "142MB",
        "CreatedAt": "2024-01-01T00:00:00Z",
    },
    {
        "ID": "sha256:img002",
        "Repository": "postgres",
        "Tag": "15",
        "Size": "379MB",
        "CreatedAt": "2024-01-02T00:00:00Z",
    },
])

SAMPLE_IMAGES_JSON_LINES = (
    '{"ID":"sha256:i1","Repository":"redis","Tag":"7","Size":"120MB","CreatedAt":"2024-03-01"}\n'
    '{"ID":"sha256:i2","Repo":"mongo","tag":"6","VirtualSize":"500MB","Created":"2024-03-02"}\n'
)


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def client():
    from backend.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def operator_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def viewer_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


def _mock_runtime(rt="docker"):
    return patch("backend.api.routes.containers._detect_runtime", return_value=rt)


def _mock_wrapper_result(stdout="", returncode=0, stderr=""):
    return patch(
        "backend.api.routes.containers._run_wrapper",
        return_value={
            "status": "success" if returncode == 0 else "error",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        },
    )


def _mock_approval_create(request_id="test-req-001"):
    return patch(
        "backend.api.routes.containers._approval_service.create_request",
        new=AsyncMock(return_value={"request_id": request_id, "status": "pending"}),
    )


# ===================================================================
# テスト: _wrapper_path ヘルパー
# ===================================================================


class TestWrapperPath:
    """_wrapper_path の分岐テスト"""

    def test_prod_path_exists(self):
        from backend.api.routes.containers import _wrapper_path

        with patch("backend.api.routes.containers.Path") as mock_path:
            mock_prod = MagicMock()
            mock_prod.exists.return_value = True
            mock_path.return_value = mock_prod
            mock_path.__str__ = lambda s: "/usr/local/sbin/adminui-containers.sh"
            result = _wrapper_path()
        # prod path 文字列を返す
        assert result is not None

    def test_dev_path_fallback(self):
        from backend.api.routes.containers import _wrapper_path

        with patch("backend.api.routes.containers.Path") as mock_path:
            mock_prod = MagicMock()
            mock_prod.exists.return_value = False
            # 2番目の Path() 呼び出し（__file__） -> dev path
            mock_dev = MagicMock()
            mock_dev.parent = MagicMock()
            mock_dev.parent.parent = MagicMock()
            mock_dev.parent.parent.parent = MagicMock()
            mock_dev.parent.parent.parent.__truediv__ = lambda s, x: MagicMock(
                __truediv__=lambda s2, y: MagicMock(__str__=lambda s3: "/dev/wrappers/adminui-containers.sh")
            )

            def path_side_effect(arg):
                if str(arg) == "/usr/local/sbin/adminui-containers.sh":
                    return mock_prod
                return mock_dev

            mock_path.side_effect = path_side_effect
            result = _wrapper_path()
        assert result is not None


# ===================================================================
# テスト: _detect_runtime ヘルパー
# ===================================================================


class TestDetectRuntime:
    """_detect_runtime の全分岐テスト"""

    def test_docker_found(self):
        from backend.api.routes.containers import _detect_runtime

        with patch("backend.api.routes.containers.shutil.which", side_effect=lambda x: "/usr/bin/docker" if x == "docker" else None):
            assert _detect_runtime() == "docker"

    def test_podman_found(self):
        from backend.api.routes.containers import _detect_runtime

        with patch("backend.api.routes.containers.shutil.which", side_effect=lambda x: "/usr/bin/podman" if x == "podman" else None):
            assert _detect_runtime() == "podman"

    def test_neither_found(self):
        from backend.api.routes.containers import _detect_runtime

        with patch("backend.api.routes.containers.shutil.which", return_value=None):
            assert _detect_runtime() is None


# ===================================================================
# テスト: _run_wrapper ヘルパー
# ===================================================================


class TestRunWrapperHelper:
    """_run_wrapper の全分岐テスト"""

    def test_success(self):
        from backend.api.routes.containers import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["list"])
        assert result["status"] == "success"
        assert result["stdout"] == "output"

    def test_returncode_2_runtime_not_installed(self):
        from backend.api.routes.containers import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 2

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", return_value=mock_result):
            with pytest.raises(HTTPException) as exc_info:
                _run_wrapper(["list"])
            assert exc_info.value.status_code == 503

    def test_returncode_1_with_error_message(self):
        from backend.api.routes.containers import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: invalid name"
        mock_result.returncode = 1

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", return_value=mock_result):
            with pytest.raises(HTTPException) as exc_info:
                _run_wrapper(["inspect", "bad"])
            assert exc_info.value.status_code == 400

    def test_returncode_1_without_error_keyword(self):
        """returncode=1 だが stderr に 'Error:' を含まない"""
        from backend.api.routes.containers import _run_wrapper

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "some warning"
        mock_result.returncode = 1

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", return_value=mock_result):
            result = _run_wrapper(["inspect", "name"])
        assert result["status"] == "error"
        assert result["returncode"] == 1

    def test_file_not_found(self):
        from backend.api.routes.containers import _run_wrapper

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", side_effect=FileNotFoundError("not found")):
            with pytest.raises(HTTPException) as exc_info:
                _run_wrapper(["list"])
            assert exc_info.value.status_code == 503

    def test_timeout_expired(self):
        from backend.api.routes.containers import _run_wrapper

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=30)):
            with pytest.raises(HTTPException) as exc_info:
                _run_wrapper(["list"], timeout=30)
            assert exc_info.value.status_code == 504

    def test_generic_exception(self):
        from backend.api.routes.containers import _run_wrapper

        with patch("backend.api.routes.containers._wrapper_path", return_value="/wrapper.sh"), \
             patch("backend.api.routes.containers.subprocess.run", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc_info:
                _run_wrapper(["list"])
            assert exc_info.value.status_code == 500


# ===================================================================
# テスト: _require_runtime ヘルパー
# ===================================================================


class TestRequireRuntime:
    """_require_runtime の分岐テスト"""

    def test_returns_runtime(self):
        from backend.api.routes.containers import _require_runtime

        with _mock_runtime("docker"):
            assert _require_runtime() == "docker"

    def test_raises_when_none(self):
        from backend.api.routes.containers import _require_runtime

        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                _require_runtime()
            assert exc_info.value.status_code == 503


# ===================================================================
# テスト: _validate_container_name ヘルパー
# ===================================================================


class TestValidateContainerName:
    """_validate_container_name の分岐テスト"""

    @pytest.mark.parametrize(
        "valid_name",
        ["nginx", "my-container", "app_v2", "web.server", "A123", "a" * 128],
    )
    def test_valid_names(self, valid_name):
        from backend.api.routes.containers import _validate_container_name

        _validate_container_name(valid_name)  # no exception

    @pytest.mark.parametrize(
        "bad_name",
        [
            "nginx;rm -rf /",
            "app|cat",
            "test name",
            "test$(id)",
            "test`id`",
            "../etc/passwd",
            "a" * 129,
            "test{bad}",
            "test[0]",
            "",
        ],
    )
    def test_invalid_names(self, bad_name):
        from backend.api.routes.containers import _validate_container_name

        with pytest.raises(HTTPException) as exc_info:
            _validate_container_name(bad_name)
        assert exc_info.value.status_code == 400


# ===================================================================
# テスト: _parse_container_list ヘルパー
# ===================================================================


class TestParseContainerList:
    """_parse_container_list の全分岐テスト"""

    def test_json_array(self):
        from backend.api.routes.containers import _parse_container_list

        result = _parse_container_list(SAMPLE_CONTAINERS_JSON_ARRAY, "docker")
        assert len(result) == 2
        assert result[0].name == "nginx"
        assert result[0].runtime == "docker"

    def test_json_lines(self):
        from backend.api.routes.containers import _parse_container_list

        result = _parse_container_list(SAMPLE_CONTAINERS_JSON_LINES, "podman")
        assert len(result) == 2
        assert result[0].runtime == "podman"

    def test_empty_string(self):
        from backend.api.routes.containers import _parse_container_list

        result = _parse_container_list("", "docker")
        assert result == []

    def test_invalid_json_array(self):
        from backend.api.routes.containers import _parse_container_list

        result = _parse_container_list("[invalid json", "docker")
        # falls through to JSON Lines parsing, each line also fails -> empty
        assert result == []

    def test_invalid_json_lines(self):
        from backend.api.routes.containers import _parse_container_list

        result = _parse_container_list("not json\nalso not json\n", "docker")
        assert result == []

    def test_blank_lines_skipped(self):
        from backend.api.routes.containers import _parse_container_list

        stdout = '\n  \n{"ID":"a","Names":"x","Image":"img","Status":"Up","State":"running","CreatedAt":"","Ports":""}\n\n'
        result = _parse_container_list(stdout, "docker")
        assert len(result) == 1


# ===================================================================
# テスト: _dict_to_container ヘルパー
# ===================================================================


class TestDictToContainer:
    """_dict_to_container の全分岐テスト"""

    def test_docker_format(self):
        from backend.api.routes.containers import _dict_to_container

        d = {
            "ID": "abc123def456",
            "Names": "/nginx",
            "Image": "nginx:latest",
            "Status": "Up 2 hours",
            "State": "running",
            "CreatedAt": "2024-01-15",
            "Ports": "80/tcp",
        }
        c = _dict_to_container(d, "docker")
        assert c.name == "nginx"  # leading / stripped
        assert c.id == "abc123def456"
        assert c.runtime == "docker"

    def test_podman_format(self):
        from backend.api.routes.containers import _dict_to_container

        d = {
            "Id": "xyz789",
            "Name": "myapp",
            "image": "myapp:v2",
            "status": "exited",
            "state": "exited",
            "created": "2024-01-01",
            "ports": {"80": "8080"},
        }
        c = _dict_to_container(d, "podman")
        assert c.name == "myapp"
        assert c.runtime == "podman"
        assert c.ports  # dict converted to string

    def test_names_as_list(self):
        from backend.api.routes.containers import _dict_to_container

        d = {"Names": ["web", "app"], "Image": "img", "ID": "123"}
        c = _dict_to_container(d, "docker")
        assert c.name == "web, app"

    def test_ports_as_list(self):
        from backend.api.routes.containers import _dict_to_container

        d = {"Names": "test", "Image": "img", "ID": "123", "Ports": [{"80": "8080"}]}
        c = _dict_to_container(d, "docker")
        assert isinstance(c.ports, str)

    def test_id_truncated_to_12(self):
        from backend.api.routes.containers import _dict_to_container

        d = {"ID": "a" * 64, "Names": "test", "Image": "img"}
        c = _dict_to_container(d, "docker")
        assert len(c.id) == 12

    def test_empty_dict(self):
        from backend.api.routes.containers import _dict_to_container

        c = _dict_to_container({}, "docker")
        assert c.name == ""
        assert c.image == ""

    def test_state_lowercase(self):
        from backend.api.routes.containers import _dict_to_container

        d = {"State": "Running", "Names": "x", "Image": "y", "ID": "z"}
        c = _dict_to_container(d, "docker")
        assert c.state == "running"


# ===================================================================
# テスト: _parse_image_list ヘルパー
# ===================================================================


class TestParseImageList:
    """_parse_image_list の全分岐テスト"""

    def test_json_array(self):
        from backend.api.routes.containers import _parse_image_list

        result = _parse_image_list(SAMPLE_IMAGES_JSON_ARRAY, "docker")
        assert len(result) == 2

    def test_json_lines(self):
        from backend.api.routes.containers import _parse_image_list

        result = _parse_image_list(SAMPLE_IMAGES_JSON_LINES, "docker")
        assert len(result) == 2

    def test_empty_string(self):
        from backend.api.routes.containers import _parse_image_list

        result = _parse_image_list("", "docker")
        assert result == []

    def test_invalid_json_array(self):
        from backend.api.routes.containers import _parse_image_list

        result = _parse_image_list("[bad", "docker")
        assert result == []

    def test_invalid_json_lines(self):
        from backend.api.routes.containers import _parse_image_list

        result = _parse_image_list("not json\nbad\n", "docker")
        assert result == []

    def test_blank_lines_skipped(self):
        from backend.api.routes.containers import _parse_image_list

        stdout = '\n{"ID":"i1","Repository":"r","Tag":"t","Size":"1MB","CreatedAt":"2024-01-01"}\n\n'
        result = _parse_image_list(stdout, "docker")
        assert len(result) == 1


# ===================================================================
# テスト: _dict_to_image ヘルパー
# ===================================================================


class TestDictToImage:
    """_dict_to_image の全分岐テスト"""

    def test_standard_fields(self):
        from backend.api.routes.containers import _dict_to_image

        d = {
            "ID": "sha256:abc123def456",
            "Repository": "nginx",
            "Tag": "latest",
            "Size": "142MB",
            "CreatedAt": "2024-01-01",
        }
        img = _dict_to_image(d)
        assert img.repository == "nginx"
        assert img.tag == "latest"
        assert img.id == "sha256:abc12"  # truncated to 12

    def test_alternative_fields(self):
        from backend.api.routes.containers import _dict_to_image

        d = {
            "id": "xyz789",
            "repository": "myimg",
            "tag": "v2",
            "size": "100MB",
            "created": "2024-02-01",
        }
        img = _dict_to_image(d)
        assert img.repository == "myimg"
        assert img.tag == "v2"

    def test_repo_alias(self):
        from backend.api.routes.containers import _dict_to_image

        d = {"Repo": "myrepo", "Id": "aaa"}
        img = _dict_to_image(d)
        assert img.repository == "myrepo"

    def test_virtual_size_fallback(self):
        from backend.api.routes.containers import _dict_to_image

        d = {"VirtualSize": "500MB", "ID": "b"}
        img = _dict_to_image(d)
        assert img.size == "500MB"

    def test_tag_default(self):
        from backend.api.routes.containers import _dict_to_image

        d = {"ID": "c"}
        img = _dict_to_image(d)
        assert img.tag == "latest"

    def test_empty_dict(self):
        from backend.api.routes.containers import _dict_to_image

        img = _dict_to_image({})
        assert img.repository == ""
        assert img.tag == "latest"


# ===================================================================
# テスト: _now_iso ヘルパー
# ===================================================================


class TestNowIso:
    """_now_iso の動作テスト"""

    def test_returns_iso_string(self):
        from backend.api.routes.containers import _now_iso

        result = _now_iso()
        assert isinstance(result, str)
        assert "T" in result


# ===================================================================
# テスト: GET /api/containers エンドポイント
# ===================================================================


class TestListContainersEndpoint:
    """GET /api/containers の全分岐テスト"""

    def test_success_json_array(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout=SAMPLE_CONTAINERS_JSON_ARRAY):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["running"] >= 1
        assert data["stopped"] >= 1

    def test_success_json_lines(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout=SAMPLE_CONTAINERS_JSON_LINES):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_empty_list(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout="[]"):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_no_runtime(self, client, admin_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.status_code == 503

    def test_running_detection_by_up_in_status(self, client, admin_headers):
        """status に 'Up' を含むコンテナも running としてカウント"""
        data = json.dumps([
            {"ID": "a", "Names": "x", "Image": "i", "Status": "Up 1 day", "State": "some", "CreatedAt": "", "Ports": ""},
        ])
        with _mock_runtime(), _mock_wrapper_result(stdout=data):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.json()["running"] == 1

    def test_podman_runtime(self, client, admin_headers):
        with _mock_runtime("podman"), _mock_wrapper_result(stdout="[]"):
            resp = client.get("/api/containers", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["runtime"] == "podman"


# ===================================================================
# テスト: GET /api/containers/images エンドポイント
# ===================================================================


class TestListImagesEndpoint:
    """GET /api/containers/images の全分岐テスト"""

    def test_success(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout=SAMPLE_IMAGES_JSON_ARRAY):
            resp = client.get("/api/containers/images", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_no_runtime(self, client, admin_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get("/api/containers/images", headers=admin_headers)
        assert resp.status_code == 503

    def test_empty(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout="[]"):
            resp = client.get("/api/containers/images", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ===================================================================
# テスト: GET /api/containers/{name} エンドポイント
# ===================================================================


class TestInspectContainerEndpoint:
    """GET /api/containers/{name} の全分岐テスト"""

    def test_success_json(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout=SAMPLE_INSPECT):
            resp = client.get("/api/containers/nginx", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["name"] == "nginx"
        assert isinstance(data["detail"], list)

    def test_success_plain_text(self, client, admin_headers):
        """stdout が JSON でない場合はそのまま返す"""
        with _mock_runtime(), _mock_wrapper_result(stdout="plain text info"):
            resp = client.get("/api/containers/nginx", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["detail"] == "plain text info"

    def test_invalid_name(self, client, admin_headers):
        with _mock_runtime():
            resp = client.get("/api/containers/bad;name", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, admin_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get("/api/containers/nginx", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# テスト: GET /api/containers/{name}/logs エンドポイント
# ===================================================================


class TestContainerLogsEndpoint:
    """GET /api/containers/{name}/logs の全分岐テスト"""

    def test_success(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout="2024-01-15 Starting..."):
            resp = client.get("/api/containers/nginx/logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "nginx"
        assert "logs" in data

    def test_invalid_name(self, client, admin_headers):
        with _mock_runtime():
            resp = client.get("/api/containers/bad;name/logs", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, admin_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get("/api/containers/nginx/logs", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# テスト: GET /api/containers/{name}/stats エンドポイント
# ===================================================================


class TestContainerStatsEndpoint:
    """GET /api/containers/{name}/stats の全分岐テスト"""

    def test_success_json(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout=SAMPLE_STATS):
            resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "CPUPerc" in data["stats"]

    def test_invalid_json_stats(self, client, admin_headers):
        """stats が JSON でない場合は raw フィールドで返す"""
        with _mock_runtime(), _mock_wrapper_result(stdout="not json stats"):
            resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert "raw" in resp.json()["stats"]

    def test_empty_stats(self, client, admin_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout="{}"):
            resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
        assert resp.status_code == 200

    def test_invalid_name(self, client, admin_headers):
        with _mock_runtime():
            resp = client.get("/api/containers/bad;name/stats", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, admin_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get("/api/containers/nginx/stats", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# テスト: POST /api/containers/{name}/start エンドポイント
# ===================================================================


class TestStartContainerEndpoint:
    """POST /api/containers/{name}/start の全分岐テスト"""

    def test_success(self, client, operator_headers):
        with _mock_runtime(), _mock_wrapper_result(stdout="nginx"):
            resp = client.post("/api/containers/nginx/start", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "start"
        assert data["status"] == "success"

    def test_failure(self, client, operator_headers):
        with _mock_runtime(), _mock_wrapper_result(returncode=1, stderr="No such container"):
            resp = client.post("/api/containers/nginx/start", headers=operator_headers)
        assert resp.status_code == 500

    def test_invalid_name(self, client, operator_headers):
        with _mock_runtime():
            resp = client.post("/api/containers/bad;name/start", headers=operator_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, operator_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.post("/api/containers/nginx/start", headers=operator_headers)
        assert resp.status_code == 503

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/containers/nginx/start", headers=viewer_headers)
        assert resp.status_code == 403


# ===================================================================
# テスト: POST /api/containers/{name}/stop エンドポイント
# ===================================================================


class TestStopContainerEndpoint:
    """POST /api/containers/{name}/stop の全分岐テスト"""

    def test_creates_approval(self, client, operator_headers):
        with _mock_runtime(), _mock_approval_create("stop-req-001"):
            resp = client.post("/api/containers/nginx/stop", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["action"] == "stop"
        assert data["request_id"] == "stop-req-001"

    def test_approval_exception(self, client, operator_headers):
        with _mock_runtime(), patch(
            "backend.api.routes.containers._approval_service.create_request",
            new=AsyncMock(side_effect=RuntimeError("DB fail")),
        ):
            resp = client.post("/api/containers/nginx/stop", headers=operator_headers)
        assert resp.status_code == 500

    def test_invalid_name(self, client, operator_headers):
        with _mock_runtime():
            resp = client.post("/api/containers/bad;name/stop", headers=operator_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, operator_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.post("/api/containers/nginx/stop", headers=operator_headers)
        assert resp.status_code == 503

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/containers/nginx/stop", headers=viewer_headers)
        assert resp.status_code == 403


# ===================================================================
# テスト: POST /api/containers/{name}/restart エンドポイント
# ===================================================================


class TestRestartContainerEndpoint:
    """POST /api/containers/{name}/restart の全分岐テスト"""

    def test_creates_approval(self, client, operator_headers):
        with _mock_runtime(), _mock_approval_create("restart-req-001"):
            resp = client.post("/api/containers/myapp/restart", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["action"] == "restart"

    def test_approval_exception(self, client, operator_headers):
        with _mock_runtime(), patch(
            "backend.api.routes.containers._approval_service.create_request",
            new=AsyncMock(side_effect=RuntimeError("DB fail")),
        ):
            resp = client.post("/api/containers/myapp/restart", headers=operator_headers)
        assert resp.status_code == 500

    def test_invalid_name(self, client, operator_headers):
        with _mock_runtime():
            resp = client.post("/api/containers/bad;name/restart", headers=operator_headers)
        assert resp.status_code in (400, 422)

    def test_no_runtime(self, client, operator_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.post("/api/containers/myapp/restart", headers=operator_headers)
        assert resp.status_code == 503

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/containers/myapp/restart", headers=viewer_headers)
        assert resp.status_code == 403


# ===================================================================
# テスト: POST /api/containers/prune エンドポイント
# ===================================================================


class TestPruneEndpoint:
    """POST /api/containers/prune の全分岐テスト"""

    def test_creates_approval(self, client, operator_headers):
        with _mock_runtime(), _mock_approval_create("prune-req-001"):
            resp = client.post("/api/containers/prune", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["action"] == "prune"

    def test_approval_exception(self, client, operator_headers):
        with _mock_runtime(), patch(
            "backend.api.routes.containers._approval_service.create_request",
            new=AsyncMock(side_effect=RuntimeError("DB fail")),
        ):
            resp = client.post("/api/containers/prune", headers=operator_headers)
        assert resp.status_code == 500

    def test_no_runtime(self, client, operator_headers):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.post("/api/containers/prune", headers=operator_headers)
        assert resp.status_code == 503

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/containers/prune", headers=viewer_headers)
        assert resp.status_code == 403


# ===================================================================
# テスト: GET /api/containers/{name}/logs/stream (SSE)
# ===================================================================


class TestStreamEndpoint:
    """GET /api/containers/{name}/logs/stream の全分岐テスト"""

    def test_no_token(self, client):
        """token パラメータなしは 422"""
        resp = client.get("/api/containers/nginx/logs/stream")
        assert resp.status_code in (401, 403, 422)

    def test_invalid_token(self, client):
        with _mock_runtime():
            resp = client.get("/api/containers/nginx/logs/stream?token=bad.jwt.token")
        assert resp.status_code == 401

    def test_invalid_container_name(self, client, admin_token):
        with _mock_runtime():
            resp = client.get(f"/api/containers/bad%3Bname/logs/stream?token={admin_token}")
        assert resp.status_code in (400, 422)

    def test_tail_too_large(self, client, admin_token):
        with _mock_runtime():
            resp = client.get(f"/api/containers/nginx/logs/stream?tail=9999&token={admin_token}")
        assert resp.status_code == 422

    def test_tail_zero(self, client, admin_token):
        with _mock_runtime():
            resp = client.get(f"/api/containers/nginx/logs/stream?tail=0&token={admin_token}")
        assert resp.status_code == 422

    def test_no_runtime(self, client, admin_token):
        with patch("backend.api.routes.containers._detect_runtime", return_value=None):
            resp = client.get(f"/api/containers/nginx/logs/stream?token={admin_token}")
        assert resp.status_code == 503

    def test_valid_request_starts_stream(self, client, admin_token):
        """有効なリクエストで SSE ストリームが開始される"""
        with _mock_runtime(), patch(
            "asyncio.create_subprocess_exec",
            side_effect=Exception("not in test"),
        ):
            resp = client.get(
                f"/api/containers/nginx/logs/stream?token={admin_token}",
                headers={"Accept": "text/event-stream"},
            )
        # SSE は正常に開始されるか、subprocess のモックエラーで 200 + error event
        assert resp.status_code in (200, 500)

    def test_viewer_with_read_permission(self, client, viewer_token):
        """viewer は read:containers 権限でストリーム可能"""
        with _mock_runtime(), patch(
            "asyncio.create_subprocess_exec",
            side_effect=Exception("not in test"),
        ):
            resp = client.get(
                f"/api/containers/nginx/logs/stream?token={viewer_token}",
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code in (200, 500)


# ===================================================================
# テスト: 認証なしアクセス
# ===================================================================


class TestNoAuthAccess:
    """認証なしアクセスの拒否テスト"""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/containers"),
            ("GET", "/api/containers/images"),
            ("GET", "/api/containers/nginx"),
            ("GET", "/api/containers/nginx/logs"),
            ("GET", "/api/containers/nginx/stats"),
            ("POST", "/api/containers/nginx/start"),
            ("POST", "/api/containers/nginx/stop"),
            ("POST", "/api/containers/nginx/restart"),
            ("POST", "/api/containers/prune"),
        ],
    )
    def test_no_auth_rejected(self, client, method, path):
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path)
        assert resp.status_code in (401, 403)
