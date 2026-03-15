"""
journal.py カバレッジ改善テスト v2

対象: backend/api/routes/journal.py
目標: 90%以上のカバレッジ
既存テスト (test_journal_coverage.py) で不足しているパスを網羅する。
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _get_error_message(resp):
    """レスポンスからエラーメッセージを取得 (detail or message)"""
    body = resp.json()
    return body.get("detail") or body.get("message") or ""


def _mock_result(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# =====================================================================
# GET /api/journal/list - 全分岐カバー
# =====================================================================


class TestJournalListV2:
    """list エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_success_with_lines(self, mock_method, test_client, admin_headers):
        """正常系: 複数行のログ返却"""
        mock_method.return_value = {"stdout": "line1\nline2\nline3\n", "stderr": ""}
        resp = test_client.get("/api/journal/list?lines=100", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert data["logs"] == ["line1", "line2", "line3"]
        assert "timestamp" in data

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_custom_lines_param(self, mock_method, test_client, admin_headers):
        """lines パラメータが渡されること"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get("/api/journal/list?lines=500", headers=admin_headers)
        assert resp.status_code == 200
        mock_method.assert_called_once_with(500)

    def test_list_lines_min_boundary(self, test_client, admin_headers):
        """lines=1 は正常"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_journal_list",
            return_value={"stdout": "", "stderr": ""},
        ):
            resp = test_client.get("/api/journal/list?lines=1", headers=admin_headers)
        assert resp.status_code == 200

    def test_list_lines_max_boundary(self, test_client, admin_headers):
        """lines=1000 は正常"""
        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.get_journal_list",
            return_value={"stdout": "", "stderr": ""},
        ):
            resp = test_client.get("/api/journal/list?lines=1000", headers=admin_headers)
        assert resp.status_code == 200

    def test_list_lines_over_max_rejected(self, test_client, admin_headers):
        """lines=1001 は 422"""
        resp = test_client.get("/api/journal/list?lines=1001", headers=admin_headers)
        assert resp.status_code == 422

    def test_list_lines_zero_rejected(self, test_client, admin_headers):
        """lines=0 は 422"""
        resp = test_client.get("/api/journal/list?lines=0", headers=admin_headers)
        assert resp.status_code == 422

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_general_exception_503(self, mock_method, test_client, admin_headers):
        """一般例外 -> 503"""
        mock_method.side_effect = RuntimeError("unexpected error")
        resp = test_client.get("/api/journal/list", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "unexpected error" in msg

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_http_exception_reraise(self, mock_method, test_client, admin_headers):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=429, detail="rate limited")
        resp = test_client.get("/api/journal/list", headers=admin_headers)
        assert resp.status_code == 429

    def test_list_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/list")
        assert resp.status_code in (401, 403)

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_filters_empty_lines(self, mock_method, test_client, admin_headers):
        """空行がフィルタされること"""
        mock_method.return_value = {"stdout": "line1\n\n\nline2\n", "stderr": ""}
        resp = test_client.get("/api/journal/list", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 2


# =====================================================================
# GET /api/journal/units - 全分岐カバー
# =====================================================================


class TestJournalUnitsV2:
    """units エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units")
    def test_units_success(self, mock_method, test_client, admin_headers):
        """正常系: ユニット一覧返却"""
        mock_method.return_value = {
            "stdout": "nginx.service\nsshd.service\ncron.service\n",
            "stderr": "",
        }
        resp = test_client.get("/api/journal/units", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert "nginx.service" in data["units"]

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units")
    def test_units_empty(self, mock_method, test_client, admin_headers):
        """空のユニット一覧"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get("/api/journal/units", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["units"] == []

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units")
    def test_units_general_exception_503(self, mock_method, test_client, admin_headers):
        """一般例外 -> 503"""
        mock_method.side_effect = OSError("journal unavailable")
        resp = test_client.get("/api/journal/units", headers=admin_headers)
        assert resp.status_code == 503
        assert "journal unavailable" in _get_error_message(resp)

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_units")
    def test_units_http_exception_reraise(self, mock_method, test_client, admin_headers):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=500, detail="internal")
        resp = test_client.get("/api/journal/units", headers=admin_headers)
        assert resp.status_code == 500

    def test_units_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/units")
        assert resp.status_code in (401, 403)


# =====================================================================
# GET /api/journal/unit-logs/{unit_name} - 全分岐カバー
# =====================================================================


