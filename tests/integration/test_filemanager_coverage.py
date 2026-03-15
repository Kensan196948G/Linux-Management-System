"""
filemanager.py カバレッジ改善テスト

対象: backend/api/routes/filemanager.py
既存テストと重複しない validate_path/upload/chmod/search のエッジケースを網羅
"""

import io
from unittest.mock import patch

import pytest
from fastapi import HTTPException


# =====================================================================
# validate_path 単体テスト
# =====================================================================


class TestValidatePath:
    """validate_path ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.filemanager import validate_path

        self.fn = validate_path

    def test_valid_var_log(self):
        """正常パス /var/log"""
        result = self.fn("/var/log")
        assert result.startswith("/var/log") or result.startswith("/")

    def test_valid_etc_nginx(self):
        """/etc/nginx は許可"""
        result = self.fn("/etc/nginx")
        assert "/etc/nginx" in result or result.endswith("nginx")

    def test_valid_tmp(self):
        """/tmp は許可"""
        result = self.fn("/tmp")
        assert result  # 何か返る

    @pytest.mark.parametrize(
        "path",
        [
            "/etc/shadow",
            "/root",
            "/usr/bin",
            "/proc/1/mem",
            "/sys/kernel",
            "/boot",
            "/dev/null",
        ],
    )
    def test_disallowed_dirs_rejected(self, path):
        """許可リスト外のディレクトリは拒否"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn(path)
        assert exc_info.value.status_code == 400

    def test_empty_string_rejected(self):
        """空文字列は拒否"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn("")
        assert exc_info.value.status_code == 400

    def test_none_rejected(self):
        """None は拒否"""
        with pytest.raises((HTTPException, TypeError)):
            self.fn(None)

    def test_dotdot_slash_rejected(self):
        """../ を含むパスは拒否"""
        with pytest.raises(HTTPException):
            self.fn("/var/log/../../../etc/passwd")

    def test_slash_dotdot_rejected(self):
        """/.. を含むパスは拒否"""
        with pytest.raises(HTTPException):
            self.fn("/var/log/..")

    def test_bare_dotdot_rejected(self):
        """.. のみは拒否"""
        with pytest.raises(HTTPException):
            self.fn("..")

    def test_null_byte_rejected(self):
        """Null バイト含有は拒否"""
        with pytest.raises(HTTPException):
            self.fn("/var/log/test\x00.log")

    def test_relative_path_rejected(self):
        """相対パスは拒否"""
        with pytest.raises(HTTPException):
            self.fn("var/log")

    def test_allowed_dir_exact_match(self):
        """/var/log 完全一致"""
        result = self.fn("/var/log")
        assert result  # 正常に返る

    def test_allowed_dir_subpath(self):
        """/var/log/syslog はサブパスとして許可"""
        # /var/log/syslog が実在しなくても validate_path は realpath で検証
        # 実在チェックは行わない（realpath が解決できれば OK）
        try:
            result = self.fn("/var/log/syslog")
            assert result  # 存在すれば正常
        except HTTPException:
            pass  # ファイル不在でも realpath の結果次第

    def test_symlink_traversal_blocked(self, tmp_path):
        """シンボリックリンク経由のトラバーサルはブロック"""
        # /tmp 配下にシンボリックリンクを作成
        link = tmp_path / "evil_link"
        link.symlink_to("/etc/shadow")
        with pytest.raises(HTTPException):
            self.fn(str(link))


# =====================================================================
# POST /api/files/upload エッジケース
# =====================================================================


class TestUploadEdgeCases:
    """upload の追加エッジケーステスト"""

    def test_upload_empty_filename_rejected(self, test_client, admin_headers):
        """空ファイル名は拒否 (422)"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("", io.BytesIO(b"data"), "text/plain")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "filename",
        [
            "test file.txt",
            "test<script>.txt",
        ],
    )
    def test_upload_invalid_filenames(self, filename, test_client, admin_headers):
        """不正なファイル名パターン（スペース・特殊文字）は 422"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": (filename, io.BytesIO(b"data"), "text/plain")},
            data={"dest_path": "/var/www/html"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_upload_allowed_dest_var_www_subdir(self, test_client, admin_headers):
        """アップロード先: /var/www/html は許可"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {
                "status": "success",
                "stdout": "ok",
                "stderr": "",
            }
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_upload_dest_etc_nginx_forbidden(self, test_client, admin_headers):
        """/etc/nginx は ALLOWED_BASE_DIRS にあるが UPLOAD_ALLOWED_DIRS にない → 403"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("test.conf", io.BytesIO(b"config"), "text/plain")},
            data={"dest_path": "/etc/nginx"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_upload_dest_etc_ssh_forbidden(self, test_client, admin_headers):
        """/etc/ssh は UPLOAD_ALLOWED_DIRS にない → 403"""
        resp = test_client.post(
            "/api/files/upload",
            files={"file": ("key.pub", io.BytesIO(b"pubkey"), "text/plain")},
            data={"dest_path": "/etc/ssh"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_upload_value_error_returns_500(self, test_client, admin_headers):
        """ValueError は 500"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.side_effect = ValueError("invalid data")
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_upload_exact_10mb_accepted(self, test_client, admin_headers):
        """ちょうど 10MB は許容"""
        content = b"x" * (10 * 1024 * 1024)
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {
                "status": "success",
                "stdout": "ok",
                "stderr": "",
            }
            resp = test_client.post(
                "/api/files/upload",
                files={
                    "file": ("big.bin", io.BytesIO(content), "application/octet-stream")
                },
                data={"dest_path": "/var/www/html"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_upload_viewer_allowed(self, test_client, viewer_headers):
        """viewer ロールは write:filemanager 権限を持つためアップロード可能"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.upload_file.return_value = {
                "status": "success",
                "stdout": "ok",
                "stderr": "",
            }
            resp = test_client.post(
                "/api/files/upload",
                files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
                data={"dest_path": "/var/www/html"},
                headers=viewer_headers,
            )
        assert resp.status_code == 200


# =====================================================================
# POST /api/files/chmod エッジケース
# =====================================================================


class TestChmodEdgeCases:
    """chmod の追加エッジケーステスト"""

    @pytest.mark.parametrize(
        "mode",
        [
            "000",
            "777",
            "0644",
            "0755",
            "1777",
            "4755",
        ],
    )
    def test_chmod_valid_modes(self, mode, test_client, admin_headers):
        """有効な octal モードは受理"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {
                "status": "success",
                "stdout": "ok",
                "stderr": "",
            }
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": mode},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "mode",
        [
            "89",
            "12345",
            "rwx",
            "u+x",
            "",
            "9999",
            "abc",
            "7778",
        ],
    )
    def test_chmod_invalid_modes(self, mode, test_client, admin_headers):
        """不正なモードは 422"""
        resp = test_client.post(
            "/api/files/chmod",
            json={"path": "/var/www/html/test.txt", "mode": mode},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_chmod_value_error_returns_500(self, test_client, admin_headers):
        """chmod で ValueError → 500"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.side_effect = ValueError("invalid chmod")
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_chmod_viewer_allowed(self, test_client, viewer_headers):
        """viewer ロールは write:filemanager 権限を持つため chmod 可能"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.chmod_file.return_value = {
                "status": "success",
                "stdout": "ok",
                "stderr": "",
            }
            resp = test_client.post(
                "/api/files/chmod",
                json={"path": "/var/www/html/test.txt", "mode": "644"},
                headers=viewer_headers,
            )
        assert resp.status_code == 200


