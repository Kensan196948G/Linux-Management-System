"""
logs.py カバレッジ改善テスト

backend/api/routes/logs.py のヘルパー関数・エンドポイントの
未カバー行を重点的にテストする。既存テストとの重複を避ける。
"""

import json
import re
from datetime import datetime, timezone
from unittest.mock import mock_open, patch

import pytest
from fastapi import HTTPException


# ===================================================================
# ヘルパー関数の直接インポート
# ===================================================================

from backend.api.routes.logs import (
    ADVANCED_ALLOWED_LOG_FILES,
    FORBIDDEN_CHARS_ADV,
    FORBIDDEN_CHARS_LOG,
    MAX_REGEX_LENGTH,
    MAX_RESULT_LINES,
    _compile_pattern,
    _detect_level,
    _load_saved_filters,
    _save_saved_filters,
    _validate_adv_query,
    _validate_query,
)


# ===================================================================
# _validate_query — 全禁止文字テスト
# ===================================================================


class TestValidateQuery:
    """_validate_query ヘルパーの直接テスト"""

    @pytest.mark.parametrize(
        "char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"]
    )
    def test_forbidden_char_raises_400(self, char):
        """各禁止文字で HTTPException(400) を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_query(f"test{char}injection")
        assert exc.value.status_code == 400
        assert "Forbidden" in exc.value.detail

    def test_valid_query_passes(self):
        """禁止文字なしの通常文字列は例外を送出しないこと"""
        _validate_query("normal search query")

    def test_empty_string_passes(self):
        """空文字列は禁止文字チェックを通過すること"""
        _validate_query("")

    def test_japanese_query_passes(self):
        """日本語クエリは禁止文字チェックを通過すること"""
        _validate_query("エラーログ検索")

    def test_multiple_forbidden_chars(self):
        """複数禁止文字を含む場合、最初の文字で 400 が発生すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_query(";|&")
        assert exc.value.status_code == 400


# ===================================================================
# _validate_adv_query — 高度検索禁止文字テスト
# ===================================================================


