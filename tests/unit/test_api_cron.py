"""
Cron API エンドポイントのユニットテスト

backend/api/routes/cron.py のカバレッジ向上
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestListCronJobs:
    """GET /api/cron/{username} テスト"""

    def test_list_cron_jobs_success(self, test_client, auth_headers):
        """正常系: Cronジョブ一覧取得"""
        mock_result = {
            "status": "success",
            "user": "testuser",
            "jobs": [
                {
                    "id": "job1",
                    "line_number": 1,
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": "/data /backup",
                    "comment": "Daily backup",
                    "enabled": True,
                },
            ],
            "total_count": 1,
            "max_allowed": 10,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_count"] == 1

    def test_list_cron_jobs_invalid_username(self, test_client, auth_headers):
        """不正なユーザー名 → 400"""
        response = test_client.get("/api/cron/bad%3Buser", headers=auth_headers)
        assert response.status_code == 400

    def test_list_cron_jobs_error_invalid_username(self, test_client, auth_headers):
        """エラーコード INVALID_USERNAME → 400"""
        mock_result = {
            "status": "error",
            "code": "INVALID_USERNAME",
            "message": "Invalid username",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 400

    def test_list_cron_jobs_error_forbidden_user(self, test_client, auth_headers):
        """エラーコード FORBIDDEN_USER → 403"""
        mock_result = {
            "status": "error",
            "code": "FORBIDDEN_USER",
            "message": "Forbidden user",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 403

    def test_list_cron_jobs_error_user_not_found(self, test_client, auth_headers):
        """エラーコード USER_NOT_FOUND → 404"""
        mock_result = {
            "status": "error",
            "code": "USER_NOT_FOUND",
            "message": "User not found",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 404

    def test_list_cron_jobs_error_unknown(self, test_client, auth_headers):
        """不明なエラーコード → 500"""
        mock_result = {
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Something wrong",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 500

    def test_list_cron_jobs_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/cron/testuser", headers=auth_headers)

        assert response.status_code == 500

    def test_list_cron_jobs_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/cron/testuser")
        assert response.status_code == 403


class TestAddCronJob:
    """POST /api/cron/{username} テスト"""

    def test_add_cron_job_success(self, test_client, admin_headers):
        """正常系: Cronジョブ追加"""
        mock_result = {
            "status": "success",
            "message": "Cron job added",
            "total_jobs": 1,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": "/data /backup",
                    "comment": "Daily backup",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_add_cron_job_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        response = test_client.post(
            "/api/cron/bad%3Buser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_add_cron_job_schedule_forbidden_chars(self, test_client, admin_headers):
        """スケジュール禁止文字 → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *; rm -rf /",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_schedule_not_5_fields(self, test_client, admin_headers):
        """スケジュール5フィールドでない → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 *",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_schedule_every_minute(self, test_client, admin_headers):
        """スケジュール毎分実行 → 422 (最小 */5)"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "* * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_schedule_too_frequent(self, test_client, admin_headers):
        """スケジュール間隔短すぎ (*/3) → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/3 * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_schedule_invalid_chars(self, test_client, admin_headers):
        """スケジュールフィールド不正文字 → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 abc * *",
                "command": "/usr/bin/rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_command_forbidden_chars(self, test_client, admin_headers):
        """コマンド禁止文字 → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync; rm -rf /",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_command_not_absolute(self, test_client, admin_headers):
        """コマンド相対パス → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "rsync",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_command_forbidden(self, test_client, admin_headers):
        """FORBIDDEN_CRON_COMMANDS → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/bin/bash",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_command_not_in_allowlist(self, test_client, admin_headers):
        """allowlist外のコマンド → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/unknown_command",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_arguments_forbidden_chars(self, test_client, admin_headers):
        """引数禁止文字 → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
                "arguments": "--delete; rm -rf /",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_arguments_path_traversal(self, test_client, admin_headers):
        """引数パストラバーサル → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
                "arguments": "../../../etc/passwd",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_comment_forbidden_chars(self, test_client, admin_headers):
        """コメント禁止文字 → 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
                "comment": "backup; malicious",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_add_cron_job_error_forbidden_command(self, test_client, admin_headers):
        """エラーコード FORBIDDEN_COMMAND → 403"""
        mock_result = {
            "status": "error",
            "code": "FORBIDDEN_COMMAND",
            "message": "Command forbidden",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 403

    def test_add_cron_job_error_user_not_found(self, test_client, admin_headers):
        """エラーコード USER_NOT_FOUND → 404"""
        mock_result = {
            "status": "error",
            "code": "USER_NOT_FOUND",
            "message": "User not found",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 404

    def test_add_cron_job_error_max_jobs(self, test_client, admin_headers):
        """エラーコード MAX_JOBS_EXCEEDED → 409"""
        mock_result = {
            "status": "error",
            "code": "MAX_JOBS_EXCEEDED",
            "message": "Maximum jobs exceeded",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 409

    def test_add_cron_job_error_invalid_args(self, test_client, admin_headers):
        """エラーコード INVALID_ARGS → 400"""
        mock_result = {
            "status": "error",
            "code": "INVALID_ARGS",
            "message": "Invalid arguments",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_add_cron_job_error_unknown(self, test_client, admin_headers):
        """不明なエラーコード → 500"""
        mock_result = {
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Something failed",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = mock_result
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_add_cron_job_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestRemoveCronJob:
    """DELETE /api/cron/{username} テスト"""

    def test_remove_cron_job_success(self, test_client, admin_headers):
        """正常系: Cronジョブ削除"""
        mock_result = {
            "status": "success",
            "message": "Cron job disabled",
            "remaining_jobs": 2,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = mock_result
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 3},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_remove_cron_job_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        response = test_client.request(
            "DELETE",
            "/api/cron/bad%3Buser",
            json={"line_number": 1},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_remove_cron_job_error_invalid_line(self, test_client, admin_headers):
        """エラーコード INVALID_LINE_NUMBER → 400"""
        mock_result = {
            "status": "error",
            "code": "INVALID_LINE_NUMBER",
            "message": "Invalid line number",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = mock_result
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_remove_cron_job_error_forbidden_user(self, test_client, admin_headers):
        """エラーコード FORBIDDEN_USER → 403"""
        mock_result = {
            "status": "error",
            "code": "FORBIDDEN_USER",
            "message": "Forbidden user",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = mock_result
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )

        assert response.status_code == 403

    def test_remove_cron_job_error_line_not_found(self, test_client, admin_headers):
        """エラーコード LINE_NOT_FOUND → 404"""
        mock_result = {
            "status": "error",
            "code": "LINE_NOT_FOUND",
            "message": "Line not found",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = mock_result
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 999},
                headers=admin_headers,
            )

        assert response.status_code == 404

    def test_remove_cron_job_error_unknown(self, test_client, admin_headers):
        """不明なエラーコード → 500"""
        mock_result = {
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Something failed",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = mock_result
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_remove_cron_job_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.side_effect = SudoWrapperError("Failed")
            response = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )

        assert response.status_code == 500


class TestToggleCronJob:
    """PUT /api/cron/{username}/toggle テスト"""

    def test_toggle_enable_success(self, test_client, admin_headers):
        """正常系: Cronジョブ有効化"""
        mock_result = {
            "status": "success",
            "message": "Cron job enabled",
            "active_jobs": 3,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_toggle_disable_success(self, test_client, admin_headers):
        """正常系: Cronジョブ無効化"""
        mock_result = {
            "status": "success",
            "message": "Cron job disabled",
            "active_jobs": 2,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": False},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_toggle_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        response = test_client.put(
            "/api/cron/bad%3Buser/toggle",
            json={"line_number": 1, "enabled": True},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_toggle_error_already_enabled(self, test_client, admin_headers):
        """エラーコード ALREADY_ENABLED → 400"""
        mock_result = {
            "status": "error",
            "code": "ALREADY_ENABLED",
            "message": "Already enabled",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_toggle_error_forbidden_user(self, test_client, admin_headers):
        """エラーコード FORBIDDEN_USER → 403"""
        mock_result = {
            "status": "error",
            "code": "FORBIDDEN_USER",
            "message": "Forbidden user",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 403

    def test_toggle_error_command_not_allowed(self, test_client, admin_headers):
        """エラーコード COMMAND_NOT_ALLOWED → 403"""
        mock_result = {
            "status": "error",
            "code": "COMMAND_NOT_ALLOWED",
            "message": "Command not allowed",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 403

    def test_toggle_error_user_not_found(self, test_client, admin_headers):
        """エラーコード USER_NOT_FOUND → 404"""
        mock_result = {
            "status": "error",
            "code": "USER_NOT_FOUND",
            "message": "User not found",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 404

    def test_toggle_error_max_jobs(self, test_client, admin_headers):
        """エラーコード MAX_JOBS_EXCEEDED → 409"""
        mock_result = {
            "status": "error",
            "code": "MAX_JOBS_EXCEEDED",
            "message": "Max jobs exceeded",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 409

    def test_toggle_error_unknown(self, test_client, admin_headers):
        """不明なエラーコード → 500"""
        mock_result = {
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Something failed",
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = mock_result
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_toggle_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.side_effect = SudoWrapperError("Failed")
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )

        assert response.status_code == 500
