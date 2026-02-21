"""
ユーザー・グループ管理 API の統合テスト

認証・認可・入力バリデーションを中心にテスト
（sudo ラッパーは実環境不要のため、500 も正常として許容する）
"""

import pytest


class TestUserListEndpoint:
    """GET /api/users - ユーザー一覧取得"""

    def test_list_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users")
        assert response.status_code == 403

    def test_list_viewer_has_read_users_permission(self, test_client, viewer_headers):
        """viewer ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users", headers=viewer_headers)
        # sudo が使えない環境では 500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_list_operator_has_read_users_permission(self, test_client, auth_headers):
        """operator ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users", headers=auth_headers)
        assert response.status_code != 403

    def test_list_invalid_sort_key(self, test_client, auth_headers):
        """無効なソートキーは 422 を返すこと"""
        response = test_client.get(
            "/api/users",
            params={"sort_by": "invalid_key"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_valid_sort_keys(self, test_client, auth_headers):
        """有効なソートキーは受け付けること"""
        for sort_key in ["username", "uid", "last_login"]:
            response = test_client.get(
                "/api/users",
                params={"sort_by": sort_key},
                headers=auth_headers,
            )
            # バリデーションは通過（sudo 不可環境では 500 になる場合がある）
            assert response.status_code != 422, f"sort_by={sort_key} should be accepted"

    def test_list_invalid_filter_locked(self, test_client, auth_headers):
        """無効な filter_locked は 422 を返すこと"""
        response = test_client.get(
            "/api/users",
            params={"filter_locked": "maybe"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_limit_too_large(self, test_client, auth_headers):
        """上限超えの limit は 422 を返すこと"""
        response = test_client.get(
            "/api/users",
            params={"limit": 501},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_limit_zero(self, test_client, auth_headers):
        """limit=0 は 422 を返すこと"""
        response = test_client.get(
            "/api/users",
            params={"limit": 0},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_invalid_username_filter(self, test_client, auth_headers):
        """不正な username_filter は 422 を返すこと"""
        response = test_client.get(
            "/api/users",
            params={"username_filter": "test!user"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestUserDetailEndpoint:
    """GET /api/users/{username} - ユーザー詳細取得"""

    def test_detail_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users/testuser")
        assert response.status_code == 403

    def test_detail_viewer_has_read_permission(self, test_client, viewer_headers):
        """viewer ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users/testuser", headers=viewer_headers)
        # sudo が使えない環境では 404/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_detail_invalid_username_special_chars(self, test_client, auth_headers):
        """特殊文字を含むユーザー名は 400/422 を返すこと"""
        response = test_client.get("/api/users/test%7Cuser", headers=auth_headers)
        assert response.status_code in [400, 422]

    def test_detail_system_user_not_forbidden(self, test_client, auth_headers):
        """root ユーザー詳細取得は認可拒否にはならないこと（形式検証は通過）"""
        response = test_client.get("/api/users/root", headers=auth_headers)
        # root は形式バリデーションを通過し、ラッパー呼び出しへ進む
        # sudo が使えない環境では 404/500 になるが、403 にはならない
        assert response.status_code != 403


class TestCreateUserEndpoint:
    """POST /api/users - ユーザー作成"""

    def test_create_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
            },
        )
        assert response.status_code == 403

    def test_create_viewer_lacks_write_users(self, test_client, viewer_headers):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
            },
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_create_operator_lacks_write_users(self, test_client, auth_headers):
        """operator ロールも write:users 権限がないこと（admin のみ）"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
            },
            headers=auth_headers,
        )
        # operator には write:users がないため 403
        assert response.status_code == 403

    def test_create_admin_has_write_users(self, test_client, admin_headers):
        """admin ロールは write:users 権限を持つこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
                "shell": "/bin/bash",
            },
            headers=admin_headers,
        )
        # sudo が使えない環境では 400/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_create_short_password_rejected(self, test_client, admin_headers):
        """短すぎるパスワードは 422 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "short",  # 8文字未満
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_invalid_username_pattern(self, test_client, admin_headers):
        """不正なユーザー名パターンは 422 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "1startwithnumber",  # 数字始まりは不可
                "password": "SecurePass123!",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_forbidden_username_rejected(self, test_client, admin_headers):
        """禁止ユーザー名（root）は 400 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "root",
                "password": "SecurePass123!",
            },
            headers=admin_headers,
        )
        assert response.status_code in [400, 422]

    def test_create_disallowed_shell_rejected(self, test_client, admin_headers):
        """allowlist 外のシェルは 400 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
                "shell": "/usr/bin/evil-shell",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_create_missing_required_fields(self, test_client, admin_headers):
        """必須フィールドなしは 422 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={"username": "newuser"},  # password が欠如
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_gecos_with_injection_chars(self, test_client, admin_headers):
        """GECOS フィールドのインジェクション文字は 400 を返すこと"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "SecurePass123!",
                "gecos": "Test User; rm -rf /",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400


class TestDeleteUserEndpoint:
    """DELETE /api/users/{username} - ユーザー削除"""

    def test_delete_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.delete("/api/users/testuser")
        assert response.status_code == 403

    def test_delete_viewer_lacks_write_users(self, test_client, viewer_headers):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.delete("/api/users/testuser", headers=viewer_headers)
        assert response.status_code == 403

    def test_delete_operator_lacks_write_users(self, test_client, auth_headers):
        """operator ロールも write:users 権限がないこと"""
        response = test_client.delete("/api/users/testuser", headers=auth_headers)
        assert response.status_code == 403

    def test_delete_admin_has_write_users(self, test_client, admin_headers):
        """admin ロールは write:users 権限を持つこと"""
        response = test_client.delete("/api/users/testuser", headers=admin_headers)
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_delete_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名は 400 を返すこと"""
        response = test_client.delete(
            "/api/users/test%7Cuser",  # URL エンコードされた | 文字
            headers=admin_headers,
        )
        assert response.status_code in [400, 422]


class TestChangePasswordEndpoint:
    """PUT /api/users/{username}/password - パスワード変更"""

    def test_change_password_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "NewSecurePass123!"},
        )
        assert response.status_code == 403

    def test_change_password_viewer_lacks_write_users(self, test_client, viewer_headers):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "NewSecurePass123!"},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_change_password_operator_lacks_write_users(self, test_client, auth_headers):
        """operator ロールも write:users 権限がないこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "NewSecurePass123!"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_change_password_admin_has_write_users(self, test_client, admin_headers):
        """admin ロールは write:users 権限を持つこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "NewSecurePass123!"},
            headers=admin_headers,
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_change_password_too_short(self, test_client, admin_headers):
        """短すぎるパスワードは 422 を返すこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "short"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_change_password_missing_field(self, test_client, admin_headers):
        """必須フィールドなしは 422 を返すこと"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestGroupListEndpoint:
    """GET /api/users/groups/list - グループ一覧取得"""

    def test_list_groups_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users/groups/list")
        assert response.status_code == 403

    def test_list_groups_viewer_has_read_permission(self, test_client, viewer_headers):
        """viewer ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users/groups/list", headers=viewer_headers)
        # sudo が使えない環境では 500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_list_groups_invalid_sort_key(self, test_client, auth_headers):
        """無効なソートキーは 422 を返すこと"""
        response = test_client.get(
            "/api/users/groups/list",
            params={"sort_by": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_groups_valid_sort_keys(self, test_client, auth_headers):
        """有効なソートキーは受け付けること"""
        for sort_key in ["name", "gid", "member_count"]:
            response = test_client.get(
                "/api/users/groups/list",
                params={"sort_by": sort_key},
                headers=auth_headers,
            )
            assert response.status_code != 422, f"sort_by={sort_key} should be accepted"


class TestCreateGroupEndpoint:
    """POST /api/users/groups - グループ作成"""

    def test_create_group_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "newgroup"},
        )
        assert response.status_code == 403

    def test_create_group_viewer_lacks_write_users(self, test_client, viewer_headers):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "newgroup"},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_create_group_operator_lacks_write_users(self, test_client, auth_headers):
        """operator ロールも write:users 権限がないこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "newgroup"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_create_group_admin_has_write_users(self, test_client, admin_headers):
        """admin ロールは write:users 権限を持つこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "newgroup"},
            headers=admin_headers,
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403

    def test_create_group_forbidden_name(self, test_client, admin_headers):
        """禁止グループ名（root）は 400 を返すこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "root"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_create_group_invalid_name_pattern(self, test_client, admin_headers):
        """不正なグループ名パターンは 422 を返すこと"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "1invalid"},  # 数字始まりは不可
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_group_missing_name(self, test_client, admin_headers):
        """必須フィールドなしは 422 を返すこと"""
        response = test_client.post(
            "/api/users/groups",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestDeleteGroupEndpoint:
    """DELETE /api/users/groups/{name} - グループ削除"""

    def test_delete_group_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.delete("/api/users/groups/testgroup")
        assert response.status_code == 403

    def test_delete_group_viewer_lacks_write_users(self, test_client, viewer_headers):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.delete(
            "/api/users/groups/testgroup", headers=viewer_headers
        )
        assert response.status_code == 403

    def test_delete_group_admin_has_write_users(self, test_client, admin_headers):
        """admin ロールは write:users 権限を持つこと"""
        response = test_client.delete(
            "/api/users/groups/testgroup", headers=admin_headers
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403 にはならない
        assert response.status_code != 403


class TestModifyGroupMembershipEndpoint:
    """PUT /api/users/groups/{name}/members - グループメンバー変更"""

    def test_modify_membership_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "add", "user": "testuser"},
        )
        assert response.status_code == 403

    def test_modify_membership_viewer_lacks_write_users(
        self, test_client, viewer_headers
    ):
        """viewer ロールは write:users 権限がないこと"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "add", "user": "testuser"},
            headers=viewer_headers,
        )
        assert response.status_code == 403

    def test_modify_membership_invalid_action(self, test_client, admin_headers):
        """無効な action は 422 を返すこと"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "invalid", "user": "testuser"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_modify_membership_valid_add(self, test_client, admin_headers):
        """action=add は受け付けること"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "add", "user": "testuser"},
            headers=admin_headers,
        )
        # sudo が使えない環境では 4xx/500 になる場合があるが、403/422 にはならない
        assert response.status_code not in [403, 422]

    def test_modify_membership_valid_remove(self, test_client, admin_headers):
        """action=remove は受け付けること"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "remove", "user": "testuser"},
            headers=admin_headers,
        )
        assert response.status_code not in [403, 422]

    def test_modify_membership_missing_fields(self, test_client, admin_headers):
        """必須フィールドなしは 422 を返すこと"""
        response = test_client.put(
            "/api/users/groups/testgroup/members",
            json={"action": "add"},  # user が欠如
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestUsersSecurityPrinciples:
    """ユーザー・グループ管理 API のセキュリティ原則確認"""

    def test_allowed_shells_structure(self):
        """allowlist に定義されたシェルは絶対パスであること"""
        from backend.core.constants import ALLOWED_SHELLS

        for shell in ALLOWED_SHELLS:
            assert shell.startswith("/"), f"Shell must be absolute path: {shell}"

    def test_forbidden_usernames_include_root(self):
        """FORBIDDEN_USERNAMES に root が含まれること"""
        from backend.core.constants import FORBIDDEN_USERNAMES

        assert "root" in FORBIDDEN_USERNAMES

    def test_forbidden_usernames_include_system_accounts(self):
        """FORBIDDEN_USERNAMES にシステムアカウントが含まれること"""
        from backend.core.constants import FORBIDDEN_USERNAMES

        system_accounts = ["bin", "daemon", "nobody", "www-data"]
        for account in system_accounts:
            assert account in FORBIDDEN_USERNAMES, f"System account {account} must be forbidden"

    def test_forbidden_groups_include_root(self):
        """FORBIDDEN_GROUPS に root が含まれること"""
        from backend.core.constants import FORBIDDEN_GROUPS

        assert "root" in FORBIDDEN_GROUPS

    def test_forbidden_groups_include_sudo(self):
        """FORBIDDEN_GROUPS に sudo グループが含まれること"""
        from backend.core.constants import FORBIDDEN_GROUPS

        assert "sudo" in FORBIDDEN_GROUPS

    def test_allowed_shells_include_false(self):
        """/bin/false がシェル allowlist に含まれること（アカウント無効化用）"""
        from backend.core.constants import ALLOWED_SHELLS

        assert "/bin/false" in ALLOWED_SHELLS

    def test_validation_module_rejects_injection_chars(self):
        """バリデーションモジュールがインジェクション文字を拒否すること"""
        from backend.core.validation import ValidationError, validate_no_forbidden_chars

        injection_inputs = [
            "test; rm -rf /",
            "test | cat /etc/passwd",
            "test & malicious",
            "test$(whoami)",
        ]
        for bad_input in injection_inputs:
            try:
                validate_no_forbidden_chars(bad_input, "test_field")
                assert False, f"Should have raised ValidationError for: {bad_input}"
            except ValidationError:
                pass  # 期待通り

    def test_username_validation_rejects_path_traversal(self):
        """ユーザー名バリデーションがパストラバーサルを拒否すること"""
        from backend.core.validation import ValidationError, validate_username

        try:
            validate_username("../../etc/passwd")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass  # 期待通り


class TestUserListWithMocks:
    """GET /api/users - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_list_users_success_path(self, test_client, auth_headers):
        """list_users が成功レスポンスを返すパスを網羅（lines 174-182）"""
        from unittest.mock import patch

        mock_result = {
            "status": "success",
            "total_users": 2,
            "returned_users": 2,
            "sort_by": "username",
            "users": [
                {"username": "alice", "uid": 1001},
                {"username": "bob", "uid": 1002},
            ],
            "timestamp": "2026-02-21T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper.list_users", return_value=mock_result):
            response = test_client.get("/api/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_users"] == 2

    def test_list_users_error_status_returns_403(self, test_client, auth_headers):
        """list_users がエラーレスポンスを返す場合 403 を返すこと（lines 161-172）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "Permission denied by wrapper"}
        with patch("backend.api.routes.users.sudo_wrapper.list_users", return_value=mock_result):
            response = test_client.get("/api/users", headers=auth_headers)
        assert response.status_code == 403
        assert "Permission denied" in response.json()["message"]

    def test_list_users_sudo_wrapper_error_returns_500(self, test_client, auth_headers):
        """list_users で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.list_users",
            side_effect=SudoWrapperError("Wrapper script not found"),
        ):
            response = test_client.get("/api/users", headers=auth_headers)
        assert response.status_code == 500
        assert "User list retrieval failed" in response.json()["message"]

    def test_list_users_with_filter_and_sort(self, test_client, auth_headers):
        """フィルタ・ソートパラメータ付きで list_users が呼ばれること"""
        from unittest.mock import patch

        mock_result = {
            "status": "success",
            "total_users": 1,
            "returned_users": 1,
            "sort_by": "uid",
            "users": [{"username": "alice", "uid": 1001}],
            "timestamp": "2026-02-21T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper.list_users", return_value=mock_result) as mock_call:
            response = test_client.get(
                "/api/users",
                params={"sort_by": "uid", "limit": 10, "filter_locked": "false", "username_filter": "alice"},
                headers=auth_headers,
            )
        assert response.status_code == 200
        mock_call.assert_called_once_with(
            sort_by="uid",
            limit=10,
            filter_locked="false",
            username_filter="alice",
        )


