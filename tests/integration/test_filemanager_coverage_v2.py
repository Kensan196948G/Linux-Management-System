"""
filemanager.py カバレッジ改善テスト v2

対象: backend/api/routes/filemanager.py
目標: 90%以上カバレッジ
既存テスト(test_filemanager_api/coverage/enhanced)で未カバーの分岐を網羅

カバー対象:
  - validate_path: realpath 後の再検証失敗パス (lines 90-98)
  - upload: ファイルサイズ超過 413 (line 238)
  - upload: sudo_wrapper 返却 status=error → 400 (lines 242-243)
  - upload: SudoWrapperError → 500 (lines 252-254)
  - upload: /tmp, /home アップロード先
  - upload: ファイル名なし (filename=None)
  - chmod: sudo_wrapper 返却 status=error → 400 (lines 269-270)
  - chmod: SudoWrapperError → 500 (lines 279-281)
  - list/stat/read/search: audit_log.record 呼び出し確認
  - search: 複数結果パース
"""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.core.sudo_wrapper import SudoWrapperError


# =====================================================================
# validate_path: realpath 再検証パス
# =====================================================================


class TestValidatePathRealpathRejection:
    """validate_path の realpath 後再検証 (lines 88-98)"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.filemanager import validate_path
        self.fn = validate_path

    def test_realpath_resolves_outside_allowed_dir(self):
        """realpath が許可外ディレクトリに解決される場合は 400"""
        # os.path.realpath は validate_path 内で2回呼ばれる: パス自体 + base_dir
        # パスが /usr/bin/evil に解決されるが base_dir は正常なケース
        original_realpath = os.path.realpath

        def mock_realpath(p):
            if p == "/var/log/somefile":
                return "/usr/bin/evil"
            return original_realpath(p)

        with patch("backend.api.routes.filemanager.os.path.realpath", side_effect=mock_realpath):
            with pytest.raises(HTTPException) as exc_info:
                self.fn("/var/log/somefile")
            assert exc_info.value.status_code == 400

    def test_realpath_resolves_to_allowed_dir(self):
        """realpath が許可ディレクトリ内に解決される場合は成功"""
        with patch("backend.api.routes.filemanager.os.path.realpath") as mock_rp:
            # realpath で base_dir も解決されるので両方モック
            mock_rp.side_effect = lambda p: p  # identity
            result = self.fn("/var/log/test.log")
            assert result == "/var/log/test.log"

    def test_realpath_exact_base_dir_match(self):
        """realpath 解決後にベースディレクトリ完全一致"""
        with patch("backend.api.routes.filemanager.os.path.realpath") as mock_rp:
            mock_rp.side_effect = lambda p: p
            result = self.fn("/etc/nginx")
            assert result == "/etc/nginx"

    @pytest.mark.parametrize("path", [
        "/var/log/../../etc/passwd",
        "/tmp/../root/.bashrc",
        "/home/../etc/shadow",
    ])
    def test_traversal_with_dotdot_in_allowed_prefix(self, path):
        """許可ディレクトリから始まるが ../ を含むパスは拒否"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn(path)
        assert exc_info.value.status_code == 400


# =====================================================================
# POST /api/files/upload: 追加カバレッジ
# =====================================================================


