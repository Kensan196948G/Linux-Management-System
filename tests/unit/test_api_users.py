"""
Users API エンドポイントのユニットテスト

backend/api/routes/users.py のカバレッジ向上
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


class TestListUsers:
    """GET /api/users テスト"""

    def test_list_users_success(self, test_client, auth_headers):
        """正常系: ユーザー一覧取得"""
        mock_result = {
            "status": "success",
            "total_users": 2,
            "returned_users": 2,
            "sort_by": "username",
            "users": [
                {"username": "testuser1", "uid": 1001},
                {"username": "testuser2", "uid": 1002},
            ],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = mock_result
            response = test_client.get("/api/users", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_users"] == 2

    def test_list_users_with_params(self, test_client, auth_headers):
        """クエリパラメータ付きで取得"""
        mock_result = {
            "status": "success",
            "total_users": 1,
            "returned_users": 1,
            "sort_by": "uid",
            "users": [{"username": "testuser1", "uid": 1001}],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = mock_result
            response = test_client.get(
                "/api/users?sort_by=uid&limit=50&filter_locked=true",
                headers=auth_headers,
            )

        assert response.status_code == 200

    def test_list_users_error_status(self, test_client, auth_headers):
        """エラーステータス → 403"""
        mock_result = {"status": "error", "message": "Permission denied"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = mock_result
            response = test_client.get("/api/users", headers=auth_headers)

        assert response.status_code == 403

    def test_list_users_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.side_effect = SudoWrapperError("Wrapper failed")
            response = test_client.get("/api/users", headers=auth_headers)

        assert response.status_code == 500

    def test_list_users_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/users")
        assert response.status_code == 403


class TestGetUserDetail:
    """GET /api/users/{username} テスト"""

    def test_get_user_detail_success(self, test_client, auth_headers):
        """正常系: ユーザー詳細取得"""
        mock_result = {
            "status": "success",
            "user": {"username": "testuser", "uid": 1001, "groups": ["users"]},
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.return_value = mock_result
            response = test_client.get("/api/users/testuser", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user"]["username"] == "testuser"

    def test_get_user_detail_invalid_username(self, test_client, auth_headers):
        """不正なユーザー名 → 400"""
        response = test_client.get(
            "/api/users/root;rm%20-rf", headers=auth_headers
        )
        assert response.status_code == 400

    def test_get_user_detail_error_status(self, test_client, auth_headers):
        """ユーザー未発見 → 404"""
        mock_result = {"status": "error", "message": "User not found"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.return_value = mock_result
            response = test_client.get(
                "/api/users/nonexistent", headers=auth_headers
            )

        assert response.status_code == 404

    def test_get_user_detail_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/users/testuser", headers=auth_headers
            )

        assert response.status_code == 500


class TestCreateUser:
    """POST /api/users テスト"""

    def test_create_user_success(self, test_client, admin_headers):
        """正常系: ユーザー作成"""
        mock_result = {"status": "success", "message": "User created", "uid": 1005}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.return_value = mock_result
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "securepassword123",
                    "shell": "/bin/bash",
                    "gecos": "NewUser",
                    "groups": [],
                },
                headers=admin_headers,
            )

        assert response.status_code == 201

    def test_create_user_forbidden_username(self, test_client, admin_headers):
        """FORBIDDEN_USERNAMES → 400"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "root",
                "password": "securepassword123",
                "shell": "/bin/bash",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "reserved" in response.json()["message"]

    def test_create_user_invalid_shell(self, test_client, admin_headers):
        """ALLOWED_SHELLS 外のシェル → 400"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "securepassword123",
                "shell": "/bin/evil_shell",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "Shell not allowed" in response.json()["message"]

    def test_create_user_forbidden_gecos_chars(self, test_client, admin_headers):
        """GECOS 禁止文字 → 400"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "securepassword123",
                "shell": "/bin/bash",
                "gecos": "User; rm -rf /",
            },
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "gecos" in response.json()["message"]

    def test_create_user_invalid_group_name(self, test_client, admin_headers):
        """不正なグループ名 → 400"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "securepassword123",
                "shell": "/bin/bash",
                "groups": ["valid-group", "bad;group"],
            },
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_create_user_error_status(self, test_client, admin_headers):
        """sudo_wrapper がエラーを返すケース → 400"""
        mock_result = {"status": "error", "message": "User already exists"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.return_value = mock_result
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "securepassword123",
                    "shell": "/bin/bash",
                },
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_create_user_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/users",
                json={
                    "username": "newuser",
                    "password": "securepassword123",
                    "shell": "/bin/bash",
                },
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_create_user_pydantic_validation(self, test_client, admin_headers):
        """Pydantic バリデーション: ユーザー名パターン違反 → 422"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "UPPERCASE",
                "password": "securepassword123",
                "shell": "/bin/bash",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_user_short_password(self, test_client, admin_headers):
        """Pydantic バリデーション: パスワード短すぎ → 422"""
        response = test_client.post(
            "/api/users",
            json={
                "username": "newuser",
                "password": "short",
                "shell": "/bin/bash",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestDeleteUser:
    """DELETE /api/users/{username} テスト"""

    def test_delete_user_success(self, test_client, admin_headers):
        """正常系: ユーザー削除"""
        mock_result = {"status": "success", "message": "User deleted"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = mock_result
            response = test_client.delete(
                "/api/users/testuser", headers=admin_headers
            )

        assert response.status_code == 200

    def test_delete_user_with_options(self, test_client, admin_headers):
        """オプション付き削除"""
        mock_result = {"status": "success", "message": "User deleted with home removal"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = mock_result
            response = test_client.delete(
                "/api/users/testuser?remove_home=true&backup_home=true&force_logout=true",
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_delete_user_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        response = test_client.delete(
            "/api/users/bad%3Buser", headers=admin_headers
        )
        assert response.status_code == 400

    def test_delete_user_error_status(self, test_client, admin_headers):
        """sudo_wrapper エラー → 400"""
        mock_result = {"status": "error", "message": "User not found"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = mock_result
            response = test_client.delete(
                "/api/users/nonexistent", headers=admin_headers
            )

        assert response.status_code == 400

    def test_delete_user_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.side_effect = SudoWrapperError("Failed")
            response = test_client.delete(
                "/api/users/testuser", headers=admin_headers
            )

        assert response.status_code == 500


class TestChangePassword:
    """PUT /api/users/{username}/password テスト"""

    def test_change_password_success(self, test_client, admin_headers):
        """正常系: パスワード変更"""
        mock_result = {"status": "success", "message": "Password changed"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.return_value = mock_result
            response = test_client.put(
                "/api/users/testuser/password",
                json={"password": "newsecurepassword123"},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_change_password_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        response = test_client.put(
            "/api/users/bad|user/password",
            json={"password": "newsecurepassword123"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_change_password_error_status(self, test_client, admin_headers):
        """エラーステータス → 400"""
        mock_result = {"status": "error", "message": "Password change denied"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.return_value = mock_result
            response = test_client.put(
                "/api/users/testuser/password",
                json={"password": "newsecurepassword123"},
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_change_password_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.side_effect = SudoWrapperError("Failed")
            response = test_client.put(
                "/api/users/testuser/password",
                json={"password": "newsecurepassword123"},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_change_password_short(self, test_client, admin_headers):
        """パスワードが短すぎ → 422"""
        response = test_client.put(
            "/api/users/testuser/password",
            json={"password": "short"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestListGroups:
    """GET /api/users/groups/list テスト"""

    def test_list_groups_success(self, test_client, auth_headers):
        """正常系: グループ一覧取得"""
        mock_result = {
            "status": "success",
            "total_groups": 3,
            "returned_groups": 3,
            "sort_by": "name",
            "groups": [
                {"name": "users", "gid": 100},
                {"name": "developers", "gid": 101},
                {"name": "admins", "gid": 102},
            ],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = mock_result
            response = test_client.get(
                "/api/users/groups/list", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_groups"] == 3

    def test_list_groups_error_status(self, test_client, auth_headers):
        """エラーステータス → 403"""
        mock_result = {"status": "error", "message": "Access denied"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = mock_result
            response = test_client.get(
                "/api/users/groups/list", headers=auth_headers
            )

        assert response.status_code == 403

    def test_list_groups_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.side_effect = SudoWrapperError("Failed")
            response = test_client.get(
                "/api/users/groups/list", headers=auth_headers
            )

        assert response.status_code == 500


class TestCreateGroup:
    """POST /api/users/groups テスト"""

    def test_create_group_success(self, test_client, admin_headers):
        """正常系: グループ作成"""
        mock_result = {"status": "success", "message": "Group created", "gid": 2001}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.return_value = mock_result
            response = test_client.post(
                "/api/users/groups",
                json={"name": "newgroup"},
                headers=admin_headers,
            )

        assert response.status_code == 201

    def test_create_group_forbidden_group(self, test_client, admin_headers):
        """FORBIDDEN_GROUPS → 400"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "root"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_create_group_forbidden_username_collision(self, test_client, admin_headers):
        """FORBIDDEN_USERNAMES との衝突 → 400"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "daemon"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_create_group_error_status(self, test_client, admin_headers):
        """sudo_wrapper がエラー → 400"""
        mock_result = {"status": "error", "message": "Group already exists"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.return_value = mock_result
            response = test_client.post(
                "/api/users/groups",
                json={"name": "newgroup"},
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_create_group_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.side_effect = SudoWrapperError("Failed")
            response = test_client.post(
                "/api/users/groups",
                json={"name": "newgroup"},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_create_group_pydantic_validation(self, test_client, admin_headers):
        """Pydantic バリデーション: パターン違反 → 422"""
        response = test_client.post(
            "/api/users/groups",
            json={"name": "INVALID GROUP"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestDeleteGroup:
    """DELETE /api/users/groups/{name} テスト"""

    def test_delete_group_success(self, test_client, admin_headers):
        """正常系: グループ削除"""
        mock_result = {"status": "success", "message": "Group deleted"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.return_value = mock_result
            response = test_client.delete(
                "/api/users/groups/testgroup", headers=admin_headers
            )

        assert response.status_code == 200

    def test_delete_group_invalid_name(self, test_client, admin_headers):
        """不正なグループ名 → 400"""
        response = test_client.delete(
            "/api/users/groups/bad%3Bgroup", headers=admin_headers
        )
        assert response.status_code == 400

    def test_delete_group_error_status(self, test_client, admin_headers):
        """エラーステータス → 400"""
        mock_result = {"status": "error", "message": "Group not found"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.return_value = mock_result
            response = test_client.delete(
                "/api/users/groups/testgroup", headers=admin_headers
            )

        assert response.status_code == 400

    def test_delete_group_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.side_effect = SudoWrapperError("Failed")
            response = test_client.delete(
                "/api/users/groups/testgroup", headers=admin_headers
            )

        assert response.status_code == 500


class TestModifyGroupMembership:
    """PUT /api/users/groups/{name}/members テスト"""

    def test_add_member_success(self, test_client, admin_headers):
        """正常系: メンバー追加"""
        mock_result = {"status": "success", "message": "User added to group"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = mock_result
            response = test_client.put(
                "/api/users/groups/developers/members",
                json={"action": "add", "user": "testuser"},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_remove_member_success(self, test_client, admin_headers):
        """正常系: メンバー削除"""
        mock_result = {"status": "success", "message": "User removed from group"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = mock_result
            response = test_client.put(
                "/api/users/groups/developers/members",
                json={"action": "remove", "user": "testuser"},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_modify_invalid_groupname(self, test_client, admin_headers):
        """不正なグループ名 → 400"""
        response = test_client.put(
            "/api/users/groups/bad%3Bgroup/members",
            json={"action": "add", "user": "testuser"},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_modify_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 422 (Pydantic pattern)"""
        response = test_client.put(
            "/api/users/groups/developers/members",
            json={"action": "add", "user": "BAD;USER"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_modify_forbidden_group(self, test_client, admin_headers):
        """FORBIDDEN_GROUPS → 400"""
        response = test_client.put(
            "/api/users/groups/root/members",
            json={"action": "add", "user": "testuser"},
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "forbidden" in response.json()["message"].lower()

    def test_modify_error_status(self, test_client, admin_headers):
        """エラーステータス → 400"""
        mock_result = {"status": "error", "message": "User not in group"}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = mock_result
            response = test_client.put(
                "/api/users/groups/developers/members",
                json={"action": "remove", "user": "testuser"},
                headers=admin_headers,
            )

        assert response.status_code == 400

    def test_modify_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError 発生時 → 500"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.side_effect = SudoWrapperError("Failed")
            response = test_client.put(
                "/api/users/groups/developers/members",
                json={"action": "add", "user": "testuser"},
                headers=admin_headers,
            )

        assert response.status_code == 500

    def test_modify_invalid_action(self, test_client, admin_headers):
        """Pydantic バリデーション: 不正な action → 422"""
        response = test_client.put(
            "/api/users/groups/developers/members",
            json={"action": "destroy", "user": "testuser"},
            headers=admin_headers,
        )
        assert response.status_code == 422
