"""
ログ検索モジュール - 統合テスト

/api/logsearch エンドポイントの統合テスト（sudo_wrapper をモック）
"""

from unittest.mock import patch

import pytest

# ==============================================================================
# テスト用サンプルデータ
# ==============================================================================

SAMPLE_FILES = {
    "status": "success",
    "file_count": 3,
    "files": ["/var/log/syslog", "/var/log/auth.log", "/var/log/kern.log"],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_SEARCH = {
    "status": "success",
    "pattern": "error",
    "logfile": "syslog",
    "lines_returned": 2,
    "results": [
        "Jan  1 00:00:00 server kernel: error detected",
        "Jan  1 00:00:01 server sshd[123]: error connecting",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

SAMPLE_ERRORS = {
    "status": "success",
    "error_count": 2,
    "errors": [
        "Jan  1 00:00:00 server kernel: error detected",
        "Jan  1 00:00:01 server sshd[123]: error connecting",
    ],
    "timestamp": "2026-01-01T00:00:00Z",
}

EMPTY_SEARCH = {
    "status": "success",
    "pattern": "nonexistent",
    "logfile": "syslog",
    "lines_returned": 0,
    "results": [],
    "timestamp": "2026-01-01T00:00:00Z",
}

EMPTY_ERRORS = {
    "status": "success",
    "error_count": 0,
    "errors": [],
    "timestamp": "2026-01-01T00:00:00Z",
}

# ==============================================================================
# 認証テスト
# ==============================================================================


class TestLogsearchAuth:
    """未認証リクエストは拒否されること"""

    def test_files_no_auth(self, test_client):
        """未認証で /files は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/files")
        assert response.status_code in (401, 403)

    def test_search_no_auth(self, test_client):
        """未認証で /search は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error")
        assert response.status_code in (401, 403)

    def test_recent_errors_no_auth(self, test_client):
        """未認証で /recent-errors は 401/403 を返すこと"""
        response = test_client.get("/api/logsearch/recent-errors")
        assert response.status_code in (401, 403)


# ==============================================================================
# 正常系テスト
# ==============================================================================


class TestLogsearchSuccess:
    """正常系のテスト"""

    def test_list_files_success(self, test_client, auth_headers):
        """/files が 200 とファイル一覧を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "file_count" in data
        assert data["file_count"] == 3
        assert "/var/log/syslog" in data["files"]

    def test_search_basic(self, test_client, auth_headers):
        """/search?pattern=error が 200 と結果を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["pattern"] == "error"
        assert "results" in data
        assert data["lines_returned"] == 2

    def test_search_with_logfile_and_lines(self, test_client, auth_headers):
        """/search?pattern=error&logfile=syslog&lines=10 が 200 を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH) as mock:
            response = test_client.get(
                "/api/logsearch/search?pattern=error&logfile=syslog&lines=10",
                headers=auth_headers,
            )
        assert response.status_code == 200
        mock.assert_called_once_with("error", "syslog", 10)

    def test_recent_errors_success(self, test_client, auth_headers):
        """/recent-errors が 200 とエラー一覧を返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", return_value=SAMPLE_ERRORS):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        assert data["error_count"] == 2

    def test_viewer_can_list_files(self, test_client, viewer_headers):
        """viewer ロールでも /files にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=viewer_headers)
        assert response.status_code == 200

    def test_viewer_can_search(self, test_client, viewer_headers):
        """viewer ロールでも /search にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=SAMPLE_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=viewer_headers)
        assert response.status_code == 200

    def test_admin_can_list_files(self, test_client, admin_headers):
        """admin ロールでも /files にアクセスできること"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", return_value=SAMPLE_FILES):
            response = test_client.get("/api/logsearch/files", headers=admin_headers)
        assert response.status_code == 200

    def test_empty_results(self, test_client, auth_headers):
        """検索結果が空でも正常に返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=EMPTY_SEARCH):
            response = test_client.get("/api/logsearch/search?pattern=nonexistent", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["lines_returned"] == 0

    def test_empty_errors(self, test_client, auth_headers):
        """エラーログが空でも正常に返すこと"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", return_value=EMPTY_ERRORS):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == []
        assert data["error_count"] == 0


# ==============================================================================
# バリデーションテスト
# ==============================================================================


class TestLogsearchValidation:
    """入力バリデーションのテスト"""

    def test_search_no_pattern(self, test_client, auth_headers):
        """pattern なしで /search は 422 を返すこと"""
        response = test_client.get("/api/logsearch/search", headers=auth_headers)
        assert response.status_code == 422

    def test_search_forbidden_semicolon_in_pattern(self, test_client, auth_headers):
        """pattern にセミコロンが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err;ls", headers=auth_headers)
        assert response.status_code == 400

    def test_search_forbidden_pipe_in_pattern(self, test_client, auth_headers):
        """pattern にパイプが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err|grep", headers=auth_headers)
        assert response.status_code == 400

    def test_search_forbidden_char_in_logfile(self, test_client, auth_headers):
        """logfile にセミコロンが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&logfile=sys;log", headers=auth_headers)
        assert response.status_code == 400

    def test_search_path_traversal_in_logfile(self, test_client, auth_headers):
        """logfile にパストラバーサルが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&logfile=../etc/passwd", headers=auth_headers)
        assert response.status_code == 400

    def test_search_lines_too_large(self, test_client, auth_headers):
        """lines=201 の場合 422 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&lines=201", headers=auth_headers)
        assert response.status_code == 422

    def test_search_lines_too_small(self, test_client, auth_headers):
        """lines=0 の場合 422 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=error&lines=0", headers=auth_headers)
        assert response.status_code == 422

    def test_search_dollar_in_pattern(self, test_client, auth_headers):
        """pattern にドル記号が含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err$HOME", headers=auth_headers)
        assert response.status_code == 400

    def test_search_backtick_in_pattern(self, test_client, auth_headers):
        """pattern にバッククォートが含まれる場合 400 を返すこと"""
        response = test_client.get("/api/logsearch/search?pattern=err%60id%60", headers=auth_headers)
        assert response.status_code == 400


# ==============================================================================
# エラーハンドリングテスト
# ==============================================================================


class TestLogsearchErrorHandling:
    """エラーハンドリングのテスト"""

    def test_list_files_sudo_wrapper_error(self, test_client, auth_headers):
        """list_log_files で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 500

    def test_search_sudo_wrapper_error(self, test_client, auth_headers):
        """search_logs で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 500

    def test_recent_errors_sudo_wrapper_error(self, test_client, auth_headers):
        """get_recent_errors で SudoWrapperError → 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", side_effect=SudoWrapperError("wrapper failed")):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 500

    def test_list_files_generic_exception(self, test_client, auth_headers):
        """list_log_files で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.list_log_files", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert response.status_code == 503

    def test_search_generic_exception(self, test_client, auth_headers):
        """search_logs で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.search_logs", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/search?pattern=error", headers=auth_headers)
        assert response.status_code == 503

    def test_recent_errors_generic_exception(self, test_client, auth_headers):
        """get_recent_errors で Exception → 503"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors", side_effect=Exception("unexpected")):
            response = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert response.status_code == 503


class TestLogsearchTailEndpoint:
    """GET /api/logsearch/tail エンドポイントのテスト"""

    def test_get_tail_success(self, test_client, auth_headers):
        """tail-multi が正常に結果を返す"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi") as m:
            m.return_value = {"output": ["line1", "line2"], "files": ["syslog", "auth.log"], "timestamp": "2026-01-01T00:00:00Z"}
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "output" in data
        assert data["lines_per_file"] == 30

    def test_get_tail_custom_lines(self, test_client, auth_headers):
        """lines パラメータを指定できる"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi") as m:
            m.return_value = {"output": [], "files": [], "timestamp": "2026-01-01T00:00:00Z"}
            resp = test_client.get("/api/logsearch/tail?lines=10", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["lines_per_file"] == 10

    def test_get_tail_lines_too_large(self, test_client, auth_headers):
        """lines > 100 は 422"""
        resp = test_client.get("/api/logsearch/tail?lines=200", headers=auth_headers)
        assert resp.status_code == 422

    def test_get_tail_lines_too_small(self, test_client, auth_headers):
        """lines < 5 は 422"""
        resp = test_client.get("/api/logsearch/tail?lines=1", headers=auth_headers)
        assert resp.status_code == 422

    def test_get_tail_sudo_error(self, test_client, auth_headers):
        """SudoWrapperError → 500"""
        from unittest.mock import patch
        from backend.core.sudo_wrapper import SudoWrapperError
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi", side_effect=SudoWrapperError("fail")):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 500

    def test_get_tail_generic_exception(self, test_client, auth_headers):
        """Exception → 503"""
        from unittest.mock import patch
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi", side_effect=Exception("unexpected")):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 503

    def test_get_tail_unauthenticated(self, test_client):
        """認証なし → 401"""
        resp = test_client.get("/api/logsearch/tail")
        assert resp.status_code in (401, 403)


# ==============================================================================
# HTTPException 再送出パス（lines 49, 86, 88, 108, 140）
# ==============================================================================


class TestLogsearchHTTPExceptionReraise:
    """各エンドポイントの except HTTPException: raise パスをカバー"""

    def test_list_files_reraises_http_exception(self, test_client, auth_headers):
        """list_log_files: 内部で HTTPException が発生した場合に再送出 (line 49)"""
        from fastapi import HTTPException
        from unittest.mock import patch

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            side_effect=HTTPException(status_code=503, detail="upstream down"),
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 503

    def test_search_raises_value_error_returns_400(self, test_client, auth_headers):
        """search_logs: ValueError → 400 (line 86)"""
        from unittest.mock import patch

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=ValueError("bad value"),
        ):
            resp = test_client.get("/api/logsearch/search?pattern=test", headers=auth_headers)
        assert resp.status_code == 400

    def test_search_reraises_http_exception(self, test_client, auth_headers):
        """search_logs: 内部で HTTPException → 再送出 (line 88)"""
        from fastapi import HTTPException
        from unittest.mock import patch

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/logsearch/search?pattern=test", headers=auth_headers)
        assert resp.status_code == 429

    def test_recent_errors_reraises_http_exception(self, test_client, auth_headers):
        """get_recent_errors: 内部で HTTPException → 再送出 (line 108)"""
        from fastapi import HTTPException
        from unittest.mock import patch

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            side_effect=HTTPException(status_code=503, detail="svc down"),
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 503

    def test_tail_reraises_http_exception(self, test_client, auth_headers):
        """get_log_tail_multi: 内部で HTTPException → 再送出 (line 140)"""
        from fastapi import HTTPException
        from unittest.mock import patch

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            side_effect=HTTPException(status_code=503, detail="tail svc down"),
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 503


