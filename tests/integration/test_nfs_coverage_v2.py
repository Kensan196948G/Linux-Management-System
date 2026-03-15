"""
nfs.py カバレッジ改善テスト v2

対象: backend/api/routes/nfs.py (46% -> 85%+)
未カバー箇所を重点的にテスト:
  - _validate_mount_point: 正規表現チェック・allowlist プレフィックスチェック
  - _run_nfs_wrapper: subprocess呼び出し
  - _parse_mount_line: 各形式のパース・不正入力
  - _parse_fstab_line: 各形式のパース・コメント行・不正入力
  - MountRequest: 全 field_validator（nfs_server, export_path, mount_point, options）
  - UmountRequest: field_validator
  - get_nfs_mounts: タイムアウト・一般例外
  - get_fstab_entries: タイムアウト・一般例外
  - request_mount: 承認フロー成功・失敗
  - request_umount: 承認フロー成功・失敗
  - get_nfs_status: mount コマンド不存在・タイムアウト・一般例外
"""

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

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
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _mock_nfs_wrapper(stdout="", returncode=0, stderr=""):
    mock_result = MagicMock()
    mock_result.stdout = stdout
    mock_result.returncode = returncode
    mock_result.stderr = stderr
    return patch("backend.api.routes.nfs._run_nfs_wrapper", return_value=mock_result)


def _mock_approval_create(request_id="nfs-req-001"):
    return patch(
        "backend.api.routes.nfs._approval_service.create_request",
        new_callable=AsyncMock,
        return_value={"request_id": request_id, "status": "pending"},
    )


# ===================================================================
# _validate_mount_point ヘルパーテスト
# ===================================================================


class TestValidateMountPoint:
    """_validate_mount_point の全分岐テスト"""

    def test_valid_mnt(self):
        from backend.api.routes.nfs import _validate_mount_point
        # 例外が出なければOK
        _validate_mount_point("/mnt/data")

    def test_valid_media(self):
        from backend.api.routes.nfs import _validate_mount_point
        _validate_mount_point("/media/usb")

    def test_valid_srv_nfs(self):
        from backend.api.routes.nfs import _validate_mount_point
        _validate_mount_point("/srv/nfs/share")

    def test_valid_data_nfs(self):
        from backend.api.routes.nfs import _validate_mount_point
        _validate_mount_point("/data/nfs/backup")

    def test_reject_invalid_format(self):
        from backend.api.routes.nfs import _validate_mount_point
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_mount_point("not-absolute-path")
        assert exc_info.value.status_code == 400

    def test_reject_special_chars(self):
        from backend.api.routes.nfs import _validate_mount_point
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_mount_point("/mnt/data;evil")
        assert exc_info.value.status_code == 400

    def test_reject_outside_allowlist(self):
        from backend.api.routes.nfs import _validate_mount_point
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_mount_point("/tmp/data")
        assert exc_info.value.status_code == 400

    def test_reject_root(self):
        from backend.api.routes.nfs import _validate_mount_point
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_mount_point("/")
        assert exc_info.value.status_code == 400

    def test_reject_etc(self):
        from backend.api.routes.nfs import _validate_mount_point
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_mount_point("/etc/passwd")
        assert exc_info.value.status_code == 400

    def test_exact_prefix_match(self):
        """プレフィックスそのもの（例: /mnt）は許可される"""
        from backend.api.routes.nfs import _validate_mount_point
        _validate_mount_point("/mnt")


# ===================================================================
# _parse_mount_line ヘルパーテスト
# ===================================================================


class TestParseMountLine:
    """_parse_mount_line の全分岐テスト"""

    def test_valid_nfs4_line(self):
        from backend.api.routes.nfs import _parse_mount_line
        result = _parse_mount_line("192.168.1.10:/export on /mnt/data type nfs4 (ro,noexec)")
        assert result is not None
        assert result["device"] == "192.168.1.10:/export"
        assert result["mount_point"] == "/mnt/data"
        assert result["fstype"] == "nfs4"
        assert result["options"] == "ro,noexec"

    def test_valid_nfs_line(self):
        from backend.api.routes.nfs import _parse_mount_line
        result = _parse_mount_line("server:/share on /mnt/share type nfs (rw,relatime)")
        assert result is not None
        assert result["fstype"] == "nfs"

    def test_invalid_line_returns_none(self):
        from backend.api.routes.nfs import _parse_mount_line
        assert _parse_mount_line("this is not a mount line") is None

    def test_empty_line_returns_none(self):
        from backend.api.routes.nfs import _parse_mount_line
        assert _parse_mount_line("") is None

    def test_whitespace_line_returns_none(self):
        from backend.api.routes.nfs import _parse_mount_line
        assert _parse_mount_line("   ") is None

    def test_partial_line_returns_none(self):
        from backend.api.routes.nfs import _parse_mount_line
        assert _parse_mount_line("device on mount_point") is None