class TestUserDetailWithMocks:
    """GET /api/users/{username} - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_get_user_detail_success_path(self, test_client, auth_headers):
        """get_user_detail が成功レスポンスを返すパスを網羅（lines 251-259）"""
        from unittest.mock import patch

        mock_result = {
            "status": "success",
            "user": {"username": "alice", "uid": 1001, "shell": "/bin/bash"},
            "timestamp": "2026-02-21T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper.get_user_detail", return_value=mock_result):
            response = test_client.get("/api/users/alice", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["user"]["username"] == "alice"

    def test_get_user_detail_not_found_returns_404(self, test_client, auth_headers):
        """get_user_detail がエラーレスポンスを返す場合 404 を返すこと（lines 238-249）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "User not found: nouser"}
        with patch("backend.api.routes.users.sudo_wrapper.get_user_detail", return_value=mock_result):
            response = test_client.get("/api/users/nouser", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_get_user_detail_sudo_wrapper_error_returns_500(self, test_client, auth_headers):
        """get_user_detail で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.get_user_detail",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.get("/api/users/alice", headers=auth_headers)
        assert response.status_code == 500
        assert "User detail retrieval failed" in response.json()["message"]


class TestCreateUserWithMocks:
    """POST /api/users - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_create_user_success_path(self, test_client, admin_headers):
        """ユーザー作成が成功するパスを網羅（lines 382-394）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "User created", "username": "newuser"}
        with patch("backend.api.routes.users.sudo_wrapper.add_user", return_value=mock_result):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "SecurePass123!",
                    "shell": "/bin/bash",
                },
                headers=admin_headers,
            )
        assert response.status_code == 201

    def test_create_user_wrapper_returns_error_400(self, test_client, admin_headers):
        """add_user がエラーレスポンスを返す場合 400 を返すこと（lines 369-380）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "User already exists"}
        with patch("backend.api.routes.users.sudo_wrapper.add_user", return_value=mock_result):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "SecurePass123!",
                    "shell": "/bin/bash",
                },
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "already exists" in response.json()["message"]

    def test_create_user_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """add_user で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.add_user",
            side_effect=SudoWrapperError("Script execution failed"),
        ):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "SecurePass123!",
                    "shell": "/bin/bash",
                },
                headers=admin_headers,
            )
        assert response.status_code == 500
        assert "User creation failed" in response.json()["message"]

    def test_create_user_invalid_username_validation_error(self, test_client, admin_headers):
        """validate_username が ValidationError を上げる場合 400 を返すこと（lines 294-295）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_username",
            side_effect=ValidationError("Username contains invalid chars"),
        ):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "validname",
                    "password": "SecurePass123!",
                },
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "Invalid username" in response.json()["message"]

    def test_create_user_invalid_group_name_validation_error(self, test_client, admin_headers):
        """グループ名が ValidationError を上げる場合 400 を返すこと（lines 330-333）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_groupname",
            side_effect=ValidationError("Invalid group name"),
        ):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "SecurePass123!",
                    "groups": ["badgroup"],
                },
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "Invalid group name" in response.json()["message"]

    def test_create_user_with_groups_success(self, test_client, admin_headers):
        """グループ指定でのユーザー作成が成功するパス"""
        from unittest.mock import patch

        mock_result = {"status": "success", "username": "groupuser"}
        with patch("backend.api.routes.users.sudo_wrapper.add_user", return_value=mock_result):
            response = test_client.post(
                "/api/users",
                json={
                    "username": "groupuser",
                    "password": "SecurePass123!",
                    "shell": "/bin/bash",
                    "groups": ["users"],
                },
                headers=admin_headers,
            )
        assert response.status_code == 201


class TestDeleteUserWithMocks:
    """DELETE /api/users/{username} - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_delete_user_success_path(self, test_client, admin_headers):
        """ユーザー削除が成功するパスを網羅（lines 480-490）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "User deleted", "username": "olduser"}
        with patch("backend.api.routes.users.sudo_wrapper.delete_user", return_value=mock_result):
            response = test_client.delete("/api/users/olduser", headers=admin_headers)
        assert response.status_code == 200

    def test_delete_user_wrapper_returns_error_400(self, test_client, admin_headers):
        """delete_user がエラーレスポンスを返す場合 400 を返すこと（lines 467-478）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "User is currently logged in"}
        with patch("backend.api.routes.users.sudo_wrapper.delete_user", return_value=mock_result):
            response = test_client.delete("/api/users/olduser", headers=admin_headers)
        assert response.status_code == 400
        assert "logged in" in response.json()["message"]

    def test_delete_user_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """delete_user で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.delete_user",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.delete("/api/users/olduser", headers=admin_headers)
        assert response.status_code == 500
        assert "User deletion failed" in response.json()["message"]

    def test_delete_user_with_options(self, test_client, admin_headers):
        """remove_home / backup_home / force_logout パラメータ付きで削除できること"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "User deleted with home"}
        with patch("backend.api.routes.users.sudo_wrapper.delete_user", return_value=mock_result) as mock_call:
            response = test_client.delete(
                "/api/users/olduser",
                params={"remove_home": True, "backup_home": False, "force_logout": True},
                headers=admin_headers,
            )
        assert response.status_code == 200
        mock_call.assert_called_once_with(
            username="olduser",
            remove_home=True,
            backup_home=False,
            force_logout=True,
        )


