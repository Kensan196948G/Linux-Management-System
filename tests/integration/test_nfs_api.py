"""
NFS マウント管理モジュール - 統合テスト

APIエンドポイントの統合テスト（subprocess / approval_service をモック）

テストケース数: 20件以上
- 認証テスト（未認証 403）
- 権限テスト（Viewer=読み取り専用、Operatorのみ書き込み）
- マウント一覧取得
- fstab エントリ取得
- NFS ステータス取得
- 不正なマウントポイント（allowlist外）の拒否
- 特殊文字を含む入力の拒否（セキュリティテスト）
- 承認フロー経由のマウント/アンマウント
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ==============================================================================
# サンプルデータ
# ==============================================================================

SAMPLE_MOUNT_OUTPUT = """\
192.168.1.10:/export/data on /mnt/data type nfs4 (ro,noexec,nosuid,relatime)
192.168.1.20:/backup on /mnt/backup type nfs (ro,noexec,nosuid)
"""

SAMPLE_FSTAB_OUTPUT = """\
192.168.1.10:/export/data /mnt/data nfs4 ro,noexec,nosuid 0 0
192.168.1.20:/backup /mnt/backup nfs ro,noexec 0 0
"""

SAMPLE_CHECK_OUTPUT = """\
192.168.1.10:/export/data /mnt/data nfs4 ro,relatime 0 0
"""

SAMPLE_APPROVAL_RESULT = {"request_id": "nfs-req-001", "status": "pending"}


def _mock_subprocess_run(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """subprocess.run をモックするコンテキストマネージャを返す。"""
    mock_result = MagicMock()
    mock_result.stdout = stdout
    mock_result.returncode = returncode
    mock_result.stderr = stderr
    return patch("backend.api.routes.nfs._run_nfs_wrapper", return_value=mock_result)


def _mock_approval_create(request_id: str = "nfs-req-001"):
    """_approval_service.create_request を非同期モックする。"""
    return patch(
        "backend.api.routes.nfs._approval_service.create_request",
        new_callable=AsyncMock,
        return_value={"request_id": request_id, "status": "pending"},
    )


# ==============================================================================
# フィクスチャ
# ==============================================================================


@pytest.fixture(scope="module")
def test_client():
    """FastAPI テストクライアント（モジュールスコープ）"""
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    os.environ["ENV"] = "dev"

    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_headers(test_client):
    """Admin ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    """Operator ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    """Viewer ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def approver_headers(test_client):
    """Approver ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# TC001-TC004: 認証なしアクセス（403）
# ==============================================================================


class TestNfsUnauthorized:
    """認証なしアクセスは 403 を返すこと"""

    def test_mounts_no_auth(self, test_client):
        """TC001: GET /api/nfs/mounts — 認証なしは 403"""
        resp = test_client.get("/api/nfs/mounts")
        assert resp.status_code == 403

    def test_fstab_no_auth(self, test_client):
        """TC002: GET /api/nfs/fstab — 認証なしは 403"""
        resp = test_client.get("/api/nfs/fstab")
        assert resp.status_code == 403

    def test_mount_no_auth(self, test_client):
        """TC003: POST /api/nfs/mount — 認証なしは 403"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data"},
        )
        assert resp.status_code == 403

    def test_status_no_auth(self, test_client):
        """TC004: GET /api/nfs/status — 認証なしは 403"""
        resp = test_client.get("/api/nfs/status")
        assert resp.status_code == 403


# ==============================================================================
# TC005-TC009: マウント一覧取得 (GET /api/nfs/mounts)
# ==============================================================================


