"""
logs.py カバレッジ改善テスト v3

v2 でカバー済みの分岐を避け、未カバー行を重点的にテスト:
- GET /api/logs/search (GET): SudoWrapperError の Forbidden character パス (line 315-319)
- GET /api/logs/search (GET): SudoWrapperError 非Forbidden パス (lines 320-331)
- GET /api/logs/search (GET): sudo_wrapper.search_logs がエラーステータスを返すパス (lines 291-302)
- GET /api/logs/files: 正常系・エラーステータス・SudoWrapperError パス
- GET /api/logs/recent-errors: 正常系・エラーステータス・SudoWrapperError パス
- GET /api/logs/{service_name}: エラーステータス返却パス (lines 888-901)
- GET /api/logs/{service_name}: SudoWrapperError パス (lines 916-931)
- POST /api/logs/search: PermissionError パス (lines 497-499)
- POST /api/logs/search: allowlist外ファイル拒否 (lines 461-466)
- POST /api/logs/search: regex モードでの禁止文字通過
- POST /api/logs/search: 非regex モードでの禁止文字拒否
- GET /api/logs/stats: 大量行バッファの pop(0) ロジック (lines 589-590)
- GET /api/logs/timeline: 不正な日時 ValueError パス (line 688)
- GET /api/logs/timeline: 24時間外のログ除外 (lines 684)
- GET /api/logs/timeline: 非allowlistファイルスキップ (line 663)
- DELETE /api/logs/saved-filters/{id}: 存在しないフィルター (lines 833-837)
- GET /api/logs/saved-filters: 正常系
- POST /api/logs/saved-filters: allowlist外ファイル拒否 (lines 761-766)
- _validate_query の全禁止文字テスト
"""

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from backend.api.routes.logs import _validate_query
from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# _validate_query 禁止文字テスト（全文字網羅）
# ===================================================================


