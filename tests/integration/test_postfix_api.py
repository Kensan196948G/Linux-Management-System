"""Postfix API テスト (TC_PTF_001〜020)"""

import pytest
from unittest.mock import MagicMock, patch

from backend.core.sudo_wrapper import SudoWrapperError


class TestPostfixStatus:
    """Postfix ステータス取得テスト"""

    def test_TC_PTF_001_status_success(self, test_client, admin_token):
        """TC_PTF_001: ステータス取得成功（admin）"""
        mock_data = {"status": "running", "version": "postfix 3.6.0", "queue_count": 0}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_status", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "running"

    def test_TC_PTF_002_status_viewer(self, test_client, viewer_token):
        """TC_PTF_002: viewer でもステータス取得可能"""
        mock_data = {"status": "stopped", "version": "unknown", "queue_count": 0}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_status", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_PTF_003_status_unavailable(self, test_client, admin_token):
        """TC_PTF_003: postfix 未インストール環境"""
        mock_data = {"status": "unavailable", "message": "postfix is not installed"}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_status", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "unavailable"

    def test_TC_PTF_004_status_unauthenticated(self, test_client):
        """TC_PTF_004: 未認証は拒否"""
        resp = test_client.get("/api/postfix/status")
        assert resp.status_code in (401, 403)

    def test_TC_PTF_005_status_wrapper_error(self, test_client, admin_token):
        """TC_PTF_005: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.postfix.sudo_wrapper.get_postfix_status",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/postfix/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503


class TestPostfixQueue:
    """Postfix キュー取得テスト"""

    def test_TC_PTF_006_queue_success(self, test_client, admin_token):
        """TC_PTF_006: キュー取得成功"""
        mock_data = {"queue": "Mail queue is empty\n"}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_queue", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/queue",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "queue" in body["data"]

    def test_TC_PTF_007_queue_with_messages(self, test_client, auth_token):
        """TC_PTF_007: キューにメッセージあり"""
        mock_data = {"queue": "ABC123  1234 Fri Feb 27   user@example.com\n(connect to mail.example.com: refused)\n                                         dest@example.com\n"}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_queue", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/queue",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert resp.status_code == 200

    def test_TC_PTF_008_queue_unauthenticated(self, test_client):
        """TC_PTF_008: 未認証は拒否"""
        resp = test_client.get("/api/postfix/queue")
        assert resp.status_code in (401, 403)

    def test_TC_PTF_009_queue_wrapper_error(self, test_client, admin_token):
        """TC_PTF_009: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.postfix.sudo_wrapper.get_postfix_queue",
            side_effect=SudoWrapperError("queue error"),
        ):
            resp = test_client.get(
                "/api/postfix/queue",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_PTF_010_queue_unavailable(self, test_client, admin_token):
        """TC_PTF_010: postfix 未インストール時のキュー"""
        mock_data = {"status": "unavailable", "message": "postfix is not installed"}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_queue", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/queue",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200


class TestPostfixLogs:
    """Postfix ログ取得テスト"""

    def test_TC_PTF_011_logs_default(self, test_client, admin_token):
        """TC_PTF_011: デフォルト50行取得"""
        mock_data = {"logs": "Feb 27 12:00:00 server postfix/smtpd[1234]: connect from...\n", "lines": 50}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "logs" in body["data"]

    def test_TC_PTF_012_logs_custom_lines(self, test_client, admin_token):
        """TC_PTF_012: 行数指定"""
        mock_data = {"logs": "log content\n", "lines": 100}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_logs", return_value=mock_data) as mock:
            resp = test_client.get(
                "/api/postfix/logs?lines=100",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(lines=100)

    def test_TC_PTF_013_logs_max_limit(self, test_client, admin_token):
        """TC_PTF_013: 200行上限の検証"""
        resp = test_client.get(
            "/api/postfix/logs?lines=201",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_PTF_014_logs_min_limit(self, test_client, admin_token):
        """TC_PTF_014: 最小1行の検証"""
        resp = test_client.get(
            "/api/postfix/logs?lines=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_TC_PTF_015_logs_unauthenticated(self, test_client):
        """TC_PTF_015: 未認証は拒否"""
        resp = test_client.get("/api/postfix/logs")
        assert resp.status_code in (401, 403)

    def test_TC_PTF_016_logs_wrapper_error(self, test_client, admin_token):
        """TC_PTF_016: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.postfix.sudo_wrapper.get_postfix_logs",
            side_effect=SudoWrapperError("logs error"),
        ):
            resp = test_client.get(
                "/api/postfix/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_PTF_017_logs_viewer(self, test_client, viewer_token):
        """TC_PTF_017: viewer でもログ取得可能"""
        mock_data = {"logs": "", "lines": 50}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/logs",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_TC_PTF_018_logs_empty(self, test_client, admin_token):
        """TC_PTF_018: ログが空の場合"""
        mock_data = {"logs": "", "lines": 50}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_logs", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["logs"] == ""

    def test_TC_PTF_019_status_queue_count_nonzero(self, test_client, admin_token):
        """TC_PTF_019: キュー数が0以外のステータス"""
        mock_data = {"status": "running", "version": "postfix 3.6.0", "queue_count": 5}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_status", return_value=mock_data):
            resp = test_client.get(
                "/api/postfix/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["queue_count"] == 5

    def test_TC_PTF_020_logs_200_lines(self, test_client, admin_token):
        """TC_PTF_020: 最大200行の取得"""
        mock_data = {"logs": "log\n" * 200, "lines": 200}
        with patch("backend.api.routes.postfix.sudo_wrapper.get_postfix_logs", return_value=mock_data) as mock:
            resp = test_client.get(
                "/api/postfix/logs?lines=200",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(lines=200)
