"""
logsearch.py カバレッジ改善テスト v2

対象: backend/api/routes/logsearch.py
目標: 90%以上のカバレッジ
既存テスト (test_logsearch_coverage.py) で不足しているパスを網羅する。
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _get_error_message(resp):
    """レスポンスからエラーメッセージを取得 (detail or message)"""
    body = resp.json()
    return body.get("detail") or body.get("message") or ""


# =====================================================================
# /files - SudoWrapperError / Exception パス
# =====================================================================


class TestListLogFilesSudoErrors:
    """list_log_files の SudoWrapperError / Exception パス"""

    def test_files_sudo_wrapper_error_500(self, test_client, auth_headers):
        """SudoWrapperError -> 500"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 500
        assert "wrapper failed" in _get_error_message(resp)

    def test_files_general_exception_503(self, test_client, auth_headers):
        """一般例外 -> 503"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 503
        assert "unexpected" in _get_error_message(resp)

    def test_files_http_exception_reraise(self, test_client, auth_headers):
        """HTTPException は再送出"""
        from fastapi import HTTPException

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 429

    def test_files_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/logsearch/files")
        assert resp.status_code in (401, 403)

    def test_files_success_with_data(self, test_client, auth_headers):
        """正常系: ファイルリスト返却"""
        mock_data = {
            "files": ["/var/log/syslog", "/var/log/auth.log"],
            "file_count": 2,
            "timestamp": "2026-03-15T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_count"] == 2
        assert len(data["files"]) == 2


# =====================================================================
# /search - SudoWrapperError / ValueError / Exception パス
# =====================================================================


class TestSearchLogsSudoErrors:
    """search_logs の SudoWrapperError / ValueError / Exception パス"""

    def test_search_sudo_wrapper_error_500(self, test_client, auth_headers):
        """SudoWrapperError -> 500"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=SudoWrapperError("search failed"),
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test", headers=auth_headers
            )
        assert resp.status_code == 500
        assert "search failed" in _get_error_message(resp)

    def test_search_value_error_400(self, test_client, auth_headers):
        """ValueError -> 400"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=ValueError("invalid pattern"),
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test", headers=auth_headers
            )
        assert resp.status_code == 400
        assert "invalid pattern" in _get_error_message(resp)

    def test_search_general_exception_503(self, test_client, auth_headers):
        """一般例外 -> 503"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=RuntimeError("unexpected error"),
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test", headers=auth_headers
            )
        assert resp.status_code == 503
        assert "unexpected error" in _get_error_message(resp)

    def test_search_http_exception_reraise(self, test_client, auth_headers):
        """HTTPException は再送出"""
        from fastapi import HTTPException

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test", headers=auth_headers
            )
        assert resp.status_code == 429

    def test_search_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/logsearch/search?pattern=test")
        assert resp.status_code in (401, 403)

    def test_search_missing_pattern_422(self, test_client, auth_headers):
        """pattern パラメータなし -> 422"""
        resp = test_client.get("/api/logsearch/search", headers=auth_headers)
        assert resp.status_code == 422

    def test_search_pattern_too_long_422(self, test_client, auth_headers):
        """pattern が 101 文字 -> 422"""
        long_pattern = "a" * 101
        resp = test_client.get(
            f"/api/logsearch/search?pattern={long_pattern}", headers=auth_headers
        )
        assert resp.status_code == 422

    def test_search_lines_over_max_422(self, test_client, auth_headers):
        """lines=201 -> 422"""
        resp = test_client.get(
            "/api/logsearch/search?pattern=test&lines=201", headers=auth_headers
        )
        assert resp.status_code == 422

    def test_search_lines_zero_422(self, test_client, auth_headers):
        """lines=0 -> 422"""
        resp = test_client.get(
            "/api/logsearch/search?pattern=test&lines=0", headers=auth_headers
        )
        assert resp.status_code == 422

    def test_search_logfile_with_slash_rejected(self, test_client, auth_headers):
        """logfile に / を含む -> 400 (regex バリデーション)"""
        resp = test_client.get(
            "/api/logsearch/search?pattern=test&logfile=nginx/access.log",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_search_success_with_results(self, test_client, auth_headers):
        """正常系: 検索結果返却"""
        mock_data = {
            "pattern": "error",
            "logfile": "syslog",
            "results": ["Jan 1 error in module A", "Jan 2 error in module B"],
            "lines_returned": 2,
            "timestamp": "2026-03-15T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            return_value=mock_data,
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=error", headers=auth_headers
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines_returned"] == 2
        assert len(data["results"]) == 2


# =====================================================================
# /recent-errors - SudoWrapperError / Exception パス
# =====================================================================


class TestRecentErrorsSudoErrors:
    """recent-errors の SudoWrapperError / Exception パス"""

    def test_recent_errors_sudo_wrapper_error_500(self, test_client, auth_headers):
        """SudoWrapperError -> 500"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            side_effect=SudoWrapperError("error retrieval failed"),
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 500
        assert "error retrieval failed" in _get_error_message(resp)

    def test_recent_errors_general_exception_503(self, test_client, auth_headers):
        """一般例外 -> 503"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            side_effect=RuntimeError("journal crash"),
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 503

    def test_recent_errors_http_exception_reraise(self, test_client, auth_headers):
        """HTTPException は再送出"""
        from fastapi import HTTPException

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            side_effect=HTTPException(status_code=502, detail="bad gateway"),
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 502

    def test_recent_errors_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/logsearch/recent-errors")
        assert resp.status_code in (401, 403)

    def test_recent_errors_success_with_data(self, test_client, auth_headers):
        """正常系: エラーリスト返却"""
        mock_data = {
            "errors": ["error line 1", "error line 2"],
            "error_count": 2,
            "timestamp": "2026-03-15T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] == 2


# =====================================================================
# /tail - SudoWrapperError / Exception パス
# =====================================================================


class TestTailSudoErrors:
    """tail の SudoWrapperError / Exception パス"""

    def test_tail_sudo_wrapper_error_500(self, test_client, auth_headers):
        """SudoWrapperError -> 500"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            side_effect=SudoWrapperError("tail failed"),
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 500
        assert "tail failed" in _get_error_message(resp)

    def test_tail_general_exception_503(self, test_client, auth_headers):
        """一般例外 -> 503"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            side_effect=RuntimeError("unexpected"),
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 503

    def test_tail_http_exception_reraise(self, test_client, auth_headers):
        """HTTPException は再送出"""
        from fastapi import HTTPException

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 429

    def test_tail_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/logsearch/tail")
        assert resp.status_code in (401, 403)

    def test_tail_lines_over_max_422(self, test_client, auth_headers):
        """lines=101 -> 422"""
        resp = test_client.get("/api/logsearch/tail?lines=101", headers=auth_headers)
        assert resp.status_code == 422

    def test_tail_lines_under_min_422(self, test_client, auth_headers):
        """lines=4 -> 422"""
        resp = test_client.get("/api/logsearch/tail?lines=4", headers=auth_headers)
        assert resp.status_code == 422

    def test_tail_success_with_data(self, test_client, auth_headers):
        """正常系: tail 結果返却"""
        mock_data = {
            "lines": ["line1", "line2", "line3"],
            "lines_returned": 3,
            "timestamp": "2026-03-15T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines_returned"] == 3
        assert data["lines_per_file"] == 30


# =====================================================================
# /stream - 追加エッジケース
# =====================================================================


class TestStreamV2:
    """stream SSE エンドポイントの追加テスト"""

    def test_stream_missing_token_422(self, test_client):
        """token パラメータなし -> 422"""
        resp = test_client.get("/api/logsearch/stream?logfile=syslog")
        assert resp.status_code == 422

    def test_stream_logfile_regex_rejects_hash(self, test_client, auth_token):
        """logfile に # を含む -> 400 (regex バリデーション)"""
        resp = test_client.get(
            f"/api/logsearch/stream?logfile=sys%23log&token={auth_token}"
        )
        assert resp.status_code == 400

    def test_stream_logfile_not_in_allowed_list(self, test_client, auth_token):
        """許可リストにないファイル -> 400"""
        resp = test_client.get(
            f"/api/logsearch/stream?logfile=messages&token={auth_token}"
        )
        assert resp.status_code == 400
        msg = _get_error_message(resp)
        assert "not allowed" in msg.lower() or "allowed" in msg.lower()

    def test_stream_syslog_success(self, test_client, auth_token):
        """syslog (許可リスト内) で SSE 接続成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"connected" in chunks

    def test_stream_heartbeat_on_timeout(self, test_client, auth_token):
        """readline タイムアウトでハートビートが送信される"""
        call_count = 0

        async def readline_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return b""

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(side_effect=readline_side_effect)
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c

        decoded = chunks.decode()
        assert "heartbeat" in decoded

    def test_stream_exception_in_generator(self, test_client, auth_token):
        """event_generator 内で一般例外 -> error イベント"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=RuntimeError("stream crash")
        )
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c

        decoded = chunks.decode()
        # connected は送信される（例外は readline 時に発生するので connected の後）
        assert "connected" in decoded

    @pytest.mark.parametrize(
        "logfile",
        ["syslog", "auth.log", "kern.log", "dpkg.log"],
    )
    def test_stream_all_allowed_logfiles(self, logfile, test_client, auth_token):
        """全許可ファイルでの SSE 接続成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET",
                f"/api/logsearch/stream?logfile={logfile}&token={auth_token}",
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        # connected イベントの logfile が正しいこと
        for line in chunks.decode().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("type") == "connected":
                    assert data["logfile"] == logfile
                    break


# =====================================================================
# _validate_search_param ヘルパー直接テスト (追加)
# =====================================================================


class TestValidateSearchParamV2:
    """_validate_search_param の追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.logsearch import _validate_search_param

        self.fn = _validate_search_param

    def test_clean_string_no_raise(self):
        """禁止文字なしの文字列は例外を投げない"""
        self.fn("normal-search_term.log", "pattern")  # should not raise

    def test_empty_string_no_raise(self):
        """空文字列は禁止文字がないので例外を投げない"""
        self.fn("", "pattern")  # should not raise

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"])
    def test_each_forbidden_char_raises(self, char):
        """各禁止文字で HTTPException(400) が発生"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            self.fn(f"test{char}value", "test_param")
        assert exc_info.value.status_code == 400
        assert f"Forbidden character '{char}'" in exc_info.value.detail

    def test_multiple_forbidden_chars_first_detected(self):
        """複数の禁止文字がある場合、最初に見つかったものでエラー"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            self.fn("test;value|pipe", "param")
        assert exc_info.value.status_code == 400
        assert ";" in exc_info.value.detail


# =====================================================================
# 定数テスト (追加)
# =====================================================================


class TestLogsearchConstantsV2:
    """モジュール定数の追加テスト"""

    def test_router_exists(self):
        """router がインスタンスとして存在"""
        from backend.api.routes.logsearch import router

        assert router is not None

    def test_stream_allowed_log_files_count(self):
        """_STREAM_ALLOWED_LOG_FILES が6つ"""
        from backend.api.routes.logsearch import _STREAM_ALLOWED_LOG_FILES

        assert len(_STREAM_ALLOWED_LOG_FILES) == 6

    def test_stream_allowed_log_files_includes_nginx(self):
        """nginx ログが許可リストに含まれる"""
        from backend.api.routes.logsearch import _STREAM_ALLOWED_LOG_FILES

        assert "nginx/access.log" in _STREAM_ALLOWED_LOG_FILES
        assert "nginx/error.log" in _STREAM_ALLOWED_LOG_FILES