class TestValidateQueryAllChars:
    """_validate_query の全禁止文字テスト"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"])
    def test_forbidden_char_raises_400(self, char):
        """禁止文字 '{char}' が含まれると HTTPException(400) を送出"""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _validate_query(f"test{char}value")
        assert exc.value.status_code == 400

    def test_valid_query_passes(self):
        """禁止文字のない文字列は通過"""
        _validate_query("normal search text 123")


# ===================================================================
# GET /api/logs/search (GET method) テスト
# ===================================================================


class TestSearchLogsGetMethod:
    """GET /api/logs/search エンドポイントの分岐テスト"""

    def test_search_success(self, test_client, admin_headers):
        """正常系: sudo_wrapper.search_logs が成功結果を返す"""
        mock_result = {
            "status": "success",
            "matches": ["line1", "line2"],
            "lines_returned": 2,
        }
        with patch("backend.api.routes.logs.sudo_wrapper.search_logs", return_value=mock_result):
            resp = test_client.get("/api/logs/search?q=error&file=syslog&lines=50", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["lines_returned"] == 2

    def test_search_error_status_returns_400(self, test_client, admin_headers):
        """sudo_wrapper.search_logs がエラーステータスを返す場合 400 (lines 291-302)"""
        mock_result = {
            "status": "error",
            "message": "File not allowed",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.search_logs", return_value=mock_result):
            resp = test_client.get("/api/logs/search?q=error&file=syslog&lines=50", headers=admin_headers)
        assert resp.status_code == 400
        body = resp.json()
        assert "File not allowed" in body.get("detail", body.get("message", ""))

    def test_search_wrapper_forbidden_char_error(self, test_client, admin_headers):
        """SudoWrapperError に 'Forbidden character' が含まれる場合 400 (lines 315-319)"""
        with patch(
            "backend.api.routes.logs.sudo_wrapper.search_logs",
            side_effect=SudoWrapperError("Forbidden character in query"),
        ):
            resp = test_client.get("/api/logs/search?q=error&file=syslog", headers=admin_headers)
        assert resp.status_code == 400

    def test_search_wrapper_generic_error(self, test_client, admin_headers):
        """SudoWrapperError (非Forbidden) の場合 500 (lines 320-331)"""
        with patch(
            "backend.api.routes.logs.sudo_wrapper.search_logs",
            side_effect=SudoWrapperError("Command failed"),
        ):
            resp = test_client.get("/api/logs/search?q=error&file=syslog", headers=admin_headers)
        assert resp.status_code == 500

    def test_search_forbidden_char_in_query_rejected(self, test_client, admin_headers):
        """クエリに禁止文字が含まれる場合 400"""
        resp = test_client.get("/api/logs/search?q=test;rm&file=syslog", headers=admin_headers)
        assert resp.status_code == 400

    def test_search_forbidden_char_in_file_rejected(self, test_client, admin_headers):
        """ファイル名に禁止文字が含まれる場合 400"""
        resp = test_client.get("/api/logs/search?q=error&file=syslog|cat", headers=admin_headers)
        assert resp.status_code == 400

    def test_search_no_auth(self, test_client):
        """未認証で 403"""
        resp = test_client.get("/api/logs/search?q=test&file=syslog")
        assert resp.status_code == 403


# ===================================================================
# GET /api/logs/files テスト
# ===================================================================


class TestListLogFiles:
    """GET /api/logs/files エンドポイントの分岐テスト"""

    def test_files_success(self, test_client, admin_headers):
        """正常系: ファイル一覧を返す"""
        mock_result = {
            "status": "success",
            "files": ["/var/log/syslog", "/var/log/auth.log"],
            "file_count": 2,
        }
        with patch("backend.api.routes.logs.sudo_wrapper.list_log_files", return_value=mock_result):
            resp = test_client.get("/api/logs/files", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["file_count"] == 2

    def test_files_error_status_returns_500(self, test_client, admin_headers):
        """エラーステータスの場合 500 (lines 362-366)"""
        mock_result = {
            "status": "error",
            "message": "Cannot list files",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.list_log_files", return_value=mock_result):
            resp = test_client.get("/api/logs/files", headers=admin_headers)
        assert resp.status_code == 500

    def test_files_wrapper_error_returns_500(self, test_client, admin_headers):
        """SudoWrapperError で 500 (lines 378-383)"""
        with patch(
            "backend.api.routes.logs.sudo_wrapper.list_log_files",
            side_effect=SudoWrapperError("Permission denied"),
        ):
            resp = test_client.get("/api/logs/files", headers=admin_headers)
        assert resp.status_code == 500

    def test_files_no_auth(self, test_client):
        """未認証で 403"""
        resp = test_client.get("/api/logs/files")
        assert resp.status_code == 403


# ===================================================================
# GET /api/logs/recent-errors テスト
# ===================================================================


class TestRecentErrors:
    """GET /api/logs/recent-errors エンドポイントの分岐テスト"""

    def test_recent_errors_success(self, test_client, admin_headers):
        """正常系: エラーログを返す"""
        mock_result = {
            "status": "success",
            "errors": ["error1", "error2"],
            "error_count": 2,
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_recent_errors", return_value=mock_result):
            resp = test_client.get("/api/logs/recent-errors", headers=admin_headers)
        assert resp.status_code == 200

    def test_recent_errors_error_status_returns_500(self, test_client, admin_headers):
        """エラーステータスの場合 500 (lines 414-417)"""
        mock_result = {
            "status": "error",
            "message": "Failed to get errors",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_recent_errors", return_value=mock_result):
            resp = test_client.get("/api/logs/recent-errors", headers=admin_headers)
        assert resp.status_code == 500

    def test_recent_errors_wrapper_error_returns_500(self, test_client, admin_headers):
        """SudoWrapperError で 500 (lines 430-435)"""
        with patch(
            "backend.api.routes.logs.sudo_wrapper.get_recent_errors",
            side_effect=SudoWrapperError("read failed"),
        ):
            resp = test_client.get("/api/logs/recent-errors", headers=admin_headers)
        assert resp.status_code == 500

    def test_recent_errors_no_auth(self, test_client):
        """未認証で 403"""
        resp = test_client.get("/api/logs/recent-errors")
        assert resp.status_code == 403


# ===================================================================
# GET /api/logs/{service_name} 追加分岐テスト
# ===================================================================


class TestServiceLogsErrorPaths:
    """GET /api/logs/{service_name} のエラーパス"""

    def test_service_logs_error_status_returns_403(self, test_client, auth_headers):
        """sudo_wrapper がエラーステータスを返す場合 403 (lines 888-901)"""
        mock_result = {
            "status": "error",
            "message": "Service not in allowlist",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_logs", return_value=mock_result):
            resp = test_client.get("/api/logs/nginx?lines=50", headers=auth_headers)
        assert resp.status_code == 403

    def test_service_logs_wrapper_error_returns_500(self, test_client, auth_headers):
        """SudoWrapperError で 500 (lines 916-931)"""
        with patch(
            "backend.api.routes.logs.sudo_wrapper.get_logs",
            side_effect=SudoWrapperError("journalctl failed"),
        ):
            resp = test_client.get("/api/logs/nginx", headers=auth_headers)
        assert resp.status_code == 500


# ===================================================================
# POST /api/logs/search 追加分岐テスト
# ===================================================================


class TestAdvancedSearchAdditionalBranches:
    """POST /api/logs/search の追加分岐"""

    def test_allowlist_violation_returns_400(self, test_client, admin_headers):
        """allowlist 外のファイル指定で 400 (lines 461-466)"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test", "files": ["/etc/shadow"], "limit": 10},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "allowlist" in body.get("detail", body.get("message", ""))

    def test_permission_denied_adds_error_entry(self, test_client, admin_headers):
        """PermissionError でエラーエントリが追加されること (lines 497-499)"""
        original_open = open

        def permission_denied_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                raise PermissionError(f"Permission denied: {file}")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=permission_denied_open):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "test", "files": ["/var/log/syslog"], "limit": 10},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matches"] == 1
        assert "Permission denied" in data["results"][0]["message"]
        assert data["results"][0]["level"] == "ERROR"
        assert data["results"][0]["lineno"] == 0

    def test_regex_mode_with_forbidden_chars_passes(self, test_client, admin_headers):
        """regex モードでは禁止文字チェックをスキップ (line 125)"""
        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog",):
                return io.StringIO("test$pattern found here\n")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "test.*pattern", "files": ["/var/log/syslog"], "regex": True, "limit": 10},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_non_regex_mode_forbidden_char_rejected(self, test_client, admin_headers):
        """非regex モードで禁止文字が含まれると 400"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test;inject", "files": ["/var/log/syslog"], "regex": False, "limit": 10},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_from_time_to_time_fields_accepted(self, test_client, admin_headers):
        """from_time / to_time フィールドが受け付けられること"""
        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                return io.StringIO("test line\n")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "test",
                    "files": ["/var/log/syslog"],
                    "from_time": "2026-01-01T00:00:00",
                    "to_time": "2026-12-31T23:59:59",
                    "limit": 10,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# GET /api/logs/stats 追加テスト
# ===================================================================


class TestLogStatsAdditional:
    """GET /api/logs/stats のバッファ pop(0) ロジックテスト"""

    def test_stats_large_file_buffer_overflow(self, test_client, admin_headers, tmp_path):
        """5000行超のファイルで pop(0) が動作すること (lines 589-590)"""
        # 5002行のログ: 最初の行は ERROR、中間は INFO、最後は WARN
        lines = ["error first line\n"]
        lines += ["info normal line\n"] * 5000
        lines += ["warning last line\n"]
        log_content = "".join(lines)
        log_file = tmp_path / "big.log"
        log_file.write_text(log_content, encoding="utf-8")

        with patch("backend.api.routes.logs.ADVANCED_ALLOWED_LOG_FILES", [str(log_file)]):
            resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        per_file = data["per_file"][str(log_file)]
        # 最初の ERROR 行は pop(0) で消えるので、INFO+WARN のみ残る
        assert per_file["WARN"] >= 1
        assert per_file["INFO"] >= 1


# ===================================================================
# GET /api/logs/timeline 追加テスト
# ===================================================================


class TestLogTimelineAdditional:
    """GET /api/logs/timeline の追加分岐テスト"""

    def test_timeline_old_logs_excluded(self, test_client, admin_headers):
        """24時間より前のログは集計されないこと (line 684)"""
        # 30日前のタイムスタンプ
        old_date = datetime.now(timezone.utc) - timedelta(days=30)
        month_abbr = old_date.strftime("%b")
        day = old_date.day
        hour = old_date.hour

        log_content = f"{month_abbr}  {day} {hour:02d}:30:00 host kernel: error occurred\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # 古いログなのでカウントされない
        assert sum(data["datasets"][0]["data"]) == 0

    def test_timeline_invalid_datetime_skipped(self, test_client, admin_headers):
        """不正な日時で ValueError が発生した場合スキップ (line 688)"""
        # 存在しない日付: 2月30日
        log_content = "Feb 30 12:00:00 host kernel: error occurred\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        # ValueError でスキップされるので 0
        assert sum(resp.json()["datasets"][0]["data"]) == 0

    def test_timeline_nonexistent_files_skipped(self, test_client, admin_headers):
        """存在しないファイルはスキップ (line 666-667)"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert sum(resp.json()["datasets"][0]["data"]) == 0

    def test_timeline_hour_negative_wraps(self, test_client, admin_headers):
        """hour < 0 の場合 +24 でラップされること (lines 686-687)"""
        now = datetime.now(timezone.utc)
        # 23時間前のログ
        past = now - timedelta(hours=23)
        month_abbr = past.strftime("%b")
        day = past.day
        hour = past.hour

        log_content = f"{month_abbr}  {day} {hour:02d}:30:00 host kernel: error happened\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert sum(resp.json()["datasets"][0]["data"]) >= 1

    def test_timeline_iso_invalid_datetime_skipped(self, test_client, admin_headers):
        """ISO形式で不正な日時の場合 ValueError でスキップ (line 703)"""
        log_content = "9999-13-45T99:00:00 error happened\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert sum(resp.json()["datasets"][0]["data"]) == 0


