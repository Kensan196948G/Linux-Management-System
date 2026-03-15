"""
logs.py カバレッジ改善テスト v2

未カバー行を重点的にテスト:
- get_service_logs 正常系（LogsResponse構築）
- advanced_search_logs の FileNotFoundError パス
- get_log_stats の PermissionError パス / 実データ走査
- get_log_timeline の syslog / ISO タイムスタンプ解析
- _save_saved_filters の OSError パス
- _load_saved_filters の壊れた JSON / OSError パス
- _detect_level の全レベル検出
- _compile_pattern の正常系・異常系
- _validate_adv_query の regex モードスキップ
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import HTTPException


# ===================================================================
# _detect_level 直接テスト（全レベル網羅）
# ===================================================================

from backend.api.routes.logs import (
    _compile_pattern,
    _detect_level,
    _load_saved_filters,
    _save_saved_filters,
    _validate_adv_query,
    _validate_query,
    SAVED_FILTERS_PATH,
)


class TestDetectLevelComprehensive:
    """_detect_level の全ログレベル検出を網羅テスト"""

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("Jan  1 00:00:00 host kernel: error detected", "ERROR"),
            ("critical failure in module", "ERROR"),
            ("emerg: system is going down", "ERROR"),
            ("alert: immediate action needed", "ERROR"),
            ("fatal: cannot continue", "ERROR"),
            ("Jan  1 00:00:00 host kernel: warning low memory", "WARN"),
            ("warn: disk space low", "WARN"),
            ("info: service started successfully", "INFO"),
            ("notice: new user created", "INFO"),
            ("debug: entering function foo", "DEBUG"),
            ("no level marker in this line", "UNKNOWN"),
            ("", "UNKNOWN"),
        ],
    )
    def test_detect_level_all_levels(self, line, expected):
        """全ログレベルが正しく検出されること"""
        assert _detect_level(line) == expected

    def test_detect_level_case_insensitive(self):
        """大文字小文字を問わず検出すること"""
        assert _detect_level("ERROR uppercase") == "ERROR"
        assert _detect_level("Error mixed") == "ERROR"
        assert _detect_level("WARNING uppercase") == "WARN"
        assert _detect_level("Debug lowercase") == "DEBUG"

    def test_detect_level_priority_error_over_warn(self):
        """ERROR が WARN より優先されること"""
        assert _detect_level("error and warning in same line") == "ERROR"


# ===================================================================
# _compile_pattern 直接テスト
# ===================================================================


class TestCompilePattern:
    """_compile_pattern のテスト"""

    def test_compile_plain_text(self):
        """非regexモードでプレーン文字列をエスケープしてコンパイルすること"""
        pat = _compile_pattern("test.string", is_regex=False)
        assert pat.search("test.string")
        # ドットがエスケープされるので任意文字マッチではない
        assert not pat.search("testXstring")

    def test_compile_regex_mode(self):
        """regexモードで正規表現としてコンパイルすること"""
        pat = _compile_pattern("test.*string", is_regex=True)
        assert pat.search("test-and-string")
        assert pat.search("teststring")

    def test_compile_invalid_regex_raises_400(self):
        """不正な正規表現は HTTPException(400) を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _compile_pattern("[invalid(regex", is_regex=True)
        assert exc.value.status_code == 400
        assert "Invalid regex" in exc.value.detail

    def test_compile_regex_case_insensitive(self):
        """コンパイルされたパターンが大文字小文字を区別しないこと"""
        pat = _compile_pattern("ERROR", is_regex=False)
        assert pat.search("error message")
        assert pat.search("ERROR message")


# ===================================================================
# _validate_adv_query 直接テスト
# ===================================================================


class TestValidateAdvQuery:
    """_validate_adv_query のテスト"""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`", ">", "<"])
    def test_forbidden_char_non_regex_raises(self, char):
        """非regexモードで禁止文字が含まれると HTTPException を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_adv_query(f"test{char}inject", allow_regex=False)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`", ">", "<"])
    def test_forbidden_char_regex_mode_passes(self, char):
        """regexモードでは禁止文字チェックをスキップすること"""
        # Should not raise
        _validate_adv_query(f"test{char}regex", allow_regex=True)

    def test_valid_query_non_regex_passes(self):
        """禁止文字のない通常文字列は通過すること"""
        _validate_adv_query("normal search query", allow_regex=False)


# ===================================================================
# _load_saved_filters / _save_saved_filters 直接テスト
# ===================================================================


