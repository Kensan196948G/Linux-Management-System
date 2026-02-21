"""
Cron ジョブ管理 API の統合テスト

認証・認可・入力バリデーションを中心にテスト
（sudo ラッパーは実環境不要のため、500 も正常として許容する）
"""

import pytest


class TestCronListEndpoint:
    """GET /api/cron/{username} - Cron ジョブ一覧取得"""

    def test_list_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/cron/testuser")
        assert response.status_code == 403

    def test_list_viewer_has_read_cron_permission(self, test_client, viewer_headers):
        """viewer ロールは read:cron 権限を持つこと"""
        response = test_client.get("/api/cron/testuser", headers=viewer_headers)
        # sudo が使えない環境では 500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_list_operator_has_read_cron_permission(self, test_client, auth_headers):
        """operator ロールは read:cron 権限を持つこと"""
        response = test_client.get("/api/cron/testuser", headers=auth_headers)
        assert response.status_code != 403

    def test_list_invalid_username_special_chars(self, test_client, auth_headers):
        """特殊文字を含むユーザー名は 422 を返すこと"""
        # FastAPI のルートパスには ; が使えないためURLエンコードなしで送る
        response = test_client.get("/api/cron/test;user", headers=auth_headers)
        assert response.status_code in [400, 422]

    def test_list_username_injection_attempt(self, test_client, auth_headers):
        """インジェクション文字を含むユーザー名は拒否されること"""
        response = test_client.get("/api/cron/test%7Cuser", headers=auth_headers)
        # URL デコード後にバリデーションがかかる
        assert response.status_code in [400, 422]

    def test_list_system_user_forbidden(self, test_client, auth_headers):
        """root ユーザーは 403 を返すこと"""
        response = test_client.get("/api/cron/root", headers=auth_headers)
        assert response.status_code in [400, 403]


