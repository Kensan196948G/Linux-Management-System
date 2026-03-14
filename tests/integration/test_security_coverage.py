"""
security.py カバレッジ改善テスト

対象: backend/api/routes/security.py (555 stmts, 27% -> 80%+ 目標)
既存テストと重複しない新規テストに集中する。

テスト方針:
  - ヘルパー関数の直接テスト (tmp_path + patch)
  - エンドポイントのエッジケース
  - parametrize で境界値を網羅
"""

import json
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest


# ==============================================================================
# テストデータ生成ヘルパー
# ==============================================================================


def _make_entry(
    operation: str,
    user_id: str = "admin",
    status: str = "success",
    target: str = "system",
    details: dict = None,
    hours_ago: float = 0,
) -> dict:
    ts = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return {
        "timestamp": ts.isoformat(),
        "operation": operation,
        "user_id": user_id,
        "target": target,
        "status": status,
        "details": details or {},
    }


def _write_jsonl(path: Path, entries: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _make_mock_conn(port: int, pid: int = 1234, status: str = "LISTEN") -> MagicMock:
    conn = MagicMock()
    conn.status = status
    conn.laddr = MagicMock()
    conn.laddr.port = port
    conn.pid = pid
    conn.type = MagicMock()
    conn.type.name = "SOCK_STREAM"
    return conn


# ==============================================================================
# 1. _read_audit_jsonl ヘルパーテスト
# ==============================================================================


class TestReadAuditJsonl:
    """_read_audit_jsonl の境界値テスト"""

    def test_empty_file_returns_empty_list(self, tmp_path):
        """空ファイルは空リストを返す"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert _read_audit_jsonl(f) == []

    def test_blank_lines_skipped(self, tmp_path):
        """空行はスキップされる"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "blanks.jsonl"
        f.write_text('\n\n{"a":1}\n\n{"b":2}\n\n', encoding="utf-8")
        result = _read_audit_jsonl(f)
        assert len(result) == 2

    def test_mixed_valid_invalid_lines(self, tmp_path):
        """有効行と無効行が混在していても有効行のみ返す"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "mixed.jsonl"
        f.write_text(
            '{"ok":1}\n' "not json at all\n" '{"ok":2}\n' "{bad json\n" '{"ok":3}\n',
            encoding="utf-8",
        )
        result = _read_audit_jsonl(f)
        assert len(result) == 3

    def test_single_entry(self, tmp_path):
        """1行のみのファイル"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "single.jsonl"
        f.write_text('{"key": "value"}\n', encoding="utf-8")
        result = _read_audit_jsonl(f)
        assert len(result) == 1
        assert result[0]["key"] == "value"

    def test_unicode_content(self, tmp_path):
        """日本語を含むJSON行を正しくパースする"""
        from backend.api.routes.security import _read_audit_jsonl

        f = tmp_path / "unicode.jsonl"
        f.write_text('{"msg": "テスト"}\n', encoding="utf-8")
        result = _read_audit_jsonl(f)
        assert result[0]["msg"] == "テスト"


# ==============================================================================
# 2. _collect_failed_logins_hourly ヘルパーテスト
# ==============================================================================


class TestCollectFailedLoginsHourly:
    """_collect_failed_logins_hourly の詳細テスト"""

    def test_empty_entries(self):
        """空リストで total=0, hourly=24スロット"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        result = _collect_failed_logins_hourly([])
        assert result.total == 0
        assert result.unique_ips == 0
        assert len(result.hourly) == 24

    def test_non_login_failed_ignored(self):
        """login_failed 以外のoperationは無視"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [_make_entry("login_success", hours_ago=1)]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 0

    def test_entry_missing_timestamp_skipped(self):
        """timestamp が欠落したエントリはスキップ"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [{"operation": "login_failed"}]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 0

    def test_entry_invalid_timestamp_skipped(self):
        """不正な timestamp はスキップ"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [{"operation": "login_failed", "timestamp": "not-a-date"}]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 0

    def test_old_entry_excluded(self):
        """25時間以上前のエントリは除外"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [_make_entry("login_failed", hours_ago=25)]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 0

    def test_recent_entry_counted(self):
        """直近のエントリはカウントされる"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [
            _make_entry("login_failed", hours_ago=0.5, details={"ip": "1.2.3.4"})
        ]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 1
        assert result.unique_ips == 1

    def test_unique_ip_counting_with_source_ip(self):
        """details.source_ip からIPを取得"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [
            _make_entry("login_failed", hours_ago=1, details={"source_ip": "10.0.0.1"}),
            _make_entry("login_failed", hours_ago=1, details={"source_ip": "10.0.0.1"}),
        ]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 2
        assert result.unique_ips == 1

    def test_ip_from_target_field(self):
        """details.ip / source_ip がない場合は target からIPを取得"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        entries = [_make_entry("login_failed", hours_ago=1, target="10.0.0.99")]
        result = _collect_failed_logins_hourly(entries)
        assert result.unique_ips == 1

    def test_naive_timestamp_treated_as_utc(self):
        """tzinfo がないタイムスタンプはUTCとして扱う"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        entries = [{"operation": "login_failed", "timestamp": ts}]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 1

    def test_hourly_slots_have_hour_and_count(self):
        """各hourlyスロットにhourとcountがある"""
        from backend.api.routes.security import _collect_failed_logins_hourly

        result = _collect_failed_logins_hourly([])
        for item in result.hourly:
            assert hasattr(item, "hour")
            assert hasattr(item, "count")
            assert item.count >= 0


# ==============================================================================
# 3. _collect_open_ports_psutil ヘルパーテスト
# ==============================================================================


class TestCollectOpenPortsPsutil:
    """_collect_open_ports_psutil の詳細テスト"""

    def test_empty_connections(self):
        """接続なしの場合は空リスト"""
        from backend.api.routes.security import _collect_open_ports_psutil

        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[]
        ):
            result = _collect_open_ports_psutil()
        assert result == []

    def test_access_denied_returns_empty(self):
        """AccessDenied でも空リスト（例外を飲む）"""
        from backend.api.routes.security import _collect_open_ports_psutil

        with patch(
            "backend.api.routes.security.psutil.net_connections",
            side_effect=psutil.AccessDenied(pid=1),
        ):
            result = _collect_open_ports_psutil()
        assert result == []

    def test_permission_error_returns_empty(self):
        """PermissionError でも空リスト"""
        from backend.api.routes.security import _collect_open_ports_psutil

        with patch(
            "backend.api.routes.security.psutil.net_connections",
            side_effect=PermissionError("no permission"),
        ):
            result = _collect_open_ports_psutil()
        assert result == []

    def test_non_listen_connections_ignored(self):
        """LISTEN 以外の接続はスキップ"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=80, status="ESTABLISHED")
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            result = _collect_open_ports_psutil()
        assert result == []

    def test_connection_without_laddr_ignored(self):
        """laddr がない接続はスキップ"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = MagicMock()
        conn.status = "LISTEN"
        conn.laddr = None
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            result = _collect_open_ports_psutil()
        assert result == []

    def test_duplicate_port_deduplicated(self):
        """同じポートが複数あっても重複除去"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn1 = _make_mock_conn(port=80, pid=100)
        conn2 = _make_mock_conn(port=80, pid=200)
        with patch(
            "backend.api.routes.security.psutil.net_connections",
            return_value=[conn1, conn2],
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "nginx"
                result = _collect_open_ports_psutil()
        assert len(result) == 1

    def test_dangerous_port_flagged(self):
        """危険ポート (21, 23, 25等) は dangerous=True"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=23, pid=100)
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "telnetd"
                result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].dangerous is True

    def test_safe_port_not_flagged(self):
        """非危険ポート (8080等) は dangerous=False"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=8080, pid=100)
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "uvicorn"
                result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].dangerous is False

    def test_process_name_resolved(self):
        """pid が存在する場合はプロセス名を取得"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=22, pid=1000)
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "sshd"
                result = _collect_open_ports_psutil()
        assert result[0].name == "sshd"

    def test_process_no_such_process(self):
        """NoSuchProcess でも name=None で正常返却"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=22, pid=99999)
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch(
                "backend.api.routes.security.psutil.Process",
                side_effect=psutil.NoSuchProcess(pid=99999),
            ):
                result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].name is None

    def test_process_access_denied(self):
        """Process AccessDenied でも name=None で正常返却"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=22, pid=1)
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            with patch(
                "backend.api.routes.security.psutil.Process",
                side_effect=psutil.AccessDenied(pid=1),
            ):
                result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].name is None

    def test_no_pid_connection(self):
        """pid が None の接続"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conn = _make_mock_conn(port=443, pid=None)
        conn.pid = None
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=[conn]
        ):
            result = _collect_open_ports_psutil()
        assert len(result) == 1
        assert result[0].pid is None
        assert result[0].name is None

    def test_sorted_by_port(self):
        """結果がポート番号でソートされる"""
        from backend.api.routes.security import _collect_open_ports_psutil

        conns = [
            _make_mock_conn(port=8080, pid=1),
            _make_mock_conn(port=22, pid=2),
            _make_mock_conn(port=443, pid=3),
        ]
        with patch(
            "backend.api.routes.security.psutil.net_connections", return_value=conns
        ):
            with patch("backend.api.routes.security.psutil.Process") as mp:
                mp.return_value.name.return_value = "daemon"
                result = _collect_open_ports_psutil()
        ports = [p.port for p in result]
        assert ports == sorted(ports)


