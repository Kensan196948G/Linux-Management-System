"""
journal.py カバレッジ改善テスト

対象: backend/api/routes/journal.py
既存テストと重複しない、search/stats/validate のエッジケースを網羅
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _mock_result(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# =====================================================================
# _validate_unit_name 単体テスト
# =====================================================================


class TestValidateUnitName:
    """_validate_unit_name ヘルパー関数のテスト"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from backend.api.routes.journal import _validate_unit_name

        self.fn = _validate_unit_name

    @pytest.mark.parametrize(
        "name",
        [
            "nginx.service",
            "sshd.service",
            "systemd-networkd",
            "user@1000.service",
            "a",
        ],
    )
    def test_valid_names(self, name):
        """正常なユニット名は例外を投げない"""
        self.fn(name)  # should not raise

    def test_empty_name_raises(self):
        """空文字列は HTTPException"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn("")
        assert exc_info.value.status_code == 400

    def test_none_name_raises(self):
        """None は HTTPException"""
        with pytest.raises(HTTPException):
            self.fn(None)

    def test_too_long_name_raises(self):
        """129文字はHTTPException"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn("a" * 129)
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        "name",
        [
            "nginx;rm",
            "nginx|cat",
            "nginx$var",
            "nginx`cmd`",
            "nginx (test)",
            "nginx&bg",
        ],
    )
    def test_special_chars_rejected(self, name):
        """特殊文字を含むユニット名は拒否"""
        with pytest.raises(HTTPException) as exc_info:
            self.fn(name)
        assert exc_info.value.status_code == 400

    def test_128_char_name_accepted(self):
        """128文字ちょうどは受理"""
        self.fn("a" * 128)  # should not raise


# =====================================================================
# GET /api/journal/search エッジケース
# =====================================================================


