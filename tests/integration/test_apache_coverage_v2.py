"""
apache.py カバレッジ改善テスト v2

対象: backend/api/routes/apache.py
目標: 90%以上カバレッジ
既存テスト(test_apache_api/advanced)で未カバーの分岐を網羅

カバー対象:
  - GET /api/apache/config       - 正常系・SudoWrapperError (lines 237-258)
  - GET /api/apache/logs         - 正常系・SudoWrapperError・lines パラメータ (lines 261-290)
  - GET /api/apache/vhosts-detail - parse_wrapper_result 経由の正常系 (lines 298-319)
  - GET /api/apache/ssl-certs    - parse_wrapper_result 経由の正常系 (lines 327-348)
  - parse_wrapper_result 統合テスト
  - audit_log.record 呼び出し確認
  - 各エンドポイントの未認証アクセス拒否
"""

import json
from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# テストデータ
# ===================================================================

def _make_wrapper_result(data: dict) -> dict:
    """sudo_wrapper が返す形式のデータを生成"""
    return {"status": "success", "output": json.dumps(data)}


APACHE_STATUS_DATA = {
    "status": "success",
    "service": "apache2",
    "active": "active",
    "enabled": "enabled",
    "version": "Apache/2.4.57",
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_VHOSTS_DATA = {
    "status": "success",
    "vhosts_raw": "*:80 localhost",
    "vhosts": [{"port": "80", "server_name": "localhost"}],
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_MODULES_DATA = {
    "status": "success",
    "modules_raw": "core_module (static)",
    "modules": [{"name": "core_module", "type": "static"}],
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_CONFIG_CHECK_DATA = {
    "status": "success",
    "syntax_ok": True,
    "output": "Syntax OK",
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_CONFIG_DATA = {
    "status": "success",
    "config": "ServerRoot /etc/apache2\nTimeout 300",
    "config_file": "/etc/apache2/apache2.conf",
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_LOGS_DATA = {
    "status": "success",
    "logs": "[error] Something went wrong\n[warn] Deprecated config",
    "lines": 50,
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_VHOSTS_DETAIL_DATA = {
    "status": "success",
    "vhosts_raw": "*:80 localhost (/etc/apache2/sites-enabled/000-default.conf)",
    "vhosts": [{"port": "80", "server_name": "localhost", "doc_root": "/var/www/html"}],
    "timestamp": "2026-03-15T00:00:00Z",
}

APACHE_SSL_CERTS_DATA = {
    "status": "success",
    "certs": [{"path": "/etc/ssl/certs/ca.crt", "expires": "2027-03-15"}],
    "timestamp": "2026-03-15T00:00:00Z",
}


# ===================================================================
# GET /api/apache/status - 追加テスト
# ===================================================================


class TestApacheStatusV2:
    """status エンドポイントの追加カバレッジ"""

    def test_status_parse_wrapper_result_json(self, test_client, admin_headers):
        """parse_wrapper_result による JSON パース統合"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_status",
                    return_value=_make_wrapper_result(APACHE_STATUS_DATA)):
            resp = test_client.get("/api/apache/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["service"] == "apache2"

    def test_status_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_status",
                    return_value=_make_wrapper_result(APACHE_STATUS_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_status_wrapper_error_detail_message(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_status",
                    side_effect=SudoWrapperError("apache2 not installed")):
            resp = test_client.get("/api/apache/status", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# GET /api/apache/vhosts - 追加テスト
# ===================================================================


class TestApacheVhostsV2:
    """vhosts エンドポイントの追加カバレッジ"""

    def test_vhosts_parse_wrapper_result_json(self, test_client, admin_headers):
        """JSON パース統合"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts",
                    return_value=_make_wrapper_result(APACHE_VHOSTS_DATA)):
            resp = test_client.get("/api/apache/vhosts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_vhosts_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts",
                    return_value=_make_wrapper_result(APACHE_VHOSTS_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/vhosts", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_vhosts_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts",
                    side_effect=SudoWrapperError("command failed")):
            resp = test_client.get("/api/apache/vhosts", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# GET /api/apache/modules - 追加テスト
# ===================================================================


class TestApacheModulesV2:
    """modules エンドポイントの追加カバレッジ"""

    def test_modules_parse_wrapper_result_json(self, test_client, admin_headers):
        """JSON パース統合"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_modules",
                    return_value=_make_wrapper_result(APACHE_MODULES_DATA)):
            resp = test_client.get("/api/apache/modules", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_modules_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_modules",
                    return_value=_make_wrapper_result(APACHE_MODULES_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/modules", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_modules_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_modules",
                    side_effect=SudoWrapperError("apache2ctl not found")):
            resp = test_client.get("/api/apache/modules", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# GET /api/apache/config-check - 追加テスト
# ===================================================================


class TestApacheConfigCheckV2:
    """config-check エンドポイントの追加カバレッジ"""

    def test_config_check_parse_wrapper_result_json(self, test_client, admin_headers):
        """JSON パース統合"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config_check",
                    return_value=_make_wrapper_result(APACHE_CONFIG_CHECK_DATA)):
            resp = test_client.get("/api/apache/config-check", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["syntax_ok"] is True

    def test_config_check_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config_check",
                    return_value=_make_wrapper_result(APACHE_CONFIG_CHECK_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/config-check", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_config_check_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config_check",
                    side_effect=SudoWrapperError("config check failed")):
            resp = test_client.get("/api/apache/config-check", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# GET /api/apache/config - 正常系 + 異常系
# ===================================================================


class TestApacheConfig:
    """config エンドポイントのテスト"""

    def test_config_success(self, test_client, admin_headers):
        """正常系: Apache 設定ファイル内容を取得"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config",
                    return_value=_make_wrapper_result(APACHE_CONFIG_DATA)):
            resp = test_client.get("/api/apache/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "config" in data
        assert data["config_file"] == "/etc/apache2/apache2.conf"

    def test_config_wrapper_error(self, test_client, admin_headers):
        """異常系: SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config",
                    side_effect=SudoWrapperError("config read failed")):
            resp = test_client.get("/api/apache/config", headers=admin_headers)
        assert resp.status_code == 503

    def test_config_unauthorized(self, test_client):
        """未認証: 401/403"""
        resp = test_client.get("/api/apache/config")
        assert resp.status_code in (401, 403)

    def test_config_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config",
                    return_value=_make_wrapper_result(APACHE_CONFIG_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/config", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_config_viewer_allowed(self, test_client, viewer_headers):
        """Viewer ロールは read:servers で取得可能"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config",
                    return_value=_make_wrapper_result(APACHE_CONFIG_DATA)):
            resp = test_client.get("/api/apache/config", headers=viewer_headers)
        assert resp.status_code == 200

    def test_config_parse_non_json_output(self, test_client, admin_headers):
        """output が JSON でない場合は result をそのまま返す"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_config",
                    return_value={"status": "success", "output": "not json", "timestamp": "2026-03-15T00:00:00Z"}):
            resp = test_client.get("/api/apache/config", headers=admin_headers)
        assert resp.status_code == 200


# ===================================================================
# GET /api/apache/logs - 正常系 + 異常系
# ===================================================================


class TestApacheLogs:
    """logs エンドポイントのテスト"""

    def test_logs_success_default_lines(self, test_client, admin_headers):
        """正常系: デフォルト50行"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)):
            resp = test_client.get("/api/apache/logs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "logs" in data

    def test_logs_custom_lines(self, test_client, admin_headers):
        """正常系: lines パラメータ指定"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)) as mock_fn:
            resp = test_client.get("/api/apache/logs?lines=100", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=100)

    def test_logs_lines_1(self, test_client, admin_headers):
        """正常系: lines=1"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)):
            resp = test_client.get("/api/apache/logs?lines=1", headers=admin_headers)
        assert resp.status_code == 200

    def test_logs_lines_200(self, test_client, admin_headers):
        """正常系: lines=200 (最大)"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)):
            resp = test_client.get("/api/apache/logs?lines=200", headers=admin_headers)
        assert resp.status_code == 200

    def test_logs_lines_over_200_rejected(self, test_client, admin_headers):
        """異常系: lines=201 → 422"""
        resp = test_client.get("/api/apache/logs?lines=201", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_lines_0_rejected(self, test_client, admin_headers):
        """異常系: lines=0 → 422"""
        resp = test_client.get("/api/apache/logs?lines=0", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_wrapper_error(self, test_client, admin_headers):
        """異常系: SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    side_effect=SudoWrapperError("log read failed")):
            resp = test_client.get("/api/apache/logs", headers=admin_headers)
        assert resp.status_code == 503

    def test_logs_unauthorized(self, test_client):
        """未認証: 401/403"""
        resp = test_client.get("/api/apache/logs")
        assert resp.status_code in (401, 403)

    def test_logs_audit_log_recorded(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_logs_audit_log_contains_lines(self, test_client, admin_headers):
        """audit_log に lines パラメータが記録される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/logs?lines=75", headers=admin_headers)
        assert resp.status_code == 200
        call_kwargs = mock_audit.record.call_args
        details = call_kwargs.kwargs.get("details", {})
        assert details.get("lines") == 75

    def test_logs_viewer_allowed(self, test_client, viewer_headers):
        """Viewer は read:servers 権限で取得可能"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_logs",
                    return_value=_make_wrapper_result(APACHE_LOGS_DATA)):
            resp = test_client.get("/api/apache/logs", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# GET /api/apache/vhosts-detail - 追加テスト
# ===================================================================


class TestApacheVhostsDetailV2:
    """vhosts-detail エンドポイントの追加カバレッジ"""

    def test_vhosts_detail_parse_json(self, test_client, admin_headers):
        """parse_wrapper_result による JSON パース"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts_detail",
                    return_value=_make_wrapper_result(APACHE_VHOSTS_DETAIL_DATA)):
            resp = test_client.get("/api/apache/vhosts-detail", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_vhosts_detail_audit_log(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts_detail",
                    return_value=_make_wrapper_result(APACHE_VHOSTS_DETAIL_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/vhosts-detail", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_vhosts_detail_wrapper_error_message(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts_detail",
                    side_effect=SudoWrapperError("vhosts detail failed")):
            resp = test_client.get("/api/apache/vhosts-detail", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# GET /api/apache/ssl-certs - 追加テスト
# ===================================================================


class TestApacheSslCertsV2:
    """ssl-certs エンドポイントの追加カバレッジ"""

    def test_ssl_certs_parse_json(self, test_client, admin_headers):
        """parse_wrapper_result による JSON パース"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_ssl_certs",
                    return_value=_make_wrapper_result(APACHE_SSL_CERTS_DATA)):
            resp = test_client.get("/api/apache/ssl-certs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_ssl_certs_audit_log(self, test_client, admin_headers):
        """audit_log.record が呼び出される"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_ssl_certs",
                    return_value=_make_wrapper_result(APACHE_SSL_CERTS_DATA)), \
             patch("backend.api.routes.apache.audit_log") as mock_audit:
            resp = test_client.get("/api/apache/ssl-certs", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_ssl_certs_wrapper_error_message(self, test_client, admin_headers):
        """SudoWrapperError → 503"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_ssl_certs",
                    side_effect=SudoWrapperError("ssl certs unavailable")):
            resp = test_client.get("/api/apache/ssl-certs", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# parse_wrapper_result 統合テスト
# ===================================================================


class TestParseWrapperResultIntegration:
    """parse_wrapper_result の各パス"""

    def test_json_string_parsed(self):
        """output が JSON 文字列の場合パースされる"""
        from backend.api.routes._utils import parse_wrapper_result
        result = parse_wrapper_result({"status": "success", "output": '{"key": "value"}'})
        assert result == {"key": "value"}

    def test_non_json_string_returns_original(self):
        """output が非 JSON 文字列の場合そのまま返す"""
        from backend.api.routes._utils import parse_wrapper_result
        original = {"status": "success", "output": "plain text"}
        result = parse_wrapper_result(original)
        assert result == original

    def test_no_output_key_returns_original(self):
        """output キーがない場合そのまま返す"""
        from backend.api.routes._utils import parse_wrapper_result
        original = {"status": "success", "data": "something"}
        result = parse_wrapper_result(original)
        assert result == original

    def test_output_none_returns_original(self):
        """output が None の場合そのまま返す"""
        from backend.api.routes._utils import parse_wrapper_result
        original = {"status": "success", "output": None}
        result = parse_wrapper_result(original)
        assert result == original

    def test_output_empty_string_returns_original(self):
        """output が空文字列の場合そのまま返す"""
        from backend.api.routes._utils import parse_wrapper_result
        original = {"status": "success", "output": ""}
        result = parse_wrapper_result(original)
        assert result == original

    def test_output_non_string_returns_original(self):
        """output が文字列でない場合そのまま返す"""
        from backend.api.routes._utils import parse_wrapper_result
        original = {"status": "success", "output": 42}
        result = parse_wrapper_result(original)
        assert result == original