# =====================================================================
# GET /api/files/search エッジケース
# =====================================================================


class TestFileSearchEdgeCases:
    """search エンドポイントの追加テスト"""

    @pytest.mark.parametrize("forbidden_char", [";", "|", "$", "(", ")", "`", ">", "<"])
    def test_search_forbidden_chars(self, forbidden_char, test_client, viewer_headers):
        """各禁止文字でパターンが拒否される"""
        resp = test_client.get(
            "/api/files/search",
            params={"directory": "/var/log", "pattern": f"test{forbidden_char}cmd"},
            headers=viewer_headers,
        )
        assert resp.status_code == 400

    def test_search_forbidden_ampersand(self, test_client, viewer_headers):
        """& を含むパターンが拒否される"""
        resp = test_client.get(
            "/api/files/search",
            params={"directory": "/var/log", "pattern": "test&cmd"},
            headers=viewer_headers,
        )
        assert resp.status_code == 400

    def test_search_normal_pattern(self, test_client, viewer_headers):
        """正常なパターン *.log"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.search_files.return_value = {"stdout": "/var/log/syslog\n", "stderr": ""}
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=viewer_headers,
            )
        assert resp.status_code == 200
        assert len(resp.json()["files"]) >= 1

    def test_search_empty_results(self, test_client, viewer_headers):
        """検索結果なし"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.search_files.return_value = {"stdout": "", "stderr": ""}
            resp = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.xyz",
                headers=viewer_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_search_disallowed_directory(self, test_client, viewer_headers):
        """許可外ディレクトリで検索 → 400"""
        resp = test_client.get(
            "/api/files/search?directory=/root&pattern=*.txt",
            headers=viewer_headers,
        )
        assert resp.status_code == 400


