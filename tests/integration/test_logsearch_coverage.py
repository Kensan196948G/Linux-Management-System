"""
ログ検索API カバレッジ拡張テスト

logsearch.py のカバレッジを 80%+ に引き上げるための追加テスト。
既存 test_logsearch_api.py と重複しない新規テストに集中する。
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest


# ==============================================================================
# _validate_search_param ヘルパー直接テスト
# ==============================================================================


class TestValidateSearchParam:
    """_validate_search_param の禁止文字バリデーション網羅テスト"""

    @pytest.mark.parametrize(
        "char,encoded",
        [
            (";", "%3B"),
            ("|", "%7C"),
            ("&", "%26"),
            ("$", "%24"),
            ("(", "%28"),
            (")", "%29"),
            ("`", "%60"),
            (">", "%3E"),
            ("<", "%3C"),
            ("*", "%2A"),
            ("?", "%3F"),
            ("{", "%7B"),
            ("}", "%7D"),
            ("[", "%5B"),
            ("]", "%5D"),
        ],
    )
    def test_forbidden_char_in_pattern_returns_400(
        self, test_client, auth_headers, char, encoded
    ):
        """全15種の禁止文字が pattern に含まれる場合 400 を返すこと"""
        resp = test_client.get(
            f"/api/logsearch/search?pattern=test{encoded}cmd",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "Forbidden character" in msg or "forbidden" in msg.lower()

    @pytest.mark.parametrize(
        "char,encoded",
        [
            (";", "%3B"),
            ("|", "%7C"),
            ("&", "%26"),
            ("`", "%60"),
        ],
    )
    def test_forbidden_char_in_logfile_returns_400(
        self, test_client, auth_headers, char, encoded
    ):
        """禁止文字が logfile に含まれる場合 400 を返すこと"""
        resp = test_client.get(
            f"/api/logsearch/search?pattern=error&logfile=sys{encoded}log",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_validate_logfile_regex_rejects_space(self, test_client, auth_headers):
        """logfile にスペースが含まれる場合 regex バリデーションで 400"""
        resp = test_client.get(
            "/api/logsearch/search?pattern=error&logfile=sys%20log",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_validate_logfile_regex_rejects_slash(self, test_client, auth_headers):
        """logfile にスラッシュが含まれる場合 regex バリデーションで 400"""
        resp = test_client.get(
            "/api/logsearch/search?pattern=error&logfile=..%2Fetc%2Fpasswd",
            headers=auth_headers,
        )
        assert resp.status_code == 400


# ==============================================================================
# /files エンドポイント追加テスト
# ==============================================================================


class TestListLogFilesExtra:
    """list_log_files の追加カバレッジテスト"""

    def test_files_returns_timestamp(self, test_client, auth_headers):
        """レスポンスに timestamp が含まれること"""
        mock_data = {"files": [], "file_count": 0, "timestamp": "2026-01-01T00:00:00Z"}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_files_empty_result(self, test_client, auth_headers):
        """空のファイル一覧でも正常に返ること"""
        mock_data = {"files": [], "file_count": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"] == []
        assert data["file_count"] == 0
        # timestamp がデフォルト生成されること
        assert "timestamp" in data

    def test_files_missing_keys_uses_defaults(self, test_client, auth_headers):
        """sudo_wrapper の戻り値にキーが不足していてもデフォルトで補完"""
        mock_data = {}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.list_log_files",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/files", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"] == []
        assert data["file_count"] == 0
        assert "timestamp" in data


# ==============================================================================
# /search エンドポイント追加テスト
# ==============================================================================


class TestSearchLogsExtra:
    """search_logs の追加カバレッジテスト"""

    def test_search_missing_keys_uses_defaults(self, test_client, auth_headers):
        """sudo_wrapper 戻り値にキーが不足していてもデフォルトで補完"""
        mock_data = {}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pattern"] == "test"
        assert data["logfile"] == "syslog"
        assert data["results"] == []
        assert data["lines_returned"] == 0

    def test_search_custom_logfile(self, test_client, auth_headers):
        """logfile パラメータに auth.log を指定"""
        mock_data = {
            "pattern": "error",
            "logfile": "auth.log",
            "results": [],
            "lines_returned": 0,
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ) as mock:
            resp = test_client.get(
                "/api/logsearch/search?pattern=error&logfile=auth.log",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("error", "auth.log", 50)

    def test_search_max_lines(self, test_client, auth_headers):
        """lines=200 (最大値) で正常に動作"""
        mock_data = {"results": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ) as mock:
            resp = test_client.get(
                "/api/logsearch/search?pattern=test&lines=200",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("test", "syslog", 200)

    def test_search_min_lines(self, test_client, auth_headers):
        """lines=1 (最小値) で正常に動作"""
        mock_data = {"results": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ) as mock:
            resp = test_client.get(
                "/api/logsearch/search?pattern=test&lines=1",
                headers=auth_headers,
            )
        assert resp.status_code == 200
        mock.assert_called_once_with("test", "syslog", 1)

    def test_search_logfile_with_dot(self, test_client, auth_headers):
        """logfile にドットを含む名前 (kern.log) で正常に動作"""
        mock_data = {"results": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test&logfile=kern.log",
                headers=auth_headers,
            )
        assert resp.status_code == 200

    def test_search_logfile_with_hyphen(self, test_client, auth_headers):
        """logfile にハイフンを含む名前 (dpkg-log) で正常に動作"""
        mock_data = {"results": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test&logfile=dpkg-log",
                headers=auth_headers,
            )
        assert resp.status_code == 200

    def test_search_logfile_with_underscore(self, test_client, auth_headers):
        """logfile にアンダースコアを含む名前で正常に動作"""
        mock_data = {"results": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.search_logs", return_value=mock_data
        ):
            resp = test_client.get(
                "/api/logsearch/search?pattern=test&logfile=my_custom_log",
                headers=auth_headers,
            )
        assert resp.status_code == 200


# ==============================================================================
# /recent-errors 追加テスト
# ==============================================================================


class TestRecentErrorsExtra:
    """recent-errors の追加カバレッジテスト"""

    def test_recent_errors_missing_keys_uses_defaults(self, test_client, auth_headers):
        """sudo_wrapper 戻り値にキーが不足していてもデフォルトで補完"""
        mock_data = {}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["errors"] == []
        assert data["error_count"] == 0
        assert "timestamp" in data

    def test_recent_errors_large_count(self, test_client, auth_headers):
        """大量のエラーでも正常に返ること"""
        errors = [f"error line {i}" for i in range(100)]
        mock_data = {
            "errors": errors,
            "error_count": 100,
            "timestamp": "2026-01-01T00:00:00Z",
        }
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_recent_errors",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/recent-errors", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["error_count"] == 100


# ==============================================================================
# /tail 追加テスト
# ==============================================================================


class TestTailExtra:
    """tail の追加カバレッジテスト"""

    def test_tail_missing_keys_uses_defaults(self, test_client, auth_headers):
        """sudo_wrapper 戻り値にキーが不足していてもデフォルトで補完"""
        mock_data = {}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/tail", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == []
        assert data["lines_returned"] == 0
        assert data["lines_per_file"] == 30

    def test_tail_boundary_lines_5(self, test_client, auth_headers):
        """lines=5 (最小値) で正常に動作"""
        mock_data = {"lines": ["line1"], "lines_returned": 1}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            return_value=mock_data,
        ) as mock:
            resp = test_client.get("/api/logsearch/tail?lines=5", headers=auth_headers)
        assert resp.status_code == 200
        mock.assert_called_once_with(5)

    def test_tail_boundary_lines_100(self, test_client, auth_headers):
        """lines=100 (最大値) で正常に動作"""
        mock_data = {"lines": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            return_value=mock_data,
        ) as mock:
            resp = test_client.get(
                "/api/logsearch/tail?lines=100", headers=auth_headers
            )
        assert resp.status_code == 200
        mock.assert_called_once_with(100)

    def test_tail_viewer_can_access(self, test_client, viewer_headers):
        """viewer ロールでも /tail にアクセスできること"""
        mock_data = {"lines": [], "lines_returned": 0}
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_log_tail_multi",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/logsearch/tail", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# /stream SSE 追加テスト
# ==============================================================================


class TestStreamExtra:
    """stream SSE エンドポイントの追加カバレッジテスト"""

    def test_stream_decode_token_returns_none(self, test_client):
        """decode_token が None を返す場合 → 401"""
        with patch("backend.core.auth.decode_token", return_value=None):
            resp = test_client.get(
                "/api/logsearch/stream?logfile=syslog&token=expired_token"
            )
        assert resp.status_code == 401
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "Invalid token" in msg or "token" in msg.lower()

    def test_stream_forbidden_char_ampersand_in_logfile(self, test_client, auth_token):
        """logfile に & を含む場合 → 400"""
        resp = test_client.get(
            f"/api/logsearch/stream?logfile=sys%26log&token={auth_token}"
        )
        assert resp.status_code == 400

    def test_stream_disallowed_logfile_custom(self, test_client, auth_token):
        """ALLOWED_LOG_FILES に含まれないファイル → 400"""
        resp = test_client.get(
            f"/api/logsearch/stream?logfile=nginx.log&token={auth_token}"
        )
        assert resp.status_code == 400
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "not allowed" in msg or "allowed" in msg.lower()

    def test_stream_allowed_logfile_auth_log(self, test_client, auth_token):
        """auth.log (許可リスト内) で SSE 接続成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=auth.log&token={auth_token}"
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"connected" in chunks
        # logfile が auth.log であること
        connected_data = None
        for line in chunks.decode().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("type") == "connected":
                    connected_data = data
                    break
        assert connected_data is not None
        assert connected_data["logfile"] == "auth.log"

    def test_stream_allowed_logfile_kern_log(self, test_client, auth_token):
        """kern.log (許可リスト内) で SSE 接続成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=kern.log&token={auth_token}"
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"connected" in chunks

    def test_stream_allowed_logfile_dpkg_log(self, test_client, auth_token):
        """dpkg.log (許可リスト内) で SSE 接続成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=dpkg.log&token={auth_token}"
            ) as resp:
                assert resp.status_code == 200
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        assert b"connected" in chunks

    def test_stream_multiple_log_lines(self, test_client, auth_token):
        """複数のログ行が連続で配信されること"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[
                b"Jan 01 00:00:00 host sshd: line1\n",
                b"Jan 01 00:00:01 host sshd: line2\n",
                b"Jan 01 00:00:02 host sshd: line3\n",
                b"",
            ]
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
        log_events = [
            json.loads(line[6:])
            for line in decoded.split("\n")
            if line.startswith("data: ") and '"type": "log"' in line
        ]
        assert len(log_events) == 3
        assert "line1" in log_events[0]["line"]
        assert "line2" in log_events[1]["line"]
        assert "line3" in log_events[2]["line"]

    def test_stream_empty_line_skipped(self, test_client, auth_token):
        """空行はスキップされて配信されないこと"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[
                b"\n",  # 空行（strip 後に空文字列）
                b"Jan 01 data line\n",
                b"",
            ]
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
        log_events = [
            json.loads(line[6:])
            for line in decoded.split("\n")
            if line.startswith("data: ") and '"type": "log"' in line
        ]
        assert len(log_events) == 1

    def test_stream_proc_already_exited_skip_terminate(self, test_client, auth_token):
        """proc.returncode が None でない場合 terminate をスキップ"""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0  # 既に終了済み
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                for _ in resp.iter_bytes():
                    pass
        # terminate は呼ばれないこと
        mock_proc.terminate.assert_not_called()

    def test_stream_terminate_timeout_handled(self, test_client, auth_token):
        """proc.wait() がタイムアウトしても例外がハンドリングされる"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                chunks = b""
                for c in resp.iter_bytes():
                    chunks += c
        # エラーなく完了すること
        assert b"connected" in chunks

    def test_stream_utf8_decode_error_handled(self, test_client, auth_token):
        """不正 UTF-8 バイト列が errors='replace' で処理されること"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[
                b"valid line with \xff\xfe invalid bytes\n",
                b"",
            ]
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
        assert '"type": "log"' in decoded

    def test_stream_headers_correct(self, test_client, auth_token):
        """SSE レスポンスのヘッダーが正しいこと"""
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.terminate = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with test_client.stream(
                "GET", f"/api/logsearch/stream?logfile=syslog&token={auth_token}"
            ) as resp:
                assert "text/event-stream" in resp.headers.get("content-type", "")
                assert resp.headers.get("cache-control") == "no-cache"
                assert resp.headers.get("x-accel-buffering") == "no"
                for _ in resp.iter_bytes():
                    pass


