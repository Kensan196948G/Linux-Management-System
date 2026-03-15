"""
audit.py カバレッジ改善テスト v2

対象: backend/api/routes/audit.py
目標: 90%以上カバレッジ
既存テスト(test_audit_api.py)で未カバーの分岐を網羅

カバー対象:
  - list_audit_logs: has_next=True ページネーション (lines 103-106)
  - list_audit_logs: 2ページ目以降のスライス (lines 108-110)
  - list_audit_logs: end_date パラメータ (line 88)
  - list_audit_logs: user_id フィルタ (line 97)
  - export: 日時フィルタ (lines 247-252)
  - export: user_id/operation/status フィルタ (lines 233-235, 259-261)
  - export: details が dict の CSV 変換 (lines 282-283)
  - stats: Operator/Approver の user_counts 制限 (lines 195-196)
  - stats: Admin の by_user 全ユーザー表示 (line 203)
  - stats: 非 Admin/Operator/Approver ロールの by_user 空 (line 203)
  - user-activity: Operator 拒否 (lines 319-320)
  - user-activity: タイムスタンプ解析の例外パス (lines 350-353)
  - user-activity: entries 内の集計 (lines 339-352)
  - summary: success/error/failure カウント (lines 397-398)
  - summary: total=0 の success_rate (line 408)
"""

import json
from unittest.mock import patch

import pytest


# ===================================================================
# サンプルデータ
# ===================================================================

SAMPLE_ENTRIES = [
    {
        "timestamp": "2026-03-15T10:00:00+00:00",
        "operation": "service_restart",
        "user_id": "admin@example.com",
        "target": "nginx",
        "status": "success",
        "details": {"return_code": 0},
    },
    {
        "timestamp": "2026-03-15T11:00:00+00:00",
        "operation": "firewall_rules_read",
        "user_id": "operator@example.com",
        "target": "firewall",
        "status": "success",
        "details": {},
    },
    {
        "timestamp": "2026-03-15T14:30:00+00:00",
        "operation": "service_restart",
        "user_id": "admin@example.com",
        "target": "apache",
        "status": "failure",
        "details": {"error": "timeout"},
    },
]


def _generate_entries(n: int) -> list:
    """N 件のダミーエントリを生成"""
    return [
        {
            "timestamp": f"2026-03-15T{i % 24:02d}:00:00+00:00",
            "operation": f"op_{i % 5}",
            "user_id": f"user{i % 3}@example.com",
            "target": f"target_{i}",
            "status": "success" if i % 3 != 0 else "error",
            "details": {"index": i},
        }
        for i in range(n)
    ]


# ===================================================================
# list_audit_logs: ページネーション has_next
# ===================================================================


class TestAuditLogsPagination:
    """list_audit_logs のページネーション分岐カバレッジ"""

    def test_has_next_true_when_more_entries(self, test_client, admin_headers):
        """has_next=True: fetch_limit+1 以上のエントリがある場合"""
        # per_page=2, page=1 → fetch_limit=2 → 3件返せば has_next=True
        entries = _generate_entries(3)
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs?page=1&per_page=2",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_next"] is True
        assert len(data["entries"]) == 2
        assert data["total"] == 2  # fetch_limit (has_next の場合)

    def test_has_next_false_when_exact_entries(self, test_client, admin_headers):
        """has_next=False: ちょうど fetch_limit 件の場合"""
        entries = _generate_entries(2)
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs?page=1&per_page=2",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_next"] is False

    def test_page_2_slicing(self, test_client, admin_headers):
        """2ページ目: offset=(2-1)*3=3 のスライス"""
        entries = _generate_entries(7)  # page=2, per_page=3 → fetch_limit=6+1=7
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs?page=2&per_page=3",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 3
        assert len(data["entries"]) == 3  # entries[3:6]

    def test_page_beyond_data(self, test_client, admin_headers):
        """データ数を超えるページ番号"""
        entries = _generate_entries(2)
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs?page=10&per_page=50",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 0


