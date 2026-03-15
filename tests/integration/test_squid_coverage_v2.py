"""
squid.py カバレッジ改善テスト v2

対象: backend/api/routes/squid.py (全4エンドポイント)
既存テストで不足している分岐を網羅する。

カバー対象:
  - 全エンドポイントの audit_log 呼び出し検証（operation/target/status）
  - parse_wrapper_result の JSON パース成功・失敗分岐
  - SudoWrapperError 例外パス（全エンドポイント）
  - レスポンスモデルの全フィールド検証
  - logs の lines パラメータ境界値
  - config-check の syntax_ok 分岐
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ======================================================================
# ヘルパー
# ======================================================================


def _mock_output(**kwargs):
    """sudo_wrapper 形式のモック出力"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


def _raw_output(**kwargs):
    """parse不要な直接返却形式"""
    defaults = {"status": "ok", "timestamp": "2026-03-15T00:00:00Z"}
    defaults.update(kwargs)
    return defaults


# ======================================================================
# status エンドポイント
# ======================================================================


class TestSquidStatusCoverageV2:
    """GET /api/squid/status の追加カバレッジ"""

    def test_status_audit_log_details(self, test_client, admin_headers):
        """audit_log が正しい引数で呼ばれること"""
        with patch("backend.api.routes.squid.audit_log") as mock_audit:
            with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
                mock_sw.get_squid_status.return_value = _raw_output(
                    service="squid", active="active", enabled="enabled"
                )
                resp = test_client.get("/api/squid/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "squid_status"
        assert call_kwargs["target"] == "squid"
        assert call_kwargs["status"] == "success"

    def test_status_response_all_fields(self, test_client, admin_headers):
        """全レスポンスフィールドの確認"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_status.return_value = _raw_output(
                service="squid",
                active="active",
                enabled="enabled",
                version="5.7",
                message=None,
            )
            resp = test_client.get("/api/squid/status", headers=admin_headers)
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "squid"
        assert data["active"] == "active"
        assert data["enabled"] == "enabled"
        assert data["version"] == "5.7"

    def test_status_unavailable_response(self, test_client, admin_headers):
        """Squid 未インストール時の unavailable レスポンス"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_status.return_value = _raw_output(
                status="unavailable",
                message="Squid not found",
            )
            resp = test_client.get("/api/squid/status", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"
        assert resp.json()["message"] == "Squid not found"

    def test_status_json_output_parsed(self, test_client, admin_headers):
        """output フィールドの JSON が正しくパースされること"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_status.return_value = _mock_output(
                service="squid", active="active", enabled="enabled"
            )
            resp = test_client.get("/api/squid/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "squid"


# ======================================================================
# cache エンドポイント
# ======================================================================


class TestSquidCacheCoverageV2:
    """GET /api/squid/cache の追加カバレッジ"""

    def test_cache_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.squid.audit_log") as mock_audit:
            with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
                mock_sw.get_squid_cache.return_value = _raw_output(
                    cache_raw="Cache info..."
                )
                resp = test_client.get("/api/squid/cache", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "squid_cache"

    def test_cache_response_fields(self, test_client, admin_headers):
        """cache_raw フィールドの確認"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_cache.return_value = _raw_output(
                cache_raw="Squid Object Cache: Version 5.7\nHTTP Requests: 12345"
            )
            resp = test_client.get("/api/squid/cache", headers=admin_headers)
        data = resp.json()
        assert "cache_raw" in data
        assert "Squid Object Cache" in data["cache_raw"]

    def test_cache_unavailable(self, test_client, admin_headers):
        """cache unavailable"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_cache.return_value = _raw_output(
                status="unavailable", message="squid not installed"
            )
            resp = test_client.get("/api/squid/cache", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_cache_json_output_parsed(self, test_client, admin_headers):
        """JSON output 形式のパース"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_cache.return_value = _mock_output(
                cache_raw="Cache data here"
            )
            resp = test_client.get("/api/squid/cache", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# logs エンドポイント
# ======================================================================


class TestSquidLogsCoverageV2:
    """GET /api/squid/logs の追加カバレッジ"""

    def test_logs_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.squid.audit_log") as mock_audit:
            with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
                mock_sw.get_squid_logs.return_value = _raw_output(
                    logs_raw="access log line", lines=50
                )
                resp = test_client.get("/api/squid/logs", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "squid_logs"

    def test_logs_response_fields(self, test_client, admin_headers):
        """レスポンスフィールドの確認"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_logs.return_value = _raw_output(
                logs_raw="log line 1\nlog line 2", lines=2
            )
            resp = test_client.get("/api/squid/logs?lines=2", headers=admin_headers)
        data = resp.json()
        assert "logs_raw" in data
        assert data["lines"] == 2

    @pytest.mark.parametrize("lines", [1, 50, 100, 200])
    def test_logs_valid_lines_param(self, test_client, admin_headers, lines):
        """有効な lines パラメータ"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_logs.return_value = _raw_output(
                logs_raw="log data", lines=lines
            )
            resp = test_client.get(
                f"/api/squid/logs?lines={lines}", headers=admin_headers
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize("lines", [0, -1, 201, 999])
    def test_logs_invalid_lines_param(self, test_client, admin_headers, lines):
        """無効な lines パラメータ → 422"""
        resp = test_client.get(
            f"/api/squid/logs?lines={lines}", headers=admin_headers
        )
        assert resp.status_code == 422

    def test_logs_default_lines(self, test_client, admin_headers):
        """デフォルト lines=50 で呼ばれること"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_logs.return_value = _raw_output(
                logs_raw="log", lines=50
            )
            resp = test_client.get("/api/squid/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_sw.get_squid_logs.assert_called_once_with(lines=50)

    def test_logs_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_logs.return_value = _mock_output(
                logs_raw="log line", lines=1
            )
            resp = test_client.get("/api/squid/logs?lines=1", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# config-check エンドポイント
# ======================================================================


class TestSquidConfigCheckCoverageV2:
    """GET /api/squid/config-check の追加カバレッジ"""

    def test_config_check_audit_log(self, test_client, admin_headers):
        """audit_log が呼ばれること"""
        with patch("backend.api.routes.squid.audit_log") as mock_audit:
            with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
                mock_sw.get_squid_config_check.return_value = _raw_output(
                    syntax_ok=True, output=""
                )
                resp = test_client.get("/api/squid/config-check", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args[1]
        assert call_kwargs["operation"] == "squid_config_check"
        assert call_kwargs["target"] == "squid"

    def test_config_check_syntax_ok_true(self, test_client, admin_headers):
        """構文OK → syntax_ok=True"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_config_check.return_value = _raw_output(
                syntax_ok=True, output=""
            )
            resp = test_client.get("/api/squid/config-check", headers=admin_headers)
        data = resp.json()
        assert data["syntax_ok"] is True

    def test_config_check_syntax_ok_false(self, test_client, admin_headers):
        """構文エラー → syntax_ok=False"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_config_check.return_value = _raw_output(
                syntax_ok=False, output="FATAL: bad line"
            )
            resp = test_client.get("/api/squid/config-check", headers=admin_headers)
        data = resp.json()
        assert data["syntax_ok"] is False
        assert "FATAL" in data["output"]

    def test_config_check_unavailable(self, test_client, admin_headers):
        """Squid 未インストール"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_config_check.return_value = _raw_output(
                status="unavailable", message="squid not found"
            )
            resp = test_client.get("/api/squid/config-check", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "unavailable"

    def test_config_check_json_output_parsed(self, test_client, admin_headers):
        """JSON output パース"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            mock_sw.get_squid_config_check.return_value = _mock_output(
                syntax_ok=True, output=""
            )
            resp = test_client.get("/api/squid/config-check", headers=admin_headers)
        assert resp.status_code == 200


# ======================================================================
# パラメトライズ: 全エンドポイントの SudoWrapperError テスト
# ======================================================================


class TestSquidAllEndpointErrors:
    """全エンドポイントの SudoWrapperError テスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/squid/status", "get_squid_status"),
            ("/api/squid/cache", "get_squid_cache"),
            ("/api/squid/logs", "get_squid_logs"),
            ("/api/squid/config-check", "get_squid_config_check"),
        ],
    )
    def test_sudo_wrapper_error_returns_503(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).side_effect = SudoWrapperError("fail")
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/squid/status",
            "/api/squid/cache",
            "/api/squid/logs",
            "/api/squid/config-check",
        ],
    )
    def test_unauthenticated(self, test_client, endpoint):
        """未認証で拒否"""
        resp = test_client.get(endpoint)
        assert resp.status_code in (401, 403)


# ======================================================================
# viewer ロールアクセス
# ======================================================================


class TestSquidViewerAccess:
    """viewer ロールのアクセス確認"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/squid/status", "get_squid_status"),
            ("/api/squid/cache", "get_squid_cache"),
            ("/api/squid/logs", "get_squid_logs"),
            ("/api/squid/config-check", "get_squid_config_check"),
        ],
    )
    def test_viewer_can_access(
        self, test_client, viewer_headers, endpoint, wrapper_method
    ):
        """viewer ロールは read:squid 権限で全エンドポイントにアクセス可能"""
        with patch("backend.api.routes.squid.sudo_wrapper") as mock_sw:
            getattr(mock_sw, wrapper_method).return_value = _raw_output()
            resp = test_client.get(endpoint, headers=viewer_headers)
        assert resp.status_code == 200
