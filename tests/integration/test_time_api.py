"""
System Time 管理モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）

テストケース数: 18件
- 正常系: 時刻状態取得、タイムゾーン一覧、タイムゾーン変更
- 異常系: 権限不足、未認証、無効なタイムゾーン名
- セキュリティ: インジェクション攻撃、パストラバーサル攻撃
"""

from unittest.mock import patch

import pytest

# ===================================================================
# テストデータ
# ===================================================================

SAMPLE_TIME_STATUS = {
    "status": "ok",
    "data": {
        "system_time": "2026-02-27T18:00:00+09:00",
        "utc_time": "2026-02-27T09:00:00+00:00",
        "timezone": "Asia/Tokyo",
        "ntp_synchronized": "yes",
        "ntp_service": "chrony",
        "rtc_time": "2026-02-27T09:00:00+00:00",
    },
}

SAMPLE_TIMEZONES = {
    "status": "ok",
    "data": {
        "timezones": [
            "Africa/Abidjan",
            "America/New_York",
            "Asia/Tokyo",
            "Europe/London",
            "UTC",
        ]
    },
}

SAMPLE_TZ_SET_RESULT = {
    "status": "ok",
    "data": {
        "message": "Timezone set to Asia/Tokyo",
        "timezone": "Asia/Tokyo",
    },
}


# ===================================================================
# テストクラス
# ===================================================================


class TestTimeStatusAPI:
    """GET /api/time/status のテスト"""

    def test_get_time_status_viewer(self, test_client, viewer_token):
        """TC001: Viewer ロールで時刻状態取得成功"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_TIME_STATUS,
        ):
            resp = test_client.get(
                "/api/time/status",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_get_time_status_operator(self, test_client, auth_headers):
        """TC002: Operator ロールで時刻状態取得成功"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_TIME_STATUS,
        ):
            resp = test_client.get("/api/time/status", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_time_status_admin(self, test_client, admin_token):
        """TC003: Admin ロールで時刻状態取得成功"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_TIME_STATUS,
        ):
            resp = test_client.get(
                "/api/time/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200

    def test_get_time_status_unauthorized(self, test_client):
        """TC004: 未認証でアクセス拒否"""
        resp = test_client.get("/api/time/status")
        assert resp.status_code in (401, 403)

    def test_get_time_status_response_structure(self, test_client, auth_headers):
        """TC005: レスポンス構造確認（timezone, ntp_synchronized 等）"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            return_value=SAMPLE_TIME_STATUS,
        ):
            resp = test_client.get("/api/time/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "timezone" in data["data"]
        assert "ntp_synchronized" in data["data"]
        assert "system_time" in data["data"]


class TestTimezonesAPI:
    """GET /api/time/timezones のテスト"""

    def test_list_timezones_success(self, test_client, auth_headers):
        """TC006: タイムゾーン一覧取得成功"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_timezones",
            return_value=SAMPLE_TIMEZONES,
        ):
            resp = test_client.get("/api/time/timezones", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "timezones" in data["data"]

    def test_list_timezones_viewer(self, test_client, viewer_token):
        """TC007: Viewer ロールでタイムゾーン一覧取得可能"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_timezones",
            return_value=SAMPLE_TIMEZONES,
        ):
            resp = test_client.get(
                "/api/time/timezones",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
        assert resp.status_code == 200

    def test_list_timezones_unauthorized(self, test_client):
        """TC008: 未認証でアクセス拒否"""
        resp = test_client.get("/api/time/timezones")
        assert resp.status_code in (401, 403)


class TestSetTimezoneAPI:
    """POST /api/time/timezone のテスト"""

    def test_set_timezone_admin_success(self, test_client, admin_token):
        """TC009: Admin ロールでタイムゾーン変更成功"""
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.set_timezone",
            return_value=SAMPLE_TZ_SET_RESULT,
        ):
            resp = test_client.post(
                "/api/time/timezone",
                json={"timezone": "Asia/Tokyo", "reason": "JST に変更するため"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["timezone"] == "Asia/Tokyo"

    def test_set_timezone_forbidden_operator(self, test_client, auth_headers):
        """TC010: Operator ロールはタイムゾーン変更不可"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "テスト"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_set_timezone_forbidden_viewer(self, test_client, viewer_token):
        """TC011: Viewer ロールはタイムゾーン変更不可"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "テスト"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    def test_set_timezone_invalid_format(self, test_client, admin_token):
        """TC012: 無効なタイムゾーン名形式は拒否（バリデーションエラー）"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "INVALID TIMEZONE", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_timezone_injection_semicolon(self, test_client, admin_token):
        """TC013: セミコロンを含むインジェクション攻撃は拒否"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/Tokyo; rm -rf /", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_timezone_path_traversal(self, test_client, admin_token):
        """TC014: パストラバーサル攻撃は拒否"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "../../etc/passwd", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_timezone_injection_backtick(self, test_client, admin_token):
        """TC015: バッククォートを含むインジェクション攻撃は拒否"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/`id`", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_timezone_empty_reason(self, test_client, admin_token):
        """TC016: 理由が空の場合はバリデーションエラー"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/Tokyo", "reason": ""},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_set_timezone_unauthorized(self, test_client):
        """TC017: 未認証は拒否"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC", "reason": "テスト"},
        )
        assert resp.status_code in (401, 403)

    def test_set_timezone_utc_success(self, test_client, admin_token):
        """TC018: UTC タイムゾーン設定成功"""
        utc_result = {"status": "ok", "data": {"message": "Timezone set to UTC", "timezone": "UTC"}}
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.set_timezone",
            return_value=utc_result,
        ):
            resp = test_client.post(
                "/api/time/timezone",
                json={"timezone": "UTC", "reason": "UTC に変更"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["timezone"] == "UTC"


class TestTimeErrorPaths:
    """system_time.py エラーパスカバレッジ向上"""

    def test_status_wrapper_error(self, test_client, admin_token):
        """time status SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_time_status",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/time/status",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_timezones_wrapper_error(self, test_client, admin_token):
        """timezones SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.get_timezones",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.get(
                "/api/time/timezones",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_set_timezone_wrapper_error(self, test_client, admin_token):
        """set timezone SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch(
            "backend.api.routes.system_time.sudo_wrapper.set_timezone",
            side_effect=SudoWrapperError("failed"),
        ):
            resp = test_client.post(
                "/api/time/timezone",
                json={"timezone": "UTC", "reason": "テスト"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 500

    def test_timezone_invalid_format(self, test_client, admin_token):
        """タイムゾーン名に無効文字が含まれる場合 422"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "UTC; rm -rf /", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    def test_timezone_path_traversal(self, test_client, admin_token):
        """タイムゾーン名にパストラバーサルが含まれる場合 422"""
        resp = test_client.post(
            "/api/time/timezone",
            json={"timezone": "Asia/../etc/passwd", "reason": "テスト"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422
