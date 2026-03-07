"""
セキュリティダッシュボード API 統合テスト

対象エンドポイント:
  GET /api/security/failed-logins   - 過去24時間の失敗ログイン時間別集計
  GET /api/security/open-ports      - 開放ポート一覧 (psutil)
  GET /api/security/sudo-history    - sudo 操作履歴 (audit_log.jsonl)
  GET /api/security/score           - セキュリティスコア (0-100)
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest


# ==============================================================================
# サンプルデータ
# ==============================================================================

def _make_audit_entry(operation: str, user_id: str = "admin", status: str = "success",
                      target: str = "system", details: dict = None,
                      hours_ago: float = 0) -> dict:
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


SAMPLE_FAILED_LOGIN_ENTRIES = [
    _make_audit_entry("login_failed", user_id="unknown", status="failure",
                      target="192.168.1.10", details={"ip": "192.168.1.10"}, hours_ago=1),
    _make_audit_entry("login_failed", user_id="unknown", status="failure",
                      target="192.168.1.20", details={"ip": "192.168.1.20"}, hours_ago=2),
    _make_audit_entry("login_failed", user_id="unknown", status="failure",
                      target="192.168.1.10", details={"ip": "192.168.1.10"}, hours_ago=3),
]

SAMPLE_SUDO_ENTRIES = [
    _make_audit_entry("service_restart", user_id="operator@example.com", status="success",
                      target="nginx", hours_ago=1),
    _make_audit_entry("service_stop", user_id="operator@example.com", status="success",
                      target="apache2", hours_ago=12),
    _make_audit_entry("security_open_ports_read", user_id="admin@example.com",
                      status="success", target="open_ports", hours_ago=0.5),
]


# ==============================================================================
# psutil モック用ヘルパー
# ==============================================================================

def _make_mock_connection(port: int, pid: int = 1234) -> MagicMock:
    conn = MagicMock()
    conn.status = "LISTEN"
    conn.laddr = MagicMock()
    conn.laddr.port = port
    conn.pid = pid
    conn.type = MagicMock()
    conn.type.name = "SOCK_STREAM"
    return conn


# ==============================================================================
# テストクラス
# ==============================================================================


class TestFailedLoginsEndpoint:
    """GET /api/security/failed-logins"""

    def test_returns_200_with_valid_auth(self, test_client, auth_headers):
        """認証済みリクエストで 200 を返すこと"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        assert response.status_code == 200

    def test_response_schema(self, test_client, auth_headers):
        """レスポンスに hourly / total / unique_ips が含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert "hourly" in data
        assert "total" in data
        assert "unique_ips" in data

    def test_hourly_has_24_slots(self, test_client, auth_headers):
        """hourly に 24 スロットが含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert len(data["hourly"]) == 24

    def test_empty_when_no_audit_file(self, test_client, auth_headers):
        """audit_log.jsonl がない場合は total=0 の空データを返すこと"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert data["total"] == 0
        assert data["unique_ips"] == 0

    def test_counts_login_failed_events(self, test_client, auth_headers):
        """login_failed イベントを正しく集計すること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=SAMPLE_FAILED_LOGIN_ENTRIES):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert data["total"] == 3

    def test_counts_unique_ips(self, test_client, auth_headers):
        """ユニーク IP 数を正しくカウントすること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=SAMPLE_FAILED_LOGIN_ENTRIES):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert data["unique_ips"] == 2  # 192.168.1.10 と 192.168.1.20

    def test_ignores_non_login_failed_events(self, test_client, auth_headers):
        """login_failed 以外のイベントは集計しないこと"""
        entries = [_make_audit_entry("service_restart"), _make_audit_entry("login_success")]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        assert data["total"] == 0

    def test_401_without_auth(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/security/failed-logins")
        assert response.status_code == 403

    def test_hourly_item_has_hour_and_count(self, test_client, auth_headers):
        """hourly の各アイテムに hour と count が含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/failed-logins", headers=auth_headers)
        data = response.json()
        item = data["hourly"][0]
        assert "hour" in item
        assert "count" in item
        assert isinstance(item["count"], int)


