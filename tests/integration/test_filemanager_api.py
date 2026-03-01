"""
ファイルマネージャーモジュール - 統合テスト (20件以上)

パストラバーサル防止・allowlist・認証・200行制限のテスト
"""
from unittest.mock import patch

import pytest

# ==============================================================================
# サンプルデータ
# ==============================================================================

SAMPLE_LS_OUTPUT = """\
total 48
drwxr-xr-x  5 root   root   4096 2024-01-15T10:00:00 .
drwxr-xr-x 22 root   root   4096 2024-01-14T09:00:00 ..
drwxr-xr-x  2 root   adm    4096 2024-01-15T10:05:00 apt
-rw-r--r--  1 root   root  12345 2024-01-15T11:00:00 syslog
-rw-r--r--  1 root   root   8765 2024-01-14T23:59:59 auth.log
"""

SAMPLE_STAT_OUTPUT = (
    '{"name":"/var/log/syslog","size":12345,"type":"regular file",'
    '"permissions":"-rw-r--r--","owner":"root","group":"root",'
    '"modified":"2024-01-15 11:00:00","inode":123456}'
)

SAMPLE_READ_OUTPUT = "line1\nline2\nline3\n"

SAMPLE_SEARCH_OUTPUT = "/var/log/syslog\n/var/log/auth.log\n"


def _ok(stdout: str) -> dict:
    return {"status": "success", "stdout": stdout, "stderr": ""}


# ==============================================================================
# 認証なし (401/403) テスト
# ==============================================================================


class TestFilesystemAuth:
    """認証なしは 403 を返すこと"""

    def test_list_no_auth(self, test_client):
        response = test_client.get("/api/files/list?path=/var/log")
        assert response.status_code == 403

    def test_stat_no_auth(self, test_client):
        response = test_client.get("/api/files/stat?path=/var/log/syslog")
        assert response.status_code == 403

    def test_read_no_auth(self, test_client):
        response = test_client.get("/api/files/read?path=/var/log/syslog")
        assert response.status_code == 403

    def test_search_no_auth(self, test_client):
        response = test_client.get("/api/files/search?directory=/var/log&pattern=*.log")
        assert response.status_code == 403


# ==============================================================================
# /api/files/allowed-dirs テスト (認証不要)
# ==============================================================================


class TestAllowedDirs:
    """GET /api/files/allowed-dirs は認証不要で200を返すこと"""

    def test_allowed_dirs_no_auth(self, test_client):
        """認証なしでも allowed-dirs は 200 を返す"""
        response = test_client.get("/api/files/allowed-dirs")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "allowed_dirs" in data
        assert isinstance(data["allowed_dirs"], list)

    def test_allowed_dirs_contains_var_log(self, test_client):
        """/var/log が許可リストに含まれる"""
        response = test_client.get("/api/files/allowed-dirs")
        data = response.json()
        assert "/var/log" in data["allowed_dirs"]

    def test_allowed_dirs_contains_expected(self, test_client):
        """期待するディレクトリが全て含まれる"""
        response = test_client.get("/api/files/allowed-dirs")
        dirs = response.json()["allowed_dirs"]
        for expected in ["/var/log", "/etc/nginx", "/etc/apache2", "/etc/ssh", "/tmp", "/var/www", "/home"]:
            assert expected in dirs


# ==============================================================================
# /api/files/list テスト
# ==============================================================================