class TestSavedFiltersHelpers:
    """_load_saved_filters / _save_saved_filters のテスト"""

    def test_load_nonexistent_file(self, tmp_path):
        """ファイルが存在しない場合は空リストを返すこと"""
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_path / "nonexistent.json"):
            result = _load_saved_filters()
        assert result == {"filters": []}

    def test_load_corrupt_json(self, tmp_path):
        """壊れた JSON ファイルの場合は空リストを返すこと"""
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{invalid json", encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", corrupt):
            result = _load_saved_filters()
        assert result == {"filters": []}

    def test_load_valid_json(self, tmp_path):
        """有効な JSON ファイルを正しく読み込むこと"""
        valid = tmp_path / "valid.json"
        data = {"filters": [{"id": "test-1", "name": "test filter"}]}
        valid.write_text(json.dumps(data), encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", valid):
            result = _load_saved_filters()
        assert len(result["filters"]) == 1
        assert result["filters"][0]["name"] == "test filter"

    def test_save_creates_parent_dirs(self, tmp_path):
        """親ディレクトリが存在しない場合に自動作成すること"""
        nested = tmp_path / "deep" / "nested" / "filters.json"
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", nested):
            _save_saved_filters({"filters": [{"id": "x"}]})
        assert nested.exists()
        saved = json.loads(nested.read_text(encoding="utf-8"))
        assert saved["filters"][0]["id"] == "x"

    def test_save_oserror_raises_500(self, tmp_path):
        """書き込みエラー時に HTTPException(500) を送出すること"""
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_path / "filters.json"):
            with patch("builtins.open", side_effect=OSError("disk full")):
                with pytest.raises(HTTPException) as exc:
                    _save_saved_filters({"filters": []})
                assert exc.value.status_code == 500


# ===================================================================
# get_service_logs 正常系エンドポイントテスト
# ===================================================================


