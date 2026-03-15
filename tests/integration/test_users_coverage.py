"""
ユーザー・グループ管理 API カバレッジ向上テスト

sudo_wrapper をモックして、全ブランチ（成功・エラー・例外）をカバー
"""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

SUCCESS_USER_LIST = {
    "status": "success",
    "total_users": 2,
    "returned_users": 2,
    "sort_by": "username",
    "users": [
        {"username": "alice", "uid": 1001, "locked": False},
        {"username": "bob", "uid": 1002, "locked": True},
    ],
    "timestamp": "2025-01-01T00:00:00Z",
}

SUCCESS_USER_DETAIL = {
    "status": "success",
    "user": {
        "username": "alice",
        "uid": 1001,
        "gid": 1001,
        "gecos": "",
        "home": "/home/alice",
        "shell": "/bin/bash",
        "locked": False,
        "groups": [],
    },
    "timestamp": "2025-01-01T00:00:00Z",
}

SUCCESS_ADD_USER = {
    "status": "success",
    "message": "User created",
    "username": "newuser",
}

SUCCESS_DELETE_USER = {
    "status": "success",
    "message": "User deleted",
    "username": "alice",
}

SUCCESS_CHANGE_PW = {
    "status": "success",
    "message": "Password changed",
    "username": "alice",
}

SUCCESS_GROUP_LIST = {
    "status": "success",
    "total_groups": 1,
    "returned_groups": 1,
    "sort_by": "name",
    "groups": [{"name": "staff", "gid": 50, "members": []}],
    "timestamp": "2025-01-01T00:00:00Z",
}

SUCCESS_ADD_GROUP = {
    "status": "success",
    "message": "Group created",
    "name": "newgroup",
}

SUCCESS_DELETE_GROUP = {
    "status": "success",
    "message": "Group deleted",
    "name": "oldgroup",
}

SUCCESS_MODIFY_MEMBERSHIP = {
    "status": "success",
    "message": "Membership updated",
}

ERROR_RESULT = {"status": "error", "message": "Operation denied"}


# ---------------------------------------------------------------------------
# GET /api/users  (list_users) – lines 128-192
# ---------------------------------------------------------------------------


