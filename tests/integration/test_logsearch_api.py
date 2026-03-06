"""
ログ検索モジュール - 統合テスト

/api/logsearch エンドポイントの統合テスト（sudo_wrapper をモック）
"""

from unittest.mock import patch

import pytest

# ==============================================================================
# テスト用サンプルデータ
# ==============================================================================

SAMPLE_FILES = {
    "status": "success",
    "file_count": 3,
    "files": ["/var/log/syslog", "/var/log/auth.log", "/var/log/kern.log"],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SEARCH = {
    "status": "success",
    "pattern": "error",
    "logfile": "syslog",
    "lines_returned": 2,
    "results": [
        "Jan  1 00:00:00 server kernel: error detected",
        "Jan  1 00:00:01 server sshd[123]: error connecting",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_ERRORS = {
    "status": "success",
    "error_count": 2,
    "errors": [
        "Jan  1 00:00:00 server kernel: error detected",
        "Jan  1 00:00:01 server sshd[123]: error connecting",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

EMPTY_SEARCH = {
    "status": "success",
    "pattern": "nonexistent",
    "logfile": "syslog",
    "lines_returned": 0,
    "results": [],
    "timestamp": "2026-01-01T00:00:00Z",
}

EMPTY_ERRORS = {
    "status": "success",
    "error_count": 0,
    "errors": [],
    "timestamp": "2026-01-01T00:00:00Z",
}

# ==============================================================================
# 認証テスト
# ==============================================================================


class TestLogsearchAuth:
    """未認証リクエストは拒否されること"""

    def test_files_no_auth(self, test_client):
        """未認証で /files は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/files")
        assert response.status_code in (401, 403)

    def test_search_no_auth(self, test_client):
        """未認証で /search は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error")
        assert response.status_code in (401, 403)

    def test_recent_errors_no_auth(self, test_client):
        """未認証で /recent-errors は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/recent-errors")
        assert response.status_code in (401, 403)


# ==============================================================================
# 正常系テスト
# ==============================================================================


class TestLogsearchSuccess:
    """正常系のテスト"""

    def test_list_files_success(self, test_client, auth_headers):
        """/files が 200 とファイル一覧を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "file_count" in data
        assert data["file_count"] == 3
        assert "/var/log/syslog" in data["files"]

    def test_search_basic(self, test_client, auth_headers):
        """/search?pattern=error が 200 と結果を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["pattern"] == "error"
        assert "results" in data
        assert data["lines_returned"] == 2

    def test_search_with_logfile_and_lines(self, test_client, auth_headers):
        """/search?pattern=error&logfile=syslog&lines=10 が 200 を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH) as mock:
            response = test_client.get(
                "/api/logsearch/search?pattern=error&logfile=syslog&lines=10",
                headers=auth_headers,
            )
        assert response.status_code == 200
        mock.assert_called_once_with("error", "syslog", 10)

    def test_recent_errors_success(self, test_client, auth_headers):
        """/recent-errors が 200 とエラー一覧を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", return_value=SAMPLE_ERRORS):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        assert data["error_count"] == 2

    def test_viewer_can_list_files(self, test_client, viewer_headers):
        """viewer ロールでも /files にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_search(self, test_client, viewer_headers):
        """viewer ロールでも /search にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=viewer_headers)
        assert response.status_code == 200

    def test_admin_can_list_files(self, test_client, admin_headers):
        """admin ロールでも /files にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=admin_headers)
        assert response.status_code == 200

    def test_empty_results(self, test_client, auth_headers):
        """検索結果が空でも正常に返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=EMPTY_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=nonexistent", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["lines_returned"] == 0

    def test_empty_errors(self, test_client, auth_headers):
        """エラーログが空でも正常に返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", return_value=EMPTY_ERRORS):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == []
        assert data["error_count"] == 0


# ==============================================================================
# バリデーションテスト
# ==============================================================================


class TestLogsearchValidation:
    """入力バリデーションのテスト"""

    def test_search_no_pattern(self, test_client, auth_headers):
        """pattern なしで /search は 422 を返すこと"""
        response = test_client.get("/api/logsearch/search", headers=auth_headers)
        assert response.status_code == 422

    def test_search_forbidden_semicolon_in_pattern(self, test_client, auth_headers):
        """pattern にセミコロンが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err;ls", headers=auth_headers)
        assert response.status_code == 400

    def test_search_forbidden_pipe_in_pattern(self, test_client, auth_headers):
        """pattern にパイプが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err|grep", headers=auth_headers)
        assert response.status_code == 400

    def test_search_forbidden_char_in_logfile(self, test_client, auth_headers):
        """logfile にセミコロンが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&logfile=sys;log", headers=auth_headers)
        assert response.status_code == 400

    def test_search_path_traversal_in_logfile(self, test_client, auth_headers):
        """logfile にパストラバーサルが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&logfile=../etc/passwd", headers=auth_headers)
        assert response.status_code == 400

    def test_search_lines_too_large(self, test_client, auth_headers):
        """lines=201 の場合 422 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&lines=201", headers=auth_headers)
        assert response.status_code == 422

    def test_search_lines_too_small(self, test_client, auth_headers):
        """lines=0 の場合 422 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&lines=0", headers=auth_headers)
        assert response.status_code == 422

    def test_search_dollar_in_pattern(self, test_client, auth_headers):
        """pattern にドル記号が含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err$HOME", headers=auth_headers)
        assert response.status_code == 400

    def test_search_backtick_in_pattern(self, test_client, auth_headers):
        """pattern にバッククォートが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err%60id%60", headers=auth_headers)
        assert response.status_code == 400


# ==============================================================================
# エラーハンドリングテスト
# ==============================================================================


class TestLogsearchErrorHandling:
    """エラーハンドリングのテスト"""

    def test_list_files_sudo_wrapper_error(self, test_client, auth_headers):
        """list_log_files で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 500

    def test_search_sudo_wrapper_error(self, test_client, auth_headers):
        """search_logs で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 500

    def test_recent_errors_sudo_wrapper_error(self, test_client, auth_headers):
        """get_recent_errors で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 500

    def test_list_files_generic_exception(self, test_client, auth_headers):
        """list_log_files で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 503

    def test_search_generic_exception(self, test_client, auth_headers):
        """search_logs で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 503

    def test_recent_errors_generic_exception(self, test_client, auth_headers):
        """get_recent_errors で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 503


class TestLogsearchTailEndpoint:
    """GET /api/logsearch/tail エンドポイントのテスト"""

    def test_get_tail_success(self, test_client, auth_headers):
        """tail-multi が正常に結果を返す"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi") as m:
            m.return_value = {"output": ["line1", "line2"], "files": ["syslog", "auth.log"], "timestamp": "2026-01-01T00:00:00Z"}
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "output" in data
        assert data["lines_per_file"] == 30

    def test_get_tail_custom_lines(self, test_client, auth_headers):
        """lines パラメータを指定できる"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi") as m:
            m.return_value = {"output": [], "files": [], "timestamp": "2026-01-01T00:00:00Z"}
            resp = test_client.get("/api/logsearch/tail?lines=10", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["lines_per_file"] == 10

    def test_get_tail_lines_too_large(self, test_client, auth_headers):
        """lines > 100 は 422"""
        resp = test_client.get("/api/logsearch/tail?lines=200", headers=auth_headers)
        assert resp.status_code == 422

    def test_get_tail_lines_too_small(self, test_client, auth_headers):
        """lines < 5 は 422"""
        resp = test_client.get("/api/logsearch/tail?lines=1", headers=auth_headers)
        assert resp.status_code == 422

    def test_get_tail_sudo_error(self, test_client, auth_headers):
        """SudoWrapperError → 500"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi", side_effect=SudoWrapperError("fail")):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 500

    def test_get_tail_generic_exception(self, test_client, auth_headers):
        """Exception → 503"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi", side_effect=Exception("unexpected")):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 503

    def test_get_tail_unauthenticated(self, test_client):
        """認証なし → 401"""
        resp = test_client.get("/api/logsearch/tail")
        assert resp.status_code in (401, 403)
