"""
GET /api/cron/validate エンドポイントの統合テスト

cron式バリデーション: 正常系・異常系・セキュリティ
"""

import pytest


class TestCronValidateEndpoint:
    """GET /api/cron/validate — cron式バリデーション"""

    def test_valid_every_5_minutes(self, test_client, auth_headers):
        """*/5 * * * * は valid=true を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "description" in data
        assert data["description"]  # 空文字でないこと

    def test_valid_daily_midnight(self, test_client, auth_headers):
        """0 0 * * * (毎日0時) は valid=true を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "毎日" in data["description"] or "0" in data["description"]

    def test_valid_every_hour(self, test_client, auth_headers):
        """0 * * * * (毎時) は valid=true を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 * * * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_valid_monthly(self, test_client, auth_headers):
        """0 0 1 * * (毎月1日) は valid=true を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 1 * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_invalid_expression_wrong_field_count(self, test_client, auth_headers):
        """フィールド数が5でない式は valid=false を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "description" in data

    def test_invalid_expression_bad_chars_in_field(self, test_client, auth_headers):
        """無効な文字を含むフィールドは valid=false を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "abc * * * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_invalid_out_of_range_minute(self, test_client, auth_headers):
        """分フィールドが範囲外 (60) は valid=false を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "60 * * * *"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_forbidden_chars_semicolon(self, test_client, auth_headers):
        """; を含む式は 400 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": ";rm -rf /"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_forbidden_chars_pipe(self, test_client, auth_headers):
        """| を含む式は 400 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * * | ls"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_forbidden_chars_ampersand(self, test_client, auth_headers):
        """& を含む式は 400 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * *&ls"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_forbidden_chars_backtick(self, test_client, auth_headers):
        """バッククォートを含む式は 400 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "`id`"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_missing_expression_returns_422(self, test_client, auth_headers):
        """expression パラメータなしは 422 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_unauthenticated_returns_403(self, test_client):
        """認証なしは 403 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * *"},
        )
        assert response.status_code == 403

    def test_viewer_can_validate(self, test_client, viewer_headers):
        """viewer ロールは read:cron 権限でバリデーション可能なこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 2 * * *"},
            headers=viewer_headers,
        )
        assert response.status_code == 200

    def test_response_contains_expression_field(self, test_client, auth_headers):
        """レスポンスに expression フィールドが含まれること"""
        expr = "*/10 * * * *"
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": expr},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["expression"] == expr

    def test_inject_dollar_sign(self, test_client, auth_headers):
        """$ を含む式は 400 を返すこと"""
        response = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * *$VAR"},
            headers=auth_headers,
        )
        assert response.status_code == 400