# ==============================================================================
# 4. _collect_sudo_history ヘルパーテスト
# ==============================================================================


class TestCollectSudoHistory:
    """_collect_sudo_history の詳細テスト"""

    def test_empty_entries(self):
        """空リストで空の結果"""
        from backend.api.routes.security import _collect_sudo_history

        result = _collect_sudo_history([])
        assert result == []

    def test_limit_default_20(self):
        """デフォルトlimit=20"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [_make_entry("op_" + str(i), hours_ago=i * 0.1) for i in range(30)]
        result = _collect_sudo_history(entries)
        assert len(result) <= 20

    def test_custom_limit(self):
        """カスタムlimit"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [_make_entry("op_" + str(i), hours_ago=i * 0.1) for i in range(10)]
        result = _collect_sudo_history(entries, limit=5)
        assert len(result) <= 5

    def test_custom_days(self):
        """days パラメータで期間を制限"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [
            _make_entry("recent_op", hours_ago=1),
            _make_entry("old_op", hours_ago=24 * 10),  # 10日前
        ]
        result = _collect_sudo_history(entries, days=3)
        assert len(result) == 1

    def test_entry_without_timestamp_skipped(self):
        """timestamp がないエントリはスキップ"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [{"operation": "test_op"}]
        result = _collect_sudo_history(entries)
        assert result == []

    def test_entry_invalid_timestamp_skipped(self):
        """不正な timestamp はスキップ"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [{"operation": "test_op", "timestamp": "invalid"}]
        result = _collect_sudo_history(entries)
        assert result == []

    def test_empty_operation_skipped(self):
        """operation が空のエントリはスキップ"""
        from backend.api.routes.security import _collect_sudo_history

        ts = datetime.now(tz=timezone.utc).isoformat()
        entries = [{"operation": "", "timestamp": ts}]
        result = _collect_sudo_history(entries)
        assert result == []

    def test_user_defaults_to_unknown(self):
        """user_id が未定義の場合は 'unknown'"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [_make_entry("test_op", hours_ago=0.1)]
        del entries[0]["user_id"]
        result = _collect_sudo_history(entries)
        assert len(result) == 1
        assert result[0].user == "unknown"

    def test_status_defaults_to_unknown(self):
        """status が未定義の場合は 'unknown'"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [_make_entry("test_op", hours_ago=0.1)]
        del entries[0]["status"]
        result = _collect_sudo_history(entries)
        assert len(result) == 1
        assert result[0].result == "unknown"

    def test_naive_timestamp_treated_as_utc(self):
        """tzinfo がないタイムスタンプはUTCとして処理"""
        from backend.api.routes.security import _collect_sudo_history

        ts = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        entries = [
            {"operation": "test_op", "timestamp": ts, "user_id": "u1", "status": "ok"}
        ]
        result = _collect_sudo_history(entries)
        assert len(result) == 1

    def test_reversed_iteration(self):
        """逆順で最新エントリを先に取得"""
        from backend.api.routes.security import _collect_sudo_history

        entries = [
            _make_entry("old_op", hours_ago=5),
            _make_entry("new_op", hours_ago=0.1),
        ]
        result = _collect_sudo_history(entries, limit=1)
        assert result[0].operation == "new_op"


# ==============================================================================
# 5. _calculate_security_score ヘルパーテスト
# ==============================================================================


class TestCalculateSecurityScore:
    """_calculate_security_score の境界値テスト"""

    def test_perfect_score(self):
        """脅威なしで高スコア"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(0, 0, 0, 0)
        assert result.score >= 90

    def test_max_failed_logins(self):
        """20件以上の失敗ログインでリスク最大"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(20, 0, 0, 0)
        assert result.details.failed_login_risk == 0

    def test_dangerous_ports_decrease_score(self):
        """危険ポートがスコアを下げる"""
        from backend.api.routes.security import _calculate_security_score

        r_safe = _calculate_security_score(0, 3, 0, 0)
        r_danger = _calculate_security_score(0, 3, 2, 0)
        assert r_safe.score > r_danger.score

    def test_many_open_ports_decrease_score(self):
        """ポートが多いとスコアが下がる"""
        from backend.api.routes.security import _calculate_security_score

        r_few = _calculate_security_score(0, 3, 0, 0)
        r_many = _calculate_security_score(0, 15, 0, 0)
        assert r_few.score >= r_many.score

    def test_sudo_ops_affect_score(self):
        """sudo操作数がスコアに影響"""
        from backend.api.routes.security import _calculate_security_score

        r_low = _calculate_security_score(0, 0, 0, 0)
        r_high = _calculate_security_score(0, 0, 0, 50)
        assert r_low.score >= r_high.score

    def test_score_clamped_to_0_100(self):
        """スコアは 0-100 にクランプ"""
        from backend.api.routes.security import _calculate_security_score

        r_max = _calculate_security_score(100, 50, 10, 200)
        assert 0 <= r_max.score <= 100
        r_min = _calculate_security_score(0, 0, 0, 0)
        assert 0 <= r_min.score <= 100

    def test_details_risk_clamped(self):
        """details の各リスク値が 0-100 にクランプ"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(100, 50, 10, 200)
        assert 0 <= result.details.failed_login_risk <= 100
        assert 0 <= result.details.open_ports_risk <= 100

    @pytest.mark.parametrize(
        "failed,expected_risk",
        [
            (0, 100),
            (5, 75),
            (10, 50),
            (20, 0),
        ],
    )
    def test_failed_login_risk_formula(self, failed, expected_risk):
        """失敗ログインリスク計算式の検証"""
        from backend.api.routes.security import _calculate_security_score

        result = _calculate_security_score(failed, 0, 0, 0)
        assert result.details.failed_login_risk == expected_risk