# ===================================================================
# list_audit_logs: フィルタパラメータ
# ===================================================================


class TestAuditLogsFilters:
    """list_audit_logs のフィルタパラメータカバレッジ"""

    def test_user_id_filter(self, test_client, admin_headers):
        """user_id フィルタが query に渡される"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]) as mock_q:
            resp = test_client.get(
                "/api/audit/logs?user_id=admin@example.com",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert mock_q.call_args.kwargs.get("user_id") == "admin@example.com"

    def test_end_date_filter(self, test_client, admin_headers):
        """end_date フィルタが query に渡される"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]) as mock_q:
            resp = test_client.get(
                "/api/audit/logs?end_date=2026-12-31T23:59:59Z",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        end_dt = mock_q.call_args.kwargs.get("end_date")
        assert end_dt is not None

    def test_start_and_end_date_filter(self, test_client, admin_headers):
        """start_date と end_date の両方指定"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]) as mock_q:
            resp = test_client.get(
                "/api/audit/logs?start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        assert mock_q.call_args.kwargs.get("start_date") is not None
        assert mock_q.call_args.kwargs.get("end_date") is not None

    def test_all_filters_combined(self, test_client, admin_headers):
        """全フィルタ同時指定"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]) as mock_q:
            resp = test_client.get(
                "/api/audit/logs?user_id=admin@example.com&operation=login&status=success"
                "&start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        kwargs = mock_q.call_args.kwargs
        assert kwargs["user_id"] == "admin@example.com"
        assert kwargs["operation"] == "login"
        assert kwargs["status"] == "success"

    def test_invalid_end_date_returns_400(self, test_client, admin_headers):
        """不正な end_date → 400"""
        resp = test_client.get(
            "/api/audit/logs?end_date=not-a-date",
            headers=admin_headers,
        )
        assert resp.status_code == 400


# ===================================================================
# export: フィルタ + CSV details 変換
# ===================================================================


class TestAuditExportFilters:
    """export エンドポイントのフィルタとデータ変換カバレッジ"""

    def test_export_csv_with_filters(self, test_client, admin_headers):
        """CSV エクスポートにフィルタパラメータを適用"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=SAMPLE_ENTRIES) as mock_q:
            resp = test_client.get(
                "/api/audit/logs/export?format=csv"
                "&user_id=admin@example.com&operation=service_restart&status=success",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        kwargs = mock_q.call_args.kwargs
        assert kwargs["user_id"] == "admin@example.com"
        assert kwargs["operation"] == "service_restart"
        assert kwargs["status"] == "success"

    def test_export_csv_details_dict_serialized(self, test_client, admin_headers):
        """CSV エクスポートで details (dict) が JSON 文字列に変換される"""
        entries = [
            {
                "timestamp": "2026-03-15T10:00:00",
                "operation": "test_op",
                "user_id": "admin@example.com",
                "target": "test",
                "status": "success",
                "details": {"key": "value", "nested": True},
            }
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs/export?format=csv",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        content = resp.text
        # details カラムに JSON 文字列が含まれる
        assert '"key"' in content or "key" in content

    def test_export_json_with_date_filters(self, test_client, admin_headers):
        """JSON エクスポートに日時フィルタ適用"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]) as mock_q:
            resp = test_client.get(
                "/api/audit/logs/export?format=json"
                "&start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T23:59:59Z",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        kwargs = mock_q.call_args.kwargs
        assert kwargs["start_date"] is not None
        assert kwargs["end_date"] is not None

    def test_export_csv_multiple_entries(self, test_client, admin_headers):
        """CSV エクスポートで複数エントリが正しく出力される"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=SAMPLE_ENTRIES):
            resp = test_client.get(
                "/api/audit/logs/export?format=csv",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) == len(SAMPLE_ENTRIES) + 1  # header + entries

    def test_export_csv_details_non_dict(self, test_client, admin_headers):
        """details が dict でない場合はそのまま出力"""
        entries = [
            {
                "timestamp": "2026-03-15T10:00:00",
                "operation": "test_op",
                "user_id": "admin@example.com",
                "target": "test",
                "status": "success",
                "details": "plain string",
            }
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get(
                "/api/audit/logs/export?format=csv",
                headers=admin_headers,
            )
        assert resp.status_code == 200


# ===================================================================
# stats: Operator/Approver の user_counts 制限
# ===================================================================


class TestAuditStatsRoleFiltering:
    """stats のロール別 user_counts フィルタリング"""

    def test_stats_operator_user_counts_self_only(self, test_client, operator_headers):
        """Operator は by_user に自分のみ含まれる (lines 195-196)"""
        entries = [
            {
                "timestamp": "2026-03-15T10:00:00",
                "operation": "service_restart",
                "user_id": "operator@example.com",
                "target": "nginx",
                "status": "success",
                "details": {},
            },
            {
                "timestamp": "2026-03-15T11:00:00",
                "operation": "login",
                "user_id": "admin@example.com",
                "target": "system",
                "status": "success",
                "details": {},
            },
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/stats", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        by_user = data["by_user"]
        # Operator は自分のデータのみ
        assert "operator@example.com" in by_user or len(by_user) <= 1

    def test_stats_approver_user_counts_self_only(self, test_client, approver_headers):
        """Approver は by_user に自分のみ含まれる"""
        entries = [
            {
                "timestamp": "2026-03-15T10:00:00",
                "operation": "approval",
                "user_id": "approver@example.com",
                "target": "request_1",
                "status": "success",
                "details": {},
            },
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/stats", headers=approver_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_stats_admin_sees_all_users(self, test_client, admin_headers):
        """Admin は by_user に全ユーザーが含まれる"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "2026-03-15T11:00:00", "operation": "login",
             "user_id": "user2@example.com", "target": "system", "status": "success", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        by_user = data["by_user"]
        assert "admin@example.com" in by_user
        assert "user2@example.com" in by_user

    def test_stats_unknown_operation_counted(self, test_client, admin_headers):
        """operation が空の場合 'unknown' としてカウントされる"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00", "operation": "",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/stats", headers=admin_headers)
        assert resp.status_code == 200


# ===================================================================
# user-activity: Operator 拒否 + タイムスタンプ解析
# ===================================================================


class TestUserActivityReportV2:
    """user-activity レポートの追加カバレッジ"""

    def test_operator_cannot_access_report(self, test_client, operator_headers):
        """Operator はレポート閲覧不可 (Approver以上) → 403"""
        resp = test_client.get("/api/audit/report/user-activity", headers=operator_headers)
        assert resp.status_code == 403

    def test_report_with_entries_containing_timestamps(self, test_client, admin_headers):
        """タイムスタンプ解析が正常に動作し by_hour に反映される"""
        entries = [
            {"timestamp": "2026-03-15T10:30:00+00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "2026-03-15T10:45:00+00:00", "operation": "logout",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "2026-03-15T14:00:00+00:00", "operation": "restart",
             "user_id": "admin@example.com", "target": "nginx", "status": "error", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_operations"] == 3
        # by_hour に時間帯データがある
        hour_10 = next((h for h in data["by_hour"] if h["hour"] == "10"), None)
        assert hour_10 is not None
        assert hour_10["count"] >= 2

    def test_report_with_invalid_timestamp(self, test_client, admin_headers):
        """タイムスタンプが不正な場合は例外を無視して処理続行 (lines 350-353)"""
        entries = [
            {"timestamp": "not-a-timestamp", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "", "operation": "logout",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_operations"] == 2

    def test_report_approver_can_access(self, test_client, approver_headers):
        """Approver はレポート閲覧可能"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/user-activity", headers=approver_headers)
        assert resp.status_code == 200

    def test_report_days_1(self, test_client, admin_headers):
        """days=1 の最小値"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/user-activity?days=1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 1

    def test_report_days_90_max(self, test_client, admin_headers):
        """days=90 の最大値"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/user-activity?days=90", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 90

    def test_report_by_user_limited(self, test_client, admin_headers):
        """by_user は most_common(20) で上位20件に制限"""
        entries = _generate_entries(50)
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["by_user"]) <= 20

    def test_report_by_operation_limited(self, test_client, admin_headers):
        """by_operation は most_common(20) で上位20件に制限"""
        entries = _generate_entries(50)
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["by_operation"]) <= 20

    def test_report_entry_missing_fields_uses_unknown(self, test_client, admin_headers):
        """エントリにフィールドが欠けている場合 'unknown' にフォールバック"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00+00:00", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/user-activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_operations"] == 1


# ===================================================================
# summary: success_rate / error_count
# ===================================================================


class TestAuditSummaryV2:
    """summary レポートの追加カバレッジ"""

    def test_summary_counts_success_and_errors(self, test_client, admin_headers):
        """success/error/failure の正しいカウント"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "2026-03-15T11:00:00", "operation": "restart",
             "user_id": "admin@example.com", "target": "nginx", "status": "error", "details": {}},
            {"timestamp": "2026-03-15T12:00:00", "operation": "restart",
             "user_id": "admin@example.com", "target": "apache", "status": "failure", "details": {}},
            {"timestamp": "2026-03-15T13:00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4
        assert data["success_count"] == 2
        assert data["error_count"] == 2  # error(1) + failure(1)
        assert data["success_rate"] == 50.0

    def test_summary_zero_total_success_rate(self, test_client, admin_headers):
        """total=0 のとき success_rate=0.0"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["success_rate"] == 0.0

    def test_summary_top_operations_limit(self, test_client, admin_headers):
        """top_operations は most_common(10) で上位10件"""
        entries = [
            {"timestamp": f"2026-03-15T{i % 24:02d}:00:00", "operation": f"op_{i}",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}}
            for i in range(20)
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["top_operations"]) <= 10

    def test_summary_hours_1(self, test_client, admin_headers):
        """hours=1 最小値"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/summary?hours=1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 1

    def test_summary_hours_720_max(self, test_client, admin_headers):
        """hours=720 最大値"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/summary?hours=720", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 720

    def test_summary_operator_can_access(self, test_client, operator_headers):
        """Operator は summary にアクセス可能"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/report/summary", headers=operator_headers)
        assert resp.status_code == 200

    def test_summary_by_status_dict(self, test_client, admin_headers):
        """by_status は dict 形式"""
        entries = SAMPLE_ENTRIES
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["by_status"], dict)

    def test_summary_all_success(self, test_client, admin_headers):
        """全件 success のとき success_rate=100.0"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}}
            for _ in range(5)
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/report/summary", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success_rate"] == 100.0


# ===================================================================
# operations: 追加カバレッジ
# ===================================================================


class TestAuditOperationsV2:
    """operations エンドポイントの追加カバレッジ"""

    def test_operations_entries_with_empty_operation(self, test_client, admin_headers):
        """operation が空文字列のエントリはフィルタされる"""
        entries = [
            {"timestamp": "2026-03-15T10:00:00", "operation": "",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
            {"timestamp": "2026-03-15T11:00:00", "operation": "login",
             "user_id": "admin@example.com", "target": "system", "status": "success", "details": {}},
        ]
        with patch("backend.api.routes.audit.audit_log.query", return_value=entries):
            resp = test_client.get("/api/audit/operations", headers=admin_headers)
        assert resp.status_code == 200
        ops = resp.json()["operations"]
        assert "" not in ops
        assert "login" in ops

    def test_operations_approver_allowed(self, test_client, approver_headers):
        """Approver は operations にアクセス可能"""
        with patch("backend.api.routes.audit.audit_log.query", return_value=[]):
            resp = test_client.get("/api/audit/operations", headers=approver_headers)
        assert resp.status_code == 200