# ===================================================================
# GET /api/logs/allowed-files テスト
# ===================================================================


class TestAllowedFiles:
    """GET /api/logs/allowed-files エンドポイント"""

    def test_allowed_files_returns_list(self, test_client, admin_headers):
        """allowlist ファイル一覧を返すこと"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "file_count" in data
        assert data["file_count"] == len(data["files"])
        # 各エントリにpath/name/existsがあること
        for f in data["files"]:
            assert "path" in f
            assert "name" in f
            assert "exists" in f

    def test_allowed_files_no_auth(self, test_client):
        """未認証で403"""
        resp = test_client.get("/api/logs/allowed-files")
        assert resp.status_code == 403


# ===================================================================
# GET /api/logs/saved-filters テスト
# ===================================================================


class TestSavedFiltersEndpoints:
    """保存フィルター CRUD テスト"""

    def test_list_saved_filters_empty(self, test_client, admin_headers, tmp_path):
        """フィルターなしの場合空リストを返す"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["filters"] == []

    def test_create_and_list_filter(self, test_client, admin_headers, tmp_path):
        """フィルター作成後にリストに含まれること"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            # 作成
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "my filter", "query": "error", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
            assert resp.status_code == 201
            created = resp.json()
            assert created["name"] == "my filter"
            assert "id" in created

            # リスト
            resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 1

    def test_create_filter_allowlist_violation(self, test_client, admin_headers, tmp_path):
        """allowlist 外ファイル指定で 400 (lines 761-766)"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "bad filter", "query": "test", "files": ["/etc/passwd"]},
                headers=admin_headers,
            )
        assert resp.status_code == 400
        body = resp.json()
        assert "allowlist" in body.get("detail", body.get("message", ""))

    def test_delete_saved_filter_success(self, test_client, admin_headers, tmp_path):
        """フィルター削除成功"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            # 作成
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "to delete", "query": "warn", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
            filter_id = resp.json()["id"]

            # 削除
            resp = test_client.delete(f"/api/logs/saved-filters/{filter_id}", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["deleted"] == filter_id

    def test_delete_nonexistent_filter_returns_404(self, test_client, admin_headers, tmp_path):
        """存在しないフィルター削除で 404 (lines 833-837)"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.delete("/api/logs/saved-filters/nonexistent-uuid", headers=admin_headers)
        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body.get("detail", body.get("message", "")).lower()

    def test_create_filter_with_regex_flag(self, test_client, admin_headers, tmp_path):
        """regex フラグ付きフィルター作成"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "regex filter", "query": "error.*fatal", "files": ["/var/log/syslog"], "regex": True},
                headers=admin_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["regex"] is True

    def test_saved_filters_no_auth(self, test_client):
        """未認証で 403"""
        resp = test_client.get("/api/logs/saved-filters")
        assert resp.status_code == 403