# ==============================================================================
# 6. _check_ssh_config ヘルパーテスト
# ==============================================================================


class TestCheckSshConfig:
    """_check_ssh_config のテスト (ファイルをモック)"""

    def test_default_values_when_file_missing(self):
        """sshd_config が存在しない場合のデフォルト判定"""
        from backend.api.routes.security import _check_ssh_config

        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        assert len(results) == 4
        # PasswordAuthentication デフォルト yes -> non-compliant
        assert results[0][0] == "ssh_password_auth"
        assert results[0][1] is False

    def test_compliant_ssh_config(self):
        """全て準拠の sshd_config"""
        from backend.api.routes.security import _check_ssh_config

        config_text = (
            "PasswordAuthentication no\n"
            "PermitRootLogin no\n"
            "PubkeyAuthentication yes\n"
            "Protocol 2\n"
        )
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        for _, compliant, _, _ in results:
            assert compliant is True

    def test_permit_root_prohibit_password(self):
        """PermitRootLogin prohibit-password も準拠"""
        from backend.api.routes.security import _check_ssh_config

        config_text = "PermitRootLogin prohibit-password\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        prl = [r for r in results if r[0] == "ssh_permit_root"][0]
        assert prl[1] is True

    def test_comment_lines_ignored(self):
        """コメント行は無視される"""
        from backend.api.routes.security import _check_ssh_config

        config_text = "# PasswordAuthentication no\nPasswordAuthentication yes\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        pa = [r for r in results if r[0] == "ssh_password_auth"][0]
        assert pa[1] is False  # yes -> non-compliant

    def test_protocol_1_non_compliant(self):
        """Protocol 1 は非準拠"""
        from backend.api.routes.security import _check_ssh_config

        config_text = "Protocol 1,2\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        proto = [r for r in results if r[0] == "ssh_protocol"][0]
        assert proto[1] is False

    def test_os_error_handled(self):
        """OSError が出ても例外を投げずに返す"""
        from backend.api.routes.security import _check_ssh_config

        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.side_effect = OSError("permission denied")
            MockPath.return_value = mock_path
            results = _check_ssh_config()
        assert len(results) == 4