class TestOpenPortsEndpoint:
    """GET /api/security/open-ports"""

    def test_returns_200_with_valid_auth(self, test_client, auth_headers):
        """認証済みリクエストで 200 を返すこと"""
        with patch("psutil.net_connections", return_value=[]):
            response = test_client.get("/api/security/open-ports", headers=auth_headers)
        assert response.status_code == 200

    def test_response_has_ports_list(self, test_client, auth_headers):
        """レスポンスに ports リストが含まれること"""
        with patch("psutil.net_connections", return_value=[]):
            response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        assert "ports" in data
        assert isinstance(data["ports"], list)

    def test_port_entry_schema(self, test_client, auth_headers):
        """ポートエントリに必須フィールドが含まれること"""
        mock_conn = _make_mock_connection(port=22, pid=1234)
        with patch("psutil.net_connections", return_value=[mock_conn]):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "sshd"
                response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        if data["ports"]:
            p = data["ports"][0]
            assert "port" in p
            assert "proto" in p
            assert "state" in p
            assert "dangerous" in p

    def test_known_dangerous_port_flagged(self, test_client, auth_headers):
        """危険ポート (23=telnet) は dangerous=True でフラグが立つこと"""
        mock_conn = _make_mock_connection(port=23, pid=999)
        with patch("psutil.net_connections", return_value=[mock_conn]):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "telnetd"
                response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        dangerous_ports = [p for p in data["ports"] if p["port"] == 23]
        if dangerous_ports:
            assert dangerous_ports[0]["dangerous"] is True

    def test_safe_port_not_flagged(self, test_client, auth_headers):
        """安全なポート (8080) は dangerous=False であること"""
        mock_conn = _make_mock_connection(port=8080, pid=1234)
        with patch("psutil.net_connections", return_value=[mock_conn]):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "uvicorn"
                response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        port_8080 = [p for p in data["ports"] if p["port"] == 8080]
        if port_8080:
            assert port_8080[0]["dangerous"] is False

    def test_401_without_auth(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/security/open-ports")
        assert response.status_code == 403

    def test_empty_when_no_connections(self, test_client, auth_headers):
        """リスニングポートがない場合は空リストを返すこと"""
        with patch("psutil.net_connections", return_value=[]):
            response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        assert data["ports"] == []

    def test_multiple_known_dangerous_ports(self, test_client, auth_headers):
        """複数の危険ポート (21=ftp, 23=telnet) が全て dangerous=True になること"""
        conns = [_make_mock_connection(port=21, pid=100), _make_mock_connection(port=23, pid=200)]
        with patch("psutil.net_connections", return_value=conns):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "daemon"
                response = test_client.get("/api/security/open-ports", headers=auth_headers)
        data = response.json()
        for p in data["ports"]:
            if p["port"] in (21, 23):
                assert p["dangerous"] is True


class TestSudoHistoryEndpoint:
    """GET /api/security/sudo-history"""

    def test_returns_200_with_valid_auth(self, test_client, auth_headers):
        """認証済みリクエストで 200 を返すこと"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        assert response.status_code == 200

    def test_response_has_history_list(self, test_client, auth_headers):
        """レスポンスに history リストが含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_empty_when_no_audit_file(self, test_client, auth_headers):
        """audit_log.jsonl がない場合は空リストを返すこと"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        assert data["history"] == []

    def test_history_item_schema(self, test_client, auth_headers):
        """履歴アイテムに timestamp / user / operation / result が含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=SAMPLE_SUDO_ENTRIES):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        if data["history"]:
            item = data["history"][0]
            assert "timestamp" in item
            assert "user" in item
            assert "operation" in item
            assert "result" in item

    def test_max_20_entries(self, test_client, auth_headers):
        """最大20件のみ返すこと"""
        entries = [_make_audit_entry("service_restart", hours_ago=i) for i in range(30)]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=entries):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        assert len(data["history"]) <= 20

    def test_filters_old_entries(self, test_client, auth_headers):
        """7日以上前のエントリは含まれないこと"""
        old_entry = _make_audit_entry("service_restart", hours_ago=24 * 8)  # 8日前
        recent_entry = _make_audit_entry("service_restart", hours_ago=1)
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[old_entry, recent_entry]):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        # 古いエントリは除外され、直近のみ残る
        assert len(data["history"]) == 1

    def test_401_without_auth(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/security/sudo-history")
        assert response.status_code == 403

    def test_result_field_reflects_status(self, test_client, auth_headers):
        """result フィールドがエントリの status を反映すること"""
        entry = _make_audit_entry("service_restart", status="success", hours_ago=0.1)
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[entry]):
            response = test_client.get("/api/security/sudo-history", headers=auth_headers)
        data = response.json()
        if data["history"]:
            assert data["history"][0]["result"] == "success"