class TestJournalUnitLogsV2:
    """unit-logs エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_success(self, mock_method, test_client, admin_headers):
        """正常系: 特定ユニットのログ返却"""
        mock_method.return_value = {"stdout": "log1\nlog2\n", "stderr": ""}
        resp = test_client.get(
            "/api/journal/unit-logs/nginx.service", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["unit"] == "nginx.service"
        assert data["count"] == 2

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "nginx service",
            "nginx;rm",
            "nginx|cat",
            "nginx$var",
            "nginx&bg",
            "nginx(test)",
        ],
    )
    def test_unit_logs_invalid_name_400(
        self, invalid_name, test_client, admin_headers
    ):
        """不正なユニット名 -> 400"""
        resp = test_client.get(
            f"/api/journal/unit-logs/{invalid_name}", headers=admin_headers
        )
        assert resp.status_code in (400, 422)

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_value_error_400(self, mock_method, test_client, admin_headers):
        """ValueError -> 400"""
        mock_method.side_effect = ValueError("invalid unit format")
        resp = test_client.get(
            "/api/journal/unit-logs/nginx.service", headers=admin_headers
        )
        assert resp.status_code == 400
        assert "invalid unit format" in _get_error_message(resp)

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_general_exception_503(
        self, mock_method, test_client, admin_headers
    ):
        """一般例外 -> 503"""
        mock_method.side_effect = RuntimeError("journal crash")
        resp = test_client.get(
            "/api/journal/unit-logs/nginx.service", headers=admin_headers
        )
        assert resp.status_code == 503

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_http_exception_reraise(
        self, mock_method, test_client, admin_headers
    ):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=429, detail="rate limit")
        resp = test_client.get(
            "/api/journal/unit-logs/nginx.service", headers=admin_headers
        )
        assert resp.status_code == 429

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_empty_result(self, mock_method, test_client, admin_headers):
        """ログなし -> count=0"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get(
            "/api/journal/unit-logs/nginx.service", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_unit_logs_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/unit-logs/nginx.service")
        assert resp.status_code in (401, 403)


# =====================================================================
# GET /api/journal/boot-logs - 全分岐カバー
# =====================================================================


class TestJournalBootLogsV2:
    """boot-logs エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs")
    def test_boot_logs_success(self, mock_method, test_client, admin_headers):
        """正常系: ブートログ返却"""
        mock_method.return_value = {
            "stdout": "boot line1\nboot line2\n",
            "stderr": "",
        }
        resp = test_client.get("/api/journal/boot-logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["logs"] == ["boot line1", "boot line2"]

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs")
    def test_boot_logs_empty(self, mock_method, test_client, admin_headers):
        """ブートログなし"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get("/api/journal/boot-logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs")
    def test_boot_logs_general_exception_503(
        self, mock_method, test_client, admin_headers
    ):
        """一般例外 -> 503"""
        mock_method.side_effect = OSError("no journal")
        resp = test_client.get("/api/journal/boot-logs", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_boot_logs")
    def test_boot_logs_http_exception_reraise(
        self, mock_method, test_client, admin_headers
    ):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=503, detail="unavailable")
        resp = test_client.get("/api/journal/boot-logs", headers=admin_headers)
        assert resp.status_code == 503

    def test_boot_logs_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/boot-logs")
        assert resp.status_code in (401, 403)


# =====================================================================
# GET /api/journal/kernel-logs - 全分岐カバー
# =====================================================================


class TestJournalKernelLogsV2:
    """kernel-logs エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs")
    def test_kernel_logs_success(self, mock_method, test_client, admin_headers):
        """正常系: カーネルログ返却"""
        mock_method.return_value = {
            "stdout": "kernel msg1\nkernel msg2\n",
            "stderr": "",
        }
        resp = test_client.get("/api/journal/kernel-logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs")
    def test_kernel_logs_empty(self, mock_method, test_client, admin_headers):
        """カーネルログなし"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get("/api/journal/kernel-logs", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs")
    def test_kernel_logs_general_exception_503(
        self, mock_method, test_client, admin_headers
    ):
        """一般例外 -> 503"""
        mock_method.side_effect = RuntimeError("kernel log error")
        resp = test_client.get("/api/journal/kernel-logs", headers=admin_headers)
        assert resp.status_code == 503

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_kernel_logs")
    def test_kernel_logs_http_exception_reraise(
        self, mock_method, test_client, admin_headers
    ):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=502, detail="bad gateway")
        resp = test_client.get("/api/journal/kernel-logs", headers=admin_headers)
        assert resp.status_code == 502

    def test_kernel_logs_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/kernel-logs")
        assert resp.status_code in (401, 403)