class TestGetServiceLogsSuccess:
    """GET /api/logs/{service_name} の正常系テスト"""

    def test_service_logs_success_returns_logs_response(self, test_client, auth_headers):
        """正常なログ取得で LogsResponse 形式のレスポンスを返すこと"""
        mock_result = {
            "status": "success",
            "service": "nginx",
            "lines_requested": 50,
            "lines_returned": 3,
            "logs": ["line1", "line2", "line3"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_logs", return_value=mock_result):
            resp = test_client.get("/api/logs/nginx?lines=50", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "nginx"
        assert data["lines_returned"] == 3
        assert len(data["logs"]) == 3

    def test_service_logs_custom_lines(self, test_client, auth_headers):
        """lines パラメータが正しく渡されること"""
        mock_result = {
            "status": "success",
            "service": "sshd",
            "lines_requested": 200,
            "lines_returned": 200,
            "logs": [f"line{i}" for i in range(200)],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_logs", return_value=mock_result) as mock:
            resp = test_client.get("/api/logs/sshd?lines=200", headers=auth_headers)
        assert resp.status_code == 200
        mock.assert_called_once_with("sshd", 200)

    def test_service_logs_default_lines(self, test_client, auth_headers):
        """lines 未指定時にデフォルト 100 が使われること"""
        mock_result = {
            "status": "success",
            "service": "systemd",
            "lines_requested": 100,
            "lines_returned": 10,
            "logs": [f"line{i}" for i in range(10)],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper.get_logs", return_value=mock_result) as mock:
            resp = test_client.get("/api/logs/systemd", headers=auth_headers)
        assert resp.status_code == 200
        mock.assert_called_once_with("systemd", 100)

    @pytest.mark.parametrize("invalid_name", [
        "nginx;evil",
        "sys$temp",
        "name with space",
    ])
    def test_service_logs_invalid_service_name_rejected(self, test_client, auth_headers, invalid_name):
        """不正なサービス名は 422 で拒否されること"""
        resp = test_client.get(f"/api/logs/{invalid_name}", headers=auth_headers)
        assert resp.status_code == 422

    def test_service_logs_no_auth(self, test_client):
        """未認証は 403 を返すこと"""
        resp = test_client.get("/api/logs/nginx")
        assert resp.status_code == 403


# ===================================================================
# advanced_search_logs の FileNotFoundError パス
# ===================================================================


class TestAdvancedSearchFileNotFound:
    """POST /api/logs/search の FileNotFoundError パス"""

    def test_file_not_found_skipped_silently(self, test_client, admin_headers):
        """存在しないファイルはスキップして残りの結果を返すこと"""
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                raise FileNotFoundError(f"No such file: {file}")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "test", "files": ["/var/log/syslog"], "regex": False, "limit": 10},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        # FileNotFoundError はエラーメッセージを追加せず、単にスキップする
        assert data["matches"] == 0


# ===================================================================
# get_log_stats のファイル走査テスト
# ===================================================================


class TestLogStatsFileScan:
    """GET /api/logs/stats の詳細テスト"""

    def test_stats_permission_denied_file_skipped(self, test_client, admin_headers, tmp_path):
        """PermissionError のファイルはスキップして残りを集計すること"""
        # Create a file that will raise PermissionError on read
        log_file = tmp_path / "perm_denied.log"
        log_file.write_text("error line\n", encoding="utf-8")

        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == str(log_file):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch("backend.api.routes.logs.ADVANCED_ALLOWED_LOG_FILES", [str(log_file)]):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "totals" in data
        # PermissionError のファイルは per_file に含まれない
        assert str(log_file) not in data.get("per_file", {})

    def test_stats_nonexistent_files_skipped(self, test_client, admin_headers):
        """存在しないファイルはスキップされること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_file"] == {}
        # totals は全てゼロ
        for level in ("ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"):
            assert data["totals"][level] == 0

    def test_stats_counts_levels_correctly(self, test_client, admin_headers, tmp_path):
        """レベル別カウントが正しいこと"""
        log_content = (
            "Jan 1 error occurred\n"
            "Jan 1 warning low disk\n"
            "Jan 1 info service started\n"
            "Jan 1 debug trace data\n"
            "Jan 1 no level line\n"
        )
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content, encoding="utf-8")

        with patch(
            "backend.api.routes.logs.ADVANCED_ALLOWED_LOG_FILES",
            [str(log_file)],
        ):
            resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        totals = data["totals"]
        assert totals["ERROR"] >= 1
        assert totals["WARN"] >= 1
        assert totals["INFO"] >= 1
        assert totals["DEBUG"] >= 1


# ===================================================================
# get_log_timeline のタイムスタンプ解析テスト
# ===================================================================


class TestLogTimelineParsing:
    """GET /api/logs/timeline のタイムスタンプ解析テスト"""

    def test_timeline_syslog_format_parsed(self, test_client, admin_headers, tmp_path):
        """syslog 形式のタイムスタンプが正しくパースされること"""
        now = datetime.now(timezone.utc)
        month_abbr = now.strftime("%b")
        day = now.day
        hour = now.hour

        log_content = f"{month_abbr}  {day} {hour:02d}:30:00 host kernel: error occurred\n"

        # Timeline scans hardcoded /var/log/syslog and /var/log/auth.log
        # We need to mock open for those paths and Path.exists
        original_open = open

        def mock_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                import io
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                import io
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["labels"]) == 24
        # 少なくとも1つのエラーがカウントされているはず
        assert sum(data["datasets"][0]["data"]) >= 1

    def test_timeline_iso_format_parsed(self, test_client, admin_headers):
        """ISO 形式のタイムスタンプが正しくパースされること"""
        now = datetime.now(timezone.utc)
        iso_ts = now.strftime("%Y-%m-%dT%H")

        log_content = f"{iso_ts}:30:00 host kernel: error occurred\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                import io
                return io.StringIO(log_content)
            if str(file) == "/var/log/auth.log":
                import io
                return io.StringIO("")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert sum(data["datasets"][0]["data"]) >= 1

    def test_timeline_info_lines_skipped(self, test_client, admin_headers):
        """INFO レベルの行はタイムラインに含まれないこと"""
        now = datetime.now(timezone.utc)
        month_abbr = now.strftime("%b")
        day = now.day
        hour = now.hour

        log_content = f"{month_abbr}  {day} {hour:02d}:30:00 host kernel: info message\n"

        original_open = open

        def mock_open_fn(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log"):
                import io
                return io.StringIO(log_content)
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # INFO はカウントされない
        assert sum(data["datasets"][0]["data"]) == 0

    def test_timeline_permission_denied_skipped(self, test_client, admin_headers):
        """PermissionError のファイルはスキップされること"""
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log"):
                raise PermissionError("denied")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["labels"]) == 24

    def test_timeline_no_auth(self, test_client):
        """未認証は 403"""
        resp = test_client.get("/api/logs/timeline")
        assert resp.status_code == 403


# ===================================================================
# advanced_search_logs limit 到達時の早期終了テスト
# ===================================================================


class TestAdvancedSearchLimitExhaustion:
    """POST /api/logs/search でリミット到達時の挙動"""

    def test_limit_stops_across_files(self, test_client, admin_headers):
        """複数ファイルを横断中にリミットに達した場合、次ファイルをスキップすること"""
        many_errors = "Jan 1 error line\n" * 20

        with patch("builtins.open", mock_open(read_data=many_errors)):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "error",
                    "files": ["/var/log/syslog", "/var/log/auth.log"],
                    "regex": False,
                    "limit": 5,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["matches"] == 5


# ===================================================================
# AdvancedSearchRequest バリデーションテスト
# ===================================================================


class TestAdvancedSearchRequestValidation:
    """AdvancedSearchRequest のバリデーション"""

    def test_query_too_long_rejected(self, test_client, admin_headers):
        """200文字超のクエリは 422 で拒否されること"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "x" * 201, "files": ["/var/log/syslog"]},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_limit_zero_rejected(self, test_client, admin_headers):
        """limit=0 は 422 で拒否されること"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test", "files": ["/var/log/syslog"], "limit": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_limit_over_max_rejected(self, test_client, admin_headers):
        """limit=1001 は 422 で拒否されること"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test", "files": ["/var/log/syslog"], "limit": 1001},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ===================================================================
# SavedFilterCreateRequest バリデーションテスト
# ===================================================================


class TestSavedFilterCreateRequestValidation:
    """SavedFilterCreateRequest のバリデーション"""

    def test_empty_filter_name_rejected(self, test_client, admin_headers, tmp_path):
        """空文字列のフィルター名は 422 で拒否されること"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "   ", "query": "test", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
        assert resp.status_code == 422

    def test_filter_name_too_long_rejected(self, test_client, admin_headers, tmp_path):
        """100文字超のフィルター名は 422 で拒否されること"""
        tmp_filter = tmp_path / "filters.json"
        tmp_filter.write_text('{"filters": []}', encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "x" * 101, "query": "test", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
        assert resp.status_code == 422
