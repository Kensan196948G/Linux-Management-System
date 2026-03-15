"""
Cron API カバレッジ改善テスト v2

未カバー行を重点的にカバー:
- Line 225: validate_arguments_safe で arguments=None の分岐
- Line 243: validate_comment_safe で comment=None の分岐
- Lines 307-319: _describe_cron_field の各分岐
- Lines 324-366: _build_cron_description の各パターン
- Lines 393-441: validate_cron_expression エンドポイント全分岐
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.api.routes.cron import (
    AddCronJobRequest,
    CronJobActionResponse,
    CronJobInfo,
    CronJobListResponse,
    RemoveCronJobRequest,
    ToggleCronJobRequest,
    _build_cron_description,
    _describe_cron_field,
)
from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# _describe_cron_field ユニットテスト (Lines 307-319)
# ===================================================================


class TestDescribeCronFieldCoverage:
    """_describe_cron_field の全分岐カバレッジ"""

    def test_wildcard(self):
        """'*' → 'すべての{field_name}' (line 308)"""
        assert _describe_cron_field("*", "分", "分", 59) == "すべての分"

    def test_step_interval(self):
        """'*/10' → '10分ごと' (lines 309-311)"""
        result = _describe_cron_field("*/10", "分", "分", 59)
        assert result == "10分ごと"

    def test_single_number(self):
        """'5' → '分5' (lines 312-313)"""
        result = _describe_cron_field("5", "分", "分", 59)
        assert result == "分5"

    def test_comma_list(self):
        """'1,3,5' → '分 1,3,5' (lines 314-315)"""
        result = _describe_cron_field("1,3,5", "分", "分", 59)
        assert result == "分 1,3,5"

    def test_range(self):
        """'1-5' → '分1〜5' (lines 316-318)"""
        result = _describe_cron_field("1-5", "分", "分", 59)
        assert result == "分1〜5"

    def test_fallback_unknown(self):
        """認識不能な値 → そのまま返す (line 319)"""
        result = _describe_cron_field("W", "日", "日", 31)
        assert result == "W"

    def test_step_interval_hour(self):
        """'*/2' for hour → '2時間ごと'"""
        result = _describe_cron_field("*/2", "時", "時間", 23)
        assert result == "2時間ごと"

    def test_single_number_hour(self):
        """'12' for hour → '時12'"""
        result = _describe_cron_field("12", "時", "時間", 23)
        assert result == "時12"


# ===================================================================
# _build_cron_description ユニットテスト (Lines 324-366)
# ===================================================================


class TestBuildCronDescriptionCoverage:
    """_build_cron_description の全分岐カバレッジ"""

    def test_every_minute(self):
        """'* * * * *' → '毎分' (line 329)"""
        assert _build_cron_description("* * * * *") == "毎分"

    def test_every_n_minutes(self):
        """'*/5 * * * *' → '5分ごと' (lines 330-332)"""
        assert _build_cron_description("*/5 * * * *") == "5分ごと"

    def test_every_10_minutes(self):
        """'*/10 * * * *' → '10分ごと'"""
        assert _build_cron_description("*/10 * * * *") == "10分ごと"

    def test_every_hour(self):
        """'0 * * * *' → '毎時0分' (lines 333-334)"""
        assert _build_cron_description("0 * * * *") == "毎時0分"

    def test_daily_midnight(self):
        """'0 0 * * *' → '毎日 0:00' (lines 335-336)"""
        assert _build_cron_description("0 0 * * *") == "毎日 0:00"

    def test_weekly_sunday(self):
        """'0 0 * * 0' → '毎週日曜 0:00' (lines 337-338)"""
        assert _build_cron_description("0 0 * * 0") == "毎週日曜 0:00"

    def test_monthly_first(self):
        """'0 0 1 * *' → '毎月1日 0:00' (lines 339-340)"""
        assert _build_cron_description("0 0 1 * *") == "毎月1日 0:00"

    def test_yearly(self):
        """'0 0 1 1 *' → '毎年1月1日 0:00' (lines 341-342)"""
        assert _build_cron_description("0 0 1 1 *") == "毎年1月1日 0:00"

    def test_with_month_field(self):
        """月フィールドが * 以外 (line 349-350)"""
        result = _build_cron_description("0 0 * 6 *")
        assert "月" in result

    def test_with_day_field(self):
        """日フィールドが * 以外 (lines 352-353)"""
        result = _build_cron_description("0 12 15 * *")
        assert "日" in result

    def test_weekday_single_digit_within_range(self):
        """曜日が単一数字 <=6 → WEEKDAY_NAMES 使用 (lines 355-357)"""
        result = _build_cron_description("0 * * * 3")
        assert "水曜日" in result

    def test_weekday_sunday(self):
        """曜日 0 → 日曜日"""
        result = _build_cron_description("30 2 * * 0")
        assert "日曜日" in result

    def test_weekday_saturday(self):
        """曜日 6 → 土曜日"""
        result = _build_cron_description("30 2 * * 6")
        assert "土曜日" in result

    def test_weekday_non_single_digit(self):
        """曜日がカンマ形式 → _describe_cron_field 呼び出し (lines 358-359)"""
        result = _build_cron_description("0 * * * 1,3,5")
        assert "曜日" in result

    def test_weekday_range(self):
        """曜日が範囲形式 → _describe_cron_field 呼び出し"""
        result = _build_cron_description("0 * * * 1-5")
        assert "曜日" in result

    def test_hour_field_specific(self):
        """時フィールドが * 以外 (lines 361-362)"""
        result = _build_cron_description("30 14 * * *")
        assert "時" in result

    def test_minute_field_always_added(self):
        """分フィールドは常に parts に追加される (line 364)"""
        result = _build_cron_description("30 * * * *")
        assert "分" in result

    def test_all_fields_specified(self):
        """全フィールド指定時の結合 (line 366)"""
        result = _build_cron_description("30 14 15 6 3")
        assert "月" in result
        assert "日" in result
        assert "水曜日" in result
        assert "時" in result
        assert "分" in result

    def test_month_step(self):
        """月フィールドにステップ値"""
        result = _build_cron_description("0 0 1 */3 *")
        assert "ヶ月" in result or "月" in result

    def test_day_range(self):
        """日フィールドに範囲"""
        result = _build_cron_description("0 0 1-15 * *")
        assert "日" in result


# ===================================================================
# AddCronJobRequest バリデーション (Lines 225, 243)
# ===================================================================


class TestAddCronJobRequestValidation:
    """AddCronJobRequest の Pydantic バリデーション分岐カバレッジ"""

    def test_arguments_none_returns_none(self):
        """arguments=None → None を返す (line 225)"""
        req = AddCronJobRequest(
            schedule="0 2 * * *",
            command="/usr/bin/rsync",
            arguments=None,
            comment="test",
        )
        assert req.arguments is None

    def test_comment_none_returns_none(self):
        """comment=None → None を返す (line 243)"""
        req = AddCronJobRequest(
            schedule="0 2 * * *",
            command="/usr/bin/rsync",
            arguments="/src/",
            comment=None,
        )
        assert req.comment is None

    def test_both_none(self):
        """arguments と comment が両方 None"""
        req = AddCronJobRequest(
            schedule="0 2 * * *",
            command="/usr/bin/rsync",
        )
        assert req.arguments is None
        assert req.comment is None

    def test_arguments_with_forbidden_char(self):
        """引数に禁止文字が含まれる場合は拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/usr/bin/rsync",
                arguments="/src/;rm -rf /",
            )

    def test_arguments_with_path_traversal(self):
        """引数にパストラバーサルが含まれる場合は拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/usr/bin/rsync",
                arguments="/src/../../etc/passwd",
            )

    def test_comment_with_forbidden_char(self):
        """コメントに禁止文字が含まれる場合は拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/usr/bin/rsync",
                comment="test; evil",
            )

    def test_valid_arguments_and_comment(self):
        """正常な引数とコメント"""
        req = AddCronJobRequest(
            schedule="0 2 * * *",
            command="/usr/bin/rsync",
            arguments="-av /src/ /dst/",
            comment="Daily backup sync",
        )
        assert req.arguments == "-av /src/ /dst/"
        assert req.comment == "Daily backup sync"

    def test_schedule_with_forbidden_char(self):
        """スケジュールに禁止文字"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *;ls",
                command="/usr/bin/rsync",
            )

    def test_schedule_wrong_field_count(self):
        """スケジュールのフィールド数が不正"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * *",
                command="/usr/bin/rsync",
            )

    def test_schedule_every_minute_rejected(self):
        """毎分実行 (* ) は拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="* * * * *",
                command="/usr/bin/rsync",
            )

    def test_schedule_too_short_interval(self):
        """*/1 ~ */4 は拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="*/3 * * * *",
                command="/usr/bin/rsync",
            )

    def test_command_not_absolute_path(self):
        """相対パスは拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="rsync",
            )

    def test_command_forbidden(self):
        """禁止コマンドは拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/bin/rm",
            )

    def test_command_not_in_allowlist(self):
        """allowlist にないコマンドは拒否"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/usr/bin/htop",
            )

    def test_command_with_special_chars(self):
        """コマンドに特殊文字"""
        with pytest.raises(Exception):
            AddCronJobRequest(
                schedule="0 2 * * *",
                command="/usr/bin/rsync|cat",
            )


# ===================================================================
# validate_cron_expression エンドポイント (Lines 393-441)
# ===================================================================


class TestValidateCronExpressionEndpoint:
    """GET /api/cron/validate のカバレッジ改善テスト"""

    def test_forbidden_char_semicolon(self, test_client, auth_headers):
        """禁止文字 ; → 400 (lines 393-398)"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * *;ls"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Forbidden" in resp.json().get("detail", resp.json().get("message", ""))

    def test_forbidden_char_pipe(self, test_client, auth_headers):
        """禁止文字 | → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * *|ls"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_ampersand(self, test_client, auth_headers):
        """禁止文字 & → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * *&ls"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_dollar(self, test_client, auth_headers):
        """禁止文字 $ → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "$HOME"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_parentheses(self, test_client, auth_headers):
        """禁止文字 ( → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "(cmd)"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_backtick(self, test_client, auth_headers):
        """禁止文字 ` → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "`id`"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_angle_bracket(self, test_client, auth_headers):
        """禁止文字 > → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * * > /tmp/out"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_less_than(self, test_client, auth_headers):
        """禁止文字 < → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * * < /tmp/in"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_curly_brace(self, test_client, auth_headers):
        """禁止文字 { → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * * {cmd}"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_forbidden_char_square_bracket(self, test_client, auth_headers):
        """禁止文字 [ → 400"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * * [cmd]"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_wrong_field_count_one(self, test_client, auth_headers):
        """1フィールド → valid=false (lines 401-407)"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "invalid"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "5フィールド" in data["description"]

    def test_wrong_field_count_three(self, test_client, auth_headers):
        """3フィールド → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_wrong_field_count_six(self, test_client, auth_headers):
        """6フィールド → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_invalid_chars_in_minute_field(self, test_client, auth_headers):
        """分フィールドに無効文字 → valid=false (lines 411-417)"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "abc * * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "分" in data["description"]

    def test_invalid_chars_in_hour_field(self, test_client, auth_headers):
        """時フィールドに無効文字 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 xyz * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "時" in data["description"]

    def test_invalid_chars_in_day_field(self, test_client, auth_headers):
        """日フィールドに無効文字 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 abc * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "日" in data["description"]

    def test_invalid_chars_in_month_field(self, test_client, auth_headers):
        """月フィールドに無効文字 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * JAN *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "月" in data["description"]

    def test_invalid_chars_in_weekday_field(self, test_client, auth_headers):
        """曜日フィールドに無効文字 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * MON"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "曜日" in data["description"]

    def test_minute_out_of_range(self, test_client, auth_headers):
        """分が60 → valid=false (lines 427-435)"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "60 * * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_hour_out_of_range(self, test_client, auth_headers):
        """時が24 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 24 * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_day_out_of_range(self, test_client, auth_headers):
        """日が32 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 32 * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_day_zero_out_of_range(self, test_client, auth_headers):
        """日が0 → valid=false（日は1-31）"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 0 * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_month_out_of_range(self, test_client, auth_headers):
        """月が13 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 1 13 *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_month_zero_out_of_range(self, test_client, auth_headers):
        """月が0 → valid=false（月は1-12）"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 1 0 *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_weekday_out_of_range(self, test_client, auth_headers):
        """曜日が8 → valid=false"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * 8"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "範囲外" in data["description"]

    def test_valid_expression_returns_description(self, test_client, auth_headers):
        """有効な式 → valid=true + description (lines 437-445)"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/5 * * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["description"] == "5分ごと"
        assert data["expression"] == "*/5 * * * *"

    def test_valid_complex_expression(self, test_client, auth_headers):
        """複合式 → valid=true"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "30 14 15 6 3"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert len(data["description"]) > 0

    def test_valid_with_ranges_and_steps(self, test_client, auth_headers):
        """範囲とステップを含む式 → valid=true"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "*/15 0 1-15 */2 *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_valid_with_comma_list(self, test_client, auth_headers):
        """カンマリスト → valid=true"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0,30 * * * *"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_valid_weekday_7_as_sunday(self, test_client, auth_headers):
        """曜日7 → valid=true（7は日曜として許可）"""
        resp = test_client.get(
            "/api/cron/validate",
            params={"expression": "0 0 * * 7"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True


# ===================================================================
# エンドポイント mock テスト: sudo_wrapper の各分岐
# ===================================================================


class TestListCronJobsMocked:
    """GET /api/cron/{username} の sudo_wrapper モックテスト"""

    def test_list_success(self, test_client, auth_headers):
        """正常応答 (line 535)"""
        mock_result = {
            "status": "success",
            "user": "testuser",
            "jobs": [],
            "total_count": 0,
            "max_allowed": 10,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["total_count"] == 0

    def test_list_error_invalid_username(self, test_client, auth_headers):
        """INVALID_USERNAME → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Invalid username",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 400

    def test_list_error_invalid_args(self, test_client, auth_headers):
        """INVALID_ARGS → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "INVALID_ARGS",
                "message": "Invalid arguments",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 400

    def test_list_error_forbidden_user(self, test_client, auth_headers):
        """FORBIDDEN_USER → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "FORBIDDEN_USER",
                "message": "Forbidden user",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 403

    def test_list_error_forbidden_chars(self, test_client, auth_headers):
        """FORBIDDEN_CHARS → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "FORBIDDEN_CHARS",
                "message": "Forbidden chars",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 403

    def test_list_error_user_not_found(self, test_client, auth_headers):
        """USER_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 404

    def test_list_error_unknown_code(self, test_client, auth_headers):
        """未知のエラーコード → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = {
                "status": "error",
                "code": "UNKNOWN_ERROR",
                "message": "Something went wrong",
            }
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 500

    def test_list_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError → 500 (lines 537-551)"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 500
            body = resp.json()
            msg = body.get("detail", body.get("message", ""))
            assert "failed" in msg or "wrapper" in msg

    def test_list_with_jobs(self, test_client, auth_headers):
        """ジョブあり"""
        mock_result = {
            "status": "success",
            "user": "testuser",
            "jobs": [
                {
                    "id": "job-1",
                    "line_number": 1,
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                    "arguments": "-av /src/ /dst/",
                    "comment": "backup",
                    "enabled": True,
                }
            ],
            "total_count": 1,
            "max_allowed": 10,
        }
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.list_cron_jobs.return_value = mock_result
            resp = test_client.get("/api/cron/testuser", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_count"] == 1
            assert len(data["jobs"]) == 1


class TestAddCronJobMocked:
    """POST /api/cron/{username} の sudo_wrapper モックテスト"""

    def _valid_payload(self):
        return {
            "schedule": "0 2 * * *",
            "command": "/usr/bin/rsync",
            "arguments": "-av /src/ /dst/",
            "comment": "Daily backup",
        }

    def test_add_success(self, test_client, auth_headers):
        """正常追加"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "success",
                "message": "Cron job added",
                "total_jobs": 1,
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_add_no_arguments_no_comment(self, test_client, auth_headers):
        """arguments/comment なし → None 分岐 (lines 225, 243)"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "success",
                "message": "Cron job added",
                "total_jobs": 1,
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json={
                    "schedule": "0 2 * * *",
                    "command": "/usr/bin/rsync",
                },
                headers=auth_headers,
            )
            assert resp.status_code == 200
            # sudo_wrapper.add_cron_job に空文字が渡されることを確認
            call_kwargs = mock_sw.add_cron_job.call_args
            assert call_kwargs[1]["arguments"] == "" or call_kwargs.kwargs.get("arguments") == ""

    def test_add_error_invalid_schedule(self, test_client, auth_headers):
        """INVALID_SCHEDULE → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "INVALID_SCHEDULE",
                "message": "Invalid schedule",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 400

    def test_add_error_invalid_command(self, test_client, auth_headers):
        """INVALID_COMMAND → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "INVALID_COMMAND",
                "message": "Invalid command",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 400

    def test_add_error_path_traversal(self, test_client, auth_headers):
        """PATH_TRAVERSAL → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "PATH_TRAVERSAL",
                "message": "Path traversal detected",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 400

    def test_add_error_forbidden_command(self, test_client, auth_headers):
        """FORBIDDEN_COMMAND → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "FORBIDDEN_COMMAND",
                "message": "Forbidden command",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 403

    def test_add_error_command_not_allowed(self, test_client, auth_headers):
        """COMMAND_NOT_ALLOWED → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "COMMAND_NOT_ALLOWED",
                "message": "Command not allowed",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 403

    def test_add_error_user_not_found(self, test_client, auth_headers):
        """USER_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 404

    def test_add_error_max_jobs_exceeded(self, test_client, auth_headers):
        """MAX_JOBS_EXCEEDED → 409"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "MAX_JOBS_EXCEEDED",
                "message": "Max jobs exceeded",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 409

    def test_add_error_duplicate_job(self, test_client, auth_headers):
        """DUPLICATE_JOB → 409"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "DUPLICATE_JOB",
                "message": "Duplicate job",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 409

    def test_add_error_unknown_code(self, test_client, auth_headers):
        """未知のエラーコード → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.return_value = {
                "status": "error",
                "code": "INTERNAL_ERROR",
                "message": "Internal error",
            }
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 500

    def test_add_sudo_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.add_cron_job.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.post(
                "/api/cron/testuser",
                json=self._valid_payload(),
                headers=auth_headers,
            )
            assert resp.status_code == 500

    def test_add_invalid_username(self, test_client, auth_headers):
        """不正なユーザー名 → 400"""
        resp = test_client.post(
            "/api/cron/root",
            json=self._valid_payload(),
            headers=auth_headers,
        )
        assert resp.status_code in [400, 403]


class TestRemoveCronJobMocked:
    """DELETE /api/cron/{username} の sudo_wrapper モックテスト"""

    def test_remove_success(self, test_client, admin_headers):
        """正常削除"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "success",
                "message": "Cron job disabled",
                "remaining_jobs": 0,
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_remove_error_invalid_line_number(self, test_client, admin_headers):
        """INVALID_LINE_NUMBER → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "INVALID_LINE_NUMBER",
                "message": "Invalid line number",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_remove_error_not_a_job(self, test_client, admin_headers):
        """NOT_A_JOB → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "NOT_A_JOB",
                "message": "Not a job line",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_remove_error_already_disabled(self, test_client, admin_headers):
        """ALREADY_DISABLED → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "ALREADY_DISABLED",
                "message": "Already disabled",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_remove_error_forbidden_user(self, test_client, admin_headers):
        """FORBIDDEN_USER → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "FORBIDDEN_USER",
                "message": "Forbidden user",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 403

    def test_remove_error_user_not_found(self, test_client, admin_headers):
        """USER_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 404

    def test_remove_error_line_not_found(self, test_client, admin_headers):
        """LINE_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "LINE_NOT_FOUND",
                "message": "Line not found",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 404

    def test_remove_error_unknown_code(self, test_client, admin_headers):
        """未知のエラーコード → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.return_value = {
                "status": "error",
                "code": "UNKNOWN",
                "message": "Unknown error",
            }
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 500

    def test_remove_sudo_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.remove_cron_job.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.request(
                "DELETE",
                "/api/cron/testuser",
                json={"line_number": 1},
                headers=admin_headers,
            )
            assert resp.status_code == 500


class TestToggleCronJobMocked:
    """PUT /api/cron/{username}/toggle の sudo_wrapper モックテスト"""

    def test_toggle_enable_success(self, test_client, admin_headers):
        """有効化成功"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "success",
                "message": "Cron job enabled",
                "active_jobs": 1,
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    def test_toggle_disable_success(self, test_client, admin_headers):
        """無効化成功"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "success",
                "message": "Cron job disabled",
                "active_jobs": 0,
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": False},
                headers=admin_headers,
            )
            assert resp.status_code == 200

    def test_toggle_error_already_enabled(self, test_client, admin_headers):
        """ALREADY_ENABLED → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "ALREADY_ENABLED",
                "message": "Already enabled",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_toggle_error_already_disabled(self, test_client, admin_headers):
        """ALREADY_DISABLED → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "ALREADY_DISABLED",
                "message": "Already disabled",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": False},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_toggle_error_not_adminui_comment(self, test_client, admin_headers):
        """NOT_ADMINUI_COMMENT → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "NOT_ADMINUI_COMMENT",
                "message": "Not an admin UI comment",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_toggle_error_parse_error(self, test_client, admin_headers):
        """PARSE_ERROR → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "PARSE_ERROR",
                "message": "Parse error",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_toggle_error_invalid_schedule(self, test_client, admin_headers):
        """INVALID_SCHEDULE → 400"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "INVALID_SCHEDULE",
                "message": "Invalid schedule",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_toggle_error_command_not_allowed(self, test_client, admin_headers):
        """COMMAND_NOT_ALLOWED → 403"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "COMMAND_NOT_ALLOWED",
                "message": "Command not allowed",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 403

    def test_toggle_error_user_not_found(self, test_client, admin_headers):
        """USER_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "USER_NOT_FOUND",
                "message": "User not found",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 404

    def test_toggle_error_line_not_found(self, test_client, admin_headers):
        """LINE_NOT_FOUND → 404"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "LINE_NOT_FOUND",
                "message": "Line not found",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 404

    def test_toggle_error_max_jobs_exceeded(self, test_client, admin_headers):
        """MAX_JOBS_EXCEEDED → 409"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "MAX_JOBS_EXCEEDED",
                "message": "Max jobs exceeded",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 409

    def test_toggle_error_unknown_code(self, test_client, admin_headers):
        """未知のエラーコード → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.return_value = {
                "status": "error",
                "code": "UNKNOWN",
                "message": "Unknown error",
            }
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 500

    def test_toggle_sudo_wrapper_error(self, test_client, admin_headers):
        """SudoWrapperError → 500"""
        with patch("backend.api.routes.cron.sudo_wrapper") as mock_sw:
            mock_sw.toggle_cron_job.side_effect = SudoWrapperError("wrapper failed")
            resp = test_client.put(
                "/api/cron/testuser/toggle",
                json={"line_number": 1, "enabled": True},
                headers=admin_headers,
            )
            assert resp.status_code == 500

    def test_toggle_invalid_username(self, test_client, admin_headers):
        """不正なユーザー名 → 400"""
        resp = test_client.put(
            "/api/cron/root/toggle",
            json={"line_number": 1, "enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code in [400, 403]