# ==============================================================================
# 7. _check_password_policy ヘルパーテスト
# ==============================================================================


class TestCheckPasswordPolicy:
    """_check_password_policy のテスト"""

    def test_defaults_when_file_missing(self):
        """login.defs が存在しない場合のデフォルト判定"""
        from backend.api.routes.security import _check_password_policy

        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            results = _check_password_policy()
        assert len(results) == 3

    def test_compliant_policy(self):
        """全て準拠の login.defs"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS 90\nPASS_MIN_LEN 8\nPASS_WARN_AGE 7\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        for _, compliant, _, _ in results:
            assert compliant is True

    def test_non_compliant_max_days(self):
        """PASS_MAX_DAYS > 90 は非準拠"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS 99999\nPASS_MIN_LEN 8\nPASS_WARN_AGE 7\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        max_days = [r for r in results if r[0] == "passwd_max_days"][0]
        assert max_days[1] is False

    def test_non_compliant_min_len(self):
        """PASS_MIN_LEN < 8 は非準拠"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS 60\nPASS_MIN_LEN 5\nPASS_WARN_AGE 7\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        min_len = [r for r in results if r[0] == "passwd_min_len"][0]
        assert min_len[1] is False

    def test_non_numeric_values(self):
        """数値でない値は非準拠"""
        from backend.api.routes.security import _check_password_policy

        config_text = "PASS_MAX_DAYS abc\nPASS_MIN_LEN xyz\nPASS_WARN_AGE qrs\n"
        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = config_text
            MockPath.return_value = mock_path
            results = _check_password_policy()
        for _, compliant, _, _ in results:
            assert compliant is False

    def test_os_error_handled(self):
        """OSError が出ても返す"""
        from backend.api.routes.security import _check_password_policy

        with patch("backend.api.routes.security.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.side_effect = OSError("fail")
            MockPath.return_value = mock_path
            results = _check_password_policy()
        assert len(results) == 3


# ==============================================================================
# 8. _check_firewall_status ヘルパーテスト
# ==============================================================================


class TestCheckFirewallStatus:
    """_check_firewall_status のテスト"""

    def test_no_firewall_detected(self):
        """どのファイアウォールも検出されない場合"""
        from backend.api.routes.security import _check_firewall_status

        with patch("backend.api.routes.security.Path") as MockPath:
            mock_instance = MagicMock()
            mock_instance.exists.return_value = False
            mock_instance.is_dir.return_value = False
            MockPath.return_value = mock_instance
            results = _check_firewall_status()
        assert len(results) == 1
        assert results[0][1] is False  # non-compliant
        assert "未検出" in results[0][2]

    def test_ufw_enabled(self):
        """ufw が有効の場合"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = True
                mock.read_text.return_value = "ENABLED=yes\n"
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = False
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is True
        assert "ufw" in results[0][2]

    def test_ufw_disabled(self):
        """ufw が無効の場合"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = True
                mock.read_text.return_value = "ENABLED=no\n"
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = False
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is False

    def test_firewalld_detected(self):
        """firewalld が検出された場合"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = True
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = False
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is True
        assert "firewalld" in results[0][2]

    def test_iptables_active(self):
        """iptables がアクティブの場合"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = True
                mock.read_text.return_value = "filter\nnat\n"
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert results[0][1] is True
        assert "iptables" in results[0][2]

    def test_ufw_os_error_handled(self):
        """ufw.conf の OSError は無視される"""
        from backend.api.routes.security import _check_firewall_status

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/ufw/ufw.conf":
                mock.exists.return_value = True
                mock.read_text.side_effect = OSError("fail")
            elif str(path_str) == "/etc/firewalld/firewalld.conf":
                mock.exists.return_value = False
            elif str(path_str) == "/proc/net/ip_tables_names":
                mock.exists.return_value = False
            else:
                mock.exists.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_firewall_status()
        assert len(results) == 1


# ==============================================================================
# 9. _check_sudoers ヘルパーテスト
# ==============================================================================


class TestCheckSudoers:
    """_check_sudoers のテスト"""

    def test_no_dangerous_pattern(self):
        """NOPASSWD: ALL がない場合は準拠"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "root ALL=(ALL:ALL) ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = False
            else:
                mock.read_text.side_effect = PermissionError("denied")
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is True
        assert "問題なし" in results[0][2]

    def test_nopasswd_all_detected(self):
        """NOPASSWD: ALL が検出された場合は非準拠"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "user ALL=(ALL) NOPASSWD: ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = False
            else:
                mock.read_text.side_effect = PermissionError("denied")
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is False
        assert "危険な設定" in results[0][2]

    def test_comment_lines_ignored(self):
        """コメント行の NOPASSWD: ALL は無視"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "# user ALL=(ALL) NOPASSWD: ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = False
            else:
                mock.read_text.side_effect = PermissionError("denied")
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is True

    def test_permission_error_on_sudoers(self):
        """PermissionError は安全に処理"""
        from backend.api.routes.security import _check_sudoers

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.side_effect = PermissionError("denied")
                mock.is_file.return_value = True
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = False
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert len(results) == 1

    def test_sudoers_d_scanning(self):
        """sudoers.d 配下のファイルもスキャン"""
        from backend.api.routes.security import _check_sudoers

        extra_file = MagicMock()
        extra_file.is_file.return_value = True
        extra_file.read_text.return_value = "user ALL=(ALL) NOPASSWD: ALL\n"
        extra_file.name = "custom_rule"

        def path_side_effect(path_str):
            mock = MagicMock()
            if str(path_str) == "/etc/sudoers":
                mock.read_text.return_value = "root ALL=(ALL:ALL) ALL\n"
                mock.is_file.return_value = True
                mock.name = "sudoers"
            elif str(path_str) == "/etc/sudoers.d":
                mock.is_dir.return_value = True
                mock.iterdir.return_value = [extra_file]
            return mock

        with patch("backend.api.routes.security.Path", side_effect=path_side_effect):
            results = _check_sudoers()
        assert results[0][1] is False


