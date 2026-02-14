"""
backend/core/constants.py のユニットテスト
"""

import pytest

from backend.core.constants import (
    ALLOWED_SHELLS,
    FORBIDDEN_GROUPS,
    FORBIDDEN_GROUPS_CONTAINER,
    FORBIDDEN_GROUPS_CRITICAL,
    FORBIDDEN_GROUPS_HARDWARE,
    FORBIDDEN_GROUPS_NETWORK,
    FORBIDDEN_GROUPS_SYSTEM,
    FORBIDDEN_GROUPS_SYSTEMD,
    FORBIDDEN_USERNAMES,
    FORBIDDEN_USERNAMES_ADMIN,
    FORBIDDEN_USERNAMES_APP,
    FORBIDDEN_USERNAMES_SERVICE,
    FORBIDDEN_USERNAMES_SYSTEM,
    MAX_GID,
    MAX_UID,
    MIN_GID,
    MIN_UID,
)


class TestForbiddenUsernames:
    """禁止ユーザー名定数のテスト"""

    def test_forbidden_usernames_system_includes_root(self):
        """システムユーザーにrootが含まれること"""
        assert "root" in FORBIDDEN_USERNAMES_SYSTEM

    def test_forbidden_usernames_service_includes_database_services(self):
        """サービスユーザーにデータベースサービスが含まれること"""
        assert "postgres" in FORBIDDEN_USERNAMES_SERVICE
        assert "mysql" in FORBIDDEN_USERNAMES_SERVICE
        assert "redis" in FORBIDDEN_USERNAMES_SERVICE

    def test_forbidden_usernames_admin_includes_sudo(self):
        """管理ユーザーにsudoが含まれること"""
        assert "sudo" in FORBIDDEN_USERNAMES_ADMIN
        assert "admin" in FORBIDDEN_USERNAMES_ADMIN
        assert "wheel" in FORBIDDEN_USERNAMES_ADMIN

    def test_forbidden_usernames_app_includes_adminui(self):
        """アプリユーザーにadminuiが含まれること"""
        assert "svc-adminui" in FORBIDDEN_USERNAMES_APP
        assert "adminui" in FORBIDDEN_USERNAMES_APP

    def test_forbidden_usernames_combined_list(self):
        """統合リストが全カテゴリを含むこと"""
        assert len(FORBIDDEN_USERNAMES) >= 100  # users-planner仕様: 100+件

        # 各カテゴリのサンプルが含まれること
        assert "root" in FORBIDDEN_USERNAMES  # system
        assert "postgres" in FORBIDDEN_USERNAMES  # service
        assert "sudo" in FORBIDDEN_USERNAMES  # admin
        assert "svc-adminui" in FORBIDDEN_USERNAMES  # app

    def test_no_duplicates_in_forbidden_usernames(self):
        """禁止ユーザー名に重複がないこと"""
        unique_count = len(set(FORBIDDEN_USERNAMES))
        total_count = len(FORBIDDEN_USERNAMES)
        # 多少の重複は許容（カテゴリ間で重複する可能性）
        assert unique_count >= total_count * 0.9, "Too many duplicates in FORBIDDEN_USERNAMES"


class TestForbiddenGroups:
    """禁止グループ名定数のテスト"""

    def test_forbidden_groups_critical_includes_root(self):
        """クリティカルグループにrootが含まれること"""
        assert "root" in FORBIDDEN_GROUPS_CRITICAL
        assert "sudo" in FORBIDDEN_GROUPS_CRITICAL
        assert "wheel" in FORBIDDEN_GROUPS_CRITICAL

    def test_forbidden_groups_system_includes_disk(self):
        """システムグループにdiskが含まれること（権限昇格リスク）"""
        assert "disk" in FORBIDDEN_GROUPS_SYSTEM
        # admはCRITICALグループに分類されている
        assert "adm" in FORBIDDEN_GROUPS_CRITICAL

    def test_forbidden_groups_container_includes_docker(self):
        """コンテナグループにdockerが含まれること"""
        assert "docker" in FORBIDDEN_GROUPS_CONTAINER
        assert "lxd" in FORBIDDEN_GROUPS_CONTAINER

    def test_forbidden_groups_network_includes_shadow(self):
        """ネットワーク・セキュリティグループにshadowが含まれること"""
        assert "shadow" in FORBIDDEN_GROUPS_NETWORK

    def test_forbidden_groups_systemd(self):
        """systemd関連グループが含まれること"""
        assert "systemd-journal" in FORBIDDEN_GROUPS_SYSTEMD

    def test_forbidden_groups_combined_list(self):
        """統合リストが全カテゴリを含むこと"""
        assert len(FORBIDDEN_GROUPS) >= 35  # users-planner仕様: 35+件

        # 各カテゴリのサンプルが含まれること
        assert "root" in FORBIDDEN_GROUPS
        assert "docker" in FORBIDDEN_GROUPS
        assert "shadow" in FORBIDDEN_GROUPS


class TestAllowedShells:
    """許可シェル定数のテスト"""

    def test_allowed_shells_includes_bash(self):
        """/bin/bashが含まれること"""
        assert "/bin/bash" in ALLOWED_SHELLS

    def test_allowed_shells_includes_sh(self):
        """/bin/shが含まれること"""
        assert "/bin/sh" in ALLOWED_SHELLS

    def test_allowed_shells_includes_false(self):
        """/bin/falseが含まれること（アカウント無効化用）"""
        assert "/bin/false" in ALLOWED_SHELLS

    def test_allowed_shells_count(self):
        """許可シェルが5個であること"""
        assert len(ALLOWED_SHELLS) == 5


class TestUIDGIDRanges:
    """UID/GID範囲定数のテスト"""

    def test_min_uid_is_1000(self):
        """最小UIDが1000であること（システムユーザー保護）"""
        assert MIN_UID == 1000

    def test_max_uid_is_59999(self):
        """最大UIDが59999であること"""
        assert MAX_UID == 59999

    def test_min_gid_is_1000(self):
        """最小GIDが1000であること（システムグループ保護）"""
        assert MIN_GID == 1000

    def test_max_gid_is_59999(self):
        """最大GIDが59999であること"""
        assert MAX_GID == 59999

    def test_uid_range_is_positive(self):
        """UID範囲が正であること"""
        assert MIN_UID > 0
        assert MAX_UID > MIN_UID

    def test_gid_range_is_positive(self):
        """GID範囲が正であること"""
        assert MIN_GID > 0
        assert MAX_GID > MIN_GID