# ===================================================================
# _parse_fstab_line ヘルパーテスト
# ===================================================================


class TestParseFstabLine:
    """_parse_fstab_line の全分岐テスト"""

    def test_valid_full_line(self):
        from backend.api.routes.nfs import _parse_fstab_line
        result = _parse_fstab_line("192.168.1.10:/data /mnt/data nfs4 ro,noexec 0 0")
        assert result is not None
        assert result["device"] == "192.168.1.10:/data"
        assert result["mount_point"] == "/mnt/data"
        assert result["fstype"] == "nfs4"
        assert result["options"] == "ro,noexec"
        assert result["dump"] == "0"
        assert result["pass"] == "0"

    def test_line_with_4_fields(self):
        from backend.api.routes.nfs import _parse_fstab_line
        result = _parse_fstab_line("server:/share /mnt/share nfs rw")
        assert result is not None
        assert result["dump"] == "0"
        assert result["pass"] == "0"

    def test_line_with_5_fields(self):
        from backend.api.routes.nfs import _parse_fstab_line
        result = _parse_fstab_line("server:/share /mnt/share nfs rw 1")
        assert result is not None
        assert result["dump"] == "1"
        assert result["pass"] == "0"

    def test_comment_line_returns_none(self):
        from backend.api.routes.nfs import _parse_fstab_line
        assert _parse_fstab_line("# This is a comment") is None

    def test_empty_line_returns_none(self):
        from backend.api.routes.nfs import _parse_fstab_line
        assert _parse_fstab_line("") is None

    def test_whitespace_line_returns_none(self):
        from backend.api.routes.nfs import _parse_fstab_line
        assert _parse_fstab_line("   ") is None

    def test_too_few_fields_returns_none(self):
        from backend.api.routes.nfs import _parse_fstab_line
        assert _parse_fstab_line("device mountpoint fstype") is None

    def test_two_fields_returns_none(self):
        from backend.api.routes.nfs import _parse_fstab_line
        assert _parse_fstab_line("device mountpoint") is None


# ===================================================================
# MountRequest バリデーションテスト
# ===================================================================


class TestMountRequestValidation:
    """MountRequest の全 field_validator テスト"""

    def test_valid_request(self):
        from backend.api.routes.nfs import MountRequest
        req = MountRequest(
            nfs_server="192.168.1.10",
            export_path="/export/data",
            mount_point="/mnt/data",
            options="ro,noexec,nosuid",
        )
        assert req.nfs_server == "192.168.1.10"

    def test_default_options(self):
        from backend.api.routes.nfs import MountRequest
        req = MountRequest(
            nfs_server="server.local",
            export_path="/share",
            mount_point="/mnt/share",
        )
        assert req.options == "ro,noexec,nosuid"

    @pytest.mark.parametrize("server", [
        "server;evil",
        "server|pipe",
        "server$var",
        "server`cmd`",
    ])
    def test_invalid_server_forbidden_chars(self, server):
        from backend.api.routes.nfs import MountRequest
        with pytest.raises(Exception):
            MountRequest(nfs_server=server, export_path="/data", mount_point="/mnt/data")

    def test_invalid_server_format(self):
        from backend.api.routes.nfs import MountRequest
        with pytest.raises(Exception):
            MountRequest(nfs_server="server with spaces", export_path="/data", mount_point="/mnt/data")

    @pytest.mark.parametrize("export_path", [
        "/export;evil",
        "/export|pipe",
        "not-absolute",
    ])
    def test_invalid_export_path(self, export_path):
        from backend.api.routes.nfs import MountRequest
        with pytest.raises(Exception):
            MountRequest(nfs_server="server", export_path=export_path, mount_point="/mnt/data")

    @pytest.mark.parametrize("mount_point", [
        "/tmp/evil",
        "/etc/data",
        "/home/user",
        "relative/path",
    ])
    def test_invalid_mount_point(self, mount_point):
        from backend.api.routes.nfs import MountRequest
        with pytest.raises(Exception):
            MountRequest(nfs_server="server", export_path="/data", mount_point=mount_point)

    @pytest.mark.parametrize("options", [
        "ro;evil",
        "rw|pipe",
        "rw nosuid",  # space
    ])
    def test_invalid_options(self, options):
        from backend.api.routes.nfs import MountRequest
        with pytest.raises(Exception):
            MountRequest(nfs_server="server", export_path="/data", mount_point="/mnt/data", options=options)

    @pytest.mark.parametrize("options", [
        "ro",
        "rw,noexec",
        "ro,noexec,nosuid",
        "rw,hard,intr,timeo=14",
    ])
    def test_valid_options(self, options):
        from backend.api.routes.nfs import MountRequest
        req = MountRequest(nfs_server="server", export_path="/data", mount_point="/mnt/data", options=options)
        assert req.options == options


