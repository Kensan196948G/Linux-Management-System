"""
ログ検索 API 統合テスト (Step 25)
"""

import pytest
from unittest.mock import patch


MOCK_SEARCH_RESULT = {
    "status": "success",
    "pattern": "error",
    "logfile": "syslog",
    "lines_returned": 3,
    "results": ["Jan  1 00:00:01 host svc: error occurred", "Jan  1 00:00:02 host svc: error again", "Jan  1 00:00:03 host svc: error"],
    "timestamp": "2024-01-01T00:00:00+00:00",
}

MOCK_FILES_RESULT = {
    "status": "success",
    "file_count": 2,
    "files": ["/var/log/syslog", "/var/log/auth.log"],
    "timestamp": "2024-01-01T00:00:00+00:00",
}

MOCK_ERRORS_RESULT = {
    "status": "success",
    "error_count": 2,
    "errors": ["Jan  1 00:00:01 host svc: error occurred", "Jan  1 00:00:02 host svc: critical failure"],
    "timestamp": "2024-01-01T00:00:00+00:00",
}


class TestLogSearch:
    """GET /api/logs/search エンドポイントのテスト"""

    def test_search_logs_success(self, test_client, auth_headers):
        """正常な検索クエリで 200 を返すこと"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.search_logs.return_value = MOCK_SEARCH_RESULT
            response = test_client.get(
                "/api/logs/search?q=error",
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "results" in data

    def test_search_logs_empty_query_returns_422(self, test_client, auth_headers):
        """空のクエリ (q=) で 422 を返すこと"""
        response = test_client.get("/api/logs/search?q=", headers=auth_headers)
        assert response.status_code == 422

    def test_search_logs_forbidden_chars_returns_400(self, test_client, auth_headers):
        """禁止文字を含むクエリで 400 を返すこと"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            response = test_client.get(
                "/api/logs/search?q=;rm+-rf",
                headers=auth_headers,
            )
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "Forbidden" in detail or "forbidden" in detail.lower()

    def test_search_logs_pipe_forbidden(self, test_client, auth_headers):
        """パイプ文字で 400 を返すこと"""
        response = test_client.get(
            "/api/logs/search?q=foo|bar",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_search_logs_with_file_param(self, test_client, auth_headers):
        """file パラメータ付きで正常動作すること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.search_logs.return_value = MOCK_SEARCH_RESULT
            response = test_client.get(
                "/api/logs/search?q=error&file=auth.log&lines=20",
                headers=auth_headers,
            )
        assert response.status_code == 200

    def test_search_logs_no_auth_returns_401(self, test_client):
        """認証なしで 401 を返すこと"""
        response = test_client.get("/api/logs/search?q=error")
        assert response.status_code == 401


class TestLogFiles:
    """GET /api/logs/files エンドポイントのテスト"""

    def test_list_log_files_success(self, test_client, auth_headers):
        """ログファイル一覧が 200 で返ること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.list_log_files.return_value = MOCK_FILES_RESULT
            response = test_client.get("/api/logs/files", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "files" in data

    def test_list_log_files_no_auth_returns_401(self, test_client):
        """認証なしで 401 を返すこと"""
        response = test_client.get("/api/logs/files")
        assert response.status_code == 401


class TestRecentErrors:
    """GET /api/logs/recent-errors エンドポイントのテスト"""

    def test_recent_errors_success(self, test_client, auth_headers):
        """直近エラー取得が 200 で返ること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_recent_errors.return_value = MOCK_ERRORS_RESULT
            response = test_client.get("/api/logs/recent-errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "errors" in data

    def test_recent_errors_no_auth_returns_401(self, test_client):
        """認証なしで 401 を返すこと"""
        response = test_client.get("/api/logs/recent-errors")
        assert response.status_code == 401