# ==============================================================================
# 10. _check_suid_sgid_world_writable ヘルパーテスト
# ==============================================================================


class TestCheckSuidSgidWorldWritable:
    """_check_suid_sgid_world_writable のテスト"""

    def test_no_dangerous_files(self):
        """SUID + world-writable ファイルがない場合は準拠"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_file = MagicMock()
        mock_file.is_file.return_value = True
        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = [mock_file]

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            with patch("backend.api.routes.security.os.stat") as mock_stat:
                stat_result = MagicMock()
                stat_result.st_mode = stat.S_ISUID  # SUID but no world-write
                mock_stat.return_value = stat_result
                results = _check_suid_sgid_world_writable()
        assert results[0][1] is True

    def test_dangerous_file_detected(self):
        """SUID + world-writable ファイルが検出された場合は非準拠"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_file = MagicMock()
        mock_file.is_file.return_value = True
        mock_file.__str__ = lambda self: "/usr/bin/dangerous"

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = [mock_file]

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            with patch("backend.api.routes.security.os.stat") as mock_stat:
                stat_result = MagicMock()
                stat_result.st_mode = stat.S_ISUID | stat.S_IWOTH
                mock_stat.return_value = stat_result
                results = _check_suid_sgid_world_writable()
        assert results[0][1] is False
        assert "件検出" in results[0][2]

    def test_os_stat_error_handled(self):
        """os.stat OSError はスキップ"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_file = MagicMock()
        mock_file.is_file.return_value = True

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.return_value = [mock_file]

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            with patch(
                "backend.api.routes.security.os.stat", side_effect=OSError("fail")
            ):
                results = _check_suid_sgid_world_writable()
        assert results[0][1] is True

    def test_permission_error_on_iterdir(self):
        """iterdir PermissionError は安全に処理"""
        from backend.api.routes.security import _check_suid_sgid_world_writable

        mock_dir = MagicMock()
        mock_dir.is_dir.return_value = True
        mock_dir.iterdir.side_effect = PermissionError("denied")

        with patch("backend.api.routes.security.Path") as MockPath:
            MockPath.side_effect = lambda p: mock_dir
            results = _check_suid_sgid_world_writable()
        assert len(results) == 1


# ==============================================================================
# 11. _estimate_severity ヘルパーテスト
# ==============================================================================


class TestEstimateSeverity:
    """_estimate_severity の parametrize テスト"""

    @pytest.mark.parametrize(
        "pkg,expected",
        [
            ("openssl", "HIGH"),
            ("openssh-server", "HIGH"),
            ("linux-image-5.4", "HIGH"),
            ("kernel-headers", "HIGH"),
            ("libc6", "HIGH"),
            ("glibc", "HIGH"),
            ("sudo", "HIGH"),
            ("curl", "HIGH"),
            ("wget", "HIGH"),
        ],
    )
    def test_high_severity_packages(self, pkg, expected):
        from backend.api.routes.security import _estimate_severity

        assert _estimate_severity(pkg) == expected

    @pytest.mark.parametrize(
        "pkg,expected",
        [
            ("python3", "MEDIUM"),
            ("perl-modules", "MEDIUM"),
            ("ruby2.7", "MEDIUM"),
            ("nodejs", "MEDIUM"),
            ("npm", "MEDIUM"),
            ("apache2", "MEDIUM"),
            ("nginx", "MEDIUM"),
            ("mysql-server", "MEDIUM"),
            ("postgresql-14", "MEDIUM"),
        ],
    )
    def test_medium_severity_packages(self, pkg, expected):
        from backend.api.routes.security import _estimate_severity

        assert _estimate_severity(pkg) == expected

    @pytest.mark.parametrize(
        "pkg,expected",
        [
            ("vim", "LOW"),
            ("htop", "LOW"),
            ("tree", "LOW"),
            ("nano", "LOW"),
            ("jq", "LOW"),
        ],
    )
    def test_low_severity_packages(self, pkg, expected):
        from backend.api.routes.security import _estimate_severity

        assert _estimate_severity(pkg) == expected


# ==============================================================================
# 12. _collect_vulnerability_summary ヘルパーテスト
# ==============================================================================


class TestCollectVulnerabilitySummary:
    """_collect_vulnerability_summary のテスト"""

    def test_apt_not_found(self):
        """apt がない場合は空の結果"""
        from backend.api.routes.security import _collect_vulnerability_summary

        with patch(
            "backend.api.routes.security.subprocess.run", side_effect=FileNotFoundError
        ):
            result = _collect_vulnerability_summary()
        assert result.total_upgradable == 0
        assert result.packages == []

    def test_apt_timeout(self):
        """apt がタイムアウトした場合"""
        from backend.api.routes.security import _collect_vulnerability_summary

        with patch(
            "backend.api.routes.security.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="apt", timeout=30),
        ):
            result = _collect_vulnerability_summary()
        assert result.total_upgradable == 0

    def test_parse_apt_output(self):
        """apt list --upgradable の出力をパース"""
        from backend.api.routes.security import _collect_vulnerability_summary

        apt_output = (
            "Listing... Done\n"
            "openssl/focal-security 1.1.1f-1ubuntu2.22 amd64 [upgradable from: 1.1.1f-1ubuntu2.21]\n"
            "vim/focal 2:8.1.2269 amd64 [upgradable from: 2:8.1.2268]\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.total_upgradable == 2
        assert result.high == 1  # openssl
        assert result.low == 1  # vim

    def test_empty_apt_output(self):
        """アップグレード可能なパッケージがない場合"""
        from backend.api.routes.security import _collect_vulnerability_summary

        mock_proc = MagicMock(returncode=0, stdout="Listing... Done\n", stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.total_upgradable == 0

    def test_max_50_packages(self):
        """最大50件に制限"""
        from backend.api.routes.security import _collect_vulnerability_summary

        lines = ["Listing... Done\n"]
        for i in range(60):
            lines.append(f"pkg{i}/focal 2.0 amd64 [upgradable from: 1.0]\n")
        apt_output = "".join(lines)
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert len(result.packages) <= 50
        assert result.total_upgradable == 60

    def test_severity_counts_consistent(self):
        """high + medium + low == total"""
        from backend.api.routes.security import _collect_vulnerability_summary

        apt_output = (
            "Listing... Done\n"
            "openssl/focal 2.0 amd64 [upgradable from: 1.0]\n"
            "python3/focal 3.10 amd64 [upgradable from: 3.9]\n"
            "vim/focal 9.0 amd64 [upgradable from: 8.0]\n"
        )
        mock_proc = MagicMock(returncode=0, stdout=apt_output, stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.high + result.medium + result.low == result.total_upgradable

    def test_last_updated_is_set(self):
        """last_updated がISO形式で設定される"""
        from backend.api.routes.security import _collect_vulnerability_summary

        mock_proc = MagicMock(returncode=0, stdout="Listing... Done\n", stderr="")
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            result = _collect_vulnerability_summary()
        assert result.last_updated != ""
        # ISO形式でパース可能
        datetime.fromisoformat(result.last_updated.replace("Z", "+00:00"))


# ==============================================================================
# 13. _run_compliance_checks ヘルパーテスト
# ==============================================================================


class TestRunComplianceChecks:
    """_run_compliance_checks の統合テスト"""

    def test_returns_compliance_response(self):
        """ComplianceResponse を返す"""
        from backend.api.routes.security import (
            ComplianceResponse,
            _run_compliance_checks,
        )

        result = _run_compliance_checks()
        assert isinstance(result, ComplianceResponse)

    def test_total_count_matches_checks_length(self):
        """total_count == len(checks)"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        assert result.total_count == len(result.checks)

    def test_counts_consistent(self):
        """compliant + non_compliant == total"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        assert result.compliant_count + result.non_compliant_count == result.total_count

    def test_compliance_rate_calculation(self):
        """compliance_rate の計算が正しい"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        if result.total_count > 0:
            expected = round(result.compliant_count / result.total_count * 100, 1)
            assert result.compliance_rate == expected

    def test_all_categories_present(self):
        """5カテゴリ全て存在する"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        categories = {c.category for c in result.checks}
        assert len(categories) >= 4  # 少なくとも4カテゴリ

    def test_check_items_have_descriptions(self):
        """各チェック項目にdescriptionがある"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        for check in result.checks:
            assert check.description != ""

    def test_non_compliant_has_recommendation(self):
        """非準拠項目にはrecommendationがある"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        for check in result.checks:
            if not check.compliant:
                assert check.recommendation != ""

    def test_compliant_has_empty_recommendation(self):
        """準拠項目のrecommendationは空"""
        from backend.api.routes.security import _run_compliance_checks

        result = _run_compliance_checks()
        for check in result.checks:
            if check.compliant:
                assert check.recommendation == ""


# ==============================================================================
# 14. エンドポイント統合テスト (新規カバレッジ)
# ==============================================================================


class TestScoreEndpointEdgeCases:
    """GET /api/security/score のエッジケース"""

    def test_score_with_exception_returns_500(self, test_client, admin_headers):
        """内部例外で500を返す"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/score", headers=admin_headers)
        assert resp.status_code == 500

    def test_score_with_many_dangerous_ports(self, test_client, admin_headers):
        """危険ポートが多い場合"""
        conns = [_make_mock_conn(port=p) for p in [21, 23, 25, 110, 143]]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=conns
            ):
                with patch("backend.api.routes.security.psutil.Process") as mp:
                    mp.return_value.name.return_value = "daemon"
                    resp = test_client.get("/api/security/score", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["score"] <= 70


class TestSudoHistoryEndpointEdgeCases:
    """GET /api/security/sudo-history のエッジケース"""

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で500"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/sudo-history", headers=admin_headers)
        assert resp.status_code == 500