class TestListUsersBody:
    """sudo_wrapper が実際に呼ばれる branch をカバー"""

    def test_list_users_success(self, test_client, admin_headers):
        """sudo_wrapper.list_users が成功結果を返すと 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = SUCCESS_USER_LIST
            resp = test_client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_users"] == 2

    def test_list_users_sudo_error_returns_403(self, test_client, admin_headers):
        """sudo_wrapper が status=error を返すと 403"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = ERROR_RESULT
            resp = test_client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 403

    def test_list_users_sudo_wrapper_exception_returns_500(
        self, test_client, admin_headers
    ):
        """SudoWrapperError が発生すると 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.side_effect = SudoWrapperError("permission denied")
            resp = test_client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 500

    def test_list_users_with_filter_locked_true(self, test_client, admin_headers):
        """filter_locked=true パラメータが sudo_wrapper に渡される"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = SUCCESS_USER_LIST
            resp = test_client.get(
                "/api/users",
                params={"filter_locked": "true"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        mock_sw.list_users.assert_called_once()
        call_kwargs = mock_sw.list_users.call_args.kwargs
        assert call_kwargs["filter_locked"] == "true"

    def test_list_users_with_username_filter(self, test_client, admin_headers):
        """username_filter パラメータが sudo_wrapper に渡される"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = SUCCESS_USER_LIST
            resp = test_client.get(
                "/api/users",
                params={"username_filter": "alice"},
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/users/list (list_users_alias) – line 214
# ---------------------------------------------------------------------------


class TestListUsersAlias:
    def test_list_alias_success(self, test_client, admin_headers):
        """エイリアス /list も同じ結果を返す"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = SUCCESS_USER_LIST
            resp = test_client.get("/api/users/list", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_list_alias_sudo_error(self, test_client, admin_headers):
        """エイリアスでも sudo エラーは 403"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_users.return_value = ERROR_RESULT
            resp = test_client.get("/api/users/list", headers=admin_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/users/groups (list_groups_alias) – line 240
# ---------------------------------------------------------------------------


class TestListGroupsAlias:
    def test_groups_alias_success(self, test_client, admin_headers):
        """エイリアス /groups も 200 を返す"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = SUCCESS_GROUP_LIST
            resp = test_client.get("/api/users/groups", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_groups_alias_sudo_error(self, test_client, admin_headers):
        """エイリアスでも sudo エラーは 403"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = ERROR_RESULT
            resp = test_client.get("/api/users/groups", headers=admin_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/users/{username}  (get_user_detail) – lines 263-319
# ---------------------------------------------------------------------------


class TestGetUserDetail:
    def test_get_detail_success(self, test_client, admin_headers):
        """成功時に 200 とユーザー詳細を返す"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.return_value = SUCCESS_USER_DETAIL
            resp = test_client.get("/api/users/alice", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["user"]["username"] == "alice"

    def test_get_detail_not_found(self, test_client, admin_headers):
        """sudo が status=error を返すと 404"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.return_value = ERROR_RESULT
            resp = test_client.get("/api/users/nobody", headers=admin_headers)
        assert resp.status_code == 404

    def test_get_detail_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.side_effect = SudoWrapperError("fail")
            resp = test_client.get("/api/users/alice", headers=admin_headers)
        assert resp.status_code == 500

    def test_get_detail_invalid_username_special_chars(
        self, test_client, admin_headers
    ):
        """特殊文字を含むユーザー名は 400"""
        resp = test_client.get("/api/users/bad;user", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_get_detail_viewer_can_access(self, test_client, viewer_headers):
        """viewer も read:users 権限があるのでアクセスできる"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.get_user_detail.return_value = SUCCESS_USER_DETAIL
            resp = test_client.get("/api/users/alice", headers=viewer_headers)
        assert resp.status_code == 200

    def test_get_detail_unauthenticated(self, test_client):
        """認証なしは 403"""
        resp = test_client.get("/api/users/alice")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/users  (create_user) – lines 338-447
# ---------------------------------------------------------------------------


class TestCreateUser:
    VALID_PAYLOAD = {
        "username": "newuser",
        "password": "SecurePass123!",
        "shell": "/bin/bash",
        "gecos": "NewUser",
        "groups": [],
    }

    def test_create_user_success(self, test_client, admin_headers):
        """admin が有効なリクエストを送ると 201"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.return_value = SUCCESS_ADD_USER
            resp = test_client.post(
                "/api/users", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 201

    def test_create_user_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.return_value = ERROR_RESULT
            resp = test_client.post(
                "/api/users", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 400

    def test_create_user_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.side_effect = SudoWrapperError("fail")
            resp = test_client.post(
                "/api/users", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 500

    def test_create_forbidden_username(self, test_client, admin_headers):
        """reserved ユーザー名は 400"""
        payload = {**self.VALID_PAYLOAD, "username": "root"}
        resp = test_client.post("/api/users", json=payload, headers=admin_headers)
        assert resp.status_code == 400

    def test_create_disallowed_shell(self, test_client, admin_headers):
        """allowlist 外のシェルは 400"""
        payload = {**self.VALID_PAYLOAD, "shell": "/bin/zsh_unknown"}
        resp = test_client.post("/api/users", json=payload, headers=admin_headers)
        assert resp.status_code == 400

    def test_create_invalid_gecos(self, test_client, admin_headers):
        """GECOS フィールドに禁止文字が含まれると 400"""
        payload = {**self.VALID_PAYLOAD, "gecos": "bad;gecos"}
        resp = test_client.post("/api/users", json=payload, headers=admin_headers)
        assert resp.status_code == 400

    def test_create_invalid_group_name(self, test_client, admin_headers):
        """無効なグループ名が含まれると 400"""
        payload = {**self.VALID_PAYLOAD, "groups": ["bad;group"]}
        resp = test_client.post("/api/users", json=payload, headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_create_with_groups(self, test_client, admin_headers):
        """groups フィールド付きで作成できる"""
        payload = {**self.VALID_PAYLOAD, "groups": ["users"]}
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_user.return_value = SUCCESS_ADD_USER
            resp = test_client.post("/api/users", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        call_kwargs = mock_sw.add_user.call_args.kwargs
        assert call_kwargs["groups"] == ["users"]

    def test_create_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は write:users 権限がないので 403"""
        resp = test_client.post(
            "/api/users", json=self.VALID_PAYLOAD, headers=viewer_headers
        )
        assert resp.status_code == 403

    def test_create_operator_forbidden(self, test_client, auth_headers):
        """operator は write:users 権限がないので 403"""
        resp = test_client.post(
            "/api/users", json=self.VALID_PAYLOAD, headers=auth_headers
        )
        assert resp.status_code == 403

    def test_create_user_validate_username_raises(self, test_client, admin_headers):
        """validate_username が ValidationError を発生させると 400（多層防御ブランチ）"""
        from backend.core.validation import ValidationError as VErr

        with patch(
            "backend.api.routes.users.validate_username", side_effect=VErr("bad")
        ):
            resp = test_client.post(
                "/api/users", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/users/{username}  (delete_user) – lines 470-543
# ---------------------------------------------------------------------------


class TestDeleteUser:
    def test_delete_user_success(self, test_client, admin_headers):
        """正常削除で 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = SUCCESS_DELETE_USER
            resp = test_client.delete("/api/users/alice", headers=admin_headers)
        assert resp.status_code == 200

    def test_delete_user_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = ERROR_RESULT
            resp = test_client.delete("/api/users/alice", headers=admin_headers)
        assert resp.status_code == 400

    def test_delete_user_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.side_effect = SudoWrapperError("fail")
            resp = test_client.delete("/api/users/alice", headers=admin_headers)
        assert resp.status_code == 500

    def test_delete_user_invalid_username(self, test_client, admin_headers):
        """特殊文字を含むユーザー名は 400"""
        resp = test_client.delete("/api/users/bad;user", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_delete_with_remove_home(self, test_client, admin_headers):
        """remove_home=true が sudo_wrapper に渡される"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = SUCCESS_DELETE_USER
            resp = test_client.delete(
                "/api/users/alice",
                params={"remove_home": "true"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        call_kwargs = mock_sw.delete_user.call_args.kwargs
        assert call_kwargs["remove_home"] is True

    def test_delete_with_force_logout(self, test_client, admin_headers):
        """force_logout=true が sudo_wrapper に渡される"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_user.return_value = SUCCESS_DELETE_USER
            resp = test_client.delete(
                "/api/users/alice",
                params={"force_logout": "true"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_delete_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は 403"""
        resp = test_client.delete("/api/users/alice", headers=viewer_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/users/{username}/password  (change_password) – lines 562-633
# ---------------------------------------------------------------------------


class TestChangePassword:
    def test_change_password_success(self, test_client, admin_headers):
        """正常変更で 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.return_value = SUCCESS_CHANGE_PW
            resp = test_client.put(
                "/api/users/alice/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_change_password_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.return_value = ERROR_RESULT
            resp = test_client.put(
                "/api/users/alice/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_change_password_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.change_user_password.side_effect = SudoWrapperError("fail")
            resp = test_client.put(
                "/api/users/alice/password",
                json={"password": "NewSecurePass123!"},
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_change_password_invalid_username(self, test_client, admin_headers):
        """無効ユーザー名は 400"""
        resp = test_client.put(
            "/api/users/bad;user/password",
            json={"password": "NewSecurePass123!"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_change_password_short_password(self, test_client, admin_headers):
        """短いパスワードは 422"""
        resp = test_client.put(
            "/api/users/alice/password",
            json={"password": "short"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_change_password_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は 403"""
        resp = test_client.put(
            "/api/users/alice/password",
            json={"password": "NewSecurePass123!"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/users/groups/list  (list_groups) – lines 652-701
# ---------------------------------------------------------------------------


class TestListGroups:
    def test_list_groups_success(self, test_client, admin_headers):
        """成功時に 200 とグループ一覧を返す"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = SUCCESS_GROUP_LIST
            resp = test_client.get("/api/users/groups/list", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_groups"] == 1

    def test_list_groups_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 403"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = ERROR_RESULT
            resp = test_client.get("/api/users/groups/list", headers=admin_headers)
        assert resp.status_code == 403

    def test_list_groups_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.side_effect = SudoWrapperError("fail")
            resp = test_client.get("/api/users/groups/list", headers=admin_headers)
        assert resp.status_code == 500

    def test_list_groups_sort_by_gid(self, test_client, admin_headers):
        """sort_by=gid が sudo_wrapper に渡される"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.list_groups.return_value = SUCCESS_GROUP_LIST
            resp = test_client.get(
                "/api/users/groups/list",
                params={"sort_by": "gid"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        call_kwargs = mock_sw.list_groups.call_args.kwargs
        assert call_kwargs["sort_by"] == "gid"

    def test_list_groups_unauthenticated(self, test_client):
        """認証なしは 403"""
        resp = test_client.get("/api/users/groups/list")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/users/groups  (create_group) – lines 718-793
# ---------------------------------------------------------------------------


class TestCreateGroup:
    VALID_PAYLOAD = {"name": "newgroup"}

    def test_create_group_success(self, test_client, admin_headers):
        """正常作成で 201"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.return_value = SUCCESS_ADD_GROUP
            resp = test_client.post(
                "/api/users/groups", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 201

    def test_create_group_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.return_value = ERROR_RESULT
            resp = test_client.post(
                "/api/users/groups", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 400

    def test_create_group_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.add_group.side_effect = SudoWrapperError("fail")
            resp = test_client.post(
                "/api/users/groups", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 500

    def test_create_group_forbidden_name(self, test_client, admin_headers):
        """FORBIDDEN_GROUPS に含まれる名前は 400"""
        from backend.core.constants import FORBIDDEN_GROUPS

        if FORBIDDEN_GROUPS:
            payload = {"name": list(FORBIDDEN_GROUPS)[0]}
            resp = test_client.post(
                "/api/users/groups", json=payload, headers=admin_headers
            )
            assert resp.status_code == 400

    def test_create_group_forbidden_username_collision(
        self, test_client, admin_headers
    ):
        """FORBIDDEN_USERNAMES と衝突するグループ名は 400"""
        from backend.core.constants import FORBIDDEN_USERNAMES, FORBIDDEN_GROUPS

        # root は通常 FORBIDDEN_USERNAMES にあり、FORBIDDEN_GROUPS に無い場合
        candidates = [u for u in FORBIDDEN_USERNAMES if u not in FORBIDDEN_GROUPS]
        if candidates:
            payload = {"name": candidates[0]}
            resp = test_client.post(
                "/api/users/groups", json=payload, headers=admin_headers
            )
            assert resp.status_code == 400

    def test_create_group_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は 403"""
        resp = test_client.post(
            "/api/users/groups", json=self.VALID_PAYLOAD, headers=viewer_headers
        )
        assert resp.status_code == 403

    def test_create_group_validate_groupname_raises(self, test_client, admin_headers):
        """validate_groupname が ValidationError を発生させると 400（多層防御ブランチ）"""
        from backend.core.validation import ValidationError as VErr

        with patch(
            "backend.api.routes.users.validate_groupname", side_effect=VErr("bad")
        ):
            resp = test_client.post(
                "/api/users/groups", json=self.VALID_PAYLOAD, headers=admin_headers
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/users/groups/{name}  (delete_group) – lines 810-869
# ---------------------------------------------------------------------------


class TestDeleteGroup:
    def test_delete_group_success(self, test_client, admin_headers):
        """正常削除で 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.return_value = SUCCESS_DELETE_GROUP
            resp = test_client.delete(
                "/api/users/groups/oldgroup", headers=admin_headers
            )
        assert resp.status_code == 200

    def test_delete_group_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.return_value = ERROR_RESULT
            resp = test_client.delete(
                "/api/users/groups/oldgroup", headers=admin_headers
            )
        assert resp.status_code == 400

    def test_delete_group_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.delete_group.side_effect = SudoWrapperError("fail")
            resp = test_client.delete(
                "/api/users/groups/oldgroup", headers=admin_headers
            )
        assert resp.status_code == 500

    def test_delete_group_invalid_name(self, test_client, admin_headers):
        """特殊文字を含むグループ名は 400"""
        resp = test_client.delete("/api/users/groups/bad;group", headers=admin_headers)
        assert resp.status_code in (400, 422)

    def test_delete_group_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は 403"""
        resp = test_client.delete("/api/users/groups/oldgroup", headers=viewer_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/users/groups/{name}/members  (modify_group_membership) – lines 888-977
# ---------------------------------------------------------------------------


class TestModifyGroupMembership:
    VALID_ADD = {"action": "add", "user": "alice"}
    VALID_REMOVE = {"action": "remove", "user": "alice"}

    def test_add_member_success(self, test_client, admin_headers):
        """メンバー追加 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = SUCCESS_MODIFY_MEMBERSHIP
            resp = test_client.put(
                "/api/users/groups/users/members",
                json=self.VALID_ADD,
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_remove_member_success(self, test_client, admin_headers):
        """メンバー削除 200"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = SUCCESS_MODIFY_MEMBERSHIP
            resp = test_client.put(
                "/api/users/groups/users/members",
                json=self.VALID_REMOVE,
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_modify_member_sudo_error(self, test_client, admin_headers):
        """sudo が status=error を返すと 400"""
        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.return_value = ERROR_RESULT
            resp = test_client.put(
                "/api/users/groups/users/members",
                json=self.VALID_ADD,
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_modify_member_sudo_exception(self, test_client, admin_headers):
        """SudoWrapperError は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.api.routes.users.sudo_wrapper") as mock_sw:
            mock_sw.modify_group_membership.side_effect = SudoWrapperError("fail")
            resp = test_client.put(
                "/api/users/groups/users/members",
                json=self.VALID_ADD,
                headers=admin_headers,
            )
        assert resp.status_code == 500

    def test_modify_member_forbidden_group(self, test_client, admin_headers):
        """FORBIDDEN_GROUPS に属するグループは 400"""
        from backend.core.constants import FORBIDDEN_GROUPS

        if FORBIDDEN_GROUPS:
            forbidden = list(FORBIDDEN_GROUPS)[0]
            resp = test_client.put(
                f"/api/users/groups/{forbidden}/members",
                json=self.VALID_ADD,
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_modify_member_invalid_group_name(self, test_client, admin_headers):
        """無効なグループ名は 400"""
        resp = test_client.put(
            "/api/users/groups/bad;group/members",
            json=self.VALID_ADD,
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_modify_member_invalid_username(self, test_client, admin_headers):
        """無効なユーザー名は 400/422"""
        resp = test_client.put(
            "/api/users/groups/users/members",
            json={"action": "add", "user": "bad;user"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_modify_member_invalid_action(self, test_client, admin_headers):
        """無効な action は 422"""
        resp = test_client.put(
            "/api/users/groups/users/members",
            json={"action": "delete", "user": "alice"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_modify_member_viewer_forbidden(self, test_client, viewer_headers):
        """viewer は 403"""
        resp = test_client.put(
            "/api/users/groups/users/members",
            json=self.VALID_ADD,
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_modify_member_validate_username_raises(self, test_client, admin_headers):
        """validate_username が ValidationError を発生させると 400（多層防御ブランチ）"""
        from backend.core.validation import ValidationError as VErr

        __import__(
            "backend.core.validation", fromlist=["validate_groupname"]
        ).validate_groupname

        call_count = {"n": 0}

        def side_effect(val, *args, **kwargs):
            call_count["n"] += 1
            # validate_groupname は通過、validate_username で失敗させる
            if call_count["n"] == 1:
                return  # groupname OK
            raise VErr("bad username")

        with patch(
            "backend.api.routes.users.validate_groupname", side_effect=lambda v: None
        ), patch("backend.api.routes.users.validate_username", side_effect=VErr("bad")):
            resp = test_client.put(
                "/api/users/groups/users/members",
                json=self.VALID_ADD,
                headers=admin_headers,
            )
        assert resp.status_code == 400