class TestChangePasswordWithMocks:
    """PUT /api/users/{username}/password - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_change_password_success_path(self, test_client, admin_headers):
        """パスワード変更が成功するパスを網羅（lines 567-579）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "Password changed"}
        with patch("backend.api.routes.users.sudo_wrapper.change_user_password", return_value=mock_result):
            response = test_client.put(
                "/api/users/targetuser/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert response.status_code == 200

    def test_change_password_wrapper_returns_error_400(self, test_client, admin_headers):
        """change_user_password がエラーレスポンスを返す場合 400 を返すこと（lines 554-565）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "User not found"}
        with patch("backend.api.routes.users.sudo_wrapper.change_user_password", return_value=mock_result):
            response = test_client.put(
                "/api/users/nouser/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "User not found" in response.json()["message"]

    def test_change_password_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """change_user_password で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.change_user_password",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.put(
                "/api/users/targetuser/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert response.status_code == 500
        assert "Password change failed" in response.json()["message"]

    def test_change_password_invalid_username_validation_error(self, test_client, admin_headers):
        """validate_username が ValidationError を上げる場合 400 を返すこと（lines 526-527）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_username",
            side_effect=ValidationError("Invalid username"),
        ):
            response = test_client.put(
                "/api/users/validname/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "Invalid username" in response.json()["message"]


class TestGroupListWithMocks:
    """GET /api/users/groups/list - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_list_groups_success_path(self, test_client, auth_headers):
        """list_groups が成功レスポンスを返すパスを網羅（lines 647-655）"""
        from unittest.mock import patch

        mock_result = {
            "status": "success",
            "total_groups": 3,
            "returned_groups": 3,
            "sort_by": "name",
            "groups": [
                {"name": "users", "gid": 100},
                {"name": "staff", "gid": 1001},
                {"name": "developers", "gid": 1002},
            ],
            "timestamp": "2026-02-21T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper.list_groups", return_value=mock_result):
            response = test_client.get("/api/users/groups/list", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total_groups"] == 3

    def test_list_groups_error_status_returns_403(self, test_client, auth_headers):
        """list_groups がエラーレスポンスを返す場合 403 を返すこと（lines 634-645）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "Permission denied"}
        with patch("backend.api.routes.users.sudo_wrapper.list_groups", return_value=mock_result):
            response = test_client.get("/api/users/groups/list", headers=auth_headers)
        assert response.status_code == 403

    def test_list_groups_sudo_wrapper_error_returns_500(self, test_client, auth_headers):
        """list_groups で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.list_groups",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.get("/api/users/groups/list", headers=auth_headers)
        assert response.status_code == 500
        assert "Group list retrieval failed" in response.json()["message"]


class TestCreateGroupWithMocks:
    """POST /api/users/groups - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_create_group_success_path(self, test_client, admin_headers):
        """グループ作成が成功するパスを網羅（lines 745-755）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "Group created", "name": "newgroup"}
        with patch("backend.api.routes.users.sudo_wrapper.add_group", return_value=mock_result):
            response = test_client.post(
                "/api/users/groups",
                json={"name": "newgroup"},
                headers=admin_headers,
            )
        assert response.status_code == 201

    def test_create_group_wrapper_returns_error_400(self, test_client, admin_headers):
        """add_group がエラーレスポンスを返す場合 400 を返すこと（lines 732-743）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "Group already exists"}
        with patch("backend.api.routes.users.sudo_wrapper.add_group", return_value=mock_result):
            response = test_client.post(
                "/api/users/groups",
                json={"name": "existinggroup"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "already exists" in response.json()["message"]

    def test_create_group_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """add_group で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.add_group",
            side_effect=SudoWrapperError("Script not found"),
        ):
            response = test_client.post(
                "/api/users/groups",
                json={"name": "newgroup"},
                headers=admin_headers,
            )
        assert response.status_code == 500
        assert "Group creation failed" in response.json()["message"]

    def test_create_group_validation_error_returns_400(self, test_client, admin_headers):
        """validate_groupname が ValidationError を上げる場合 400 を返すこと（lines 689-690）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_groupname",
            side_effect=ValidationError("Invalid group name"),
        ):
            response = test_client.post(
                "/api/users/groups",
                json={"name": "validname"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "Invalid group name" in response.json()["message"]

    def test_create_group_username_collision_rejected(self, test_client, admin_headers):
        """FORBIDDEN_USERNAMES と衝突するグループ名は 400 を返すこと（lines 708-712）"""
        from backend.core.constants import FORBIDDEN_USERNAMES, FORBIDDEN_GROUPS

        # FORBIDDEN_USERNAMES にあって FORBIDDEN_GROUPS にはない名前を探す
        collision_name = None
        for name in FORBIDDEN_USERNAMES:
            if name not in FORBIDDEN_GROUPS and len(name) >= 1 and name[0].islower():
                # Pydantic の pattern バリデーション ^[a-z_][a-z0-9_-]{0,31}$ を通過する名前
                import re
                if re.match(r"^[a-z_][a-z0-9_-]{0,31}$", name):
                    collision_name = name
                    break

        if collision_name is None:
            pytest.skip("No suitable collision name found in FORBIDDEN_USERNAMES")

        response = test_client.post(
            "/api/users/groups",
            json={"name": collision_name},
            headers=admin_headers,
        )
        assert response.status_code == 400


class TestDeleteGroupWithMocks:
    """DELETE /api/users/groups/{name} - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_delete_group_success_path(self, test_client, admin_headers):
        """グループ削除が成功するパスを網羅（lines 821-831）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "Group deleted", "name": "oldgroup"}
        with patch("backend.api.routes.users.sudo_wrapper.delete_group", return_value=mock_result):
            response = test_client.delete("/api/users/groups/oldgroup", headers=admin_headers)
        assert response.status_code == 200

    def test_delete_group_wrapper_returns_error_400(self, test_client, admin_headers):
        """delete_group がエラーレスポンスを返す場合 400 を返すこと（lines 808-820）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "Group has active members"}
        with patch("backend.api.routes.users.sudo_wrapper.delete_group", return_value=mock_result):
            response = test_client.delete("/api/users/groups/activegroup", headers=admin_headers)
        assert response.status_code == 400
        assert "active members" in response.json()["message"]

    def test_delete_group_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """delete_group で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.delete_group",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.delete("/api/users/groups/oldgroup", headers=admin_headers)
        assert response.status_code == 500
        assert "Group deletion failed" in response.json()["message"]

    def test_delete_group_validation_error_returns_400(self, test_client, admin_headers):
        """validate_groupname が ValidationError を上げる場合 400 を返すこと（lines 789-790）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_groupname",
            side_effect=ValidationError("Invalid group name"),
        ):
            response = test_client.delete("/api/users/groups/validname", headers=admin_headers)
        assert response.status_code == 400
        assert "Invalid group name" in response.json()["message"]