# =====================================================================
# GET /api/journal/priority-logs - 全分岐カバー
# =====================================================================


class TestJournalPriorityLogsV2:
    """priority-logs エンドポイントの全分岐テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
    def test_priority_logs_success_default(
        self, mock_method, test_client, admin_headers
    ):
        """デフォルト priority=err の正常系"""
        mock_method.return_value = {"stdout": "error log\n", "stderr": ""}
        resp = test_client.get("/api/journal/priority-logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority"] == "err"
        assert data["count"] == 1

    @pytest.mark.parametrize("bad_priority", ["critical", "error", "warn", "HIGH", "0", ""])
    def test_priority_invalid_rejected(
        self, bad_priority, test_client, admin_headers
    ):
        """不正な優先度 -> 400"""
        resp = test_client.get(
            f"/api/journal/priority-logs?priority={bad_priority}",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
    def test_priority_logs_general_exception_503(
        self, mock_method, test_client, admin_headers
    ):
        """一般例外 -> 503"""
        mock_method.side_effect = OSError("journal error")
        resp = test_client.get(
            "/api/journal/priority-logs?priority=err", headers=admin_headers
        )
        assert resp.status_code == 503

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
    def test_priority_logs_http_exception_reraise(
        self, mock_method, test_client, admin_headers
    ):
        """HTTPException は再送出"""
        mock_method.side_effect = HTTPException(status_code=429, detail="limited")
        resp = test_client.get(
            "/api/journal/priority-logs?priority=err", headers=admin_headers
        )
        assert resp.status_code == 429

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
    def test_priority_logs_empty(self, mock_method, test_client, admin_headers):
        """該当ログなし"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get(
            "/api/journal/priority-logs?priority=emerg", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_priority_logs_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/priority-logs")
        assert resp.status_code in (401, 403)


# =====================================================================
# GET /api/journal/search - 不足分岐カバー
# =====================================================================