# ===================================================================
# UmountRequest バリデーションテスト
# ===================================================================


class TestUmountRequestValidation:
    """UmountRequest の field_validator テスト"""

    def test_valid_umount(self):
        from backend.api.routes.nfs import UmountRequest
        req = UmountRequest(mount_point="/mnt/data")
        assert req.mount_point == "/mnt/data"

    @pytest.mark.parametrize("mp", ["/tmp/evil", "/etc/data", "relative"])
    def test_invalid_umount(self, mp):
        from backend.api.routes.nfs import UmountRequest
        with pytest.raises(Exception):
            UmountRequest(mount_point=mp)


# ===================================================================
# get_nfs_mounts: タイムアウト・例外テスト
# ===================================================================


class TestNfsMountsV2:
    """GET /api/nfs/mounts の追加カバレッジ"""

    def test_mounts_timeout(self, test_client, admin_headers):
        """タイムアウトで 504 を返す"""
        with patch("backend.api.routes.nfs._run_nfs_wrapper", side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=30)):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 504

    def test_mounts_generic_exception(self, test_client, admin_headers):
        """一般例外で 500 を返す"""
        with patch("backend.api.routes.nfs._run_nfs_wrapper", side_effect=RuntimeError("unexpected")):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 500

    def test_mounts_with_parse_failures(self, test_client, admin_headers):
        """パース失敗行があっても正常に処理される"""
        mixed_output = "192.168.1.10:/data on /mnt/data type nfs4 (ro)\ninvalid line\n"
        with _mock_nfs_wrapper(stdout=mixed_output):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ===================================================================
# get_fstab_entries: タイムアウト・例外テスト
# ===================================================================


class TestNfsFstabV2:
    """GET /api/nfs/fstab の追加カバレッジ"""

    def test_fstab_timeout(self, test_client, admin_headers):
        """タイムアウトで 504 を返す"""
        with patch("backend.api.routes.nfs._run_nfs_wrapper", side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=30)):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 504

    def test_fstab_generic_exception(self, test_client, admin_headers):
        """一般例外で 500 を返す"""
        with patch("backend.api.routes.nfs._run_nfs_wrapper", side_effect=RuntimeError("unexpected")):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 500

    def test_fstab_with_comments_and_empty_lines(self, test_client, admin_headers):
        """コメント行・空行がスキップされる"""
        fstab_output = "# comment\n\n192.168.1.10:/data /mnt/data nfs4 ro 0 0\n   \n"
        with _mock_nfs_wrapper(stdout=fstab_output):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_fstab_response_structure(self, test_client, admin_headers):
        """レスポンス構造の確認"""
        fstab_output = "server:/share /mnt/share nfs rw,hard 1 2\n"
        with _mock_nfs_wrapper(stdout=fstab_output):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "entries" in data
        assert "total" in data
        assert "timestamp" in data
        entry = data["entries"][0]
        assert entry["device"] == "server:/share"
        assert entry["fstype"] == "nfs"


# ===================================================================
# request_mount: 承認フロー 失敗テスト
# ===================================================================