class TestModifyGroupMembershipWithMocks:
    """PUT /api/users/groups/{name}/members - sudo_wrapper モックを使ったカバレッジ向上テスト"""

    def test_modify_membership_success_add(self, test_client, admin_headers):
        """グループへのメンバー追加が成功するパスを網羅（lines 929-946）"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "User added to group"}
        with patch("backend.api.routes.users.sudo_wrapper.modify_group_membership", return_value=mock_result):
            response = test_client.put(
                "/api/users/groups/mygroup/members",
                json={"action": "add", "user": "alice"},
                headers=admin_headers,
            )
        assert response.status_code == 200

    def test_modify_membership_success_remove(self, test_client, admin_headers):
        """グループからのメンバー削除が成功するパス"""
        from unittest.mock import patch

        mock_result = {"status": "success", "message": "User removed from group"}
        with patch("backend.api.routes.users.sudo_wrapper.modify_group_membership", return_value=mock_result):
            response = test_client.put(
                "/api/users/groups/mygroup/members",
                json={"action": "remove", "user": "alice"},
                headers=admin_headers,
            )
        assert response.status_code == 200

    def test_modify_membership_wrapper_returns_error_400(self, test_client, admin_headers):
        """modify_group_membership がエラーレスポンスを返す場合 400 を返すこと（lines 916-927）"""
        from unittest.mock import patch

        mock_result = {"status": "error", "message": "User is not a member"}
        with patch("backend.api.routes.users.sudo_wrapper.modify_group_membership", return_value=mock_result):
            response = test_client.put(
                "/api/users/groups/mygroup/members",
                json={"action": "remove", "user": "alice"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "not a member" in response.json()["message"]

    def test_modify_membership_sudo_wrapper_error_returns_500(self, test_client, admin_headers):
        """modify_group_membership で SudoWrapperError が発生する場合 500 を返すこと"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.api.routes.users.sudo_wrapper.modify_group_membership",
            side_effect=SudoWrapperError("Execution failed"),
        ):
            response = test_client.put(
                "/api/users/groups/mygroup/members",
                json={"action": "add", "user": "alice"},
                headers=admin_headers,
            )
        assert response.status_code == 500
        assert "Group membership modification failed" in response.json()["message"]

    def test_modify_membership_forbidden_group_returns_400(self, test_client, admin_headers):
        """FORBIDDEN_GROUPS のグループへのメンバーシップ変更は 400 を返すこと（lines 882-887）"""
        # "sudo" は FORBIDDEN_GROUPS に含まれている
        response = test_client.put(
            "/api/users/groups/sudo/members",
            json={"action": "add", "user": "alice"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "forbidden" in response.json()["message"].lower()

    def test_modify_membership_invalid_groupname_validation_error(self, test_client, admin_headers):
        """validate_groupname が ValidationError を上げる場合 400 を返すこと（lines 867-868）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        with patch(
            "backend.api.routes.users.validate_groupname",
            side_effect=ValidationError("Invalid group name"),
        ):
            response = test_client.put(
                "/api/users/groups/validgroup/members",
                json={"action": "add", "user": "alice"},
                headers=admin_headers,
            )
        assert response.status_code == 400
        assert "Invalid group name" in response.json()["message"]

    def test_modify_membership_invalid_username_validation_error(self, test_client, admin_headers):
        """validate_username が ValidationError を上げる場合 400 を返すこと（lines 875-876）"""
        from unittest.mock import patch
        from backend.core.validation import ValidationError

        # validate_groupname は通過させ、validate_username のみ失敗させる
        orig_validate_groupname_pass = True

        call_count = {"n": 0}

        def mock_validate(name, field=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # 1回目（groupname チェック）は通過
                return
            raise ValidationError("Invalid username")

        with patch("backend.api.routes.users.validate_groupname"):
            with patch(
                "backend.api.routes.users.validate_username",
                side_effect=ValidationError("Invalid username"),
            ):
                response = test_client.put(
                    "/api/users/groups/validgroup/members",
                    json={"action": "add", "user": "alice"},
                    headers=admin_headers,
                )
        assert response.status_code == 400
        assert "Invalid username" in response.json()["message"]