class TestComplianceEndpointEdgeCases:
    """GET /api/security/compliance のエッジケース"""

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で500"""
        with patch(
            "backend.api.routes.security._run_compliance_checks",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/compliance", headers=admin_headers)
        assert resp.status_code == 500


class TestVulnerabilitySummaryEdgeCases:
    """GET /api/security/vulnerability-summary のエッジケース"""

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で500"""
        with patch(
            "backend.api.routes.security._collect_vulnerability_summary",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get(
                "/api/security/vulnerability-summary", headers=admin_headers
            )
        assert resp.status_code == 500


class TestReportEndpointEdgeCases:
    """GET /api/security/report のエッジケース"""

    def test_exception_returns_500(self, test_client, admin_headers):
        """内部例外で500"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.get("/api/security/report", headers=admin_headers)
        assert resp.status_code == 500

    def test_hostname_os_error_fallback(self, test_client, admin_headers):
        """socket.gethostname() が失敗しても unknown で返る"""
        with patch("backend.api.routes.security.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Listing... Done\n", stderr=""
            )
            with patch(
                "backend.api.routes.security.socket.gethostname",
                side_effect=OSError("fail"),
            ):
                resp = test_client.get("/api/security/report", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["hostname"] == "unknown"


class TestReportExportEndpointEdgeCases:
    """POST /api/security/report/export のエッジケース"""

    def test_export_exception_returns_500(self, test_client, admin_headers):
        """Jinja2 テンプレートエラーで500"""
        with patch(
            "backend.api.routes.security._read_audit_jsonl",
            side_effect=RuntimeError("boom"),
        ):
            resp = test_client.post(
                "/api/security/report/export", headers=admin_headers
            )
        assert resp.status_code == 500

    def test_export_with_data(self, test_client, admin_headers):
        """正常なHTMLエクスポート"""
        entries = [_make_entry("login_failed", hours_ago=1, details={"ip": "1.2.3.4"})]
        with patch(
            "backend.api.routes.security._read_audit_jsonl", return_value=entries
        ):
            with patch("backend.api.routes.security.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="Listing... Done\n", stderr=""
                )
                resp = test_client.post(
                    "/api/security/report/export", headers=admin_headers
                )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_export_hostname_fallback(self, test_client, admin_headers):
        """エクスポートでもhostnameのOSErrorフォールバック"""
        with patch("backend.api.routes.security.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Listing... Done\n", stderr=""
            )
            with patch(
                "backend.api.routes.security.socket.gethostname",
                side_effect=OSError("fail"),
            ):
                resp = test_client.post(
                    "/api/security/report/export", headers=admin_headers
                )
        assert resp.status_code == 200

    def test_export_score_color_green(self, test_client, admin_headers):
        """スコア >= 80 の場合は緑色"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch(
                "backend.api.routes.security.psutil.net_connections", return_value=[]
            ):
                with patch("backend.api.routes.security.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0, stdout="Listing... Done\n", stderr=""
                    )
                    resp = test_client.post(
                        "/api/security/report/export", headers=admin_headers
                    )
        assert resp.status_code == 200
        assert (
            "#22c55e" in resp.text or "#f59e0b" in resp.text or "#ef4444" in resp.text
        )


