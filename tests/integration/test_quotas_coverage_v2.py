"""
quotas.py カバレッジ改善テスト v2

対象: backend/api/routes/quotas.py (77% -> 90%+)
未カバー箇所を重点的にテスト:
  - SudoWrapperError 分岐 (各エンドポイントの except ブロック)
  - export_csv: SudoWrapperError, data が list の場合, data が dict で users なしの場合
  - alerts: SudoWrapperError, soft_limit のみのユーザー (hard=0), usage_pct == threshold (境界)
  - set_quota: SudoWrapperError (audit_log error 記録含む), group タイプの正常系
  - QuotaSetRequest: hard_kb < soft_kb バリデーション
  - _validate_name / _validate_filesystem の追加分岐
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ===================================================================
# SudoWrapperError 分岐テスト
# ===================================================================

class TestQuotaStatusSudoError:
    """GET /api/quotas/status の SudoWrapperError"""

    def test_status_sudo_error_returns_503(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            side_effect=SudoWrapperError("quota not available"),
        ):
            resp = test_client.get("/api/quotas/status", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "クォータ状態取得エラー" in error_msg

    def test_status_sudo_error_with_filesystem(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            side_effect=SudoWrapperError("fs error"),
        ):
            resp = test_client.get("/api/quotas/status?filesystem=/home", headers=viewer_headers)
        assert resp.status_code == 503


class TestQuotaUsersSudoError:
    """GET /api/quotas/users の SudoWrapperError"""

    def test_users_sudo_error_returns_503(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            side_effect=SudoWrapperError("repquota failed"),
        ):
            resp = test_client.get("/api/quotas/users", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "ユーザークォータ一覧取得エラー" in error_msg


class TestQuotaUserDetailSudoError:
    """GET /api/quotas/user/{username} の SudoWrapperError"""

    def test_user_quota_sudo_error_returns_503(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_user_quota",
            side_effect=SudoWrapperError("quota -u failed"),
        ):
            resp = test_client.get("/api/quotas/user/testuser", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "ユーザークォータ取得エラー" in error_msg


class TestQuotaGroupDetailSudoError:
    """GET /api/quotas/group/{groupname} の SudoWrapperError"""

    def test_group_quota_sudo_error_returns_503(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_group_quota",
            side_effect=SudoWrapperError("quota -g failed"),
        ):
            resp = test_client.get("/api/quotas/group/devteam", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "グループクォータ取得エラー" in error_msg


class TestQuotaReportSudoError:
    """GET /api/quotas/report の SudoWrapperError"""

    def test_report_sudo_error_returns_503(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_report",
            side_effect=SudoWrapperError("repquota report failed"),
        ):
            resp = test_client.get("/api/quotas/report", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "クォータレポート取得エラー" in error_msg

    def test_report_sudo_error_with_filesystem(self, test_client, viewer_headers):
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_report",
            side_effect=SudoWrapperError("fs not found"),
        ):
            resp = test_client.get("/api/quotas/report?filesystem=/data", headers=viewer_headers)
        assert resp.status_code == 503


# ===================================================================
# CSV エクスポート: SudoWrapperError + data 形式分岐
# ===================================================================

class TestQuotaCSVExportCoverage:
    """GET /api/quotas/export/csv の未カバー分岐"""

    def test_csv_sudo_error_returns_503(self, test_client, viewer_headers):
        """SudoWrapperError で 503"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            side_effect=SudoWrapperError("csv export failed"),
        ):
            resp = test_client.get("/api/quotas/export/csv", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "CSV" in error_msg

    def test_csv_data_is_list(self, test_client, viewer_headers):
        """data が list の場合の CSV 出力 (data キーの値が list)"""
        list_data = [
            {"username": "alice", "filesystem": "/", "used_kb": 100, "soft_limit_kb": 500,
             "hard_limit_kb": 1000, "grace_period": "-", "inodes_used": 10, "inode_soft": 0, "inode_hard": 0},
        ]
        # parsed.get("data") が list を返すパターン
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value={"output": "[]"},
        ), patch(
            "backend.api.routes.quotas.parse_wrapper_result",
            return_value={"data": list_data},
        ):
            resp = test_client.get("/api/quotas/export/csv", headers=viewer_headers)
        assert resp.status_code == 200
        assert "alice" in resp.text

    def test_csv_data_dict_no_users_key(self, test_client, viewer_headers):
        """data が dict だが users キーがない場合は空 CSV"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value={"output": "{}"},
        ), patch(
            "backend.api.routes.quotas.parse_wrapper_result",
            return_value={"data": {"filesystems": []}},
        ):
            resp = test_client.get("/api/quotas/export/csv", headers=viewer_headers)
        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        # ヘッダー行のみ
        assert len(lines) == 1

    def test_csv_data_is_none(self, test_client, viewer_headers):
        """data が None の場合は空 CSV"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value={"output": "{}"},
        ), patch(
            "backend.api.routes.quotas.parse_wrapper_result",
            return_value={"status": "ok"},
        ):
            resp = test_client.get("/api/quotas/export/csv", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# アラート: SudoWrapperError + soft_limit 分岐
# ===================================================================

class TestQuotaAlertsCoverage:
    """GET /api/quotas/alerts の未カバー分岐"""

    def test_alerts_sudo_error_returns_503(self, test_client, viewer_headers):
        """SudoWrapperError で 503"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            side_effect=SudoWrapperError("alert query failed"),
        ):
            resp = test_client.get("/api/quotas/alerts", headers=viewer_headers)
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "クォータアラート取得エラー" in error_msg

    def test_alerts_soft_limit_fallback(self, test_client, viewer_headers):
        """hard_limit_kb=0 の場合は soft_limit_kb を limit として使用"""
        data_soft_only = {
            "status": "ok",
            "data": {
                "users": [
                    {"username": "softuser", "filesystem": "/", "used_kb": 900,
                     "soft_limit_kb": 1000, "hard_limit_kb": 0},
                ]
            },
        }
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=data_soft_only,
        ):
            resp = test_client.get("/api/quotas/alerts?threshold=80", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_count"] == 1
        assert data["alerts"][0]["username"] == "softuser"
        assert data["alerts"][0]["usage_percent"] == 90.0

    def test_alerts_at_exact_threshold_not_included(self, test_client, viewer_headers):
        """usage_pct == threshold の場合はアラートに含まれない (> threshold)"""
        data_exact = {
            "status": "ok",
            "data": {
                "users": [
                    {"username": "exact", "filesystem": "/", "used_kb": 800,
                     "soft_limit_kb": 1000, "hard_limit_kb": 1000},
                ]
            },
        }
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value=data_exact,
        ):
            resp = test_client.get("/api/quotas/alerts?threshold=80", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_count"] == 0

    def test_alerts_data_is_list(self, test_client, viewer_headers):
        """parsed.get("data") が list を返す場合"""
        list_data = [
            {"username": "listuser", "filesystem": "/", "used_kb": 950,
             "soft_limit_kb": 1000, "hard_limit_kb": 1000},
        ]
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_all_user_quotas",
            return_value={"output": "[]"},
        ), patch(
            "backend.api.routes.quotas.parse_wrapper_result",
            return_value={"data": list_data},
        ):
            resp = test_client.get("/api/quotas/alerts?threshold=90", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_count"] == 1
        assert data["alerts"][0]["username"] == "listuser"


# ===================================================================
# POST /api/quotas/set: SudoWrapperError + audit_log error
# ===================================================================

class TestQuotaSetCoverage:
    """POST /api/quotas/set の未カバー分岐"""

    def test_set_user_quota_sudo_error_returns_503(self, test_client, admin_headers):
        """SudoWrapperError で 503 + audit_log error 記録"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_user_quota",
            side_effect=SudoWrapperError("setquota failed"),
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/",
                    "soft_kb": 500,
                    "hard_kb": 1000,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 503
        body = resp.json()
        error_msg = body.get("detail") or body.get("message", "")
        assert "クォータ設定エラー" in error_msg

    def test_set_group_quota_sudo_error_returns_503(self, test_client, admin_headers):
        """group タイプの SudoWrapperError"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_group_quota",
            side_effect=SudoWrapperError("setquota group failed"),
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "group",
                    "name": "devteam",
                    "filesystem": "/home",
                    "soft_kb": 1000,
                    "hard_kb": 2000,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 503

    def test_set_quota_hard_less_than_soft_rejected(self, test_client, admin_headers):
        """hard_kb < soft_kb の場合は 422"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 2000,
                "hard_kb": 1000,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_set_quota_with_inodes(self, test_client, admin_headers):
        """isoft/ihard 指定ありの正常系"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_user_quota",
            return_value={"status": "success", "message": "Quota set"},
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/",
                    "soft_kb": 500,
                    "hard_kb": 1000,
                    "isoft": 100,
                    "ihard": 200,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "testuser"


# ===================================================================
# バリデーション追加テスト
# ===================================================================

class TestValidationCoverage:
    """_validate_name / _validate_filesystem の追加分岐"""

    def test_validate_filesystem_empty_string_allowed(self, test_client, viewer_headers):
        """filesystem='' (空文字列) は許可される"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value={"status": "ok"},
        ):
            resp = test_client.get("/api/quotas/status", headers=viewer_headers)
        assert resp.status_code == 200

    def test_validate_filesystem_uuid(self, test_client, viewer_headers):
        """UUID=xxx 形式のファイルシステムは許可される"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value={"status": "ok"},
        ):
            resp = test_client.get(
                "/api/quotas/status?filesystem=UUID=abc-123-def",
                headers=viewer_headers,
            )
        assert resp.status_code == 200

    def test_validate_filesystem_dev_path(self, test_client, viewer_headers):
        """/dev/sda1 形式は許可される"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value={"status": "ok"},
        ):
            resp = test_client.get(
                "/api/quotas/status?filesystem=/dev/sda1",
                headers=viewer_headers,
            )
        assert resp.status_code == 200

    def test_validate_name_with_dots_and_dashes(self, test_client, viewer_headers):
        """ユーザー名にドット・ハイフン・アンダースコアを含む場合は許可"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_user_quota",
            return_value={"status": "ok", "data": {}},
        ):
            resp = test_client.get("/api/quotas/user/test.user-name_01", headers=viewer_headers)
        assert resp.status_code == 200

    def test_validate_name_empty_rejected(self, test_client, viewer_headers):
        """空ユーザー名は 404 (FastAPI のパスルーティング)"""
        resp = test_client.get("/api/quotas/user/", headers=viewer_headers)
        # FastAPI returns 404 for missing path param or redirects
        assert resp.status_code in (307, 404, 405)

    def test_validate_groupname_special_chars_rejected(self, test_client, viewer_headers):
        """特殊文字を含むグループ名は拒否"""
        resp = test_client.get("/api/quotas/group/dev%20team", headers=viewer_headers)
        assert resp.status_code == 422


# ===================================================================
# QuotaSetRequest field_validator テスト
# ===================================================================

class TestQuotaSetRequestValidation:
    """QuotaSetRequest の field_validator 分岐"""

    def test_invalid_type_value(self, test_client, admin_headers):
        """type が 'user' でも 'group' でもない場合"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "system",
                "name": "testuser",
                "filesystem": "/",
                "soft_kb": 100,
                "hard_kb": 200,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_invalid_name_in_request_body(self, test_client, admin_headers):
        """リクエストボディの name がインジェクション"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "test$(whoami)",
                "filesystem": "/",
                "soft_kb": 100,
                "hard_kb": 200,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_invalid_filesystem_in_request_body(self, test_client, admin_headers):
        """リクエストボディの filesystem がインジェクション"""
        resp = test_client.post(
            "/api/quotas/set",
            json={
                "type": "user",
                "name": "testuser",
                "filesystem": "/tmp;ls",
                "soft_kb": 100,
                "hard_kb": 200,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_hard_kb_zero_with_positive_soft_allowed(self, test_client, admin_headers):
        """hard_kb=0 は soft_kb に関わらず許可 (v > 0 条件)"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.set_user_quota",
            return_value={"status": "success", "message": "Quota set"},
        ):
            resp = test_client.post(
                "/api/quotas/set",
                json={
                    "type": "user",
                    "name": "testuser",
                    "filesystem": "/",
                    "soft_kb": 500,
                    "hard_kb": 0,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# parse_wrapper_result 経由の output パース分岐
# ===================================================================

class TestParseWrapperResultBranches:
    """parse_wrapper_result を通じた output JSON パース分岐"""

    def test_status_with_json_output(self, test_client, viewer_headers):
        """output が JSON 文字列の場合のパース"""
        json_output = json.dumps({"status": "ok", "timestamp": "2026-01-01T00:00:00"})
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value={"status": "success", "output": json_output},
        ):
            resp = test_client.get("/api/quotas/status", headers=viewer_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_status_with_non_json_output(self, test_client, viewer_headers):
        """output が JSON でない文字列の場合はそのまま返す"""
        with patch(
            "backend.api.routes.quotas.sudo_wrapper.get_quota_status",
            return_value={"status": "success", "output": "not json"},
        ):
            resp = test_client.get("/api/quotas/status", headers=viewer_headers)
        assert resp.status_code == 200