class TestJournalSearchEdgeCases:
    """search エンドポイントの追加エッジケース"""

    @patch("subprocess.run")
    def test_search_with_since_param(self, mock_run, test_client, admin_headers):
        """since パラメータ付き検索"""
        mock_run.return_value = _mock_result("log line")
        resp = test_client.get(
            "/api/journal/search?since=-1h",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["since"] == "-1h"

    @patch("subprocess.run")
    def test_search_with_until_param(self, mock_run, test_client, admin_headers):
        """until パラメータ付き検索"""
        mock_run.return_value = _mock_result("log line")
        resp = test_client.get(
            "/api/journal/search?until=2026-03-15T00:00:00Z",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["query"]["until"] is not None

    @patch("subprocess.run")
    def test_search_with_since_and_until(self, mock_run, test_client, admin_headers):
        """since + until 複合検索"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            "/api/journal/search?since=-7d&until=-1d",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        q = resp.json()["query"]
        assert q["since"] == "-7d"
        assert q["until"] == "-1d"

    def test_search_invalid_since_chars(self, test_client, admin_headers):
        """since にシェル注入文字 → 400"""
        resp = test_client.get(
            "/api/journal/search?since=today;rm+-rf+/",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_search_invalid_until_chars(self, test_client, admin_headers):
        """until にシェル注入文字 → 400"""
        resp = test_client.get(
            "/api/journal/search?until=now$(cat+/etc/passwd)",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_search_grep_too_long(self, test_client, admin_headers):
        """grep パターンが257文字 → 400"""
        long_pattern = "a" * 257
        resp = test_client.get(
            f"/api/journal/search?grep={long_pattern}",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @patch("subprocess.run")
    def test_search_grep_256_chars_accepted(self, mock_run, test_client, admin_headers):
        """grep パターン256文字は許容"""
        pattern = "a" * 256
        mock_run.return_value = _mock_result("")
        resp = test_client.get(
            f"/api/journal/search?grep={pattern}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_grep,expected",
        [
            ("test;cmd", 400),
            ("test|pipe", 400),
            ("test$var", 400),
            ("test`cmd`", 400),
            ("test(group)", 400),
            ("test[bracket]", 400),
            ("test{brace}", 400),
        ],
    )
    def test_search_grep_shell_chars_rejected(
        self, bad_grep, expected, test_client, admin_headers
    ):
        """grep に危険な文字 → 400"""
        # URL エンコード済みで送信 (params で渡す)
        resp = test_client.get(
            "/api/journal/search",
            params={"grep": bad_grep},
            headers=admin_headers,
        )
        assert resp.status_code == expected

    @patch("subprocess.run")
    def test_search_multiple_units(self, mock_run, test_client, admin_headers):
        """カンマ区切りで複数ユニット"""
        mock_run.return_value = _mock_result("line1\nline2")
        resp = test_client.get(
            "/api/journal/search?units=nginx.service,sshd.service",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        units = resp.json()["query"]["units"]
        assert "nginx.service" in units
        assert "sshd.service" in units

    def test_search_invalid_unit_in_list(self, test_client, admin_headers):
        """ユニットリスト中に不正な名前 → 400"""
        resp = test_client.get(
            "/api/journal/search?units=nginx.service,evil;cmd",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    @patch("subprocess.run")
    def test_search_timeout_503(self, mock_run, test_client, admin_headers):
        """subprocess タイムアウト → 503"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="journalctl", timeout=30)
        resp = test_client.get("/api/journal/search", headers=admin_headers)
        assert resp.status_code == 503

    @patch("subprocess.run")
    def test_search_general_exception_503(self, mock_run, test_client, admin_headers):
        """一般例外 → 503"""
        mock_run.side_effect = OSError("journalctl not found")
        resp = test_client.get("/api/journal/search", headers=admin_headers)
        assert resp.status_code == 503

    @patch("subprocess.run")
    def test_search_empty_results(self, mock_run, test_client, admin_headers):
        """結果なし → count=0"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/search", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @patch("subprocess.run")
    def test_search_with_all_params(self, mock_run, test_client, admin_headers):
        """全パラメータ指定"""
        mock_run.return_value = _mock_result("matched line")
        resp = test_client.get(
            "/api/journal/search?units=nginx.service&priority=err&since=-1h&until=now&grep=error&lines=50",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        q = resp.json()["query"]
        assert q["priority"] == "err"
        assert q["lines"] == 50

    @patch("subprocess.run")
    def test_search_empty_units_ignored(self, mock_run, test_client, admin_headers):
        """空のunitsパラメータ"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/search?units=", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["query"]["units"] == []

    @patch("subprocess.run")
    def test_search_today_since(self, mock_run, test_client, admin_headers):
        """since=today は有効"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/search?since=today", headers=admin_headers)
        assert resp.status_code == 200


# =====================================================================
# GET /api/journal/stats エッジケース
# =====================================================================


class TestJournalStatsEdgeCases:
    """stats エンドポイントの追加エッジケース"""

    @patch("subprocess.run")
    def test_stats_custom_hours(self, mock_run, test_client, admin_headers):
        """hours=48 でカスタム期間"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats?hours=48", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 48

    @patch("subprocess.run")
    def test_stats_max_hours_720(self, mock_run, test_client, admin_headers):
        """hours=720 は受理"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats?hours=720", headers=admin_headers)
        assert resp.status_code == 200

    def test_stats_hours_zero_rejected(self, test_client, admin_headers):
        """hours=0 は 422"""
        resp = test_client.get("/api/journal/stats?hours=0", headers=admin_headers)
        assert resp.status_code == 422

    @patch("subprocess.run")
    def test_stats_subprocess_error_returns_minus_one(
        self, mock_run, test_client, admin_headers
    ):
        """subprocess 例外で by_priority に -1"""
        mock_run.side_effect = Exception("journalctl failed")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        for pri in ["emerg", "alert", "crit", "err", "warning"]:
            assert data["by_priority"][pri] == -1

    @patch("subprocess.run")
    def test_stats_total_errors_excludes_negatives(
        self, mock_run, test_client, admin_headers
    ):
        """total_errors は -1 を除外して合算"""
        # 最初の呼び出しは成功、残りは失敗
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_result("error1\nerror2")
            raise Exception("fail")

        mock_run.side_effect = side_effect
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # total_errors >= 0 (負の値は除外される)
        assert data["total_errors"] >= 0

    @patch("subprocess.run")
    def test_stats_has_timestamp(self, mock_run, test_client, admin_headers):
        """レスポンスに timestamp が含まれる"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    @patch("subprocess.run")
    def test_stats_all_priorities_present(self, mock_run, test_client, admin_headers):
        """by_priority に全優先度が含まれる"""
        mock_run.return_value = _mock_result("")
        resp = test_client.get("/api/journal/stats", headers=admin_headers)
        data = resp.json()
        for pri in ["emerg", "alert", "crit", "err", "warning"]:
            assert pri in data["by_priority"]


# =====================================================================
# 各エンドポイントの追加パターン
# =====================================================================


class TestJournalListEdgeCases:
    """list エンドポイントの追加テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_empty_response(self, mock_method, test_client, admin_headers):
        """空のログ出力"""
        mock_method.return_value = {"stdout": "", "stderr": ""}
        resp = test_client.get("/api/journal/list", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["logs"] == []

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_list")
    def test_list_has_timestamp(self, mock_method, test_client, admin_headers):
        """レスポンスに timestamp が含まれる"""
        mock_method.return_value = {"stdout": "line1", "stderr": ""}
        resp = test_client.get("/api/journal/list", headers=admin_headers)
        assert "timestamp" in resp.json()


class TestJournalUnitLogsEdgeCases:
    """unit-logs エンドポイントの追加テスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_with_at_sign(self, mock_method, test_client, admin_headers):
        """@ を含むユニット名 (user@1000)"""
        mock_method.return_value = {"stdout": "log line", "stderr": ""}
        resp = test_client.get(
            "/api/journal/unit-logs/user@1000", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["unit"] == "user@1000"

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_unit_logs")
    def test_unit_logs_with_colon(self, mock_method, test_client, admin_headers):
        """コロンを含むユニット名"""
        mock_method.return_value = {"stdout": "log", "stderr": ""}
        resp = test_client.get(
            "/api/journal/unit-logs/sys-subsystem-net-devices-eth0:0",
            headers=admin_headers,
        )
        # コロンは正規表現に含まれる
        assert resp.status_code == 200

    def test_unit_logs_space_rejected(self, test_client, admin_headers):
        """スペースを含むユニット名 → 400"""
        resp = test_client.get(
            "/api/journal/unit-logs/nginx service", headers=admin_headers
        )
        assert resp.status_code in (400, 422)


class TestJournalPriorityEdgeCases:
    """priority-logs の追加テスト"""

    @pytest.mark.parametrize(
        "pri", ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
    )
    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_journal_priority_logs")
    def test_all_valid_priorities(self, mock_method, pri, test_client, admin_headers):
        """全有効優先度が受理される"""
        mock_method.return_value = {"stdout": "log", "stderr": ""}
        resp = test_client.get(
            f"/api/journal/priority-logs?priority={pri}", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["priority"] == pri