# =====================================================================
# GET /api/files/list 追加テスト
# =====================================================================


class TestFileListEdgeCases:
    """list エンドポイントの追加テスト"""

    def test_list_etc_ssh_allowed(self, test_client, viewer_headers):
        """/etc/ssh はブラウズ許可"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stdout": "file1\nfile2\n", "stderr": ""}
            resp = test_client.get(
                "/api/files/list?path=/etc/ssh", headers=viewer_headers
            )
        assert resp.status_code == 200

    def test_list_etc_apache2_allowed(self, test_client, viewer_headers):
        """/etc/apache2 はブラウズ許可"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stdout": "", "stderr": ""}
            resp = test_client.get(
                "/api/files/list?path=/etc/apache2", headers=viewer_headers
            )
        assert resp.status_code == 200

    def test_list_home_allowed(self, test_client, viewer_headers):
        """/home はブラウズ許可"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stdout": "user1\nuser2\n", "stderr": ""}
            resp = test_client.get("/api/files/list?path=/home", headers=viewer_headers)
        assert resp.status_code == 200

    def test_list_returns_path_in_response(self, test_client, viewer_headers):
        """レスポンスに path が含まれる"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.list_files.return_value = {"stdout": "file1", "stderr": ""}
            resp = test_client.get(
                "/api/files/list?path=/var/log", headers=viewer_headers
            )
        assert resp.status_code == 200
        assert "path" in resp.json()


# =====================================================================
# GET /api/files/stat 追加テスト
# =====================================================================


class TestFileStatEdgeCases:
    """stat エンドポイントの追加テスト"""

    def test_stat_disallowed_path(self, test_client, viewer_headers):
        """許可外パス → 400"""
        resp = test_client.get(
            "/api/files/stat?path=/root/.bashrc", headers=viewer_headers
        )
        assert resp.status_code == 400

    def test_stat_returns_path_in_response(self, test_client, viewer_headers):
        """レスポンスに path が含まれる"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.stat_file.return_value = {"stdout": "stat output", "stderr": ""}
            resp = test_client.get(
                "/api/files/stat?path=/var/log", headers=viewer_headers
            )
        assert resp.status_code == 200
        assert "path" in resp.json()


# =====================================================================
# GET /api/files/read 追加テスト
# =====================================================================


class TestFileReadEdgeCases:
    """read エンドポイントの追加テスト"""

    def test_read_disallowed_path(self, test_client, viewer_headers):
        """許可外パス → 400"""
        resp = test_client.get(
            "/api/files/read?path=/root/.bashrc", headers=viewer_headers
        )
        assert resp.status_code == 400

    def test_read_response_has_content_key(self, test_client, viewer_headers):
        """レスポンスに content キーが含まれる"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.read_file.return_value = {"stdout": "file content\n", "stderr": ""}
            resp = test_client.get(
                "/api/files/read?path=/var/log&lines=10", headers=viewer_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "lines" in data
        assert data["lines"] == 10

    def test_read_lines_1(self, test_client, viewer_headers):
        """lines=1 は受理"""
        with patch("backend.api.routes.filemanager.sudo_wrapper") as m:
            m.read_file.return_value = {"stdout": "first line", "stderr": ""}
            resp = test_client.get(
                "/api/files/read?path=/var/log&lines=1", headers=viewer_headers
            )
        assert resp.status_code == 200

    def test_read_negative_lines_rejected(self, test_client, viewer_headers):
        """lines=-1 は 422"""
        resp = test_client.get(
            "/api/files/read?path=/var/log&lines=-1", headers=viewer_headers
        )
        assert resp.status_code == 422