class TestSecurityScoreEndpoint:
    """GET /api/security/score"""

    def test_returns_200_with_valid_auth(self, test_client, auth_headers):
        """認証済みリクエストで 200 を返すこと"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        assert response.status_code == 200

    def test_response_schema(self, test_client, auth_headers):
        """レスポンスに score と details が含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        data = response.json()
        assert "score" in data
        assert "details" in data

    def test_score_is_integer(self, test_client, auth_headers):
        """score が整数であること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        data = response.json()
        assert isinstance(data["score"], int)

    def test_score_range_0_to_100(self, test_client, auth_headers):
        """スコアが 0-100 の範囲内であること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        data = response.json()
        assert 0 <= data["score"] <= 100

    def test_details_has_required_fields(self, test_client, auth_headers):
        """details に failed_login_risk / open_ports_risk / recent_sudo_ops が含まれること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        data = response.json()
        det = data["details"]
        assert "failed_login_risk" in det
        assert "open_ports_risk" in det
        assert "recent_sudo_ops" in det

    def test_perfect_score_with_no_threats(self, test_client, auth_headers):
        """脅威がない場合は高いスコアになること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        data = response.json()
        assert data["score"] >= 80

    def test_score_decreases_with_failed_logins(self, test_client, auth_headers):
        """多数の失敗ログインがある場合はスコアが低くなること"""
        # 20件の失敗ログイン (失敗ログインリスクを下げる)
        many_failures = [
            _make_audit_entry("login_failed", status="failure",
                              details={"ip": f"10.0.0.{i}"}, hours_ago=i * 0.5)
            for i in range(20)
        ]
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=many_failures):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert 0 <= data["score"] <= 100

    def test_score_decreases_with_dangerous_ports(self, test_client, auth_headers):
        """危険ポートがある場合はスコアが下がること"""
        safe_conns = []
        dangerous_conns = [_make_mock_connection(port=23, pid=100)]

        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=safe_conns):
                with patch("psutil.Process"):
                    r_safe = test_client.get("/api/security/score", headers=auth_headers)

        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=dangerous_conns):
                with patch("psutil.Process") as mp:
                    mp.return_value.name.return_value = "telnetd"
                    r_danger = test_client.get("/api/security/score", headers=auth_headers)

        assert r_safe.json()["score"] >= r_danger.json()["score"]

    def test_detail_risk_fields_range_0_to_100(self, test_client, auth_headers):
        """details の各リスク値が 0-100 の範囲内であること"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=auth_headers)
        det = response.json()["details"]
        assert 0 <= det["failed_login_risk"] <= 100
        assert 0 <= det["open_ports_risk"] <= 100

    def test_401_without_auth(self, test_client):
        """認証なしで 403 を返すこと"""
        response = test_client.get("/api/security/score")
        assert response.status_code == 403

    def test_viewer_can_access_score(self, test_client, viewer_headers):
        """Viewer ロールでもスコアを取得できること (read:security 権限あり)"""
        with patch("backend.api.routes.security._read_audit_jsonl", return_value=[]):
            with patch("psutil.net_connections", return_value=[]):
                response = test_client.get("/api/security/score", headers=viewer_headers)
        assert response.status_code == 200
        assert 0 <= response.json()["score"] <= 100


class TestAuditLogHelpers:
    """ヘルパー関数の単体テスト"""

    def test_read_audit_jsonl_returns_empty_when_file_missing(self, tmp_path):
        """ファイルが存在しない場合は空リストを返すこと (例外を外に漏らさない)"""
        from backend.api.routes.security import _read_audit_jsonl
        non_existent = tmp_path / "nonexistent.jsonl"
        result = _read_audit_jsonl(non_existent)
        assert result == []

    def test_read_audit_jsonl_parses_valid_entries(self, tmp_path):
        """有効な JSONL エントリを正しくパースすること"""
        from backend.api.routes.security import _read_audit_jsonl
        jsonl_file = tmp_path / "audit.jsonl"
        entries = [
            {"timestamp": "2024-01-01T12:00:00", "operation": "login_failed", "user_id": "u1"},
            {"timestamp": "2024-01-01T13:00:00", "operation": "service_restart", "user_id": "u2"},
        ]
        _write_jsonl(jsonl_file, entries)
        result = _read_audit_jsonl(jsonl_file)
        assert len(result) == 2
        assert result[0]["operation"] == "login_failed"

    def test_read_audit_jsonl_skips_invalid_json(self, tmp_path):
        """不正な JSON 行はスキップしてパース継続すること"""
        from backend.api.routes.security import _read_audit_jsonl
        jsonl_file = tmp_path / "audit.jsonl"
        jsonl_file.write_text(
            '{"timestamp":"2024-01-01T12:00:00","operation":"login_failed"}\n'
            'INVALID JSON LINE\n'
            '{"timestamp":"2024-01-01T13:00:00","operation":"service_restart"}\n',
            encoding="utf-8",
        )
        result = _read_audit_jsonl(jsonl_file)
        assert len(result) == 2

    def test_collect_failed_logins_only_last_24h(self, tmp_path):
        """25時間以上前の login_failed は集計に含まれないこと"""
        from backend.api.routes.security import _collect_failed_logins_hourly
        entries = [
            _make_audit_entry("login_failed", hours_ago=1),   # 対象
            _make_audit_entry("login_failed", hours_ago=25),  # 対象外
        ]
        result = _collect_failed_logins_hourly(entries)
        assert result.total == 1