class TestBanditStatusAdditionalEdgeCases:
    """GET /api/security/bandit-status の追加エッジケース"""

    def test_stderr_used_when_stdout_empty(self, test_client, admin_headers):
        """stdout が空の場合は stderr をパース"""
        bandit_data = {
            "results": [{"issue_severity": "HIGH", "issue_text": "test"}],
            "metrics": {},
        }
        mock_proc = MagicMock(stdout="", stderr=json.dumps(bandit_data), returncode=1)
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["high"] == 1

    def test_bandit_only_low_issues(self, test_client, admin_headers):
        """LOW のみの結果"""
        bandit_data = {
            "results": [
                {"issue_severity": "LOW", "issue_text": "x"},
                {"issue_severity": "LOW", "issue_text": "y"},
            ],
            "metrics": {},
        }
        mock_proc = MagicMock(stdout=json.dumps(bandit_data), stderr="", returncode=1)
        with patch(
            "backend.api.routes.security.subprocess.run", return_value=mock_proc
        ):
            resp = test_client.get("/api/security/bandit-status", headers=admin_headers)
        data = resp.json()
        assert data["high"] == 0
        assert data["medium"] == 0
        assert data["low"] == 2
        assert data["total_issues"] == 2


# ==============================================================================
# 15. Pydantic モデルのテスト
# ==============================================================================