class TestCronAddEndpoint:
    """POST /api/cron/{username} - Cron ジョブ追加"""

    def test_add_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
            },
        )
        assert response.status_code == 403

    def test_add_viewer_lacks_write_cron(self, test_client, viewer_headers):
        """viewer ロールは write:cron 権限がないこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
            },
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_add_operator_has_write_cron(self, test_client, auth_headers):
        """operator ロールは write:cron 権限を持つこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
                "arguments": "/src/ /dst/",
                "comment": "Daily backup",
            },
            headers=auth_headers,
        )
        # sudo が使えない環境では 400/404/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_add_forbidden_command_rejected(self, test_client, auth_headers):
        """禁止コマンドは 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/bin/bash",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_command_not_in_allowlist(self, test_client, auth_headers):
        """allowlist 外のコマンドは 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/evil-command",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_relative_path_rejected(self, test_client, auth_headers):
        """相対パスのコマンドは 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_schedule_too_frequent(self, test_client, auth_headers):
        """1分間隔は 422 を返すこと（最小間隔 */5）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "* * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_schedule_too_frequent_4min(self, test_client, auth_headers):
        """*/4 間隔は 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/4 * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_schedule_5min_accepted(self, test_client, auth_headers):
        """*/5 間隔は受け付けること（実行は sudo に依存）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        # バリデーションは通過（sudo が使えない環境では 4xx/500 になる場合がある）
        assert response.status_code != 422

    def test_add_schedule_with_injection_chars(self, test_client, auth_headers):
        """スケジュールへのインジェクション文字は 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *; rm -rf /",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_arguments_with_injection_chars(self, test_client, auth_headers):
        """引数へのインジェクション文字は 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
                "arguments": "/src/; rm -rf /",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_missing_required_fields(self, test_client, auth_headers):
        """必須フィールドなしは 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={"schedule": "0 2 * * *"},  # command が欠如
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_add_invalid_schedule_format(self, test_client, auth_headers):
        """不正なスケジュール形式は 422 を返すこと"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "not-a-cron-expression",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestCronDeleteEndpoint:
    """DELETE /api/cron/{username} - Cron ジョブ削除"""

    def test_delete_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.delete(
            "/api/cron/testuser",
            params={"line_number": "1"},
        )
        assert response.status_code == 403

    def test_delete_viewer_lacks_write_cron(self, test_client, viewer_headers):
        """viewer ロールは write:cron 権限がないこと"""
        response = test_client.delete(
            "/api/cron/testuser",
            params={"line_number": "1"},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_delete_operator_has_write_cron(self, test_client, auth_headers):
        """operator ロールは write:cron 権限を持つこと"""
        response = test_client.delete(
            "/api/cron/testuser",
            params={"line_number": "1"},
            headers=auth_headers,
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_delete_negative_line_number(self, test_client, auth_headers):
        """負のライン番号は 422 を返すこと"""
        response = test_client.delete(
            "/api/cron/testuser",
            params={"line_number": "-1"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_delete_zero_line_number(self, test_client, auth_headers):
        """ライン番号 0 は 422 を返すこと"""
        response = test_client.delete(
            "/api/cron/testuser",
            params={"line_number": "0"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestCronToggleEndpoint:
    """PUT /api/cron/{username}/toggle - Cron ジョブ有効/無効切替"""

    def test_toggle_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.put(
            "/api/cron/testuser/toggle",
            json={"line_number": 1, "enable": True},
        )
        assert response.status_code == 403

    def test_toggle_viewer_lacks_write_cron(self, test_client, viewer_headers):
        """viewer ロールは write:cron 権限がないこと"""
        response = test_client.put(
            "/api/cron/testuser/toggle",
            json={"line_number": 1, "enable": True},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_toggle_operator_has_write_cron(self, test_client, auth_headers):
        """operator ロールは write:cron 権限を持つこと"""
        response = test_client.put(
            "/api/cron/testuser/toggle",
            json={"line_number": 1, "enable": False},
            headers=auth_headers,
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_toggle_missing_line_number(self, test_client, auth_headers):
        """line_number なしは 422 を返すこと"""
        response = test_client.put(
            "/api/cron/testuser/toggle",
            json={"enable": True},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestCronSecurityPrinciples:
    """Cron ジョブ API のセキュリティ原則確認"""

    def test_allowlist_command_structure(self):
        """allowlist に定義されたコマンドは絶対パスであること"""
        from backend.api.routes.cron import ALLOWED_CRON_COMMANDS

        for cmd in ALLOWED_CRON_COMMANDS:
            assert cmd.startswith("/"), f"Command must be absolute path: {cmd}"

    def test_forbidden_commands_include_shells(self):
        """シェルコマンドは禁止リストに含まれること"""
        from backend.api.routes.cron import FORBIDDEN_CRON_COMMANDS

        shell_commands = ["/bin/bash", "/bin/sh", "/bin/zsh"]
        for shell in shell_commands:
            assert shell in FORBIDDEN_CRON_COMMANDS, f"Shell {shell} must be forbidden"

    def test_forbidden_commands_include_rm(self):
        """/bin/rm は禁止リストに含まれること"""
        from backend.api.routes.cron import FORBIDDEN_CRON_COMMANDS

        assert "/bin/rm" in FORBIDDEN_CRON_COMMANDS
        assert "/usr/bin/rm" in FORBIDDEN_CRON_COMMANDS

    def test_forbidden_commands_include_sudo(self):
        """/usr/bin/sudo は禁止リストに含まれること"""
        from backend.api.routes.cron import FORBIDDEN_CRON_COMMANDS

        assert "/usr/bin/sudo" in FORBIDDEN_CRON_COMMANDS

    def test_max_jobs_per_user_limit(self):
        """ユーザーあたり最大ジョブ数が設定されていること"""
        from backend.api.routes.cron import MAX_CRON_JOBS_PER_USER

        assert MAX_CRON_JOBS_PER_USER > 0
        assert MAX_CRON_JOBS_PER_USER <= 20  # 合理的な上限

    def test_forbidden_argument_chars_include_injection_chars(self):
        """引数の禁止文字リストにインジェクション文字が含まれること"""
        from backend.api.routes.cron import FORBIDDEN_ARGUMENT_CHARS

        critical_chars = [";", "|", "&", "$", "`"]
        for char in critical_chars:
            assert char in FORBIDDEN_ARGUMENT_CHARS, f"Char {char!r} must be forbidden in arguments"


class TestCronValidatorEdgeCases:
    """Pydantic バリデータの境界値テスト（未カバー行 172, 206, 227, 236, 245, 250）"""

    def test_schedule_invalid_field_chars(self, test_client, auth_headers):
        """スケジュールフィールドに無効文字（アルファベット）が含まれる場合は 422"""
        # line 172: field_pattern.match が失敗するケース
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0a 2 * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_schedule_invalid_field_chars_with_letter(self, test_client, auth_headers):
        """スケジュールの時間フィールドに文字が含まれる場合は 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "5 X * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_command_with_forbidden_char_pipe(self, test_client, auth_headers):
        """コマンドにパイプ文字を含む場合は 422（line 206）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync|evil",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_command_with_forbidden_char_dollar(self, test_client, auth_headers):
        """コマンドに $ を含む場合は 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/$evil",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_arguments_with_path_traversal(self, test_client, auth_headers):
        """引数に .. を含む場合（パストラバーサル）は 422（line 236）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync",
                "arguments": "/safe/../../../etc/passwd",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_arguments_with_forbidden_char_backtick(self, test_client, auth_headers):
        """引数にバッククォートを含む場合は 422（line 227）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync",
                "arguments": "/src/`evil`/",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_comment_with_forbidden_char_semicolon(self, test_client, auth_headers):
        """コメントにセミコロンを含む場合は 422（line 245, 250）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync",
                "comment": "Daily backup; rm -rf /",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_comment_with_forbidden_char_pipe(self, test_client, auth_headers):
        """コメントにパイプを含む場合は 422"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/5 * * * *",
                "command": "/usr/bin/rsync",
                "comment": "backup | evil",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_arguments_explicit_null_is_valid(self, test_client, auth_headers):
        """arguments を明示的に null で送るとバリデーターの None 分岐を通過すること（line 227）"""
        # Pydantic v2: field_validator は明示的な null 値で呼ばれる（デフォルト値では呼ばれない）
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job added",
                "line_number": 1,
                "active_jobs": 1,
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "*/5 * * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": None,
                    "comment": None,
                },
                headers=auth_headers,
            )
        # バリデーションエラーにならないこと（line 227: if v is None: return v）
        assert response.status_code != 422

    def test_comment_explicit_null_is_valid(self, test_client, auth_headers):
        """comment を明示的に null で送るとバリデーターの None 分岐を通過すること（line 245）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job added",
                "line_number": 2,
                "active_jobs": 1,
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 3 * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": "/backup/",
                    "comment": None,
                },
                headers=auth_headers,
            )
        assert response.status_code != 422

    def test_schedule_interval_2_rejected(self, test_client, auth_headers):
        """*/2 間隔は拒否されること（line 178-179）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/2 * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_schedule_interval_1_rejected(self, test_client, auth_headers):
        """*/1 間隔は拒否されること"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "*/1 * * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_schedule_wrong_field_count(self, test_client, auth_headers):
        """フィールド数が5以外の場合は 422（line 163-164）"""
        response = test_client.post(
            "/api/cron/testuser",
            json={
                "schedule": "0 2 * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestCronListMocked:
    """GET /api/cron/{username} - モックを使ったエラーパステスト（line 350, 365-397）"""

    def test_list_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError が発生した場合は 500 を返すこと（line 387-397）"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.side_effect = SudoWrapperError("Connection failed")
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 500
            assert "Cron job list retrieval failed" in response.json()["message"]

    def test_list_error_invalid_username(self, test_client, auth_headers):
        """ラッパーが INVALID_USERNAME を返した場合は 400（line 350）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Invalid username",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 400

    def test_list_error_invalid_args(self, test_client, auth_headers):
        """ラッパーが INVALID_ARGS を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_ARGS",
                "message": "Invalid arguments",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 400

    def test_list_error_forbidden_user(self, test_client, auth_headers):
        """ラッパーが FORBIDDEN_USER を返した場合は 403（line 365-371）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "FORBIDDEN_USER",
                "message": "Access denied",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 403

    def test_list_error_forbidden_chars(self, test_client, auth_headers):
        """ラッパーが FORBIDDEN_CHARS を返した場合は 403"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "FORBIDDEN_CHARS",
                "message": "Forbidden characters detected",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 403

    def test_list_error_user_not_found(self, test_client, auth_headers):
        """ラッパーが USER_NOT_FOUND を返した場合は 404（line 372-378）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 404

    def test_list_error_unknown_code(self, test_client, auth_headers):
        """ラッパーが未知のエラーコードを返した場合は 500（line 379-384）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "UNKNOWN_ERROR_CODE",
                "message": "Something went wrong",
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 500

    def test_list_success(self, test_client, auth_headers):
        """正常にジョブ一覧を返すこと（line 365-384）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "user": "testuser",
                "jobs": [],
                "total_count": 0,
                "max_allowed": 10,
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"] == "testuser"
            assert data["total_count"] == 0

    def test_list_success_with_jobs(self, test_client, auth_headers):
        """ジョブがある場合も正常に返すこと"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.list_cron_jobs") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "user": "testuser",
                "jobs": [
                    {
                        "id": "job-001",
                        "line_number": 1,
                        "schedule": "0 2 * * *",
                        "command": "/usr/bin/rsync",
                        "arguments": "/src/ /dst/",
                        "comment": "Daily backup",
                        "enabled": True,
                    }
                ],
                "total_count": 1,
                "max_allowed": 10,
            }
            response = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 1
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["command"] == "/usr/bin/rsync"

    def test_list_invalid_username_validation_error(self, test_client, auth_headers):
        """ユーザー名バリデーションエラー（validate_usernameが例外を投げる場合）"""
        # root は validate_username で拒否される
        response = test_client.get("/api/cron/root", headers=auth_headers)
        assert response.status_code in [400, 403]


class TestCronAddMocked:
    """POST /api/cron/{username} - モックを使ったエラーパステスト（line 426-543）"""

    def test_add_invalid_username_raises_400(self, test_client, auth_headers):
        """ユーザー名バリデーション失敗時に 400（line 426-427）"""
        # 1baduser は数字始まりで validate_username が ValidationError を投げる
        response = test_client.post(
            "/api/cron/1baduser",
            json={
                "schedule": "0 2 * * *",
                "command": "/usr/bin/rsync",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_add_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError が発生した場合は 500（line 533-543）"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.side_effect = SudoWrapperError("Wrapper script not found")
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 500
            assert "Cron job addition failed" in response.json()["message"]

    def test_add_error_invalid_username_code(self, test_client, auth_headers):
        """ラッパーが INVALID_USERNAME を返した場合は 400（line 481）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Invalid username",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_add_error_invalid_schedule_code(self, test_client, auth_headers):
        """ラッパーが INVALID_SCHEDULE を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_SCHEDULE",
                "message": "Invalid schedule format",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_add_error_invalid_command_code(self, test_client, auth_headers):
        """ラッパーが INVALID_COMMAND を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_COMMAND",
                "message": "Invalid command",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_add_error_path_traversal_code(self, test_client, auth_headers):
        """ラッパーが PATH_TRAVERSAL を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "PATH_TRAVERSAL",
                "message": "Path traversal detected",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_add_error_forbidden_command_code(self, test_client, auth_headers):
        """ラッパーが FORBIDDEN_COMMAND を返した場合は 403（line 491）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "FORBIDDEN_COMMAND",
                "message": "Command is forbidden",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 403

    def test_add_error_command_not_allowed_code(self, test_client, auth_headers):
        """ラッパーが COMMAND_NOT_ALLOWED を返した場合は 403"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "COMMAND_NOT_ALLOWED",
                "message": "Command not in allowlist",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 403

    def test_add_error_user_not_found_code(self, test_client, auth_headers):
        """ラッパーが USER_NOT_FOUND を返した場合は 404（line 500）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_add_error_max_jobs_exceeded(self, test_client, auth_headers):
        """ラッパーが MAX_JOBS_EXCEEDED を返した場合は 409（line 500-504）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "MAX_JOBS_EXCEEDED",
                "message": "Maximum job limit reached",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 409

    def test_add_error_duplicate_job(self, test_client, auth_headers):
        """ラッパーが DUPLICATE_JOB を返した場合は 409"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "DUPLICATE_JOB",
                "message": "Duplicate job detected",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 409

    def test_add_error_unknown_code(self, test_client, auth_headers):
        """ラッパーが未知のエラーコードを返した場合は 500（line 505-509）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "SOME_UNKNOWN_ERROR",
                "message": "Unknown error occurred",
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert response.status_code == 500

    def test_add_success(self, test_client, auth_headers):
        """正常にジョブを追加できること（line 511-530）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job added",
                "total_jobs": 1,
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": "/backup/",
                    "comment": "Daily backup",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"] == "testuser"

    def test_add_success_with_comment_only(self, test_client, auth_headers):
        """コメントのみ指定してジョブを追加できること"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.add_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job added successfully",
                "total_jobs": 1,
            }
            response = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 3 * * 0",
                    "command": "/usr/bin/rsync",
                    "comment": "Weekly backup",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200


class TestCronRemoveMocked:
    """DELETE /api/cron/{username} - モックを使ったテスト（line 570-671）"""

    def _delete(self, test_client, url, line_number, headers):
        """DELETE リクエストをリクエストボディ付きで送信するヘルパー"""
        import json as json_mod
        return test_client.request(
            "DELETE",
            url,
            content=json_mod.dumps({"line_number": line_number}),
            headers={**headers, "Content-Type": "application/json"},
        )

    def test_remove_invalid_username_raises_400(self, test_client, auth_headers):
        """数字始まりユーザー名は ValidationError → 400（line 572-573）"""
        # 1baduser は validate_username が ValidationError を投げる
        response = self._delete(test_client, "/api/cron/1baduser", 1, auth_headers)
        assert response.status_code == 400

    def test_remove_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError が発生した場合は 500（line 660-674）"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.side_effect = SudoWrapperError("Execution failed")
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 500
            assert "Cron job removal failed" in response.json()["message"]

    def test_remove_error_invalid_username_code(self, test_client, auth_headers):
        """ラッパーが INVALID_USERNAME を返した場合は 400（line 611-621）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Invalid username",
            }
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 400

    def test_remove_error_invalid_line_number_code(self, test_client, auth_headers):
        """ラッパーが INVALID_LINE_NUMBER を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_LINE_NUMBER",
                "message": "Line number out of range",
            }
            response = self._delete(test_client, "/api/cron/testuser", 5, auth_headers)
            assert response.status_code == 400

    def test_remove_error_not_a_job_code(self, test_client, auth_headers):
        """ラッパーが NOT_A_JOB を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "NOT_A_JOB",
                "message": "Line is not a cron job",
            }
            response = self._delete(test_client, "/api/cron/testuser", 3, auth_headers)
            assert response.status_code == 400

    def test_remove_error_already_disabled_code(self, test_client, auth_headers):
        """ラッパーが ALREADY_DISABLED を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "ALREADY_DISABLED",
                "message": "Job already disabled",
            }
            response = self._delete(test_client, "/api/cron/testuser", 2, auth_headers)
            assert response.status_code == 400

    def test_remove_error_forbidden_user_code(self, test_client, auth_headers):
        """ラッパーが FORBIDDEN_USER を返した場合は 403（line 622-625）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "FORBIDDEN_USER",
                "message": "Access denied",
            }
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 403

    def test_remove_error_user_not_found_code(self, test_client, auth_headers):
        """ラッパーが USER_NOT_FOUND を返した場合は 404（line 627-630）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 404

    def test_remove_error_line_not_found_code(self, test_client, auth_headers):
        """ラッパーが LINE_NOT_FOUND を返した場合は 404"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "LINE_NOT_FOUND",
                "message": "Line not found",
            }
            response = self._delete(test_client, "/api/cron/testuser", 99, auth_headers)
            assert response.status_code == 404

    def test_remove_error_unknown_code(self, test_client, auth_headers):
        """ラッパーが未知のエラーコードを返した場合は 500（line 631-636）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "UNEXPECTED_ERROR",
                "message": "Something went wrong",
            }
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 500

    def test_remove_success(self, test_client, auth_headers):
        """正常にジョブを削除できること（line 638-658）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.remove_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job disabled (commented out)",
                "remaining_jobs": 0,
            }
            response = self._delete(test_client, "/api/cron/testuser", 1, auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"] == "testuser"


class TestCronToggleMocked:
    """PUT /api/cron/{username}/toggle - モックを使ったテスト（line 698-822）"""

    def test_toggle_invalid_username_raises_400(self, test_client, auth_headers):
        """数字始まりユーザー名は ValidationError → 400（line 700-701）"""
        # 1baduser は validate_username が ValidationError を投げる
        response = test_client.put(
            "/api/cron/1baduser/toggle",
            json={"line_number": 1, "enabled": True},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_toggle_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError が発生した場合は 500（line 811-825）"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.side_effect = SudoWrapperError("Toggle failed")
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 500
            assert "Cron job toggle failed" in response.json()["message"]

    def test_toggle_error_invalid_username_code(self, test_client, auth_headers):
        """ラッパーが INVALID_USERNAME を返した場合は 400（line 746-761）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Invalid username",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_invalid_action_code(self, test_client, auth_headers):
        """ラッパーが INVALID_ACTION を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_ACTION",
                "message": "Invalid action",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": False},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_already_disabled_code(self, test_client, auth_headers):
        """ラッパーが ALREADY_DISABLED を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "ALREADY_DISABLED",
                "message": "Job already disabled",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": False},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_already_enabled_code(self, test_client, auth_headers):
        """ラッパーが ALREADY_ENABLED を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "ALREADY_ENABLED",
                "message": "Job already enabled",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_not_adminui_comment_code(self, test_client, auth_headers):
        """ラッパーが NOT_ADMINUI_COMMENT を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "NOT_ADMINUI_COMMENT",
                "message": "Not an adminui comment",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 2, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_parse_error_code(self, test_client, auth_headers):
        """ラッパーが PARSE_ERROR を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "PARSE_ERROR",
                "message": "Failed to parse crontab",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 3, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 400

    def test_toggle_error_forbidden_user_code(self, test_client, auth_headers):
        """ラッパーが FORBIDDEN_USER を返した場合は 403（line 762-770）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "FORBIDDEN_USER",
                "message": "Access denied",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 403

    def test_toggle_error_command_not_allowed_code(self, test_client, auth_headers):
        """ラッパーが COMMAND_NOT_ALLOWED を返した場合は 403"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "COMMAND_NOT_ALLOWED",
                "message": "Command not allowed",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 403

    def test_toggle_error_user_not_found_code(self, test_client, auth_headers):
        """ラッパーが USER_NOT_FOUND を返した場合は 404（line 771-774）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_toggle_error_line_not_found_code(self, test_client, auth_headers):
        """ラッパーが LINE_NOT_FOUND を返した場合は 404"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "LINE_NOT_FOUND",
                "message": "Line not found in crontab",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 50, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_toggle_error_max_jobs_exceeded_code(self, test_client, auth_headers):
        """ラッパーが MAX_JOBS_EXCEEDED を返した場合は 409（line 776-780）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "MAX_JOBS_EXCEEDED",
                "message": "Maximum job limit reached",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 409

    def test_toggle_error_unknown_code(self, test_client, auth_headers):
        """ラッパーが未知のエラーコードを返した場合は 500（line 781-785）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "TOTALLY_UNEXPECTED",
                "message": "Something went wrong",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 500

    def test_toggle_enable_success(self, test_client, auth_headers):
        """正常に有効化できること（line 787-809）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job enabled",
                "active_jobs": 1,
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["user"] == "testuser"

    def test_toggle_disable_success(self, test_client, auth_headers):
        """正常に無効化できること"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job disabled",
                "active_jobs": 0,
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 2, "enabled": False},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"

    def test_toggle_enable_calls_sudo_with_enable_action(self, test_client, auth_headers):
        """enabled=True の場合 action='enable' で sudo が呼ばれること（line 706）"""
        from unittest.mock import patch, call

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job enabled",
                "active_jobs": 1,
            }
            test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 3, "enabled": True},
                headers=auth_headers,
            )
            mock_exec.assert_called_once_with(
                username="testuser",
                line_number=3,
                action="enable",
            )

    def test_toggle_disable_calls_sudo_with_disable_action(self, test_client, auth_headers):
        """enabled=False の場合 action='disable' で sudo が呼ばれること（line 706）"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "success",
                "message": "Cron job disabled",
                "active_jobs": 0,
            }
            test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 4, "enabled": False},
                headers=auth_headers,
            )
            mock_exec.assert_called_once_with(
                username="testuser",
                line_number=4,
                action="disable",
            )

    def test_toggle_missing_enabled_field_returns_422(self, test_client, auth_headers):
        """enabled フィールドが欠如した場合は 422"""
        response = test_client.put(
            "/api/cron/testuser/toggle",
            json={"line_number": 1},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_toggle_invalid_schedule_code(self, test_client, auth_headers):
        """ラッパーが INVALID_SCHEDULE を返した場合は 400"""
        from unittest.mock import patch

        with patch("backend.api.routes.cron.sudo_wrapper.toggle_cron_job") as mock_exec:
            mock_exec.return_value = {
                "status": "error",
                "code": "INVALID_SCHEDULE",
                "message": "Invalid schedule in crontab",
            }
            response = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=auth_headers,
            )
            assert response.status_code == 400