class TestValidateAdvQuery:
    """_validate_adv_query ヘルパーの直接テスト"""

    @pytest.mark.parametrize("char", FORBIDDEN_CHARS_ADV)
    def test_non_regex_forbidden_char_raises_400(self, char):
        """非 regex モードで禁止文字が 400 を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_adv_query(f"query{char}test", allow_regex=False)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("char", FORBIDDEN_CHARS_ADV)
    def test_regex_mode_skips_forbidden_check(self, char):
        """regex モードでは禁止文字チェックをスキップすること"""
        # Should not raise
        _validate_adv_query(f"query{char}test", allow_regex=True)

    def test_clean_query_passes_non_regex(self):
        """クリーンなクエリは非 regex モードでも通過すること"""
        _validate_adv_query("normal query", allow_regex=False)

    def test_clean_query_passes_regex(self):
        """クリーンなクエリは regex モードでも通過すること"""
        _validate_adv_query("normal query", allow_regex=True)


# ===================================================================
# _compile_pattern — パターンコンパイルテスト
# ===================================================================


class TestCompilePattern:
    """_compile_pattern ヘルパーの直接テスト"""

    def test_non_regex_escapes_special_chars(self):
        """非 regex モードで特殊文字がエスケープされること"""
        pat = _compile_pattern("test.log", is_regex=False)
        assert pat.search("test.log")
        # ドットがリテラルとしてエスケープされるので "testXlog" にはマッチしない
        assert not pat.search("testXlog")

    def test_regex_mode_uses_raw_pattern(self):
        """regex モードで正規表現がそのままコンパイルされること"""
        pat = _compile_pattern("err.*detected", is_regex=True)
        assert pat.search("error detected in kernel")

    def test_regex_case_insensitive(self):
        """regex モードで大文字小文字を無視すること"""
        pat = _compile_pattern("ERROR", is_regex=True)
        assert pat.search("error")
        assert pat.search("Error")
        assert pat.search("ERROR")

    def test_non_regex_case_insensitive(self):
        """非 regex モードで大文字小文字を無視すること"""
        pat = _compile_pattern("error", is_regex=False)
        assert pat.search("ERROR occurred")

    def test_invalid_regex_raises_400(self):
        """不正な正規表現で HTTPException(400) を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _compile_pattern("[invalid(regex", is_regex=True)
        assert exc.value.status_code == 400
        assert "Invalid regex" in exc.value.detail

    def test_empty_regex(self):
        """空の正規表現は全行にマッチすること"""
        pat = _compile_pattern("", is_regex=True)
        assert pat.search("anything")

    def test_complex_regex(self):
        """複雑な正規表現が正しくコンパイルされること"""
        pat = _compile_pattern(r"\d{4}-\d{2}-\d{2}", is_regex=True)
        assert pat.search("2026-03-15 some event")
        assert not pat.search("no date here")

    def test_unclosed_group_raises_400(self):
        """閉じ括弧なしの正規表現で 400 を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _compile_pattern("(unclosed", is_regex=True)
        assert exc.value.status_code == 400


# ===================================================================
# _detect_level — ログレベル検出テスト
# ===================================================================


class TestDetectLevel:
    """_detect_level ヘルパーの直接テスト"""

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("Jan  1 00:00:00 host kernel: error detected", "ERROR"),
            ("Jan  1 00:00:00 host kernel: err: something", "ERROR"),
            ("Jan  1 00:00:00 host kernel: critical failure", "ERROR"),
            ("Jan  1 00:00:00 host kernel: crit: disk failure", "ERROR"),
            ("Jan  1 00:00:00 host kernel: emerg: panic", "ERROR"),
            ("Jan  1 00:00:00 host kernel: alert: high temp", "ERROR"),
            ("Jan  1 00:00:00 host kernel: fatal exception", "ERROR"),
            ("Jan  1 00:00:00 host kernel: warning low memory", "WARN"),
            ("Jan  1 00:00:00 host kernel: warn: low disk", "WARN"),
            ("Jan  1 00:00:00 host sshd: info: session opened", "INFO"),
            ("Jan  1 00:00:00 host sshd: notice: something", "INFO"),
            ("Jan  1 00:00:00 host sshd: debug: trace output", "DEBUG"),
            ("Jan  1 00:00:00 host sshd: session opened", "UNKNOWN"),
            ("", "UNKNOWN"),
            ("no level keyword here at all", "UNKNOWN"),
        ],
    )
    def test_detect_level(self, line, expected):
        """各ログレベルキーワードが正しく検出されること"""
        assert _detect_level(line) == expected

    def test_detect_level_case_insensitive(self):
        """大文字小文字混在でもレベルを検出すること"""
        assert _detect_level("ERROR happened") == "ERROR"
        assert _detect_level("Error happened") == "ERROR"
        assert _detect_level("Warning issued") == "WARN"
        assert _detect_level("INFO message") == "INFO"
        assert _detect_level("Debug trace") == "DEBUG"

    def test_detect_level_priority(self):
        """ERROR が WARN より先に検出されること（優先度テスト）"""
        # "error" と "warning" が両方ある行
        result = _detect_level("error and warning in same line")
        assert result == "ERROR"


# ===================================================================
# _load_saved_filters / _save_saved_filters — JSON読み書きテスト
# ===================================================================


class TestSavedFiltersIO:
    """_load_saved_filters / _save_saved_filters の直接テスト"""

    def test_load_nonexistent_file(self, tmp_path):
        """ファイルが存在しない場合に空フィルターを返すこと"""
        fake_path = tmp_path / "nonexistent.json"
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fake_path):
            result = _load_saved_filters()
        assert result == {"filters": []}

    def test_load_valid_json(self, tmp_path):
        """正しい JSON ファイルを読み込めること"""
        data = {"filters": [{"id": "abc", "name": "test"}]}
        fp = tmp_path / "filters.json"
        fp.write_text(json.dumps(data), encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            result = _load_saved_filters()
        assert result == data

    def test_load_corrupt_json(self, tmp_path):
        """破損 JSON ファイルの場合に空フィルターを返すこと"""
        fp = tmp_path / "filters.json"
        fp.write_text("{invalid json content!!!", encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            result = _load_saved_filters()
        assert result == {"filters": []}

    def test_load_oserror(self, tmp_path):
        """OSError 発生時に空フィルターを返すこと"""
        fp = tmp_path / "filters.json"
        fp.write_text("{}", encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            with patch("builtins.open", side_effect=OSError("disk error")):
                result = _load_saved_filters()
        assert result == {"filters": []}

    def test_save_creates_parent_dir(self, tmp_path):
        """保存時に親ディレクトリを自動作成すること"""
        fp = tmp_path / "subdir" / "filters.json"
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            _save_saved_filters({"filters": []})
        assert fp.exists()
        assert json.loads(fp.read_text(encoding="utf-8")) == {"filters": []}

    def test_save_writes_correct_data(self, tmp_path):
        """保存データが正しく書き込まれること"""
        fp = tmp_path / "filters.json"
        data = {"filters": [{"id": "xyz", "name": "test filter"}]}
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            _save_saved_filters(data)
        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert saved == data

    def test_save_oserror_raises_500(self, tmp_path):
        """OSError 発生時に HTTPException(500) を送出すること"""
        fp = tmp_path / "filters.json"
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            with patch("builtins.open", side_effect=OSError("readonly filesystem")):
                with pytest.raises(HTTPException) as exc:
                    _save_saved_filters({"filters": []})
                assert exc.value.status_code == 500
                assert "Failed to persist" in exc.value.detail

    def test_save_unicode_content(self, tmp_path):
        """Unicode (日本語) コンテンツを正しく保存できること"""
        fp = tmp_path / "filters.json"
        data = {"filters": [{"id": "1", "name": "エラー監視フィルター"}]}
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            _save_saved_filters(data)
        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert saved["filters"][0]["name"] == "エラー監視フィルター"


# ===================================================================
# Pydantic モデルバリデーション
# ===================================================================


class TestPydanticModels:
    """AdvancedSearchRequest / SavedFilterCreateRequest のバリデーション"""

    def test_advanced_search_query_too_long(self):
        """クエリが MAX_REGEX_LENGTH を超える場合にバリデーションエラー"""
        from pydantic import ValidationError
        from backend.api.routes.logs import AdvancedSearchRequest

        with pytest.raises(ValidationError):
            AdvancedSearchRequest(query="x" * (MAX_REGEX_LENGTH + 1))

    def test_advanced_search_limit_zero(self):
        """limit=0 でバリデーションエラー"""
        from pydantic import ValidationError
        from backend.api.routes.logs import AdvancedSearchRequest

        with pytest.raises(ValidationError):
            AdvancedSearchRequest(query="test", limit=0)

    def test_advanced_search_limit_too_large(self):
        """limit が MAX_RESULT_LINES を超える場合にバリデーションエラー"""
        from pydantic import ValidationError
        from backend.api.routes.logs import AdvancedSearchRequest

        with pytest.raises(ValidationError):
            AdvancedSearchRequest(query="test", limit=MAX_RESULT_LINES + 1)

    def test_advanced_search_valid_defaults(self):
        """デフォルト値が正しくセットされること"""
        from backend.api.routes.logs import AdvancedSearchRequest

        req = AdvancedSearchRequest(query="test")
        assert req.files == ["/var/log/syslog"]
        assert req.regex is False
        assert req.limit == 100
        assert req.from_time is None
        assert req.to_time is None

    def test_saved_filter_empty_name(self):
        """空フィルター名でバリデーションエラー"""
        from pydantic import ValidationError
        from backend.api.routes.logs import SavedFilterCreateRequest

        with pytest.raises(ValidationError):
            SavedFilterCreateRequest(name="   ", query="test")

    def test_saved_filter_name_too_long(self):
        """フィルター名が 100 文字を超える場合にバリデーションエラー"""
        from pydantic import ValidationError
        from backend.api.routes.logs import SavedFilterCreateRequest

        with pytest.raises(ValidationError):
            SavedFilterCreateRequest(name="a" * 101, query="test")

    def test_saved_filter_name_stripped(self):
        """フィルター名の前後空白がトリムされること"""
        from backend.api.routes.logs import SavedFilterCreateRequest

        req = SavedFilterCreateRequest(name="  test filter  ", query="error")
        assert req.name == "test filter"


# ===================================================================
# GET /api/logs/search — エンドポイント追加テスト
# ===================================================================


class TestSearchLogsEndpoint:
    """GET /api/logs/search の追加カバレッジ"""

    def test_search_with_custom_lines(self, test_client, admin_headers):
        """lines パラメータ指定で正常動作すること"""
        mock_result = {
            "status": "success",
            "pattern": "test",
            "logfile": "syslog",
            "lines_returned": 1,
            "results": ["test line"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.search_logs.return_value = mock_result
            resp = test_client.get(
                "/api/logs/search?q=test&file=syslog&lines=10",
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_search_forbidden_char_in_file_param(self, test_client, admin_headers):
        """file パラメータの禁止文字で 400 を返すこと"""
        resp = test_client.get(
            "/api/logs/search?q=test&file=sys;log",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize("char", ["(", ")", "*", "?"])
    def test_search_query_each_forbidden_char(self, test_client, admin_headers, char):
        """個別の禁止文字 (括弧/アスタリスク/疑問符) で 400"""
        resp = test_client.get(
            f"/api/logs/search?q=test{char}inj",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_search_error_result_without_message(self, test_client, admin_headers):
        """result が status='error' で message なしの場合もハンドリングされること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.search_logs.return_value = {"status": "error"}
            resp = test_client.get(
                "/api/logs/search?q=test",
                headers=admin_headers,
            )
        assert resp.status_code == 400