class TestJournalSearchV2:
    """search エンドポイントの追加カバレッジ"""

    def test_search_invalid_priority_400(self, test_client, admin_headers):
        """不正な優先度 -> 400"""
        resp = test_client.get(
            "/api/journal/search?priority=critical", headers=admin_headers
        )
        assert resp.status_code == 400
        assert "不正な優先度" in _get_error_message(resp)

    @patch("subprocess.run")
    def test_search_with_valid_priority(self, mock_run, test_client, admin_headers):
        """有効な優先度 -> コマンドに -p が含まれる"""
        mock_run.return_value = _mock_result("log line")
        resp = test_client.get(
            "/api/journal/search?priority=warning", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["priority"] == "warning"

    @patch("subprocess.run")
    def test_search_with_grep_param(self, mock_run, test_client, admin_headers):
        """grep パラメータ付き検索"""
        mock_run.return_value = _mock_result("matched line")
        resp = test_client.get(
            "/api/journal/search?grep=error", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["grep"] == "error"

    @patch("subprocess.run")
    def test_search_empty_priority_ignored(self, mock_run, test_client, admin_headers):
        """空の priority は None として返される"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            "/api/journal/search?priority=", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["priority"] is None

    @patch("subprocess.run")
    def test_search_empty_grep_ignored(self, mock_run, test_client, admin_headers):
        """空の grep は None として返される"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            "/api/journal/search?grep=", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["grep"] is None

    @patch("subprocess.run")
    def test_search_lines_custom(self, mock_run, test_client, admin_headers):
        """lines パラメータが反映される"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            "/api/journal/search?lines=500", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["lines"] == 500

    def test_search_lines_over_max_rejected(self, test_client, admin_headers):
        """lines=2001 は 422"""
        resp = test_client.get(
            "/api/journal/search?lines=2001", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_search_lines_zero_rejected(self, test_client, admin_headers):
        """lines=0 は 422"""
        resp = test_client.get(
            "/api/journal/search?lines=0", headers=admin_headers
        )
        assert resp.status_code == 422

    @patch("subprocess.run")
    def test_search_unit_with_trailing_comma(self, mock_run, test_client, admin_headers):
        """末尾カンマのユニット (空文字列はスキップされる)"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            "/api/journal/search?units=nginx.service,", headers=admin_headers
        )
        assert resp.status_code == 200
        units = resp.json()["query"]["units"]
        assert units == ["nginx.service"]

    def test_search_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/search")
        assert resp.status_code in (401, 403)

    @patch("subprocess.run")
    def test_search_response_has_timestamp(self, mock_run, test_client, admin_headers):
        """レスポンスに timestamp が含まれる"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/search", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    @patch("subprocess.run")
    def test_search_response_status_success(self, mock_run, test_client, admin_headers):
        """レスポンスの status が success"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/search", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# =====================================================================
# GET /api/journal/stats - 不足分岐カバー
# =====================================================================


class TestJournalStatsV2:
    """stats エンドポイントの追加カバレッジ"""

    @patch("subprocess.run")
    def test_stats_default_hours(self, mock_run, test_client, admin_headers):
        """デフォルト hours=24"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 24

    @patch("subprocess.run")
    def test_stats_counts_nonempty_lines(self, mock_run, test_client, admin_headers):
        """空行を除外してカウント"""
        mock_run.return_value = _mock_result("line1\n\nline2\n")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        # 全 5 priority に対して mock が呼ばれ、各2行
        for pri in ["emerg", "alert", "crit", "err", "warning"]:
            assert resp.json()["by_priority"][pri] == 2

    @patch("subprocess.run")
    def test_stats_total_errors_sum(self, mock_run, test_client, admin_headers):
        """total_errors は正の値の合計"""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return _mock_result("error1\nerror2\nerror3")
            return _mock_result("")

        mock_run.side_effect = side_effect
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_errors"] == 9  # 3 * 3 lines

    def test_stats_hours_over_max_rejected(self, test_client, admin_headers):
        """hours=721 は 422"""
        resp = test_client.get("/api/journal/stats?hours=721", headers=admin_headers)
        assert resp.status_code == 422

    @patch("subprocess.run")
    def test_stats_hours_1(self, mock_run, test_client, admin_headers):
        """hours=1 の最小値"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats?hours=1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 1

    @patch("subprocess.run")
    def test_stats_status_success(self, mock_run, test_client, admin_headers):
        """レスポンスの status が success"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_stats_unauthenticated(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/journal/stats")
        assert resp.status_code in (401, 403)


# =====================================================================
# _validate_unit_name 追加テスト
# =====================================================================


class TestValidateUnitNameV2:
    """_validate_unit_name のエッジケース追加テスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.journal import _validate_unit_name

        self.fn = _validate_unit_name

    def test_dot_only_name_accepted(self):
        """ドットのみのユニット名は受理"""
        self.fn("a.b.c")  # should not raise

    def test_hyphen_name_accepted(self):
        """ハイフン含むユニット名は受理"""
        self.fn("my-service")  # should not raise

    def test_at_sign_accepted(self):
        """@ を含むユニット名は受理"""
        self.fn("user@1000.service")  # should not raise

    @pytest.mark.parametrize(
        "bad_name",
        [
            "nginx/service",
            "nginx\\service",
            "nginx service",
            "nginx\tservice",
            "nginx\nservice",
        ],
    )
    def test_special_chars_rejected(self, bad_name):
        """特殊文字を含むユニット名は拒否"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn(bad_name)
        assert exc_info.value.status_code == 400


# =====================================================================
# 定数・モジュールレベルテスト
# =====================================================================


class TestJournalConstants:
    """モジュール定数のテスト"""

    def test_allowed_priorities_frozenset(self):
        """_ALLOWED_PRIORITIES が frozenset であること"""
        from backend.api.routes.journal import _ALLOWED_PRIORITIES

        assert isinstance(_ALLOWED_PRIORITIES, frozenset)
        assert "err" in _ALLOWED_PRIORITIES
        assert "debug" in _ALLOWED_PRIORITIES
        assert len(_ALLOWED_PRIORITIES) == 8

    def test_allowed_units_pattern_compiled(self):
        """_ALLOWED_UNITS_PATTERN がコンパイル済み正規表現"""
        from backend.api.routes.journal import _ALLOWED_UNITS_PATTERN

        assert _ALLOWED_UNITS_PATTERN.match("nginx.service")
        assert not _ALLOWED_UNITS_PATTERN.match("nginx;rm")

    def test_router_exists(self):
        """router がAPIRouterインスタンス"""
        from backend.api.routes.journal import router

        assert router is not None