class TestFileList:
    """GET /api/files/list テスト"""

    def test_list_success(self, test_client, viewer_headers):
        """正常パスでディレクトリ一覧を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_files") as mock:
            mock.return_value = _ok(SAMPLE_LS_OUTPUT)
            response = test_client.get("/api/files/list?path=/var/log", headers=viewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "output" in data

    def test_list_viewer_allowed(self, test_client, viewer_headers):
        """Viewer ロールでアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_files") as mock:
            mock.return_value = _ok(SAMPLE_LS_OUTPUT)
            response = test_client.get("/api/files/list?path=/var/log", headers=viewer_headers)
        assert response.status_code == 200

    def test_list_admin_allowed(self, test_client, admin_headers):
        """Admin ロールでアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_files") as mock:
            mock.return_value = _ok(SAMPLE_LS_OUTPUT)
            response = test_client.get("/api/files/list?path=/tmp", headers=admin_headers)
        assert response.status_code == 200


# ==============================================================================
# /api/files/stat テスト
# ==============================================================================


class TestFileStat:
    """GET /api/files/stat テスト"""

    def test_stat_success(self, test_client, viewer_headers):
        """正常パスでファイル属性を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.stat_file") as mock:
            mock.return_value = _ok(SAMPLE_STAT_OUTPUT)
            response = test_client.get("/api/files/stat?path=/var/log/syslog", headers=viewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "output" in data


# ==============================================================================
# /api/files/read テスト
# ==============================================================================


class TestFileRead:
    """GET /api/files/read テスト"""

    def test_read_success(self, test_client, viewer_headers):
        """正常パスでファイル内容を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.read_file") as mock:
            mock.return_value = _ok(SAMPLE_READ_OUTPUT)
            response = test_client.get("/api/files/read?path=/var/log/syslog&lines=10", headers=viewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "content" in data

    def test_read_default_lines(self, test_client, viewer_headers):
        """lines 省略時のデフォルト (50行)"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.read_file") as mock:
            mock.return_value = _ok(SAMPLE_READ_OUTPUT)
            response = test_client.get("/api/files/read?path=/var/log/syslog", headers=viewer_headers)
        assert response.status_code == 200
        assert response.json()["lines"] == 50

    def test_read_max_200_lines(self, test_client, viewer_headers):
        """200行の読み取りは成功する"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.read_file") as mock:
            mock.return_value = _ok(SAMPLE_READ_OUTPUT)
            response = test_client.get("/api/files/read?path=/var/log/syslog&lines=200", headers=viewer_headers)
        assert response.status_code == 200

    def test_read_over_200_lines_rejected(self, test_client, viewer_headers):
        """201行以上は 422 を返す (FastAPI バリデーション)"""
        response = test_client.get("/api/files/read?path=/var/log/syslog&lines=201", headers=viewer_headers)
        assert response.status_code == 422

    def test_read_zero_lines_rejected(self, test_client, viewer_headers):
        """0行以下は 422 を返す"""
        response = test_client.get("/api/files/read?path=/var/log/syslog&lines=0", headers=viewer_headers)
        assert response.status_code == 422


# ==============================================================================
# /api/files/search テスト
# ==============================================================================


class TestFileSearch:
    """GET /api/files/search テスト"""

    def test_search_success(self, test_client, viewer_headers):
        """正常パターンで検索結果を返す"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_files") as mock:
            mock.return_value = _ok(SAMPLE_SEARCH_OUTPUT)
            response = test_client.get(
                "/api/files/search?directory=/var/log&pattern=*.log",
                headers=viewer_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "files" in data


# ==============================================================================
# セキュリティテスト: パストラバーサル
# ==============================================================================


class TestPathTraversal:
    """危険なパスは 400 を返すこと"""

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../../etc/passwd",
            "/etc/shadow",
            "/root/.ssh/id_rsa",
            "/proc/1/mem",
            "/var/log/../../../etc/passwd",
            "/root",
            "/etc/sudoers",
            "relative/path",
            "",
        ],
    )
    def test_reject_path_traversal_list(self, test_client, viewer_headers, malicious_path):
        """list エンドポイント: 危険なパスは 400 を返す"""
        response = test_client.get(
            f"/api/files/list?path={malicious_path}",
            headers=viewer_headers,
        )
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for path={malicious_path!r}, got {response.status_code}"
        )

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../../etc/passwd",
            "/etc/shadow",
            "/root/.ssh/id_rsa",
            "/proc/1/mem",
            "/var/log/../../../etc/passwd",
        ],
    )
    def test_reject_path_traversal_read(self, test_client, viewer_headers, malicious_path):
        """read エンドポイント: 危険なパスは 400 を返す"""
        response = test_client.get(
            f"/api/files/read?path={malicious_path}&lines=10",
            headers=viewer_headers,
        )
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for path={malicious_path!r}, got {response.status_code}"
        )

    def test_reject_null_byte_in_path(self, test_client, viewer_headers):
        """Null バイトを含むパスを拒否する (%00 URL エンコーディング)"""
        response = test_client.get("/api/files/list?path=/var/log/sys%00log", headers=viewer_headers)
        assert response.status_code in (400, 422)

    def test_reject_root_access(self, test_client, viewer_headers):
        """/root へのアクセスを拒否する"""
        response = test_client.get("/api/files/list?path=/root", headers=viewer_headers)
        assert response.status_code == 400

    def test_reject_etc_shadow(self, test_client, viewer_headers):
        """/etc/shadow へのアクセスを拒否する"""
        response = test_client.get("/api/files/stat?path=/etc/shadow", headers=viewer_headers)
        assert response.status_code == 400

    def test_reject_proc_mem(self, test_client, viewer_headers):
        """/proc/1/mem へのアクセスを拒否する"""
        response = test_client.get("/api/files/read?path=/proc/1/mem&lines=1", headers=viewer_headers)
        assert response.status_code == 400

    def test_reject_relative_path(self, test_client, viewer_headers):
        """相対パスを拒否する"""
        response = test_client.get("/api/files/list?path=var/log", headers=viewer_headers)
        assert response.status_code == 400

    def test_reject_search_forbidden_char_semicolon(self, test_client, viewer_headers):
        """検索パターンにセミコロンが含まれる場合は拒否"""
        response = test_client.get(
            "/api/files/search?directory=/var/log&pattern=*.log;rm+-rf+/",
            headers=viewer_headers,
        )
        assert response.status_code == 400