# ===================================================================
# GET /api/logs/files — エンドポイント追加テスト
# ===================================================================


class TestListLogFilesEndpoint:
    """GET /api/logs/files の追加カバレッジ"""

    def test_list_files_success_with_file_count(self, test_client, admin_headers):
        """正常レスポンスに file_count が含まれること"""
        mock_result = {
            "status": "success",
            "file_count": 3,
            "files": ["/var/log/syslog", "/var/log/auth.log", "/var/log/kern.log"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.list_log_files.return_value = mock_result
            resp = test_client.get("/api/logs/files", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["file_count"] == 3

    def test_list_files_error_without_message(self, test_client, admin_headers):
        """status='error' で message なしの場合もハンドリングされること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.list_log_files.return_value = {"status": "error"}
            resp = test_client.get("/api/logs/files", headers=admin_headers)
        assert resp.status_code == 500


# ===================================================================
# GET /api/logs/recent-errors — エンドポイント追加テスト
# ===================================================================


class TestRecentErrorsEndpoint:
    """GET /api/logs/recent-errors の追加カバレッジ"""

    def test_recent_errors_error_without_message(self, test_client, admin_headers):
        """status='error' で message なしの場合もハンドリングされること"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_recent_errors.return_value = {"status": "error"}
            resp = test_client.get("/api/logs/recent-errors", headers=admin_headers)
        assert resp.status_code == 500


# ===================================================================
# POST /api/logs/search — 高度検索追加テスト
# ===================================================================


class TestAdvancedSearchEndpoint:
    """POST /api/logs/search の追加カバレッジ"""

    def test_file_not_found_is_silently_skipped(self, test_client, admin_headers):
        """FileNotFoundError はスキップされ結果に含まれないこと"""
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                raise FileNotFoundError("No such file")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        # FileNotFoundError はスキップされるので Permission denied メッセージなし
        data = resp.json()
        assert data["matches"] == 0

    def test_limit_across_multiple_files(self, test_client, admin_headers):
        """limit が複数ファイル横断で適用されること"""
        many_errors = "error line\n" * 100
        with patch("builtins.open", mock_open(read_data=many_errors)):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "error",
                    "files": ["/var/log/syslog", "/var/log/auth.log"],
                    "limit": 5,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["matches"] <= 5

    def test_adv_search_forbidden_pipe_non_regex(self, test_client, admin_headers):
        """非 regex モードでパイプ文字は 400"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test|grep", "files": ["/var/log/syslog"], "regex": False},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_adv_search_pipe_allowed_in_regex(self, test_client, admin_headers):
        """regex モードでパイプ文字（OR）は許可されること"""
        with patch("builtins.open", mock_open(read_data="error line\nwarn line\n")):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "error|warn",
                    "files": ["/var/log/syslog"],
                    "regex": True,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["matches"] >= 1

    def test_adv_search_multiple_forbidden_files(self, test_client, admin_headers):
        """allowlist 外ファイルが複数ある場合に最初のもので 400"""
        resp = test_client.post(
            "/api/logs/search",
            json={
                "query": "test",
                "files": ["/var/log/syslog", "/etc/shadow"],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_adv_search_result_contains_timestamp(self, test_client, admin_headers):
        """結果に timestamp が含まれること"""
        with patch("builtins.open", mock_open(read_data="error\n")):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_adv_search_with_from_time_to_time(self, test_client, admin_headers):
        """from_time / to_time パラメータ付きリクエストが受け付けられること"""
        with patch("builtins.open", mock_open(read_data="error\n")):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "error",
                    "files": ["/var/log/syslog"],
                    "from_time": "2026-03-01T00:00:00Z",
                    "to_time": "2026-03-15T23:59:59Z",
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# GET /api/logs/allowed-files — 追加テスト
# ===================================================================


class TestAllowedFilesEndpoint:
    """GET /api/logs/allowed-files の追加カバレッジ"""

    def test_allowed_files_each_entry_has_fields(self, test_client, admin_headers):
        """各エントリに path, name, exists フィールドがあること"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        for item in resp.json()["files"]:
            assert "path" in item
            assert "name" in item
            assert "exists" in item

    def test_allowed_files_count_matches_constant(self, test_client, admin_headers):
        """返却数が ADVANCED_ALLOWED_LOG_FILES の長さと一致すること"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["file_count"] == len(ADVANCED_ALLOWED_LOG_FILES)

    def test_allowed_files_has_timestamp(self, test_client, admin_headers):
        """レスポンスに timestamp が含まれること"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_allowed_files_viewer_access(self, test_client, viewer_headers):
        """viewer ロールでもアクセス可能なこと"""
        resp = test_client.get("/api/logs/allowed-files", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# GET /api/logs/stats — 追加テスト
# ===================================================================


class TestLogStatsEndpoint:
    """GET /api/logs/stats の追加カバレッジ"""

    def test_stats_no_files_exist(self, test_client, admin_headers):
        """全ファイルが存在しない場合に空 totals を返すこと"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["ERROR"] == 0
        assert data["totals"]["WARN"] == 0
        assert data["totals"]["INFO"] == 0
        assert data["totals"]["DEBUG"] == 0
        assert data["totals"]["UNKNOWN"] == 0

    def test_stats_per_file_contains_counts(self, test_client, admin_headers):
        """per_file にファイルごとのカウントが含まれること"""
        log_content = (
            "error line\n" "warning line\n" "info line\n" "debug line\n" "no level\n"
        )
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) in ADVANCED_ALLOWED_LOG_FILES:
                from io import StringIO

                return StringIO(log_content)
            return original_open(file, *args, **kwargs)

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "per_file" in data
        # At least some files should have counts
        assert data["totals"]["ERROR"] > 0

    def test_stats_permission_denied_skipped(self, test_client, admin_headers):
        """PermissionError のファイルはスキップされること"""
        original_open = open

        def perm_error_open(file, *args, **kwargs):
            if str(file) in ADVANCED_ALLOWED_LOG_FILES:
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=perm_error_open):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        # All counts should be 0 since all files raised PermissionError
        data = resp.json()
        assert data["totals"]["ERROR"] == 0

    def test_stats_scan_lines_limit(self, test_client, admin_headers):
        """5000行を超えるファイルで末尾5000行のみ走査されること"""
        # 6000行: 先頭1000行=error, 後半5000行=info
        lines = "error line\n" * 1000 + "info line\n" * 5000
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                from io import StringIO

                return StringIO(lines)
            if str(file) in ADVANCED_ALLOWED_LOG_FILES:
                raise FileNotFoundError()
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) == "/var/log/syslog"

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # The first 1000 error lines should be popped out of the buffer
        # so INFO should dominate
        if "/var/log/syslog" in data.get("per_file", {}):
            file_counts = data["per_file"]["/var/log/syslog"]
            assert file_counts["INFO"] == 5000


# ===================================================================
# GET /api/logs/timeline — 追加テスト
# ===================================================================


class TestLogTimelineEndpoint:
    """GET /api/logs/timeline の追加カバレッジ"""

    def test_timeline_with_syslog_format(self, test_client, admin_headers):
        """syslog 形式のタイムスタンプが解析されること"""
        now = datetime.now(timezone.utc)
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        month_str = month_names[now.month - 1]
        day = now.day
        hour = now.hour
        log_line = (
            f"{month_str} {day:2d} {hour:02d}:30:00 host kernel: error detected\n"
        )

        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                from io import StringIO

                return StringIO(log_line)
            if str(file) == "/var/log/auth.log":
                from io import StringIO

                return StringIO("")
            if str(file) in ADVANCED_ALLOWED_LOG_FILES:
                raise FileNotFoundError()
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) in ("/var/log/syslog", "/var/log/auth.log")

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["labels"]) == 24
        total = sum(data["datasets"][0]["data"])
        assert total >= 1

    def test_timeline_with_iso_format(self, test_client, admin_headers):
        """ISO 形式のタイムスタンプが解析されること"""
        now = datetime.now(timezone.utc)
        log_line = f"{now.year}-{now.month:02d}-{now.day:02d}T{now.hour:02d}:30:00 host kernel: error detected\n"

        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) == "/var/log/syslog":
                from io import StringIO

                return StringIO(log_line)
            if str(file) == "/var/log/auth.log":
                from io import StringIO

                return StringIO("")
            if str(file) in ADVANCED_ALLOWED_LOG_FILES:
                raise FileNotFoundError()
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) in ("/var/log/syslog", "/var/log/auth.log")

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        total = sum(resp.json()["datasets"][0]["data"])
        assert total >= 1

    def test_timeline_no_files_exist(self, test_client, admin_headers):
        """ファイルが存在しない場合に全ゼロを返すこと"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(v == 0 for v in data["datasets"][0]["data"])

    def test_timeline_permission_denied(self, test_client, admin_headers):
        """PermissionError のファイルはスキップされること"""
        original_open = open

        def perm_error_open(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log"):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) in ("/var/log/syslog", "/var/log/auth.log")

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=perm_error_open):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert all(v == 0 for v in resp.json()["datasets"][0]["data"])

    def test_timeline_non_error_lines_skipped(self, test_client, admin_headers):
        """ERROR/WARN 以外の行はスキップされること"""
        now = datetime.now(timezone.utc)
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        month_str = month_names[now.month - 1]
        day = now.day
        hour = now.hour
        log_content = (
            f"{month_str} {day:2d} {hour:02d}:00:00 host sshd: info session opened\n"
            f"{month_str} {day:2d} {hour:02d}:00:01 host sshd: debug trace\n"
        )
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log"):
                from io import StringIO

                return StringIO(log_content)
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) in ("/var/log/syslog", "/var/log/auth.log")

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        # info/debug lines should not be counted
        assert all(v == 0 for v in resp.json()["datasets"][0]["data"])

    def test_timeline_old_timestamp_ignored(self, test_client, admin_headers):
        """24時間以上前のタイムスタンプは無視されること"""
        # Use a date from a different month to ensure > 24 hours
        log_content = "Jan  1 00:00:00 host kernel: error old event\n"

        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log"):
                from io import StringIO

                return StringIO(log_content)
            return original_open(file, *args, **kwargs)

        def selective_exists(self_path):
            return str(self_path) in ("/var/log/syslog", "/var/log/auth.log")

        with patch("pathlib.Path.exists", selective_exists):
            with patch("builtins.open", side_effect=selective_open):
                resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        # Old events (likely > 24h ago unless it's January) should be 0 or minimal

    def test_timeline_has_timestamp(self, test_client, admin_headers):
        """レスポンスに timestamp が含まれること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_timeline_labels_format(self, test_client, admin_headers):
        """labels が HH:00 形式であること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        for label in resp.json()["labels"]:
            assert re.match(r"\d{2}:00", label), f"Invalid label format: {label}"


# ===================================================================
# CRUD /api/logs/saved-filters — 追加テスト
# ===================================================================


class TestSavedFiltersEndpoint:
    """POST/GET/DELETE /api/logs/saved-filters の追加カバレッジ"""

    def _make_tmp_filter_file(self, tmp_path, data=None):
        fp = tmp_path / "saved_log_filters.json"
        fp.write_text(json.dumps(data or {"filters": []}), encoding="utf-8")
        return fp

    def test_create_filter_with_regex_flag(self, test_client, admin_headers, tmp_path):
        """regex=True のフィルター作成が正常動作すること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "Regex Filter",
                    "query": "err.*detected",
                    "files": ["/var/log/syslog"],
                    "regex": True,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["regex"] is True

    def test_create_filter_persists_to_file(self, test_client, admin_headers, tmp_path):
        """作成されたフィルターがファイルに永続化されること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "Persist Test",
                    "query": "test",
                    "files": ["/var/log/syslog"],
                },
                headers=admin_headers,
            )
        saved = json.loads(fp.read_text(encoding="utf-8"))
        assert len(saved["filters"]) == 1
        assert saved["filters"][0]["name"] == "Persist Test"

    def test_create_filter_has_created_by(self, test_client, admin_headers, tmp_path):
        """作成されたフィルターに created_by フィールドがあること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "Auth Test",
                    "query": "test",
                    "files": ["/var/log/syslog"],
                },
                headers=admin_headers,
            )
        assert resp.status_code == 201
        assert "created_by" in resp.json()

    def test_create_multiple_filters(self, test_client, admin_headers, tmp_path):
        """複数フィルターの連続作成が可能であること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            for i in range(3):
                resp = test_client.post(
                    "/api/logs/saved-filters",
                    json={
                        "name": f"Filter {i}",
                        "query": f"query{i}",
                        "files": ["/var/log/syslog"],
                    },
                    headers=admin_headers,
                )
                assert resp.status_code == 201
            list_resp = test_client.get(
                "/api/logs/saved-filters", headers=admin_headers
            )
        assert list_resp.json()["count"] == 3

    def test_list_filters_empty(self, test_client, admin_headers, tmp_path):
        """空のフィルターファイルで count=0 が返ること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["filters"] == []

    def test_list_filters_has_timestamp(self, test_client, admin_headers, tmp_path):
        """一覧レスポンスに timestamp が含まれること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_delete_filter_has_timestamp(self, test_client, admin_headers, tmp_path):
        """削除レスポンスに timestamp が含まれること"""
        initial = {
            "filters": [
                {
                    "id": "ts-test",
                    "name": "t",
                    "query": "q",
                    "files": [],
                    "regex": False,
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
        fp = self._make_tmp_filter_file(tmp_path, initial)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.delete(
                "/api/logs/saved-filters/ts-test", headers=admin_headers
            )
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_create_filter_with_multiple_files(
        self, test_client, admin_headers, tmp_path
    ):
        """複数 allowlist ファイル指定でフィルター作成が成功すること"""
        fp = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "Multi File Filter",
                    "query": "error",
                    "files": ["/var/log/syslog", "/var/log/auth.log"],
                },
                headers=admin_headers,
            )
        assert resp.status_code == 201
        assert len(resp.json()["files"]) == 2

    def test_delete_filter_viewer_access(self, test_client, viewer_headers, tmp_path):
        """viewer ロールでもフィルター削除にアクセス可能なこと"""
        initial = {
            "filters": [
                {
                    "id": "v-del",
                    "name": "v",
                    "query": "q",
                    "files": [],
                    "regex": False,
                    "created_by": "viewer",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
        fp = self._make_tmp_filter_file(tmp_path, initial)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", fp):
            resp = test_client.delete(
                "/api/logs/saved-filters/v-del", headers=viewer_headers
            )
        assert resp.status_code == 200


# ===================================================================
# GET /api/logs/{service_name} — サービスログ取得テスト
# ===================================================================


class TestServiceLogsEndpoint:
    """GET /api/logs/{service_name} の追加カバレッジ"""

    def test_service_logs_success(self, test_client, admin_headers):
        """正常なサービスログ取得が 200 を返すこと"""
        mock_result = {
            "status": "success",
            "service": "nginx",
            "lines_requested": 100,
            "lines_returned": 5,
            "logs": ["line1", "line2", "line3", "line4", "line5"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_logs.return_value = mock_result
            resp = test_client.get("/api/logs/nginx", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "nginx"
        assert data["lines_returned"] == 5

    def test_service_logs_custom_lines(self, test_client, admin_headers):
        """lines パラメータ指定で正常動作すること"""
        mock_result = {
            "status": "success",
            "service": "nginx",
            "lines_requested": 50,
            "lines_returned": 3,
            "logs": ["a", "b", "c"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_logs.return_value = mock_result
            resp = test_client.get("/api/logs/nginx?lines=50", headers=admin_headers)
        assert resp.status_code == 200

    def test_service_logs_no_auth(self, test_client):
        """認証なしで 403 を返すこと"""
        resp = test_client.get("/api/logs/nginx")
        assert resp.status_code == 403

    def test_service_logs_invalid_name_pattern(self, test_client, admin_headers):
        """不正なサービス名パターンで 422 を返すこと"""
        resp = test_client.get("/api/logs/../../etc/passwd", headers=admin_headers)
        assert resp.status_code in (404, 422)

    def test_service_logs_denied_without_message(self, test_client, admin_headers):
        """status='error' で message なしの denied 処理"""
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_logs.return_value = {"status": "error"}
            resp = test_client.get("/api/logs/nginx", headers=admin_headers)
        assert resp.status_code == 403

    def test_service_logs_response_model(self, test_client, admin_headers):
        """LogsResponse モデルのフィールドが正しいこと"""
        mock_result = {
            "status": "success",
            "service": "sshd",
            "lines_requested": 100,
            "lines_returned": 2,
            "logs": ["login success", "login failed"],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_logs.return_value = mock_result
            resp = test_client.get("/api/logs/sshd", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "service" in data
        assert "lines_requested" in data
        assert "lines_returned" in data
        assert "logs" in data
        assert "timestamp" in data

    def test_service_logs_viewer_access(self, test_client, viewer_headers):
        """viewer ロールでもサービスログにアクセス可能なこと"""
        mock_result = {
            "status": "success",
            "service": "nginx",
            "lines_requested": 100,
            "lines_returned": 0,
            "logs": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        with patch("backend.api.routes.logs.sudo_wrapper") as mock_sw:
            mock_sw.get_logs.return_value = mock_result
            resp = test_client.get("/api/logs/nginx", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# ADVANCED_ALLOWED_LOG_FILES 定数テスト
# ===================================================================


class TestAllowedFilesConstant:
    """ADVANCED_ALLOWED_LOG_FILES 定数の検証"""

    def test_all_paths_are_absolute(self):
        """全パスが絶対パスであること"""
        for path in ADVANCED_ALLOWED_LOG_FILES:
            assert path.startswith("/"), f"Not absolute: {path}"

    def test_syslog_in_list(self):
        """/var/log/syslog が含まれること"""
        assert "/var/log/syslog" in ADVANCED_ALLOWED_LOG_FILES

    def test_auth_log_in_list(self):
        """/var/log/auth.log が含まれること"""
        assert "/var/log/auth.log" in ADVANCED_ALLOWED_LOG_FILES

    def test_no_duplicates(self):
        """重複パスがないこと"""
        assert len(ADVANCED_ALLOWED_LOG_FILES) == len(set(ADVANCED_ALLOWED_LOG_FILES))

    def test_no_sensitive_files(self):
        """機密ファイルが含まれないこと"""
        sensitive = ["/etc/shadow", "/etc/passwd", "/etc/sudoers"]
        for s in sensitive:
            assert s not in ADVANCED_ALLOWED_LOG_FILES


# ===================================================================
# 定数テスト
# ===================================================================


class TestConstants:
    """モジュール定数のテスト"""

    def test_max_result_lines_positive(self):
        assert MAX_RESULT_LINES > 0

    def test_max_regex_length_positive(self):
        assert MAX_REGEX_LENGTH > 0

    def test_forbidden_chars_log_not_empty(self):
        assert len(FORBIDDEN_CHARS_LOG) > 0

    def test_forbidden_chars_adv_not_empty(self):
        assert len(FORBIDDEN_CHARS_ADV) > 0

    def test_forbidden_chars_adv_subset_of_log(self):
        """高度検索の禁止文字は基本検索の禁止文字のサブセットであること"""
        for char in FORBIDDEN_CHARS_ADV:
            assert char in FORBIDDEN_CHARS_LOG
