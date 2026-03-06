"""
audit_log.py カバレッジ向上テスト

未カバー行:
  - Lines 77-80: record() の except Exception ブロック
  - Line 134: user_id フィルタの continue パス
  - Line 142: start_date フィルタの continue パス
  - Line 144: end_date フィルタの continue パス
"""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.core.audit_log import AuditLog


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _write_entry(path, entry: dict) -> None:
    """JSONL形式でログエントリを追記"""
    with open(path, "a", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
        f.write("\n")


def _make_log_with_entries(tmp_path) -> AuditLog:
    """3件のエントリを持つ AuditLog を返す（日付はナイーブ）"""
    log = AuditLog(log_dir=str(tmp_path))

    entries = [
        {
            "user_id": "user_001",
            "operation": "login",
            "target": "system",
            "status": "success",
            "timestamp": "2026-01-15T10:00:00",
            "details": {},
        },
        {
            "user_id": "user_002",
            "operation": "service_restart",
            "target": "nginx",
            "status": "success",
            "timestamp": "2026-01-16T12:00:00",
            "details": {},
        },
        {
            "user_id": "user_001",
            "operation": "logout",
            "target": "system",
            "status": "success",
            "timestamp": "2026-01-17T14:00:00",
            "details": {},
        },
    ]

    _write_entry(tmp_path / "audit_20260115.json", entries[0])
    _write_entry(tmp_path / "audit_20260116.json", entries[1])
    _write_entry(tmp_path / "audit_20260117.json", entries[2])

    return log


# ---------------------------------------------------------------------------
# record() の例外ハンドリング（lines 77-80）
# ---------------------------------------------------------------------------

class TestAuditLogRecordException:
    """record() の except Exception ブロックのカバレッジテスト"""

    def test_record_reraises_on_write_failure(self, tmp_path):
        """ファイル書き込み失敗時に例外を再送出する（line 80: raise）"""
        log = AuditLog(log_dir=str(tmp_path))

        with patch("builtins.open", side_effect=IOError("disk full")):
            with pytest.raises(IOError, match="disk full"):
                log.record(
                    operation="test_op",
                    user_id="user_001",
                    target="test",
                    status="success",
                    details={},
                )

    def test_record_logs_error_before_reraise(self, tmp_path):
        """例外再送出前に logger.error が呼ばれる（line 78）"""
        log = AuditLog(log_dir=str(tmp_path))

        with patch("builtins.open", side_effect=PermissionError("no permission")):
            with patch("logging.Logger.error") as mock_error:
                with pytest.raises(PermissionError):
                    log.record(
                        operation="test_op",
                        user_id="user_001",
                        target="test",
                        status="success",
                        details={},
                    )
                mock_error.assert_called_once()

    def test_record_reraises_permission_error(self, tmp_path):
        """PermissionError も再送出される"""
        log = AuditLog(log_dir=str(tmp_path))

        with patch("builtins.open", side_effect=PermissionError("permission denied")):
            with pytest.raises(PermissionError, match="permission denied"):
                log.record(
                    operation="service_restart",
                    user_id="admin",
                    target="nginx",
                    status="success",
                )

    def test_record_reraises_os_error(self, tmp_path):
        """OSError も再送出される"""
        log = AuditLog(log_dir=str(tmp_path))

        with patch("builtins.open", side_effect=OSError("no space left")):
            with pytest.raises(OSError):
                log.record(
                    operation="log_view",
                    user_id="operator",
                    target="system",
                    status="success",
                )


# ---------------------------------------------------------------------------
# query() のフィルタ continue パス（lines 134, 142, 144）
# ---------------------------------------------------------------------------

class TestAuditLogQueryFilters:
    """query() のフィルタ continue パスのカバレッジテスト"""

    def test_query_filters_by_user_id_skips_others(self, tmp_path):
        """user_idフィルタ: 別ユーザーのエントリをスキップ（line 134）"""
        log = _make_log_with_entries(tmp_path)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            user_id="user_001",  # user_002 のエントリは continue でスキップ
        )

        assert len(results) == 2
        assert all(r["user_id"] == "user_001" for r in results)

    def test_query_user_id_filter_excludes_user_002(self, tmp_path):
        """user_idフィルタで user_002 のエントリが含まれないこと"""
        log = _make_log_with_entries(tmp_path)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            user_id="user_002",
        )

        assert len(results) == 1
        assert results[0]["user_id"] == "user_002"
        assert results[0]["target"] == "nginx"

    def test_query_filters_by_start_date_skips_old(self, tmp_path):
        """start_dateフィルタ: 古いエントリをスキップ（line 142）"""
        log = _make_log_with_entries(tmp_path)

        # 2026-01-15 のエントリが除外される（ナイーブ datetime で比較）
        start = datetime(2026, 1, 16, 0, 0, 0)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            start_date=start,
        )

        assert len(results) == 2
        for r in results:
            entry_time = datetime.fromisoformat(r["timestamp"])
            assert entry_time >= start

    def test_query_start_date_boundary(self, tmp_path):
        """start_date と同時刻のエントリは含まれる"""
        log = _make_log_with_entries(tmp_path)

        start = datetime(2026, 1, 15, 10, 0, 0)  # 最初のエントリと同時刻

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            start_date=start,
        )

        assert len(results) == 3  # ちょうど >= なので含まれる

    def test_query_filters_by_end_date_skips_new(self, tmp_path):
        """end_dateフィルタ: 新しいエントリをスキップ（line 144）"""
        log = _make_log_with_entries(tmp_path)

        # 2026-01-17 のエントリが除外される
        end = datetime(2026, 1, 16, 23, 59, 59)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            end_date=end,
        )

        assert len(results) == 2
        for r in results:
            entry_time = datetime.fromisoformat(r["timestamp"])
            assert entry_time <= end

    def test_query_end_date_boundary(self, tmp_path):
        """end_date と同時刻のエントリは含まれる"""
        log = _make_log_with_entries(tmp_path)

        end = datetime(2026, 1, 17, 14, 0, 0)  # 最後のエントリと同時刻

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            end_date=end,
        )

        assert len(results) == 3  # ちょうど <= なので含まれる

    def test_query_combined_filters_user_and_start_date(self, tmp_path):
        """複合フィルタ: user_id + start_date（両方の continue パスを経由）"""
        log = _make_log_with_entries(tmp_path)

        start = datetime(2026, 1, 16, 0, 0, 0)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            user_id="user_001",
            start_date=start,
        )

        # user_001 かつ 2026-01-16 以降 → 2026-01-17 のエントリのみ
        assert len(results) == 1
        assert results[0]["operation"] == "logout"

    def test_query_combined_filters_all(self, tmp_path):
        """複合フィルタ: user_id + start_date + end_date"""
        log = _make_log_with_entries(tmp_path)

        start = datetime(2026, 1, 15, 0, 0, 0)
        end = datetime(2026, 1, 15, 23, 59, 59)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            user_id="user_001",
            start_date=start,
            end_date=end,
        )

        assert len(results) == 1
        assert results[0]["operation"] == "login"

    def test_query_no_results_when_all_filtered(self, tmp_path):
        """全エントリがフィルタされると空リストを返す"""
        log = _make_log_with_entries(tmp_path)

        # 存在しない日付範囲
        start = datetime(2030, 1, 1, 0, 0, 0)

        results = log.query(
            user_role="Admin",
            requesting_user_id="admin",
            start_date=start,
        )

        assert results == []
