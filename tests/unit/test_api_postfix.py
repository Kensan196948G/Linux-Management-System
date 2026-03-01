"""
Postfix API エンドポイントのユニットテスト

backend/api/routes/postfix.py のカバレッジ向上
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestGetPostfixStatus:
    """GET /api/postfix/status テスト"""

    def test_status_success(self, test_client, auth_headers):
        """正常系: Postfixステータス取得"""
        mock_data = {"service": "postfix", "running": True, "version": "3.6.4"}
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_status.return_value = mock_data
            response = test_client.get("/api/postfix/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["running"] is True

    def test_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/postfix/status", headers=auth_headers)
        assert response.status_code == 503

    def test_status_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/postfix/status")
        assert response.status_code == 403


class TestGetPostfixQueue:
    """GET /api/postfix/queue テスト"""

    def test_queue_success(self, test_client, auth_headers):
        """正常系: メールキュー取得"""
        mock_data = {"queue_size": 5, "messages": []}
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_queue.return_value = mock_data
            response = test_client.get("/api/postfix/queue", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_queue_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_queue.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/postfix/queue", headers=auth_headers)
        assert response.status_code == 503


class TestGetPostfixLogs:
    """GET /api/postfix/logs テスト"""

    def test_logs_success_default(self, test_client, auth_headers):
        """正常系: デフォルト行数でログ取得"""
        mock_data = {"lines": ["log1", "log2"], "count": 2}
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_logs.return_value = mock_data
            response = test_client.get("/api/postfix/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_logs_success_custom_lines(self, test_client, auth_headers):
        """正常系: 行数指定"""
        mock_data = {"lines": ["log1"], "count": 1}
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_logs.return_value = mock_data
            response = test_client.get(
                "/api/postfix/logs?lines=100", headers=auth_headers
            )
        assert response.status_code == 200

    def test_logs_invalid_lines_zero(self, test_client, auth_headers):
        """不正な行数（0）"""
        response = test_client.get(
            "/api/postfix/logs?lines=0", headers=auth_headers
        )
        assert response.status_code == 422

    def test_logs_invalid_lines_over(self, test_client, auth_headers):
        """不正な行数（201）"""
        response = test_client.get(
            "/api/postfix/logs?lines=201", headers=auth_headers
        )
        assert response.status_code == 422

    def test_logs_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.postfix.sudo_wrapper") as mock_sw:
            mock_sw.get_postfix_logs.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/postfix/logs", headers=auth_headers)
        assert response.status_code == 503
