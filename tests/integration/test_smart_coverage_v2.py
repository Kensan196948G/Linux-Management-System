"""
SMART Drive Status モジュール - カバレッジ改善テスト v2

未カバー箇所を集中的にテスト:
  - _validate_disk_name: startswith("/") 分岐 / allowlist パターン各種
  - 各エンドポイントの audit_log.record 呼び出し確認
  - parse_wrapper_result の output フィールド JSON パース分岐
  - nvme デバイスパス
  - エッジケース: 空文字列、パストラバーサル、シェルインジェクション
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.api.routes.smart import _validate_disk_name


# ===================================================================
# _validate_disk_name 直接テスト
# ===================================================================


class TestValidateDiskName:
    """_validate_disk_name ヘルパーの全分岐カバレッジ"""

    @pytest.mark.parametrize(
        "input_disk,expected",
        [
            ("/dev/sda", "/dev/sda"),
            ("/dev/sdb", "/dev/sdb"),
            ("/dev/sdz", "/dev/sdz"),
            ("/dev/nvme0n0", "/dev/nvme0n0"),
            ("/dev/nvme9n9", "/dev/nvme9n9"),
        ],
    )
    def test_valid_disk_with_leading_slash(self, input_disk, expected):
        """先頭 / 付きの正常ディスク名"""
        assert _validate_disk_name(input_disk) == expected

    @pytest.mark.parametrize(
        "input_disk,expected",
        [
            ("dev/sda", "/dev/sda"),
            ("dev/nvme0n0", "/dev/nvme0n0"),
        ],
    )
    def test_valid_disk_without_leading_slash(self, input_disk, expected):
        """先頭 / 無し → 自動補完"""
        assert _validate_disk_name(input_disk) == expected

    @pytest.mark.parametrize(
        "bad_disk",
        [
            "/dev/sda1",         # パーティション番号は不許可
            "/dev/hda",          # hd* は不許可
            "/dev/vda",          # vd* は不許可
            "/dev/nvme0n0p1",    # パーティションは不許可
            "/dev/sd",           # 文字なし
            "/dev/sda;rm -rf /", # シェルインジェクション
            "/etc/passwd",       # パストラバーサル
            "",                  # 空文字列
            "/dev/../etc/passwd",
            "/dev/SD A",         # スペース
        ],
    )
    def test_invalid_disk_raises_400(self, bad_disk):
        """不正なディスク名は HTTPException(400) を発生"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_disk_name(bad_disk)
        assert exc_info.value.status_code == 400

    def test_invalid_disk_error_message_contains_name(self):
        """エラーメッセージにディスク名が含まれる"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_disk_name("/dev/INVALID")
        assert "INVALID" in str(exc_info.value.detail)


# ===================================================================
# parse_wrapper_result 経由の output JSON パーステスト
# ===================================================================


class TestSmartDisksOutputParsing:
    """output フィールドの JSON パース分岐をカバー"""

    def test_disks_with_output_json_string(self, test_client, admin_token):
        """output が JSON 文字列の場合はパースされる"""
        import json

        inner = {
            "status": "success",
            "smartctl_available": True,
            "lsblk": {"blockdevices": []},
            "timestamp": "2026-03-01T00:00:00Z",
        }
        wrapper_result = {"status": "success", "output": json.dumps(inner)}

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks",
            return_value=wrapper_result,
        ):
            resp = test_client.get(
                "/api/smart/disks",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["smartctl_available"] is True

    def test_disks_with_non_json_output(self, test_client, admin_token):
        """output が不正 JSON の場合は result をそのまま返す"""
        wrapper_result = {
            "status": "success",
            "output": "not-valid-json{{{",
            "smartctl_available": None,
            "lsblk": None,
            "timestamp": "2026-03-01T00:00:00Z",
        }

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks",
            return_value=wrapper_result,
        ):
            resp = test_client.get(
                "/api/smart/disks",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200


# ===================================================================
# SMART info エンドポイント - 追加テスト
# ===================================================================


class TestSmartInfoCoverageV2:
    """info エンドポイントの未カバー分岐"""

    def test_info_nvme_disk(self, test_client, admin_token):
        """NVMe ディスクパスでの正常取得"""
        info_data = {
            "status": "success",
            "disk": "/dev/nvme0n0",
            "info_raw": "Model: NVME_TEST\n",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_info",
            return_value=info_data,
        ):
            resp = test_client.get(
                "/api/smart/info/dev/nvme0n0",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["disk"] == "/dev/nvme0n0"

    @pytest.mark.parametrize(
        "bad_path",
        [
            "dev/sda1",
            "dev/hda",
            "etc/passwd",
            "dev/sd;ls",
        ],
    )
    def test_info_invalid_disk_paths(self, test_client, admin_token, bad_path):
        """各種不正ディスクパスで 400"""
        resp = test_client.get(
            f"/api/smart/info/{bad_path}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_info_with_output_field(self, test_client, admin_token):
        """output JSON 文字列経由のパース"""
        import json

        inner = {
            "status": "success",
            "disk": "/dev/sda",
            "info_raw": "test info",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_info",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get(
                "/api/smart/info/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200

    def test_info_audit_log_called(self, test_client, admin_token):
        """audit_log.record が正常系で呼ばれる"""
        info_data = {
            "status": "success",
            "disk": "/dev/sda",
            "info_raw": "test",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_info",
            return_value=info_data,
        ), patch("backend.api.routes.smart.audit_log") as mock_audit:
            resp = test_client.get(
                "/api/smart/info/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "smart_info"
        assert call_kwargs["status"] == "success"


# ===================================================================
# SMART health エンドポイント - 追加テスト
# ===================================================================


class TestSmartHealthCoverageV2:
    """health エンドポイントの未カバー分岐"""

    def test_health_nvme_disk(self, test_client, admin_token):
        """NVMe ディスクでの健全性チェック"""
        health_data = {
            "status": "success",
            "disk": "/dev/nvme0n0",
            "health": "PASSED",
            "output_raw": "PASSED\n",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_health",
            return_value=health_data,
        ):
            resp = test_client.get(
                "/api/smart/health/dev/nvme0n0",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["health"] == "PASSED"

    def test_health_unknown_status(self, test_client, admin_token):
        """health が unknown の場合"""
        health_data = {
            "status": "success",
            "disk": "/dev/sda",
            "health": "unknown",
            "output_raw": "",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_health",
            return_value=health_data,
        ):
            resp = test_client.get(
                "/api/smart/health/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["health"] == "unknown"

    def test_health_audit_log_called(self, test_client, admin_token):
        """audit_log.record が正常系で呼ばれる"""
        health_data = {
            "status": "success",
            "disk": "/dev/sda",
            "health": "PASSED",
            "output_raw": "PASSED\n",
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_health",
            return_value=health_data,
        ), patch("backend.api.routes.smart.audit_log") as mock_audit:
            resp = test_client.get(
                "/api/smart/health/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "smart_health"

    @pytest.mark.parametrize(
        "bad_path",
        [
            "dev/sda1",
            "dev/vda",
            "dev/sd;id",
        ],
    )
    def test_health_invalid_disk_paths(self, test_client, admin_token, bad_path):
        """不正ディスクパスで 400"""
        resp = test_client.get(
            f"/api/smart/health/{bad_path}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400


# ===================================================================
# SMART tests エンドポイント - 追加テスト
# ===================================================================


class TestSmartTestsCoverageV2:
    """tests エンドポイントの未カバー分岐"""

    def test_tests_with_output_field(self, test_client, admin_token):
        """output JSON 文字列経由のパース"""
        import json

        inner = {
            "status": "success",
            "tests": [{"disk": "/dev/sda", "selftest_raw": "test log"}],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests",
            return_value={"status": "success", "output": json.dumps(inner)},
        ):
            resp = test_client.get(
                "/api/smart/tests",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert len(resp.json()["tests"]) == 1

    def test_tests_empty_results(self, test_client, admin_token):
        """テスト結果が空リストの場合"""
        data = {
            "status": "success",
            "tests": [],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests",
            return_value=data,
        ):
            resp = test_client.get(
                "/api/smart/tests",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["tests"] == []

    def test_tests_audit_log_called(self, test_client, admin_token):
        """audit_log.record が正常系で呼ばれる"""
        data = {
            "status": "success",
            "tests": [],
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests",
            return_value=data,
        ), patch("backend.api.routes.smart.audit_log") as mock_audit:
            resp = test_client.get(
                "/api/smart/tests",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "smart_tests"
        assert call_kwargs["target"] == "smart"


# ===================================================================
# SMART disks エンドポイント - 追加テスト
# ===================================================================


class TestSmartDisksCoverageV2:
    """disks エンドポイントの未カバー分岐"""

    def test_disks_audit_log_called(self, test_client, admin_token):
        """audit_log.record が正常系で呼ばれる"""
        data = {
            "status": "success",
            "smartctl_available": True,
            "lsblk": {"blockdevices": []},
            "timestamp": "2026-03-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks",
            return_value=data,
        ), patch("backend.api.routes.smart.audit_log") as mock_audit:
            resp = test_client.get(
                "/api/smart/disks",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "smart_disks"
        assert call_kwargs["target"] == "smart"
        assert call_kwargs["status"] == "success"

    def test_disks_wrapper_error_message_in_response(self, test_client, admin_token):
        """SudoWrapperError のメッセージがレスポンスに含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_disks",
            side_effect=SudoWrapperError("specific error message"),
        ):
            resp = test_client.get(
                "/api/smart/disks",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", body.get("message", ""))
        assert "specific error message" in msg

    def test_info_wrapper_error_message_in_response(self, test_client, admin_token):
        """SMART info SudoWrapperError のメッセージがレスポンスに含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_info",
            side_effect=SudoWrapperError("info error msg"),
        ):
            resp = test_client.get(
                "/api/smart/info/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", body.get("message", ""))
        assert "info error msg" in msg

    def test_health_wrapper_error_message_in_response(self, test_client, admin_token):
        """SMART health SudoWrapperError のメッセージがレスポンスに含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_health",
            side_effect=SudoWrapperError("health error msg"),
        ):
            resp = test_client.get(
                "/api/smart/health/dev/sda",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", body.get("message", ""))
        assert "health error msg" in msg

    def test_tests_wrapper_error_message_in_response(self, test_client, admin_token):
        """SMART tests SudoWrapperError のメッセージがレスポンスに含まれる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_smart_tests",
            side_effect=SudoWrapperError("tests error msg"),
        ):
            resp = test_client.get(
                "/api/smart/tests",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail", body.get("message", ""))
        assert "tests error msg" in msg


# ===================================================================
# セキュリティ: パストラバーサル / インジェクション
# ===================================================================


class TestSmartSecurityV2:
    """セキュリティ関連の追加テスト"""

    @pytest.mark.parametrize(
        "injection_path",
        [
            "dev/sda%00",
            "dev/sda && id",
            "dev/sda | cat /etc/shadow",
            "proc/self/environ",
        ],
    )
    def test_info_injection_rejected(self, test_client, admin_token, injection_path):
        """パストラバーサル / インジェクションは 400"""
        resp = test_client.get(
            f"/api/smart/info/{injection_path}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "injection_path",
        [
            "dev/sda%00",
            "dev/sda && id",
            "dev/sda | cat /etc/shadow",
        ],
    )
    def test_health_injection_rejected(self, test_client, admin_token, injection_path):
        """パストラバーサル / インジェクションは 400"""
        resp = test_client.get(
            f"/api/smart/health/{injection_path}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400