# ==============================================================================
# SSE ストリームエンドポイント（lines 159-227）
# ==============================================================================


class TestLogsearchStreamEndpoint:
    """GET /api/logsearch/stream SSEエンドポイントテスト"""

    def test_stream_no_token_returns_422(self, test_client):
        """tokenパラメータなし → 422"""
        resp = test_client.get("/api/logsearch/stream?logfile=syslog")
        assert resp.status_code == 422

    def test_stream_invalid_token_returns_401(self, test_client):
        """不正トークン → 401 (lines 165-167)"""
        resp = test_client.get("/api/logsearch/stream?logfile=syslog&token=bad.tok.en")
        assert resp.status_code == 401

    def test_stream_forbidden_char_in_logfile_returns_400(self, test_client, auth_token):
        """禁止文字を含む logfile → 400 (line 169)"""
        resp = test_client.get(f"/api/logsearch/stream?logfile=sys%3Blog&token={auth_token}")
        assert resp.status_code == 400

    def test_stream_invalid_logfile_pattern_returns_400(self, test_client, auth_token):
        """英数字以外の logfile → 400 (lines 170-171)"""
        resp = test_client.get(f"/api/logsearch/stream?logfile=sys+log&token={auth_token}")
        assert resp.status_code == 400

    def test_stream_disallowed_logfile_returns_400(self, test_client, auth_token):
        """許可リスト外の logfile → 400 (lines 174-175)"""
        resp = test_client.get(f"/api/logsearch/stream?logfile=shadow&token={auth_token}")
        assert resp.status_code == 400

    def test_stream_valid_logfile_returns_event_stream(self, test_client, auth_token):
        """有効 logfile で SSE 接続開始 → connected イベント (lines 177-227)"""
        import asyncio
        from unittest.mock import AsyncMock, patch

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
                assert "text/event-stream" in resp.headers.get("content-type", "")
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"connected" in chunks

    def test_stream_yields_log_line(self, test_client, auth_token):
        """ログ行が SSE data イベントとして配信される (lines 200-210)"""
        from unittest.mock import AsyncMock, patch

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[b"Jan 01 00:00:00 host sshd: session opened\n", b""]
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
        assert b'"type": "log"' in chunks

    def test_stream_yields_heartbeat_on_timeout(self, test_client, auth_token):
        """readline タイムアウトで heartbeat イベントを配信する (line 213)"""
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        first_call = [True]

        async def patched_wait_for(coro, timeout=None):
            if first_call[0]:
                first_call[0] = False
                try:
                    coro.close()
                except Exception:
                    pass
                raise asyncio.TimeoutError()
            return await coro

        with patch("asyncio.wait_for", side_effect=patched_wait_for):
            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with test_client.stream(
                    "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
                ) as resp:
                    chunks = b""
                    for c in resp.iter_bytes():
                        chunks += c
        assert b"heartbeat" in chunks

    def test_stream_subprocess_exception_yields_error_event(self, test_client, auth_token):
        """subprocess 起動失敗時に error イベントを配信する (lines 216-218)"""
        from unittest.mock import patch

        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("exec spawn failed")
        ):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"error" in chunks

    def test_stream_proc_terminated_in_finally(self, test_client, auth_token):
        """正常終了後に proc.terminate() が呼ばれる (lines 220-225)"""
        from unittest.mock import AsyncMock, patch, call

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                for _ in resp.iter_bytes():
                    pass
        mock_proc.terminate.assert_called_once()