# ==============================================================================
# FORBIDDEN_CHARS 定数テスト
# ==============================================================================


class TestForbiddenCharsConstant:
    """FORBIDDEN_CHARS 定数の完全性テスト"""

    def test_forbidden_chars_count(self):
        """禁止文字が15種あること"""
        from backend.api.routes.logsearch import FORBIDDEN_CHARS

        assert len(FORBIDDEN_CHARS) == 15

    def test_forbidden_chars_contains_shell_metacharacters(self):
        """シェルメタ文字が全て含まれること"""
        from backend.api.routes.logsearch import FORBIDDEN_CHARS

        expected = [
            ";",
            "|",
            "&",
            "$",
            "(",
            ")",
            "`",
            ">",
            "<",
            "*",
            "?",
            "{",
            "}",
            "[",
            "]",
        ]
        for ch in expected:
            assert ch in FORBIDDEN_CHARS


# ==============================================================================
# _STREAM_ALLOWED_LOG_FILES 定数テスト
# ==============================================================================


class TestStreamAllowedLogFiles:
    """_STREAM_ALLOWED_LOG_FILES の定数テスト"""

    def test_stream_allowed_log_files_content(self):
        """許可リストが期待通りの内容であること"""
        from backend.api.routes.logsearch import _STREAM_ALLOWED_LOG_FILES

        assert "syslog" in _STREAM_ALLOWED_LOG_FILES
        assert "auth.log" in _STREAM_ALLOWED_LOG_FILES
        assert "kern.log" in _STREAM_ALLOWED_LOG_FILES
        assert "dpkg.log" in _STREAM_ALLOWED_LOG_FILES
