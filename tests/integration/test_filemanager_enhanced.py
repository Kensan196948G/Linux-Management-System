"""
ファイルマネージャー拡張テスト (upload/chmod)

テスト対象: backend/api/routes/filemanager.py
- POST /api/files/upload
- POST /api/files/chmod
"""

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── chmod テスト ────────────────────────────────────────────

class TestChmodEndpoint:
    def test_chmod_success(self, test_client, admin_headers):
        """TC001: 正常なchmod (644)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["mode"] == "644"

    def test_chmod_755(self, test_client, admin_headers):
        """TC002: chmod 755"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/home/testuser/script.sh", "mode": "755"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["mode"] == "755"

    def test_chmod_4digit_mode(self, test_client, admin_headers):
        """TC003: 4桁octal (setuid等)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/test", "mode": "0755"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_chmod_invalid_mode_letters(self, test_client, admin_headers):
        """TC004: 不正なmode (英字含む) → 422"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/var/www/test.txt", "mode": "abc"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_chmod_invalid_mode_9(self, test_client, admin_headers):
        """TC005: 不正なmode (9含む) → 422"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/var/www/test.txt", "mode": "999"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_chmod_path_traversal(self, test_client, admin_headers):
        """TC006: パストラバーサル → 400"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/var/www/../etc/passwd", "mode": "644"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_chmod_not_allowed_dir(self, test_client, admin_headers):
        """TC007: 許可外ディレクトリ → 400"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/root/secret.txt", "mode": "644"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_chmod_no_auth(self, test_client):
        """TC008: 認証なし → 401/403"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/var/www/test.txt", "mode": "644"},
        )
        assert resp.status_code in (401, 403)

    def test_chmod_sudo_error(self, test_client, admin_headers):
        """TC009: SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_chmod_wrapper_returns_error(self, test_client, admin_headers):
        """TC010: wrapperがerrorステータス → 400"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "error", "stdout": "", "stderr": "permission denied"}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_chmod_returns_path(self, test_client, admin_headers):
        """TC011: レスポンスにpathが含まれること"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/index.html", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert "path" in resp.json()
        assert "mode" in resp.json()


# ── upload テスト ───────────────────────────────────────────

class TestUploadEndpoint:
    def test_upload_success(self, test_client, admin_headers):
        """TC012: 正常なアップロード"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_upload_returns_path_and_size(self, test_client, admin_headers):
        """TC013: レスポンスにpath/sizeが含まれること"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("readme.md", io.BytesIO(b"# readme"), "text/markdown")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        data = resp.json()
        assert "path" in data
        assert "size" in data
        assert data["size"] == len(b"# readme")

    def test_upload_invalid_filename_special_chars(self, test_client, admin_headers):
        """TC014: 特殊文字含むファイル名 → 422"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test;cmd.txt", io.BytesIO(b"bad"), "text/plain")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upload_not_allowed_dest(self, test_client, admin_headers):
        """TC015: 許可外ディレクトリ (/etc) → 400/403"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"dest_path": "/etc"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 403)

    def test_upload_path_traversal(self, test_client, admin_headers):
        """TC016: パストラバーサル → 400"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"dest_path": "/var/www/../etc"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_upload_no_auth(self, test_client):
        """TC017: 認証なし → 401/403"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"dest_path": "/var/www/html"},
        )
        assert resp.status_code in (401, 403)

    def test_upload_sudo_error(self, test_client, admin_headers):
        """TC018: SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("ok.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_upload_file_too_large(self, test_client, admin_headers):
        """TC019: 10MB超ファイル → 413"""
        big = b"x" * (10 * 1024 * 1024 + 1)
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("big.bin", io.BytesIO(big), "application/octet-stream")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 413

    def test_upload_home_dir_allowed(self, test_client, admin_headers):
        """TC020: /home は許可ディレクトリ"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("data.csv", io.BytesIO(b"a,b,c"), "text/csv")},
                data={"dest_path": "/home/testuser"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_upload_wrapper_returns_error(self, test_client, admin_headers):
        """TC021: wrapperがerrorステータス → 400"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "error", "stdout": "", "stderr": "disk full"}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"hi"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_upload_tmp_dir_allowed(self, test_client, admin_headers):
        """TC022: /tmp は許可ディレクトリ"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("temp.txt", io.BytesIO(b"tmp data"), "text/plain")},
                data={"dest_path": "/tmp"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