# ==============================================================================
# 高度検索エンドポイント - POST /api/logs/search
# GET /api/logs/allowed-files, /stats, /timeline
# CRUD /api/logs/saved-filters
# ==============================================================================

import io
import json
import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch


# ------------------------------------------------------------------------------
# ヘルパー: ファイル読み込みモック
# ------------------------------------------------------------------------------

SAMPLE_SYSLOG_CONTENT = (
    "Jan  1 00:00:01 host kernel: error detected\n"
    "Jan  1 01:00:00 host sshd[123]: info: connection ok\n"
    "Jan  1 02:00:00 host kernel: warning: low memory\n"
    "Jan  1 03:00:00 host kernel: critical: disk failure\n"
    "Jan  1 04:00:00 host sshd[456]: debug: test\n"
    "Jan  1 05:00:00 host postfix: info: message sent\n"
)

SAMPLE_AUTH_CONTENT = (
    "Jan  1 00:10:00 host sshd[789]: Failed password for admin from 10.0.0.1\n"
    "Jan  1 00:20:00 host sshd[790]: Failed password for root from 10.0.0.2\n"
    "Jan  1 01:00:00 host sudo: operator: command ok\n"
)


# ==============================================================================
# POST /api/logs/search — 高度検索
# ==============================================================================