class TestNfsMountsList:
    """NFSマウント一覧取得のテスト"""

    def test_admin_can_list_mounts(self, test_client, admin_headers):
        """TC005: Admin は NFS マウント一覧を取得できること"""
        with _mock_subprocess_run(stdout=SAMPLE_MOUNT_OUTPUT):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total"] == 2
        assert len(data["mounts"]) == 2

    def test_viewer_can_list_mounts(self, test_client, viewer_headers):
        """TC006: Viewer は NFS マウント一覧を取得できること (read:nfs)"""
        with _mock_subprocess_run(stdout=SAMPLE_MOUNT_OUTPUT):
            resp = test_client.get("/api/nfs/mounts", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_mounts_empty_response(self, test_client, admin_headers):
        """TC007: マウントがない場合は空リストを返すこと"""
        with _mock_subprocess_run(stdout=""):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["mounts"] == []

    def test_mounts_contains_device_and_mountpoint(self, test_client, admin_headers):
        """TC008: マウント情報に device と mount_point が含まれること"""
        with _mock_subprocess_run(stdout=SAMPLE_MOUNT_OUTPUT):
            resp = test_client.get("/api/nfs/mounts", headers=admin_headers)
        assert resp.status_code == 200
        mounts = resp.json()["mounts"]
        assert mounts[0]["device"] == "192.168.1.10:/export/data"
        assert mounts[0]["mount_point"] == "/mnt/data"
        assert mounts[0]["fstype"] == "nfs4"


# ==============================================================================
# TC009-TC012: fstab エントリ取得 (GET /api/nfs/fstab)
# ==============================================================================


class TestNfsFstab:
    """fstab エントリ取得のテスト"""

    def test_admin_can_get_fstab(self, test_client, admin_headers):
        """TC009: Admin は fstab エントリを取得できること"""
        with _mock_subprocess_run(stdout=SAMPLE_FSTAB_OUTPUT):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total"] == 2

    def test_viewer_can_get_fstab(self, test_client, viewer_headers):
        """TC010: Viewer は fstab エントリを取得できること"""
        with _mock_subprocess_run(stdout=SAMPLE_FSTAB_OUTPUT):
            resp = test_client.get("/api/nfs/fstab", headers=viewer_headers)
        assert resp.status_code == 200

    def test_fstab_empty(self, test_client, admin_headers):
        """TC011: fstab に NFS エントリがない場合は空リストを返すこと"""
        with _mock_subprocess_run(stdout=""):
            resp = test_client.get("/api/nfs/fstab", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ==============================================================================
# TC012-TC013: NFS ステータス (GET /api/nfs/status)
# ==============================================================================


class TestNfsStatus:
    """NFS ステータス取得のテスト"""

    def test_admin_can_get_status(self, test_client, admin_headers):
        """TC012: Admin は NFS ステータスを取得できること"""
        mock_which = MagicMock(returncode=0, stdout="/bin/mount", stderr="")
        with patch("subprocess.run", return_value=mock_which), _mock_subprocess_run(stdout=SAMPLE_CHECK_OUTPUT):
            resp = test_client.get("/api/nfs/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "nfs_available" in data
        assert "active_mounts" in data

    def test_viewer_can_get_status(self, test_client, viewer_headers):
        """TC013: Viewer は NFS ステータスを取得できること"""
        mock_which = MagicMock(returncode=0, stdout="/bin/mount", stderr="")
        with patch("subprocess.run", return_value=mock_which), _mock_subprocess_run(stdout=""):
            resp = test_client.get("/api/nfs/status", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# TC014-TC016: 権限テスト（Viewer は write:nfs 不可）
# ==============================================================================


class TestNfsPermissions:
    """権限テスト"""

    def test_viewer_cannot_mount(self, test_client, viewer_headers):
        """TC014: Viewer は NFS マウント要求を送信できないこと (403)"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_viewer_cannot_umount(self, test_client, viewer_headers):
        """TC015: Viewer は NFS アンマウント要求を送信できないこと (403)"""
        resp = test_client.post(
            "/api/nfs/umount",
            json={"mount_point": "/mnt/data"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_operator_can_mount(self, test_client, operator_headers):
        """TC016: Operator は NFS マウント要求を送信できること"""
        with _mock_approval_create():
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "request_id" in data


# ==============================================================================
# TC017-TC021: セキュリティテスト（不正入力の拒否）
# ==============================================================================


class TestNfsSecurity:
    """セキュリティテスト - 不正入力・allowlist外の拒否"""

    def test_reject_mount_point_outside_allowlist(self, test_client, operator_headers):
        """TC017: allowlist 外のマウントポイントを拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/tmp/evil"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_umount_point_outside_allowlist(self, test_client, operator_headers):
        """TC018: allowlist 外のアンマウントポイントを拒否すること"""
        resp = test_client.post(
            "/api/nfs/umount",
            json={"mount_point": "/etc/passwd"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_shell_injection_in_server(self, test_client, operator_headers):
        """TC019: NFSサーバー名にセミコロン等の特殊文字を含む入力を拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10;rm -rf /", "export_path": "/data", "mount_point": "/mnt/data"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_pipe_in_export_path(self, test_client, operator_headers):
        """TC020: エクスポートパスにパイプ文字を含む入力を拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export|ls", "mount_point": "/mnt/data"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_special_chars_in_mount_point(self, test_client, operator_headers):
        """TC021: マウントポイントに特殊文字を含む入力を拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data;ls"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_backtick_in_server(self, test_client, operator_headers):
        """TC022: NFSサーバー名にバックティックを含む入力を拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "`id`", "export_path": "/export/data", "mount_point": "/mnt/data"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_reject_dollar_in_export_path(self, test_client, operator_headers):
        """TC023: エクスポートパスにドル記号を含む入力を拒否すること"""
        resp = test_client.post(
            "/api/nfs/mount",
            json={"nfs_server": "192.168.1.10", "export_path": "/export/$HOME", "mount_point": "/mnt/data"},
            headers=operator_headers,
        )
        assert resp.status_code == 422

    def test_valid_allowed_prefixes(self, test_client, operator_headers):
        """TC024: 許可されたマウントポイントプレフィックスは受け入れること"""
        for prefix in ["/mnt/nfs1", "/media/nfs", "/srv/nfs/data", "/data/nfs/backup"]:
            with _mock_approval_create():
                resp = test_client.post(
                    "/api/nfs/mount",
                    json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": prefix},
                    headers=operator_headers,
                )
            assert resp.status_code == 200, f"Should allow mount_point={prefix}"


# ==============================================================================
# TC025-TC027: 承認フロー経由のマウント/アンマウント
# ==============================================================================


class TestNfsApprovalFlow:
    """承認フロー経由のマウント/アンマウントテスト"""

    def test_mount_creates_approval_request(self, test_client, operator_headers):
        """TC025: マウント要求が承認リクエストを生成すること"""
        with _mock_approval_create("nfs-test-req-001"):
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["request_id"] == "nfs-test-req-001"
        assert data["action"] == "mount"
        assert data["target"] == "/mnt/data"

    def test_umount_creates_approval_request(self, test_client, operator_headers):
        """TC026: アンマウント要求が承認リクエストを生成すること"""
        with _mock_approval_create("nfs-umount-req-001"):
            resp = test_client.post(
                "/api/nfs/umount",
                json={"mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["request_id"] == "nfs-umount-req-001"
        assert data["action"] == "umount"
        assert data["target"] == "/mnt/data"

    def test_admin_can_submit_mount_approval(self, test_client, admin_headers):
        """TC027: Admin も承認フロー経由でマウント要求を送信できること"""
        with _mock_approval_create("nfs-admin-req-001"):
            resp = test_client.post(
                "/api/nfs/mount",
                json={
                    "nfs_server": "192.168.1.20",
                    "export_path": "/backup",
                    "mount_point": "/mnt/backup",
                    "options": "ro,noexec",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"

    def test_approver_can_submit_mount_approval(self, test_client, approver_headers):
        """TC028: Approver も承認フロー経由でマウント要求を送信できること"""
        with _mock_approval_create("nfs-approver-req-001"):
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "10.0.0.5", "export_path": "/share", "mount_point": "/mnt/share"},
                headers=approver_headers,
            )
        assert resp.status_code == 200

    def test_approval_response_has_request_id(self, test_client, operator_headers):
        """TC029: 承認レスポンスに request_id が含まれること"""
        with _mock_approval_create("unique-req-12345"):
            resp = test_client.post(
                "/api/nfs/mount",
                json={"nfs_server": "192.168.1.10", "export_path": "/export/data", "mount_point": "/mnt/data"},
                headers=operator_headers,
            )
        data = resp.json()
        assert "request_id" in data
        assert data["request_id"] == "unique-req-12345"