class TestNfsMountApprovalV2:
    """POST /api/nfs/mount の追加カバレッジ"""

    def test_mount_approval_service_failure(self, test_client, operator_headers):
        """承認サービスが失敗した場合 500 を返す"""
        with patch(
            "backend.api.routes.nfs._approval_service.create_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection failed"),
        ):
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "192.168.1.10", "export_path": "/data", "mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 500

    def test_mount_response_structure(self, test_client, operator_headers):
        """マウント応答の構造確認"""
        with _mock_approval_create("test-req-001"):
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "10.0.0.1", "export_path": "/share", "mount_point": "/mnt/share"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "message" in data
        assert "request_id" in data
        assert data["action"] == "mount"
        assert "timestamp" in data

    def test_mount_with_custom_options(self, test_client, operator_headers):
        """カスタムオプション付きマウント"""
        with _mock_approval_create():
            resp = test_client.post(
                "/api/nfs/mount",
                json={
                    "nfs_server": "server",
                    "export_path": "/data",
                    "mount_point": "/mnt/data",
                    "options": "rw,hard,intr",
                },
                headers=operator_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# request_umount: 承認フロー 失敗テスト
# ===================================================================


class TestNfsUmountApprovalV2:
    """POST /api/nfs/umount の追加カバレッジ"""

    def test_umount_approval_service_failure(self, test_client, operator_headers):
        """承認サービスが失敗した場合 500 を返す"""
        with patch(
            "backend.api.routes.nfs._approval_service.create_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection failed"),
        ):
            resp = test_client.post(
                "/api/nfs/umount",
                json={"mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 500

    def test_umount_response_structure(self, test_client, operator_headers):
        """アンマウント応答の構造確認"""
        with _mock_approval_create("umount-req-001"):
            resp = test_client.post(
                "/api/nfs/umount",
                json={"mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["action"] == "umount"
        assert data["target"] == "/mnt/data"


# ===================================================================
# get_nfs_status: 追加テスト
# ===================================================================


class TestNfsStatusV2:
    """GET /api/nfs/status の追加カバレッジ"""

    def test_status_mount_not_found(self, test_client, admin_headers):
        """mount コマンドが存在しない場合"""
        mock_which = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_which):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["nfs_available"] is False
        assert data["active_mounts"] == 0
        assert "mount command not found" in data["message"]

    def test_status_timeout(self, test_client, admin_headers):
        """タイムアウトで 504 を返す"""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="which", timeout=5)):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 504

    def test_status_generic_exception(self, test_client, admin_headers):
        """一般例外で 500 を返す"""
        with patch("subprocess.run", side_effect=RuntimeError("unexpected error")):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 500

    def test_status_with_active_mounts(self, test_client, admin_headers):
        """アクティブマウントがある場合"""
        mock_which = MagicMock(returncode=0, stdout="/bin/mount", stderr="")
        mock_check = MagicMock()
        mock_check.stdout = "nfs mount 1\nnfs mount 2\n"

        with patch("subprocess.run", return_value=mock_which), \
             patch("backend.api.routes.nfs._run_nfs_wrapper", return_value=mock_check):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["nfs_available"] is True
        assert data["active_mounts"] == 2

    def test_status_no_active_mounts(self, test_client, admin_headers):
        """アクティブマウントがない場合"""
        mock_which = MagicMock(returncode=0, stdout="/bin/mount", stderr="")
        mock_check = MagicMock()
        mock_check.stdout = ""

        with patch("subprocess.run", return_value=mock_which), \
             patch("backend.api.routes.nfs._run_nfs_wrapper", return_value=mock_check):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["nfs_available"] is True
        assert data["active_mounts"] == 0


# ===================================================================
# Pydantic モデルテスト
# ===================================================================


class TestNfsResponseModels:
    """レスポンスモデルのテスト"""

    def test_mounts_response_defaults(self):
        from backend.api.routes.nfs import MountsResponse
        resp = MountsResponse(status="success")
        assert resp.mounts == []
        assert resp.total == 0
        assert resp.timestamp is not None

    def test_fstab_response_defaults(self):
        from backend.api.routes.nfs import FstabResponse
        resp = FstabResponse(status="success")
        assert resp.entries == []
        assert resp.total == 0

    def test_nfs_status_response_defaults(self):
        from backend.api.routes.nfs import NfsStatusResponse
        resp = NfsStatusResponse(status="success")
        assert resp.nfs_available is False
        assert resp.active_mounts == 0
        assert resp.message is None

    def test_approval_request_response(self):
        from backend.api.routes.nfs import ApprovalRequestResponse
        resp = ApprovalRequestResponse(
            status="pending",
            message="test",
            request_id="req-001",
            action="mount",
            target="/mnt/data",
        )
        assert resp.status == "pending"
        assert resp.timestamp is not None