class TestAdvancedSearch:
    """POST /api/logs/search 高度フルテキスト検索テスト"""

    def test_advanced_search_basic(self, test_client, admin_headers):
        """allowlist ファイルへの通常検索が正常動作すること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"], "regex": False, "limit": 50},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["query"] == "error"
        assert data["matches"] >= 0

    def test_advanced_search_regex(self, test_client, admin_headers):
        """正規表現モードでマッチすること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "err.*detected", "files": ["/var/log/syslog"], "regex": True},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["regex"] is True

    def test_advanced_search_invalid_regex(self, test_client, admin_headers):
        """不正な正規表現は 400 を返すこと"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "[invalid(regex", "files": ["/var/log/syslog"], "regex": True},
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_advanced_search_forbidden_file(self, test_client, admin_headers):
        """allowlist 外ファイルは 400 を返すこと"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "test", "files": ["/etc/passwd"], "regex": False},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("message") or body.get("detail") or ""
        assert "allowlist" in str(msg).lower()

    def test_advanced_search_multiple_files(self, test_client, admin_headers):
        """複数ファイル横断検索が動作すること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={
                    "query": "error",
                    "files": ["/var/log/syslog", "/var/log/auth.log"],
                    "regex": False,
                    "limit": 100,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "files_searched" in data
        assert len(data["files_searched"]) == 2

    def test_advanced_search_limit_enforced(self, test_client, admin_headers):
        """limit パラメータが結果件数を制限すること"""
        many_lines = "Jan  1 00:00:00 host sshd: error line\n" * 200
        with patch("builtins.open", mock_open(read_data=many_lines)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"], "regex": False, "limit": 10},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["matches"] <= 10

    def test_advanced_search_no_match(self, test_client, admin_headers):
        """一致なしで空結果が返ること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "xyznonexistent123", "files": ["/var/log/syslog"], "regex": False},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["matches"] == 0

    def test_advanced_search_forbidden_chars_blocked(self, test_client, admin_headers):
        """非 regex モードで禁止文字を含むクエリは 400 を返すこと"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "error; rm -rf /", "files": ["/var/log/syslog"], "regex": False},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_advanced_search_permission_denied_file(self, test_client, admin_headers):
        """読み取り権限なしファイルはエラーメッセージを含む結果を返すこと"""
        # audit_log のファイル書き込みは通過させ、対象ログファイルのみ PermissionError にする
        original_open = open

        def selective_open(file, *args, **kwargs):
            if str(file) in ("/var/log/syslog", "/var/log/auth.log", "/var/log/kern.log"):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"], "regex": False},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert any("Permission denied" in r["message"] for r in data["results"])

    def test_advanced_search_no_auth(self, test_client):
        """未認証で 401/403 を返すこと"""
        resp = test_client.post(
            "/api/logs/search",
            json={"query": "error", "files": ["/var/log/syslog"]},
        )
        assert resp.status_code in (401, 403)

    def test_advanced_search_sql_injection_safe(self, test_client, admin_headers):
        """SQLインジェクション風文字列も安全に処理されること（非regexエスケープ）"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "' OR '1'='1", "files": ["/var/log/syslog"], "regex": False},
                headers=admin_headers,
            )
        # 禁止文字なし → 200 で空結果
        assert resp.status_code == 200

    def test_advanced_search_result_has_level_field(self, test_client, admin_headers):
        """結果にログレベルフィールドが含まれること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            resp = test_client.post(
                "/api/logs/search",
                json={"query": "error", "files": ["/var/log/syslog"], "regex": False},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        for item in resp.json()["results"]:
            assert "level" in item
            assert "file" in item
            assert "lineno" in item
            assert "message" in item


# ==============================================================================
# GET /api/logs/allowed-files
# ==============================================================================


class TestAllowedFiles:
    """GET /api/logs/allowed-files テスト"""

    def test_allowed_files_returns_list(self, test_client, admin_headers):
        """ファイル一覧が返ること"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "file_count" in data
        assert data["file_count"] > 0

    def test_allowed_files_contains_syslog(self, test_client, admin_headers):
        """syslog が allowlist に含まれること"""
        resp = test_client.get("/api/logs/allowed-files", headers=admin_headers)
        assert resp.status_code == 200
        paths = [f["path"] for f in resp.json()["files"]]
        assert "/var/log/syslog" in paths

    def test_allowed_files_no_auth(self, test_client):
        """未認証で 401/403 を返すこと"""
        resp = test_client.get("/api/logs/allowed-files")
        assert resp.status_code in (401, 403)


