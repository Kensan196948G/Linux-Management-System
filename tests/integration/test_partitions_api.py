"""
Disk Partitions モジュール - 統合テスト

テストケース数: 18件
- 正常系: list/usage/detail エンドポイント
- unavailable 系: lsblk/df/blkid 未インストール環境
- 異常系: 権限不足、未認証
- セキュリティ: SudoWrapperError 処理
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

PARTITIONS_LIST_OK = {
    "status": "success",
    "partitions": {
        "blockdevices": [
            {
                "name": "sda",
                "size": "500G",
                "type": "disk",
                "fstype": None,
                "mountpoint": None,
                "label": None,
                "uuid": None,
                "children": [
                    {"name": "sda1", "size": "499G", "type": "part", "fstype": "ext4", "mountpoint": "/", "label": None, "uuid": "abc-123"},
                    {"name": "sda2", "size": "1G", "type": "part", "fstype": "swap", "mountpoint": "[SWAP]", "label": None, "uuid": "def-456"},
                ],
            }
        ]
    },
    "timestamp": "2026-03-01T00:00:00Z",
}

PARTITIONS_LIST_UNAVAILABLE = {
    "status": "unavailable",
    "message": "lsblk not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

PARTITIONS_USAGE_OK = {
    "status": "success",
    "usage_raw": "/dev/sda1  499G   10G  489G  3% /\ntmpfs      16G     0   16G  0% /tmp",
    "timestamp": "2026-03-01T00:00:00Z",
}

PARTITIONS_USAGE_UNAVAILABLE = {
    "status": "unavailable",
    "message": "df not found",
    "timestamp": "2026-03-01T00:00:00Z",
}

PARTITIONS_DETAIL_OK = {
    "status": "success",
    "blkid_raw": '/dev/sda1: UUID="abc-123" TYPE="ext4" PARTUUID="xyz-789"\n/dev/sda2: UUID="def-456" TYPE="swap"\n',
    "timestamp": "2026-03-01T00:00:00Z",
}

PARTITIONS_DETAIL_UNAVAILABLE = {
    "status": "unavailable",
    "message": "blkid not found",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストケース
# ===================================================================


class TestPartitionsList:
    """TC_PRT_001〜006: Partitions list エンドポイントテスト"""

    def test_TC_PRT_001_list_ok(self, test_client, admin_token):
        """TC_PRT_001: パーティション一覧の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_list", return_value=PARTITIONS_LIST_OK):
            resp = test_client.get("/api/partitions/list", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["partitions"] is not None

    def test_TC_PRT_002_list_unavailable(self, test_client, admin_token):
        """TC_PRT_002: lsblk 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_list", return_value=PARTITIONS_LIST_UNAVAILABLE):
            resp = test_client.get("/api/partitions/list", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PRT_003_list_unauthorized(self, test_client):
        """TC_PRT_003: 未認証時の 401 返却"""
        resp = test_client.get("/api/partitions/list")
        assert resp.status_code in (401, 403)

    def test_TC_PRT_004_list_viewer_allowed(self, test_client, viewer_token):
        """TC_PRT_004: viewer ロールでもパーティション一覧取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_list", return_value=PARTITIONS_LIST_OK):
            resp = test_client.get("/api/partitions/list", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_PRT_005_list_wrapper_error(self, test_client, admin_token):
        """TC_PRT_005: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_list", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/partitions/list", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503

    def test_TC_PRT_006_list_operator_allowed(self, test_client, auth_token):
        """TC_PRT_006: operator ロールでもパーティション一覧取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_list", return_value=PARTITIONS_LIST_OK):
            resp = test_client.get("/api/partitions/list", headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200


class TestPartitionsUsage:
    """TC_PRT_007〜012: Partitions usage エンドポイントテスト"""

    def test_TC_PRT_007_usage_ok(self, test_client, admin_token):
        """TC_PRT_007: ディスク使用量の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_usage", return_value=PARTITIONS_USAGE_OK):
            resp = test_client.get("/api/partitions/usage", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["usage_raw"] is not None

    def test_TC_PRT_008_usage_unavailable(self, test_client, admin_token):
        """TC_PRT_008: df 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_usage", return_value=PARTITIONS_USAGE_UNAVAILABLE):
            resp = test_client.get("/api/partitions/usage", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PRT_009_usage_unauthorized(self, test_client):
        """TC_PRT_009: 未認証時の 401 返却"""
        resp = test_client.get("/api/partitions/usage")
        assert resp.status_code in (401, 403)

    def test_TC_PRT_010_usage_viewer_allowed(self, test_client, viewer_token):
        """TC_PRT_010: viewer ロールでもディスク使用量取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_usage", return_value=PARTITIONS_USAGE_OK):
            resp = test_client.get("/api/partitions/usage", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_PRT_011_usage_wrapper_error(self, test_client, admin_token):
        """TC_PRT_011: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_usage", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/partitions/usage", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503

    def test_TC_PRT_012_usage_contains_raw_data(self, test_client, admin_token):
        """TC_PRT_012: 使用量データに usage_raw フィールドが含まれること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_usage", return_value=PARTITIONS_USAGE_OK):
            resp = test_client.get("/api/partitions/usage", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "usage_raw" in data
        assert "/dev/sda1" in data["usage_raw"]


class TestPartitionsDetail:
    """TC_PRT_013〜018: Partitions detail エンドポイントテスト"""

    def test_TC_PRT_013_detail_ok(self, test_client, admin_token):
        """TC_PRT_013: ブロックデバイス詳細の正常取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_detail", return_value=PARTITIONS_DETAIL_OK):
            resp = test_client.get("/api/partitions/detail", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["blkid_raw"] is not None

    def test_TC_PRT_014_detail_unavailable(self, test_client, admin_token):
        """TC_PRT_014: blkid 未インストール時の unavailable 返却"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_detail", return_value=PARTITIONS_DETAIL_UNAVAILABLE):
            resp = test_client.get("/api/partitions/detail", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"

    def test_TC_PRT_015_detail_unauthorized(self, test_client):
        """TC_PRT_015: 未認証時の 401 返却"""
        resp = test_client.get("/api/partitions/detail")
        assert resp.status_code in (401, 403)

    def test_TC_PRT_016_detail_viewer_allowed(self, test_client, viewer_token):
        """TC_PRT_016: viewer ロールでもデバイス詳細取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_detail", return_value=PARTITIONS_DETAIL_OK):
            resp = test_client.get("/api/partitions/detail", headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 200

    def test_TC_PRT_017_detail_wrapper_error(self, test_client, admin_token):
        """TC_PRT_017: SudoWrapperError 発生時の 503 返却"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_detail", side_effect=SudoWrapperError("exec failed")):
            resp = test_client.get("/api/partitions/detail", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 503

    def test_TC_PRT_018_detail_contains_uuid(self, test_client, admin_token):
        """TC_PRT_018: blkid 出力に UUID 情報が含まれること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_partitions_detail", return_value=PARTITIONS_DETAIL_OK):
            resp = test_client.get("/api/partitions/detail", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "blkid_raw" in data
        assert "UUID" in data["blkid_raw"]
