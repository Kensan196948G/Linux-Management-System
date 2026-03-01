"""
ユーザー・グループ管理 UI強化 API 統合テスト (Step 23)

GET /api/users/list  - ユーザー一覧 (新エイリアス)
GET /api/users/groups - グループ一覧 (新エイリアス)
GET /api/users/{username} - ユーザー詳細 (既存)
"""

import pytest


class TestUserListAlias:
    """GET /api/users/list - ユーザー一覧 (エイリアス)"""

    def test_list_users_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users/list")
        assert response.status_code == 403

    def test_list_users_authenticated(self, test_client, auth_headers):
        """認証済みで users キーを含むこと"""
        response = test_client.get("/api/users/list", headers=auth_headers)
        # sudo が使えない環境では 500 になる場合があるが、403 にはならない
        assert response.status_code != 403
        if response.status_code == 200:
            data = response.json()
            assert "users" in data

    def test_list_users_viewer_has_permission(self, test_client, viewer_headers):
        """viewer ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users/list", headers=viewer_headers)
        assert response.status_code != 403

    def test_list_users_invalid_sort_key(self, test_client, auth_headers):
        """無効なソートキーは 422 を返すこと"""
        response = test_client.get(
            "/api/users/list",
            params={"sort_by": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_users_valid_sort_keys(self, test_client, auth_headers):
        """有効なソートキーは受け付けること"""
        for sort_key in ["username", "uid", "last_login"]:
            response = test_client.get(
                "/api/users/list",
                params={"sort_by": sort_key},
                headers=auth_headers,
            )
            assert response.status_code != 422, f"sort_by={sort_key} should be accepted"

    def test_list_users_limit_too_large(self, test_client, auth_headers):
        """上限超えの limit は 422 を返すこと"""
        response = test_client.get(
            "/api/users/list",
            params={"limit": 501},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestGroupListAlias:
    """GET /api/users/groups - グループ一覧 (エイリアス)"""

    def test_list_groups_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users/groups")
        assert response.status_code == 403

    def test_list_groups_authenticated(self, test_client, auth_headers):
        """認証済みで groups キーを含むこと"""
        response = test_client.get("/api/users/groups", headers=auth_headers)
        assert response.status_code != 403
        if response.status_code == 200:
            data = response.json()
            assert "groups" in data

    def test_list_groups_viewer_has_permission(self, test_client, viewer_headers):
        """viewer ロールは read:users 権限を持つこと"""
        response = test_client.get("/api/users/groups", headers=viewer_headers)
        assert response.status_code != 403

    def test_list_groups_invalid_sort_key(self, test_client, auth_headers):
        """無効なソートキーは 422 を返すこと"""
        response = test_client.get(
            "/api/users/groups",
            params={"sort_by": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_groups_valid_sort_keys(self, test_client, auth_headers):
        """有効なソートキーは受け付けること"""
        for sort_key in ["name", "gid", "member_count"]:
            response = test_client.get(
                "/api/users/groups",
                params={"sort_by": sort_key},
                headers=auth_headers,
            )
            assert response.status_code != 422, f"sort_by={sort_key} should be accepted"


class TestUserDetailEndpoint:
    """GET /api/users/{username} - ユーザー詳細"""

    def test_user_detail_nonexistent(self, test_client, auth_headers):
        """存在しないユーザーは 404 を返すこと"""
        response = test_client.get(
            "/api/users/nonexistent_user_12345",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_user_detail_unauthenticated(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/users/someuser")
        assert response.status_code == 403

    def test_user_detail_invalid_username_chars(self, test_client, auth_headers):
        """特殊文字を含むユーザー名は 400 を返すこと"""
        response = test_client.get(
            "/api/users/user;rm-rf",
            headers=auth_headers,
        )
        assert response.status_code == 400