# ==============================================================================
# GET /api/logs/stats
# ==============================================================================


class TestLogStats:
    """GET /api/logs/stats テスト"""

    def test_stats_returns_totals(self, test_client, admin_headers):
        """stats が totals を含むこと"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "totals" in data
        assert "ERROR" in data["totals"]
        assert "WARN" in data["totals"]
        assert "INFO" in data["totals"]
        assert "DEBUG" in data["totals"]

    def test_stats_totals_are_integers(self, test_client, admin_headers):
        """totals の値が整数であること"""
        with patch("builtins.open", mock_open(read_data=SAMPLE_SYSLOG_CONTENT)):
            with patch("pathlib.Path.exists", return_value=True):
                resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        totals = resp.json()["totals"]
        for key in ("ERROR", "WARN", "INFO", "DEBUG"):
            assert isinstance(totals[key], int)

    def test_stats_no_auth(self, test_client):
        """未認証で 401/403 を返すこと"""
        resp = test_client.get("/api/logs/stats")
        assert resp.status_code in (401, 403)

    def test_stats_has_timestamp(self, test_client, admin_headers):
        """レスポンスに timestamp が含まれること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()


# ==============================================================================
# GET /api/logs/timeline
# ==============================================================================


class TestLogTimeline:
    """GET /api/logs/timeline テスト"""

    def test_timeline_returns_labels_and_datasets(self, test_client, admin_headers):
        """timeline が labels と datasets を含むこと"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "labels" in data
        assert "datasets" in data

    def test_timeline_labels_count_24(self, test_client, admin_headers):
        """labels が 24 個であること（24 時間分）"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["labels"]) == 24

    def test_timeline_data_count_24(self, test_client, admin_headers):
        """datasets[0].data が 24 要素であること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["datasets"][0]["data"]) == 24

    def test_timeline_no_auth(self, test_client):
        """未認証で 401/403 を返すこと"""
        resp = test_client.get("/api/logs/timeline")
        assert resp.status_code in (401, 403)

    def test_timeline_data_are_integers(self, test_client, admin_headers):
        """timeline データ値が整数であること"""
        with patch("pathlib.Path.exists", return_value=False):
            resp = test_client.get("/api/logs/timeline", headers=admin_headers)
        assert resp.status_code == 200
        for v in resp.json()["datasets"][0]["data"]:
            assert isinstance(v, int)


# ==============================================================================
# CRUD /api/logs/saved-filters
# ==============================================================================


class TestSavedFilters:
    """POST/GET/DELETE /api/logs/saved-filters テスト"""

    def _make_tmp_filter_file(self, tmp_path: "Path") -> "Path":  # noqa: F821
        """テスト用一時フィルターファイルを作成する"""
        p = tmp_path / "saved_log_filters.json"
        p.write_text(json.dumps({"filters": []}), encoding="utf-8")
        return p

    def test_create_filter_success(self, test_client, admin_headers, tmp_path):
        """フィルター作成が 201 を返すこと"""
        tmp_filter = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "SSHエラー監視",
                    "query": "Failed password",
                    "files": ["/var/log/auth.log"],
                    "regex": False,
                },
                headers=admin_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "SSHエラー監視"
        assert "id" in data
        assert "created_at" in data

    def test_create_filter_invalid_file(self, test_client, admin_headers, tmp_path):
        """allowlist 外ファイルでフィルター作成は 400 を返すこと"""
        tmp_filter = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.post(
                "/api/logs/saved-filters",
                json={
                    "name": "悪意フィルター",
                    "query": "test",
                    "files": ["/etc/shadow"],
                },
                headers=admin_headers,
            )
        assert resp.status_code == 400

    def test_list_filters_returns_list(self, test_client, admin_headers, tmp_path):
        """フィルター一覧が返ること"""
        initial = {
            "filters": [
                {
                    "id": "aaa",
                    "name": "テスト",
                    "query": "error",
                    "files": ["/var/log/syslog"],
                    "regex": False,
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        tmp_filter = tmp_path / "saved_log_filters.json"
        tmp_filter.write_text(json.dumps(initial), encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "filters" in data
        assert "count" in data
        assert data["count"] == 1

    def test_delete_filter_success(self, test_client, admin_headers, tmp_path):
        """フィルター削除が成功すること"""
        initial = {
            "filters": [
                {
                    "id": "del-test-id",
                    "name": "削除対象",
                    "query": "error",
                    "files": ["/var/log/syslog"],
                    "regex": False,
                    "created_by": "admin",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        tmp_filter = tmp_path / "saved_log_filters.json"
        tmp_filter.write_text(json.dumps(initial), encoding="utf-8")
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.delete("/api/logs/saved-filters/del-test-id", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "del-test-id"

    def test_delete_filter_not_found(self, test_client, admin_headers, tmp_path):
        """存在しないフィルター削除は 404 を返すこと"""
        tmp_filter = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            resp = test_client.delete("/api/logs/saved-filters/nonexistent-id", headers=admin_headers)
        assert resp.status_code == 404

    def test_create_then_list_then_delete(self, test_client, admin_headers, tmp_path):
        """作成→一覧→削除の一連フロー"""
        tmp_filter = self._make_tmp_filter_file(tmp_path)
        with patch("backend.api.routes.logs.SAVED_FILTERS_PATH", tmp_filter):
            # 作成
            create_resp = test_client.post(
                "/api/logs/saved-filters",
                json={"name": "フローテスト", "query": "warn", "files": ["/var/log/syslog"]},
                headers=admin_headers,
            )
            assert create_resp.status_code == 201
            filter_id = create_resp.json()["id"]

            # 一覧確認
            list_resp = test_client.get("/api/logs/saved-filters", headers=admin_headers)
            assert list_resp.status_code == 200
            ids = [f["id"] for f in list_resp.json()["filters"]]
            assert filter_id in ids

            # 削除
            del_resp = test_client.delete(f"/api/logs/saved-filters/{filter_id}", headers=admin_headers)
            assert del_resp.status_code == 200

            # 削除後一覧確認
            list_resp2 = test_client.get("/api/logs/saved-filters", headers=admin_headers)
            ids2 = [f["id"] for f in list_resp2.json()["filters"]]
            assert filter_id not in ids2

    def test_saved_filters_no_auth(self, test_client):
        """未認証で 401/403 を返すこと"""
        assert test_client.get("/api/logs/saved-filters").status_code in (401, 403)
        assert test_client.post(
            "/api/logs/saved-filters",
            json={"name": "x", "query": "y", "files": ["/var/log/syslog"]},
        ).status_code in (401, 403)