class TestPydanticModels:
    """Pydantic モデルの境界値テスト"""

    def test_port_info_defaults(self):
        """PortInfo のデフォルト値"""
        from backend.api.routes.security import PortInfo

        p = PortInfo(port=80, proto="tcp", state="LISTEN")
        assert p.pid is None
        assert p.name is None
        assert p.dangerous is False

    def test_vulnerable_package_defaults(self):
        """VulnerablePackage のデフォルト値"""
        from backend.api.routes.security import VulnerablePackage

        vp = VulnerablePackage(name="test")
        assert vp.current_version == ""
        assert vp.available_version == ""
        assert vp.severity == "LOW"

    def test_bandit_status_defaults(self):
        """BanditStatusResponse のデフォルト値"""
        from backend.api.routes.security import BanditStatusResponse

        b = BanditStatusResponse(status="test")
        assert b.high == 0
        assert b.medium == 0
        assert b.low == 0
        assert b.total_issues == 0
        assert b.scanned is False
        assert b.error is None

    def test_compliance_response_defaults(self):
        """ComplianceResponse のデフォルト値"""
        from backend.api.routes.security import ComplianceResponse

        c = ComplianceResponse()
        assert c.checks == []
        assert c.compliant_count == 0
        assert c.compliance_rate == 0.0

    def test_vulnerability_summary_defaults(self):
        """VulnerabilitySummaryResponse のデフォルト値"""
        from backend.api.routes.security import VulnerabilitySummaryResponse

        v = VulnerabilitySummaryResponse()
        assert v.total_upgradable == 0
        assert v.packages == []
        assert v.last_updated == ""

    def test_security_score_details(self):
        """SecurityScoreDetails のフィールド"""
        from backend.api.routes.security import SecurityScoreDetails

        d = SecurityScoreDetails(
            failed_login_risk=80, open_ports_risk=60, recent_sudo_ops=5
        )
        assert d.failed_login_risk == 80
        assert d.open_ports_risk == 60
        assert d.recent_sudo_ops == 5


# ==============================================================================
# 16. DANGEROUS_PORTS 定数テスト
# ==============================================================================


class TestDangerousPorts:
    """_DANGEROUS_PORTS 定数の検証"""

    def test_known_dangerous_ports(self):
        """既知の危険ポートが含まれること"""
        from backend.api.routes.security import _DANGEROUS_PORTS

        expected = {21, 23, 25, 110, 143, 512, 513, 514, 3389, 5900}
        assert _DANGEROUS_PORTS == expected

    @pytest.mark.parametrize("port", [21, 23, 25, 110, 143, 512, 513, 514, 3389, 5900])
    def test_each_dangerous_port(self, port):
        """各危険ポートが含まれること"""
        from backend.api.routes.security import _DANGEROUS_PORTS

        assert port in _DANGEROUS_PORTS

    @pytest.mark.parametrize("port", [22, 80, 443, 8080, 8443, 3000])
    def test_safe_ports_not_in_dangerous(self, port):
        """安全なポートは含まれないこと"""
        from backend.api.routes.security import _DANGEROUS_PORTS

        assert port not in _DANGEROUS_PORTS


# ==============================================================================
# 17. _COMPLIANCE_DESCRIPTIONS 定数テスト
# ==============================================================================


class TestComplianceDescriptions:
    """_COMPLIANCE_DESCRIPTIONS 定数の検証"""

    def test_all_check_ids_have_descriptions(self):
        """全チェックIDに説明がある"""
        from backend.api.routes.security import _COMPLIANCE_DESCRIPTIONS

        expected_ids = [
            "ssh_password_auth",
            "ssh_permit_root",
            "ssh_pubkey_auth",
            "ssh_protocol",
            "passwd_max_days",
            "passwd_min_len",
            "passwd_warn_age",
            "firewall_enabled",
            "sudoers_nopasswd_all",
            "suid_world_writable",
        ]
        for check_id in expected_ids:
            assert check_id in _COMPLIANCE_DESCRIPTIONS
            assert _COMPLIANCE_DESCRIPTIONS[check_id] != ""