class TestUploadCoverageV2:
    """upload エンドポイントの未カバー分岐"""

    def test_upload_file_too_large_returns_413(self, test_client, admin_headers):
        """10MB超のファイルは 413 (line 238)"""
        content = b"x" * (10 * 1024 * 1024 + 1)
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("big.bin", io.BytesIO(content), "application/octet-stream")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 413

    def test_upload_wrapper_returns_error_status(self, test_client, admin_headers):
        """sudo_wrapper.upload_file が status=error を返す場合 400 (lines 242-243)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {
                "status": "error",
                "stderr": "disk full",
            }
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_upload_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """SudoWrapperError → 500 (lines 252-254)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.side_effect = SudoWrapperError("sudo failed")
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_upload_to_tmp_allowed(self, test_client, admin_headers):
        """/tmp へのアップロードは許可 (UPLOAD_ALLOWED_DIRS に含まれる)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/tmp"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_upload_to_home_allowed(self, test_client, admin_headers):
        """/home へのアップロードは許可"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/home"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_upload_none_filename_rejected(self, test_client, admin_headers):
        """filename が None の場合 422"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": (None, io.BytesIO(b"data"), "text/plain")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upload_success_response_contains_size(self, test_client, admin_headers):
        """成功レスポンスに size が含まれる"""
        content = b"hello world"
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["size"] == len(content)
        assert data["path"] == "/var/www/html/test.txt"

    def test_upload_disallowed_base_dir(self, test_client, admin_headers):
        """ALLOWED_BASE_DIRS にないパスへのアップロードは 400"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
            data={"dest_path": "/usr/local/bin"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_upload_wrapper_error_empty_stderr(self, test_client, admin_headers):
        """sudo_wrapper が status=error で stderr 空の場合"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "error", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    @pytest.mark.parametrize("filename", [
        "valid-file.txt",
        "file_name.log",
        "FILE.TXT",
        "test123.conf",
        "a.b",
    ])
    def test_upload_valid_filenames_accepted(self, filename, test_client, admin_headers):
        """有効なファイル名は受理"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/upload",
                files={"file": (filename, io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize("filename", [
        "file name.txt",
        "file;name.txt",
        "file|name.txt",
        "file\x00name.txt",
    ])
    def test_upload_dangerous_filenames_rejected(self, filename, test_client, admin_headers):
        """危険なファイル名は 422"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": (filename, io.BytesIO(b"data"), "text/plain")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# =====================================================================
# POST /api/files/chmod: 追加カバレッジ
# =====================================================================


class TestChmodCoverageV2:
    """chmod エンドポイントの未カバー分岐"""

    def test_chmod_wrapper_returns_error_status(self, test_client, admin_headers):
        """sudo_wrapper.chmod_file が status=error を返す場合 400 (lines 269-270)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {
                "status": "error",
                "stderr": "permission denied",
            }
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_chmod_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """SudoWrapperError → 500 (lines 279-281)"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.side_effect = SudoWrapperError("chmod sudo failed")
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_chmod_success_response_format(self, test_client, admin_headers):
        """成功レスポンスのフォーマット確認"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "success", "stdout": "ok", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "755"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["mode"] == "755"
        assert "path" in data

    def test_chmod_disallowed_path_returns_400(self, test_client, admin_headers):
        """許可外パスは 400"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/etc/shadow", "mode": "644"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_chmod_wrapper_error_empty_stderr(self, test_client, admin_headers):
        """status=error で stderr が空の場合のフォールバックメッセージ"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {"status": "error", "stderr": ""}
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 400


# =====================================================================
# GET /api/files/list: audit_log と出力確認
# =====================================================================


class TestFileListCoverageV2:
    """list エンドポイントの追加カバレッジ"""

    def test_list_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m, \
             patch("backend.api.routes.filemanager.audit_log") as mock_audit:
            m.list_files.return_value = {"stdout": "file1\n", "stderr": ""}
            resp = test_client.get("/api/files/list?path=/var/log", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args
        assert call_kwargs.kwargs.get("operation") == "filemanager_list" or \
               (call_kwargs[1].get("operation") == "filemanager_list" if call_kwargs[1] else False)

    def test_list_output_from_stdout(self, test_client, admin_headers):
        """レスポンスの output が stdout から取得される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stdout": "dir1\ndir2\nfile.txt\n", "stderr": ""}
            resp = test_client.get("/api/files/list?path=/var/log", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["output"] == "dir1\ndir2\nfile.txt\n"

    def test_list_missing_stdout_key(self, test_client, admin_headers):
        """stdout キーがない場合は空文字列"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stderr": ""}
            resp = test_client.get("/api/files/list?path=/var/log", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["output"] == ""


# =====================================================================
# GET /api/files/stat: audit_log と出力確認
# =====================================================================


class TestFileStatCoverageV2:
    """stat エンドポイントの追加カバレッジ"""

    def test_stat_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m, \
             patch("backend.api.routes.filemanager.audit_log") as mock_audit:
            m.stat_file.return_value = {"stdout": "stat info", "stderr": ""}
            resp = test_client.get("/api/files/stat?path=/var/log", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_stat_output_from_stdout(self, test_client, admin_headers):
        """レスポンスの output が stdout から取得される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.stat_file.return_value = {"stdout": "permissions: 755", "stderr": ""}
            resp = test_client.get("/api/files/stat?path=/var/log", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["output"] == "permissions: 755"


# =====================================================================
# GET /api/files/read: audit_log と出力確認
# =====================================================================


class TestFileReadCoverageV2:
    """read エンドポイントの追加カバレッジ"""

    def test_read_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m, \
             patch("backend.api.routes.filemanager.audit_log") as mock_audit:
            m.read_file.return_value = {"stdout": "content", "stderr": ""}
            resp = test_client.get("/api/files/read?path=/var/log&lines=10", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_read_content_from_stdout(self, test_client, admin_headers):
        """レスポンスの content が stdout から取得される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.read_file.return_value = {"stdout": "line1\nline2\n", "stderr": ""}
            resp = test_client.get("/api/files/read?path=/var/log&lines=5", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["content"] == "line1\nline2\n"

    def test_read_lines_200_max(self, test_client, admin_headers):
        """lines=200 は許容"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.read_file.return_value = {"stdout": "data", "stderr": ""}
            resp = test_client.get("/api/files/read?path=/var/log&lines=200", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["lines"] == 200


# =====================================================================
# GET /api/files/search: audit_log とパース確認
# =====================================================================


class TestFileSearchCoverageV2:
    """search エンドポイントの追加カバレッジ"""

    def test_search_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m, \
             patch("backend.api.routes.filemanager.audit_log") as mock_audit:
            m.search_files.return_value = {"stdout": "/var/log/test.log\n", "stderr": ""}
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_search_multiple_results_parsed(self, test_client, admin_headers):
        """複数結果が正しくパースされる"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.search_files.return_value = {
                "stdout": "/var/log/a.log\n/var/log/b.log\n/var/log/c.log\n",
                "stderr": "",
            }
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 3
        assert data["directory"] == "/var/log"
        assert data["pattern"] == "*.log"

    def test_search_results_with_empty_lines_filtered(self, test_client, admin_headers):
        """空行はフィルタされる"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.search_files.return_value = {
                "stdout": "/var/log/a.log\n\n\n/var/log/b.log\n\n",
                "stderr": "",
            }
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 2

    def test_search_sudo_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError → 500"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.search_files.side_effect = SudoWrapperError("find failed")
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=admin_headers,
            )
        assert resp.status_code == 500


# =====================================================================
# GET /api/files/allowed-dirs: 追加確認
# =====================================================================


class TestAllowedDirsCoverageV2:
    """allowed-dirs の追加カバレッジ"""

    def test_allowed_dirs_contains_tmp(self, test_client):
        """/tmp が含まれる"""
        resp = test_client.get("/api/files/allowed-dirs")
        assert resp.status_code == 200
        assert "/tmp" in resp.json()["allowed_dirs"]

    def test_allowed_dirs_response_format(self, test_client):
        """レスポンスフォーマット確認"""
        resp = test_client.get("/api/files/allowed-dirs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["allowed_dirs"], list)
        assert len(data["allowed_dirs"]) > 0
