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


# ==============================================================================
# _build_cron_description のパスカバレッジ（lines 333, 342, 346, 354, 357, 360-363）
# ==============================================================================


class TestCronBuildDescriptionPaths:
    """_build_cron_description の各分岐をカバーするテスト"""

    def test_every_minute_expression(self, test_client, auth_headers):
        """'* * * * *' → '毎分' (line 333)"""
        resp = test_client.get(
            "/api/cron/validate?expression=*+*+*+*+*",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "毎分" in data["description"]

    def test_every_sunday_expression(self, test_client, auth_headers):
        """'0 0 * * 0' → '毎週日曜 0:00' (line 342)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+0+*+*+0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_yearly_expression(self, test_client, auth_headers):
        """'0 0 1 1 *' → '毎年1月1日 0:00' (line 346)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+0+1+1+*",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_expression_with_month(self, test_client, auth_headers):
        """月フィールドあり → _describe_cron_field 呼び出し (line 354)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+0+*+6+*",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_expression_with_day(self, test_client, auth_headers):
        """日フィールドあり → _describe_cron_field 呼び出し (line 357)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+12+15+*+*",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_expression_with_weekday_single_digit(self, test_client, auth_headers):
        """曜日が単一数字 (<=6) → WEEKDAY_NAMES を使用 (lines 360-361)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+*+*+*+3",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert "水曜日" in data["description"]

    def test_expression_with_weekday_range(self, test_client, auth_headers):
        """曜日が範囲形式 → _describe_cron_field 呼び出し (line 363)"""
        resp = test_client.get(
            "/api/cron/validate?expression=0+*+*+*+1-5",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True


# ==============================================================================
# _describe_cron_field のユニットテスト（lines 312, 314-315, 318-323）
# ==============================================================================


class TestDescribeCronField:
    """_describe_cron_field 関数の各分岐をカバーするユニットテスト"""

    def test_wildcard_returns_all_label(self):
        """value='*' → 'すべての{field_name}' (line 312)"""
        from backend.api.routes.cron import _describe_cron_field

        result = _describe_cron_field("*", "分", "分", 59)
        assert result == "すべての分"

    def test_step_value_returns_interval(self):
        """value='*/5' → '5分ごと' (lines 314-315)"""
        from backend.api.routes.cron import _describe_cron_field

        result = _describe_cron_field("*/5", "分", "分", 59)
        assert result == "5分ごと"

    def test_comma_value_returns_list(self):
        """value='1,3,5' → '{field_name} 1,3,5' (lines 318-319)"""
        from backend.api.routes.cron import _describe_cron_field

        result = _describe_cron_field("1,3,5", "日", "日", 31)
        assert "1,3,5" in result

    def test_range_value_returns_range_description(self):
        """value='1-5' → '{field_name}1〜5' (lines 320-322)"""
        from backend.api.routes.cron import _describe_cron_field

        result = _describe_cron_field("1-5", "月", "ヶ月", 12)
        assert "1" in result and "5" in result

    def test_unrecognized_value_returns_raw(self):
        """認識できない値 → そのまま返す (line 323)"""
        from backend.api.routes.cron import _describe_cron_field

        result = _describe_cron_field("L", "日", "日", 31)
        assert result == "L"
